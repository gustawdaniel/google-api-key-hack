#!/usr/bin/env python3
import os
import re
import sys
import argparse
import requests
import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
from core import C

def get_pkg_from_href(href):
    # Matches the last part of the URL which is usually the package name
    # e.g. https://apkpure.com/the-weather-channel-radar/com.weather.Weather
    parts = href.strip('/').split('/')
    if parts:
        return parts[-1]
    return None

def download_apk(pkg_name, download_page_url, out_dir):
    scraper = cloudscraper.create_scraper()
    print(f"[*] Processing {C.BOLD}{pkg_name}{C.END}...")
    
    # Check if already exists
    target_file = out_dir / f"{pkg_name}.apk"
    if target_file.exists():
        print(f"  {C.Y}Skipping: Already exists.{C.END}")
        return True

    try:
        # The download_page_url is like https://apkpure.com/app-name/pkg/download
        # We need the direct link. APKPure usually has a 'click here' link if it doesn't start.
        # The direct link is often d.apkpure.com/b/APK/pkg?version=latest
        direct_url = f"https://d.apkpure.com/b/APK/{pkg_name}?version=latest"
        
        print(f"  [+] Downloading from {direct_url[:50]}...")
        r = scraper.get(direct_url, stream=True, timeout=30, allow_redirects=True)
        r.raise_for_status()
        
        # Check if we actually got an APK and not some error page
        content_type = r.headers.get('Content-Type', '')
        if 'application/vnd.android.package-archive' not in content_type and 'application/octet-stream' not in content_type:
             # Try to find filename from headers
             disp = r.headers.get('Content-Disposition', '')
             if '.apk' not in disp.lower() and '.xapk' not in disp.lower():
                print(f"  {C.R}Warning: Response might not be an APK ({content_type}).{C.END}")
        
        with open(target_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"  {C.G}Success! Saved to {target_file.name}{C.END}")
        return True
    except Exception as e:
        print(f"  {C.R}Download failed: {e}{C.END}")
        if target_file.exists(): target_file.unlink()
        return False

def main():
    parser = argparse.ArgumentParser(description="Download APKs from APKPure via Scraping")
    parser.add_argument("-q", "--query", type=str, default="maps", help="Search query")
    parser.add_argument("-l", "--limit", type=int, default=30, help="Limit")
    parser.add_argument("-o", "--output", type=str, default="apps", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(exist_ok=True)

    print(f"{C.H}APK Getter (APKPure Scraper) - Query: {args.query}{C.END}")
    
    scraper = cloudscraper.create_scraper()
    search_url = f"https://apkpure.com/search?q={args.query}"
    
    try:
        r = scraper.get(search_url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Grid results are usually in a.dd
        results = soup.select('a.dd')
        # Also check for the first detailed result if any
        first_res = soup.select_one('.search-res a.first-info')
        
        all_links = []
        if first_res:
            all_links.append(first_res['href'])
        for res in results:
            all_links.append(res['href'])
            
        # Deduplicate
        all_links = list(dict.fromkeys(all_links))
        
        pkgs = []
        for link in all_links:
            # Absolute URL check
            if link.startswith('/'):
                link = "https://apkpure.com" + link
            
            pkg = get_pkg_from_href(link)
            if pkg and pkg not in [p['pkg'] for p in pkgs]:
                pkgs.append({'pkg': pkg, 'link': link})
                
        print(f"Found {len(pkgs)} potential apps.\n")
        
        downloaded = 0
        for item in pkgs:
            if downloaded >= args.limit:
                break
            if download_apk(item['pkg'], item['link'], out_dir):
                downloaded += 1
                
        print(f"\n{C.G}Finished! Downloaded {downloaded} apps.{C.END}")

    except Exception as e:
        print(f"{C.R}Error: {e}{C.END}")

if __name__ == "__main__":
    main()
