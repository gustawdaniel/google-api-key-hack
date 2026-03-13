import os
import asyncio
import logging
import time
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from mongo_manager import MongoManager

from fastapi.middleware.cors import CORSMiddleware

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DashboardAPI")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB URI and Manager
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
db_manager = MongoManager(uri=MONGO_URI)

# WebSocket Connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

# Event Model
class Event(BaseModel):
    type: str # 'log', 'stat', 'worker_event'
    level: str = "info"
    message: str
    data: Dict[str, Any] = {}

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ... (manager and db_manager)

async def stats_broadcaster():
    """Background task to broadcast stats every 5 seconds."""
    while True:
        try:
            stats = await get_all_stats()
            await manager.broadcast({"type": "init_stats", "data": stats, "timestamp": time.time()})
        except Exception as e:
            logger.error(f"Error in stats broadcaster: {e}")
        await asyncio.sleep(5)

@app.on_event("startup")
async def startup_event():
    await db_manager.connect()
    asyncio.create_task(stats_broadcaster())

@app.on_event("shutdown")
async def shutdown_event():
    await db_manager.close()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/events")
async def post_event(event: Event):
    """Endpoint for workers to push logs/events to the dashboard."""
    event_dict = event.dict()
    event_dict["timestamp"] = time.time()
    await manager.broadcast(event_dict)
    return {"status": "broadcasted"}

class SettingsUpdate(BaseModel):
    fast_mode: bool

@app.get("/settings")
async def get_settings():
    return await db_manager.get_settings()

@app.post("/settings")
async def update_settings(settings: SettingsUpdate):
    updated = await db_manager.update_settings(settings.dict())
    await manager.broadcast({"type": "sys", "level": "warning", "message": f"Global settings updated: FAST_MODE={'ON' if updated.get('fast_mode') else 'OFF'}"})
    return updated

@app.get("/scans/stats")
async def get_scans_stats():
    """Aggregates metrics for the Scans dashboard tab."""
    if db_manager.db is None: return {}
    coll = db_manager.db["scans"]
    
    total = await coll.count_documents({})
    if total == 0:
        return {"total": 0, "apps_with_keys": 0, "apps_without_keys": 0, "vulnerable_apps": 0, "total_keys": 0, "total_working_keys": 0}
        
    apps_with_keys = await coll.count_documents({"results": {"$not": {"$size": 0}}})
    apps_without_keys = total - apps_with_keys
    vulnerable_apps = await coll.count_documents({"results.working_count": {"$gt": 0}})
    
    # Aggregate total keys found across all apps
    pipeline = [
        {"$unwind": "$results"},
        {"$group": {
            "_id": None,
            "total_keys": {"$sum": 1},
            "total_working": {"$sum": "$results.working_count"}
        }}
    ]
    cursor = coll.aggregate(pipeline)
    agg_res = await cursor.to_list(length=1)
    
    total_keys = agg_res[0]["total_keys"] if agg_res else 0
    total_working_keys = agg_res[0]["total_working"] if agg_res else 0
    
    return {
        "total_apps_scanned": total,
        "apps_with_keys": apps_with_keys,
        "apps_without_keys": apps_without_keys,
        "vulnerable_apps": vulnerable_apps,
        "total_keys_extracted": total_keys,
        "total_working_endpoints": total_working_keys,
        "percent_apps_with_keys": round((apps_with_keys / total) * 100, 1),
        "percent_vulnerable_apps": round((vulnerable_apps / total) * 100, 1)
    }

@app.get("/scans/vulnerable")
async def get_vulnerable_scans():
    """Fetches all detailed scan results where at least one key is working."""
    if db_manager.db is None: return []
    coll = db_manager.db["scans"]
    
    cursor = coll.find({"results.working_count": {"$gt": 0}}).sort("at", -1)
    docs = await cursor.to_list(length=1000)
    
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

# Serve Svelte static files
if os.path.exists("dashboard/dist"):
    app.mount("/assets", StaticFiles(directory="dashboard/dist/assets"), name="static")

@app.get("/")
async def serve_index():
    if os.path.exists("dashboard/dist/index.html"):
        return FileResponse("dashboard/dist/index.html")
    return {"message": "Dashboard frontend not built. Run 'npm run build' in dashboard folder."}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial stats on connect
        stats = await get_all_stats()
        await websocket.send_json({"type": "init_stats", "data": stats})
        
        while True:
            # Keep connection alive by responding to explicit pings
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket unexpected error: {e}")
        manager.disconnect(websocket)

_CACHED_IP = "Unknown"
_LAST_IP_CHECK = 0

async def get_public_ip():
    """Fetches the public IP address with multiple fallbacks and realistic headers. Caches result for 60s."""
    global _CACHED_IP, _LAST_IP_CHECK
    
    current_time = time.time()
    if _CACHED_IP != "Unknown" and (current_time - _LAST_IP_CHECK) < 60:
        return _CACHED_IP

    import httpx
    # Primary: ipinfo.io as requested
    try:
        url = "https://ipinfo.io/json"
        headers = {"User-Agent": "curl/8.14.1"}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=5.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if "ip" in data:
                    ip = data["ip"]
                    logger.info(f"Public IP detected via ipinfo.io: {ip}")
                    _CACHED_IP = ip
                    _LAST_IP_CHECK = current_time
                    return ip
    except Exception as e:
        logger.debug(f"Failed to fetch IP from ipinfo.io: {e}")

    # Fallback
    urls = ["https://api.ipify.org", "https://ifconfig.me/ip"]
    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
        for url in urls:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    ip = r.text.strip()
                    if ip and len(ip) <= 15: # Basic IPv4 validation
                        logger.info(f"Public IP detected via {url}: {ip}")
                        _CACHED_IP = ip
                        _LAST_IP_CHECK = current_time
                        return ip
            except Exception as e:
                pass
    
    logger.error("All public IP discovery services failed.")
    return _CACHED_IP # Return last known or "Unknown"

async def get_all_stats():
    """Aggregates stats from MongoDB."""
    stats = {
        "total": 0, "pending": 0, "downloading": 0,
        "completed": 0, "failed": 0, "free_space_gb": 0, "ip": "Unknown"
    }
    try:
        if db_manager.collection is None:
            logger.warning("DB Collection not initialized yet")
            return stats

        coll = db_manager.collection
        stats["total"] = await coll.count_documents({})
        logger.info(f"Dashboard Stats Debug: Found {stats['total']} total apps in DB")
        stats["pending"] = await coll.count_documents({"status": "PENDING"})
        stats["downloading"] = await coll.count_documents({"status": "DOWNLOADING"})
        stats["completed"] = await coll.count_documents({"status": "COMPLETED"})
        stats["failed"] = await coll.count_documents({"status": "FAILED"})
        
        # Disk space
        try:
            du = os.statvfs('/')
            stats["free_space_gb"] = round((du.f_bavail * du.f_frsize) / (1024**3), 2)
        except Exception as e:
            logger.error(f"Disk stats error: {e}")

        # IP Discovery with longer timeout
        try:
            stats["ip"] = await asyncio.wait_for(get_public_ip(), timeout=12.0)
        except Exception as e:
            logger.error(f"IP discovery timeout/error: {e}")

        return stats
    except Exception as e:
        logger.error(f"Critical error in get_all_stats: {e}", exc_info=True)
        return stats

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
