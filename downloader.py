#!/usr/bin/env python3
import asyncio
import hashlib
import os
import time
import logging
from pathlib import Path
from curl_cffi import requests as cffi_requests
from mongo_manager import MongoManager
import httpx # For event notifications
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Downloader")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]

class EventNotifier:
    def __init__(self, endpoint: str = None):
        self.endpoint = endpoint or os.environ.get("DASHBOARD_API", "http://dashboard:8000/events")

    async def notify(self, event_type: str, message: str, level: str = "info", data: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                await client.post(self.endpoint, json={
                    "type": event_type,
                    "level": level,
                    "message": message,
                    "data": data or {}
                }, timeout=1.0)
        except Exception as e:
            logger.debug(f"Could not notify dashboard: {e}")

class Downloader:
    def __init__(self, mongo_manager: MongoManager, apps_dir: str = "apps"):
        self.db = mongo_manager
        self.apps_dir = Path(apps_dir)
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.notifier = EventNotifier()

    def get_target_path(self, pkg_name: str) -> Path:
        """Saves everything flat to apps/pkg_name.apk"""
        return self.apps_dir / f"{pkg_name}.apk"

    async def get_file_hash(self, filepath: Path) -> str:
        """Asynchronously calculate SHA256 hash."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
                await asyncio.sleep(0) # Yield control
        return h.hexdigest()

    def is_valid_package(self, pkg: str) -> bool:
        """Same validation as Crawler to reject junk."""
        if not pkg or len(pkg) < 8: return False
        pkg = pkg.lower()
        if any(x in pkg for x in ['.js', '.css', '.png', '.jpg', '.jpeg', '.svg', '.json', '.txt', 'googletagmanager', 'aptoide.com']):
            return False
        if pkg.startswith(('www.', 'en.', 'rs.', 'th.', 'vn.', 'my.')):
            return False
        return pkg.count('.') >= 2 and pkg[0].isalpha() and ' ' not in pkg

    async def download_task(self, task: dict):
        pkg_name = task["_id"]
        if not self.is_valid_package(pkg_name):
            logger.warning(f"Skipping invalid package name: {pkg_name}")
            await self.db.save_failure(pkg_name, "Invalid package name format")
            return
        
        target_path = self.get_target_path(pkg_name)
        
        # APKPure download pattern
        url = f"https://d.apkpure.com/b/APK/{pkg_name}?version=latest"
        
        headers = {}
        
        if target_path.exists():
            downloaded = target_path.stat().st_size
            headers["Range"] = f"bytes={downloaded}-"
            logger.info(f"Resuming download for {pkg_name} from {downloaded} bytes")

        backoff = 30 # Increased initial backoff for 429
        try:
            while True:
                logger.info(f"Requesting {url} for {pkg_name}")
                
                def perform_request():
                    session = cffi_requests.Session(impersonate="chrome110")
                    # We can't easily stream with async to_thread returning an iterator, 
                    # so we just do the download inside the thread itself to avoid blocking.
                    r = session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True)
                    logger.info(f"Worker {pkg_name} got HTTP {r.status_code}")
                    
                    if r.status_code == 429:
                        return "429", None
                    
                    if r.status_code == 416:
                        return "416", None
                        
                    if r.status_code in [200, 206]:
                        mode = "ab" if r.status_code == 206 else "wb"
                        with open(target_path, mode) as f:
                            for chunk in r.iter_content(chunk_size=16384):
                                if chunk: f.write(chunk)
                        return "OK", None
                        
                    logger.error(f"HTTP {r.status_code} error. Body: {r.content[:500]}")
                    return "ERROR", f"HTTP {r.status_code}"
                
                status, err_msg = await asyncio.to_thread(perform_request)
                
                settings = await self.db.get_settings()
                fast_mode = settings.get("fast_mode", False)
                
                if status == "429":
                    msg = f"Rate limited (429) for {pkg_name}. Backing off {backoff}s..."
                    logger.warning(msg)
                    await self.notifier.notify("worker_event", msg, level="warning", data={"pkg": pkg_name, "backoff": backoff})
                    
                    if not fast_mode:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 1.5, 600)
                    else:
                        logger.warning(f"FAST MODE: Ignoring {backoff}s backoff, sleeping 5s instead.")
                        await asyncio.sleep(5)
                        backoff = min(backoff * 1.2, 60) # Less aggressive scale
                    continue

                if status == "416":
                    logger.info(f"File {pkg_name} already fully downloaded.")
                    break
                elif status == "OK":
                    break
                else:
                    raise Exception(err_msg)

            # Finalize
            if target_path.exists():
                fhash = await self.get_file_hash(target_path)
                stats = {
                    "filepath": str(target_path),
                    "size": target_path.stat().st_size,
                    "hash": fhash
                }
                await self.db.save_success(pkg_name, stats)
                msg = f"Successfully downloaded {pkg_name} ({stats['size']} bytes)"
                logger.info(msg)
                await self.notifier.notify("worker_event", msg, level="success", data={"pkg": pkg_name, "size": stats['size']})

        except Exception as e:
            msg = f"Failed to download {pkg_name}: {e}"
            logger.error(msg)
            await self.db.save_failure(pkg_name, str(e))
            await self.notifier.notify("worker_event", msg, level="error", data={"pkg": pkg_name, "error": str(e)})

    async def run(self):
        await self.db.connect()
        # Clean up tasks stuck from previous crashes
        await self.db.cleanup_stale_tasks()
        
        logger.info("Downloader worker started.")
        
        while True:
            task = await self.db.get_next_task()
            if not task:
                logger.debug("No pending tasks. Waiting 10s...")
                await asyncio.sleep(10)
                continue
            
            await self.download_task(task)
            
            settings = await self.db.get_settings()
            if not settings.get("fast_mode", False):
                # High jitter for stealth mode (20-60s)
                import random
                delay = random.uniform(20, 60)
                logger.info(f"Task finished. Sleeping {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                logger.info("Task finished. FAST MODE: starting next immediately.")

async def main():
    manager = MongoManager()
    worker = Downloader(manager)
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
