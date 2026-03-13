#!/usr/bin/env python3
import hashlib
import time
from pathlib import Path
from pymongo import MongoClient
from core import run_scanner_core, C, mask_key

def get_file_hash(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""): h.update(chunk)
    return h.hexdigest()

def main():
    print(f"{C.H}APK Scanner - Automated Multi-Scan Mode{C.END}")
    print(f"{C.B}{'='*60}{C.END}")
    
    db = MongoClient("mongodb://localhost:27017/").apk_hack
    apps_dir = Path("apps")
    if not apps_dir.exists(): return print(f"{C.R}[!] No 'apps' directory found.{C.END}")

    files = [f for f in apps_dir.iterdir() if f.suffix in ['.apk', '.apkm', '.xapk']]
    print(f"[*] Found {C.BOLD}{len(files)}{C.END} target files. Analyzing database...")

    for fpath in files:
        fhash = get_file_hash(fpath)
        if db.scans.find_one({"hash": fhash}):
            continue

        print(f"  {C.C}SCAN{C.END} | {C.BOLD}{fpath.name}{C.END}...", end="", flush=True)
        try:
            res = run_scanner_core(str(fpath), verbose=False)
            db.scans.insert_one({
                "filename": fpath.name, "hash": fhash, 
                "results": res, "at": time.time()
            })
            
            count = len(res)
            if count > 0:
                print(f" \r  {C.G}HIT {C.END} | {C.BOLD}{fpath.name}{C.END} -> {C.G}{count} keys found!{C.END}")
                for r_info in res:
                    k = r_info.get("key", "")
                    w_count = r_info.get("working_count", 0)
                    tests = r_info.get("results", [])
                    if w_count > 0:
                        print(f"    {C.H}{'-'*50}{C.END}")
                        print(f"    {C.BOLD}VULNERABLE KEY: {mask_key(k)}{C.END}")
                        print(f"    {C.H}{'-'*50}{C.END}")
                        for name, verdict, detail in tests:
                            if verdict == "WORKING":
                                print(f"      {C.G}{name.ljust(20)} → {verdict.ljust(15)} {detail}{C.END}")
                        print(f"\n      → {w_count}/8 working\n")
            else:
                print(f" \r  {C.R}NONE{C.END} | {C.BOLD}{fpath.name}{C.END} -> No vulnerabilities found.")
        except Exception as e:
            print(f" \r  {C.R}FAIL{C.END} | {C.BOLD}{fpath.name}{C.END} -> {e}")

    print(f"{C.B}{'='*60}{C.END}")
    print(f"{C.G}[+] Batch scan complete.{C.END}")

if __name__ == "__main__":
    main()
