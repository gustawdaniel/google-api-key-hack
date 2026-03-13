#!/usr/bin/env python3
import asyncio
import os
import shutil
from rich.live import Live
from rich.table import Table
from rich.console import Console
from motor.motor_asyncio import AsyncIOMotorClient

console = Console()

async def get_stats():
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri)
    db = client.apk_hack
    coll = db.apps
    
    total = await coll.count_documents({})
    pending = await coll.count_documents({"status": "PENDING"})
    downloading = await coll.count_documents({"status": "DOWNLOADING"})
    completed = await coll.count_documents({"status": "COMPLETED"})
    failed = await coll.count_documents({"status": "FAILED"})
    
    # Storage info
    total_space, used_space, free_space = shutil.disk_usage(".")
    
    return {
        "total": total,
        "pending": pending,
        "downloading": downloading,
        "completed": completed,
        "failed": failed,
        "free_gb": free_space / (1024**3)
    }

def generate_table(stats) -> Table:
    table = Table(title="APK Distributed Scraper Monitor", header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Packages", str(stats["total"]))
    table.add_row("Pending", str(stats["pending"]))
    table.add_row("Downloading", str(stats["downloading"]), style="yellow")
    table.add_row("Completed", str(stats["completed"]), style="bold green")
    table.add_row("Failed", str(stats["failed"]), style="bold red")
    table.add_row("Disk Space Remaining", f"{stats['free_gb']:.2f} GB")
    
    return table

async def main():
    with Live(generate_table(await get_stats()), refresh_per_second=1, console=console) as live:
        while True:
            await asyncio.sleep(10)
            stats = await get_stats()
            live.update(generate_table(stats))

if __name__ == "__main__":
    asyncio.run(main())
