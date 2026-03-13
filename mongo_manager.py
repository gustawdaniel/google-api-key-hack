import os
import logging
import time
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne, ReturnDocument
from pymongo.errors import ConnectionFailure, PyMongoError

class MongoManager:
    def __init__(self, uri: str = None, db_name: str = "apk_hack", collection_name: str = "apps"):
        self.uri = uri or os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name
        self.collection_name = collection_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.collection = None
        self.logger = logging.getLogger("MongoManager")

    async def connect(self):
        """Connects to MongoDB and initializes database and collection."""
        try:
            self.client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=5000)
            # Trigger a connection attempt
            await self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.collection = self.db[self.collection_name]
            self.logger.info(f"Successfully connected to MongoDB at {self.uri}")
            
            # Create indexes for performance
            await self.collection.create_index([("status", 1)])
            await self.collection.create_index([("hash", 1)])
            
            # Initialize settings collection
            self.settings = self.db["settings"]
        except (ConnectionFailure, PyMongoError) as e:
            self.logger.error(f"Could not connect to MongoDB: {e}")
            raise

    async def get_next_task(self) -> Optional[Dict]:
        """Atomically find one PENDING task and mark it as DOWNLOADING."""
        try:
            task = await self.collection.find_one_and_update(
                {"status": "PENDING"},
                {"$set": {"status": "DOWNLOADING", "started_at": time.time()}},
                sort=[("added_at", 1)], # Process oldest first
                return_document=ReturnDocument.AFTER
            )
            return task
        except Exception as e:
            self.logger.error(f"Error in get_next_task: {e}")
            return None

    async def cleanup_stale_tasks(self):
        """Resets tasks stuck in DOWNLOADING for too long."""
        try:
            # If a task is DOWNLOADING for more than 1 hour, reset to PENDING
            stale_time = time.time() - 3600
            result = await self.collection.update_many(
                {"status": "DOWNLOADING", "started_at": {"$lt": stale_time}},
                {"$set": {"status": "PENDING"}, "$unset": {"started_at": ""}}
            )
            if result.modified_count:
                self.logger.info(f"Reset {result.modified_count} stale tasks to PENDING.")
        except Exception as e:
            self.logger.error(f"Error in cleanup_stale_tasks: {e}")

    async def upsert_many(self, items: List[dict]):
        """Bulk adds new packages with optional metadata to the database."""
        if not items:
            return

        operations = []
        for item in items:
            pkg_id = item if isinstance(item, str) else item.get("_id")
            metadata = {} if isinstance(item, str) else item.get("metadata", {})
            
            # If it's just a string, it's a legacy call from crawler
            ops = {
                "$setOnInsert": {"status": "PENDING", "added_at": time.time()}
            }
            if metadata:
                ops["$set"] = {"metadata": metadata}

            operations.append(UpdateOne(
                {"_id": pkg_id},
                ops,
                upsert=True
            ))
        
        try:
            result = await self.collection.bulk_write(operations, ordered=False)
            self.logger.info(f"Bulk write complete: {result.upserted_count} new, {result.modified_count} updated.")
        except Exception as e:
            self.logger.error(f"Error in upsert_many: {e}")

    async def save_success(self, pkg_name: str, stats: Dict):
        """Updates record with file stats and marks status as COMPLETED."""
        try:
            update_data = {
                "status": "COMPLETED",
                "completed_at": time.time(),
                "filepath": stats.get("filepath"),
                "size": stats.get("size"),
                "hash": stats.get("hash"),
                "metadata": stats.get("metadata", {})
            }
            await self.collection.update_one(
                {"_id": pkg_name},
                {"$set": update_data}
            )
        except Exception as e:
            self.logger.error(f"Error in save_success for {pkg_name}: {e}")

    async def save_failure(self, pkg_name: str, error_msg: str):
        """Marks task as FAILED with error details."""
        try:
            await self.collection.update_one(
                {"_id": pkg_name},
                {"$set": {
                    "status": "FAILED",
                    "error": error_msg,
                    "failed_at": time.time()
                }}
            )
        except Exception as e:
            self.logger.error(f"Error in save_failure for {pkg_name}: {e}")

    async def close(self):
        """Closes the MongoDB connection."""
        if self.client:
            self.client.close()

    async def get_settings(self) -> Dict:
        """Retrieves global system settings."""
        try:
            doc = await self.settings.find_one({"_id": "global"})
            if doc: return doc
            # Default settings if none exist
            default_settings = {"_id": "global", "fast_mode": False}
            await self.settings.insert_one(default_settings)
            return default_settings
        except Exception as e:
            self.logger.error(f"Error fetching settings: {e}")
            return {"fast_mode": False}
            
    async def update_settings(self, new_settings: Dict) -> Dict:
        """Updates global system settings."""
        try:
            await self.settings.update_one(
                {"_id": "global"},
                {"$set": new_settings},
                upsert=True
            )
            return await self.get_settings()
        except Exception as e:
            self.logger.error(f"Error updating settings: {e}")
            return {}
