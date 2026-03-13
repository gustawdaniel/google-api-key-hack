#!/usr/bin/env python3
import sys
import argparse
from core import run_scanner_core, C

def main():
    parser = argparse.ArgumentParser(description="Google API Key Hunter - Single File")
    parser.add_argument("path", help="APK/APKM/XAPK file or folder")
    parser.add_argument("-t", "--threads", type=int, default=12, help="Threads (default 12)")
    args = parser.parse_args()
    
    print(f"{C.BOLD}Google API Key Hunter - Focused Mode{C.END}")
    results = run_scanner_core(args.path, threads=args.threads, verbose=True)
    if not results:
        print(f"{C.R}No keys found or path invalid.{C.END}")

if __name__ == "__main__":
    main()
