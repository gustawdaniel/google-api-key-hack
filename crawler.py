#!/usr/bin/env python3
import asyncio
import re
import logging
import random
from curl_cffi import requests as cffi_requests
from mongo_manager import MongoManager
from bs4 import BeautifulSoup

import os
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Crawler")

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

class Crawler:
    def __init__(self, mongo_manager: MongoManager):
        self.db = mongo_manager
        self.queue = asyncio.Queue(maxsize=1000)
        self.notifier = EventNotifier()

    def is_valid_package(self, pkg: str) -> bool:
        """Validates if a string looks like a Java/Android package name."""
        if not pkg or len(pkg) < 8: return False # Min length is usually like com.a.b
        
        # Exclude common hostnames and static assets
        pkg = pkg.lower()
        if any(x in pkg for x in [
            '.xml', '.gz', '.html', '.js', '.css', '.png', '.jpg', '.jpeg', 
            '.svg', '.json', '.txt', 'sitemap', 'index', 'googletagmanager',
            'analytics', 'google-analytics', 'aptoide.com', 'apkpure.com'
        ]): 
            return False
            
        # Common subdomains that pass as packages but aren't
        if pkg.startswith(('www.', 'en.', 'rs.', 'th.', 'vn.', 'my.', 'dev.', 'test.')):
            return False

        # Package names: com.example.app (at least two dots, no spaces, starts with alpha)
        # Most apps follow the 3-segment convention
        return pkg.count('.') >= 2 and pkg[0].isalpha() and ' ' not in pkg

    async def scrape_apkpure_metadata(self, pkg: str) -> dict:
        """Scrapes deep metadata for a specific package from APKPure."""
        url = f"https://apkpure.com/a/{pkg}"
        try:
            def perform_request():
                session = cffi_requests.Session(impersonate="chrome110")
                return session.get(url, timeout=15)
            r = await asyncio.to_thread(perform_request)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                # Extract meta info
                # APKPure has a 'details-sdk' or similar for info
                metadata = {"pkg": pkg}
                
                # Try to find download count
                down_info = soup.select_one('.details-install')
                if down_info:
                    metadata["downloads"] = down_info.get_text(strip=True)
                
                # Try to find rating
                rating = soup.select_one('.details-rating .average')
                if rating:
                    metadata["rating"] = rating.get_text(strip=True)

                cat = soup.select_one('.details-tag a')
                if cat:
                    metadata["category"] = cat.get_text(strip=True)
                    
                # Publish date
                date_el = soup.select_one('.additional-info .date')
                if date_el:
                    metadata["date"] = date_el.get_text(strip=True)
                    
                # Developer
                dev = soup.select_one('.details-author a')
                if dev:
                    metadata["developer"] = dev.get_text(strip=True)
                
                return metadata
        except Exception as e:
            logger.debug(f"Metadata fail for {pkg}: {e}")
            
        # If block fails, return basic structure
        return {"pkg": pkg, "basic": True}

    async def fetch_apkpure_search(self, query: str):
        """Scrapes app list from APKPure search results."""
        logger.info(f"Searching APKPure for: {query}")
        url = f"https://apkpure.com/search?q={query}"
        try:
            def perform_request():
                session = cffi_requests.Session(impersonate="chrome110")
                return session.get(url, timeout=15)
            r = await asyncio.to_thread(perform_request)
            
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                results = soup.select('a.dd')
                first_res = soup.select_one('.search-res a.first-info')
                
                links = []
                if first_res and first_res.has_attr('href'):
                    links.append(first_res['href'])
                for res in results:
                    if res.has_attr('href'):
                        links.append(res['href'])
                
                # Deduplicate and extract pkg
                links = list(dict.fromkeys(links))
                found = 0
                for link in links:
                    if link.startswith('/'):
                        link = "https://apkpure.com" + link
                    parts = link.strip('/').split('/')
                    if parts:
                        pkg = parts[-1]
                        if self.is_valid_package(pkg):
                            await self.queue.put(pkg)
                            found += 1
                logger.info(f"Query '{query}' yielded {found} valid packages from APKPure search.")
            elif r.status_code == 429:
                logger.warning(f"APKPure 429 Rate Limit on search '{query}'. Backing off.")
                await self.notifier.notify("warning", f"APKPure Rate Limit (429) on search: {query}", level="warning")
            else:
                logger.warning(f"APKPure search for '{query}' returned status code {r.status_code}")
        except Exception as e:
            logger.error(f"Error searching APKPure for {query}: {e}")

    async def fetch_apkpure_category(self, cat_url: str):
        """Scrapes app list from a specific category page (e.g. New Releases)."""
        logger.info(f"Scraping category: {cat_url}")
        try:
            def perform_request():
                session = cffi_requests.Session(impersonate="chrome110")
                return session.get(cat_url, timeout=30)
            r = await asyncio.to_thread(perform_request)
            if r.status_code == 200:
                # App links on category pages usually follow /app-name/pkg.id
                links = re.findall(r'href="/[\w-]+/([\w.]+\.[\w.]+\.[\w.]+)"', r.text)
                for pkg in links:
                    if self.is_valid_package(pkg):
                        await self.queue.put(pkg)
        except Exception as e:
            logger.error(f"Error scraping category {cat_url}: {e}")

    async def fetch_aptoide_trending(self):
        """Scrapes trending apps from Aptoide."""
        # Aptoide uses subdomains for categories sometimes, but trending is usually on the main page
        url = "https://en.aptoide.com/group/trending"
        logger.info(f"Scraping Aptoide trending: {url}")
        try:
            def perform_request():
                session = cffi_requests.Session(impersonate="chrome110")
                return session.get(url, timeout=30)
            
            r = await asyncio.to_thread(perform_request)
            if r.status_code == 200:
                # Aptoide links: https://en.aptoide.com/app/com.package.name
                links = re.findall(r'aptoide\.com/app/([\w.]+\.[\w.]+\.[\w.]+)', r.text)
                for pkg in links:
                    if self.is_valid_package(pkg):
                        await self.queue.put(pkg)
            elif r.status_code == 403:
                logger.warning(f"Aptoide blocked discovery (403).")
                logger.debug(f"Aptoide 403 Body: {r.text[:500]}")

        except Exception as e:
            logger.error(f"Error scraping Aptoide: {e}")

    def is_niche_target(self, meta: dict) -> bool:
        """Analyzes metadata to determine if the app is a good target (niche, probably vulnerable)."""
        if "basic" in meta: return True # If we failed to get metadata, assume it's worth trying
        
        # Parse downloads string like "10M+", "50K+", "10,000+"
        dls_raw = meta.get("downloads", "0").upper().replace(",", "").replace("+", "")
        multiplier = 1
        if "M" in dls_raw: multiplier = 1_000_000
        elif "K" in dls_raw: multiplier = 1_000
        
        try:
             dls_num = float(re.sub(r'[^\d.]', '', dls_raw)) * multiplier
        except:
             dls_num = 0
             
        # Reject extremely popular apps (e.g. over 1M downloads)
        if dls_num > 1_000_000:
            return False
            
        return True

    async def metadata_worker(self):
        """Worker that pulls packages, fetches metadata, and conditionally inserts into DB."""
        while True:
            try:
                pkg = await self.queue.get()
                
                # Check DB first to avoid duplicate metadata fetches
                if await self.db.collection.find_one({"_id": pkg}):
                    self.queue.task_done()
                    continue
                    
                # Brief sleep to avoid hitting 429 purely on metadata gathering
                settings = await self.db.get_settings()
                if not settings.get("fast_mode"):
                    await asyncio.sleep(params := random.uniform(1.0, 3.0))
                
                meta = await self.scrape_apkpure_metadata(pkg)
                
                if self.is_niche_target(meta):
                    doc = {"_id": pkg, "metadata": meta}
                    await self.db.upsert_many([doc])
                    msg = f"Target appended: {pkg} (DLs: {meta.get('downloads', '?')})"
                    logger.info(msg)
                    # We send single notifications for dashboard life, but maybe debounce it if too noisy
                    await self.notifier.notify("log", f"Discovered: {pkg}", data=meta)
                else:
                    logger.debug(f"Ignored popular app: {pkg} ({meta.get('downloads')})")
                
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metadata worker exception: {e}")
                self.queue.task_done()

    async def cleanup_junk_apps(self):
        """Removes existing junk apps from the database."""
        logger.info("Cleaning up junk apps from database...")
        try:
            coll = self.db.collection
            cursor = coll.find({}, {"_id": 1})
            to_delete = []
            async for doc in cursor:
                pkg = doc["_id"]
                if not self.is_valid_package(pkg):
                    to_delete.append(pkg)
            
            if to_delete:
                res = await coll.delete_many({"_id": {"$in": to_delete}})
                logger.info(f"Cleanup complete. Removed {res.deleted_count} junk records.")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    async def run(self):
        await self.db.connect()
        # Clean up history
        await self.cleanup_junk_apps()
        
        asyncio.create_task(self.metadata_worker())
        asyncio.create_task(self.metadata_worker()) # 2 workers for metadata
        
        # Shift focus strictly to niche, local, location-dependent apps to find vulnerable Maps API keys
        keywords = [
            "local transit", "city bus schedule", "regional train", "scooter rental", "bike share",
            "pizza delivery local", "grocery delivery city", "courier service", "moving company",
            "campus map", "university map", "mall map", "hospital directory", "clinic locator",
            "pharmacy locator", "atm finder local", "branch locator bank", "gas station finder",
            "ev charging local", "parking finder city", "tow truck local", "taxi service town",
            "car wash local", "plumber local", "electrician local", "pest control map",
            "hiking trails local", "fishing spots map", "hunting map regional", "park guide city",
            "real estate local agent", "property viewer map", "apartment finder map", 
            "store locator map", "food truck tracker map", "waste collection schedule",
            "local event guide", "city tour guide map", "golf course gps map", "cemetery map"
        ]
        
        while True:
            # Shuffle keywords so every run is different
            random.shuffle(keywords)
            for word in keywords:
                try:
                    pending_count = await self.db.collection.count_documents({"status": "PENDING"})
                    settings = await self.db.get_settings()
                    fast_mode = settings.get("fast_mode")
                    
                    if pending_count > 500 and not fast_mode:
                        logger.info(f"Queue full ({pending_count} pending). Pausing discovery for 60s.")
                        await asyncio.sleep(60)
                        continue
                except Exception as e:
                    logger.error(f"Error checking pending count: {e}")
                
                await self.fetch_apkpure_search(word)
                if not fast_mode:
                    await asyncio.sleep(random.uniform(5, 10)) # Small delay between searches
            
            # We skip Aptoide trending because we ONLY want niche apps, not popular ones
            # await self.fetch_aptoide_trending()
            
            # Shorter cooldown before next massive loop
            settings = await self.db.get_settings()
            if not settings.get("fast_mode"):
                delay = random.uniform(300, 600)
                logger.info(f"Search cycle finished. Cool down {delay/60:.1f}m.")
                await asyncio.sleep(delay)
            else:
                logger.info("Search cycle finished. FAST MODE active, restarting immediately.")

async def main():
    manager = MongoManager()
    crawler = Crawler(manager)
    await crawler.run()

if __name__ == "__main__":
    asyncio.run(main())

