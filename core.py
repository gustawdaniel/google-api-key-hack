#!/usr/bin/env python3
import zipfile
import re
import requests
import json
import io
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Tuple, Optional, Dict

# --- Colors ---
try:
    from colorama import init
    init(autoreset=True)
    C = type('C', (), {
        'H': '\033[95m', 'B': '\033[94m', 'G': '\033[92m',
        'Y': '\033[93m', 'R': '\033[91m', 'C': '\033[96m',
        'W': '\033[97m', 'END': '\033[0m', 'BOLD': '\033[1m'
    })()
except:
    C = type('C', (), {k: '' for k in 'H B G Y R C W END BOLD'.split()})()

# --- Configuration ---
GOOGLE_KEY_REGEX = rb'(?<![\w-])AIza[0-9A-Za-z_-]{35}(?![\w-])'

# --- Key masking ---
def mask_key(key: str, visible_chars: int = 8) -> str:
    if len(key) <= visible_chars:
        return "*" * len(key)
    return key[:visible_chars] + "*" * (len(key) - visible_chars)

# --- API Tests ---
def test_places_new(key: str):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.id"
    }
    payload = {"textQuery": "coffee"}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        return "Places API (New)", r.status_code, r.content
    except Exception as e:
        return "Places API (New)", None, str(e).encode()

def _get(name: str, url: str):
    try:
        r = requests.get(url, timeout=10)
        return name, r.status_code, r.content
    except Exception as e:
        return name, None, str(e).encode()

def test_geocoding(key: str):
    return _get("Geocoding", f"https://maps.googleapis.com/maps/api/geocode/json?address=London&key={key}")

def test_directions(key: str):
    return _get("Directions", f"https://maps.googleapis.com/maps/api/directions/json?origin=0,0&destination=1,1&key={key}")

def test_static_map(key: str):
    return _get("Static Map", f"https://maps.googleapis.com/maps/api/staticmap?center=0,0&zoom=0&size=200x200&key={key}")

def test_elevation(key: str):
    return _get("Elevation", f"https://maps.googleapis.com/maps/api/elevation/json?locations=0,0&key={key}")

def test_places_textsearch(key: str):
    return _get("Places TextSearch", f"https://maps.googleapis.com/maps/api/place/textsearch/json?query=test&key={key}")

def test_places_nearby(key: str):
    return _get("Places Nearby", f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=0,0&radius=100&key={key}")

def test_places_details(key: str):
    return _get("Places Details", f"https://maps.googleapis.com/maps/api/place/details/json?place_id=ChIJN1t_tDeuEmsRUsoyG83frY4&key={key}")

ALL_TESTS = [
    test_places_new, test_geocoding, test_directions, test_static_map,
    test_elevation, test_places_textsearch, test_places_nearby, test_places_details,
]

# --- Analyzer ---
def analyze_response(name: str, status: Optional[int], content: bytes) -> Tuple[str, str]:
    if not content: return "ERROR", "Empty response"
    if status != 200: return "ERROR", f"HTTP {status or 'Timeout'}"
    if content.startswith(b'\x89PNG'): return "WORKING", "Image returned"
    
    try:
        data = json.loads(content.decode('utf-8', errors='replace'))
        if "error" in data and "status" not in data:
            msg = data["error"].get("message", "").lower()
            code = data["error"].get("code", 0)
            if code == 403 and "billing" in msg: return "NO_BILLING", "Billing disabled"
            if "quota" in msg or "consumer" in msg: return "INVALID", "Key suspended"
            return "ERROR", msg[:80]

        api_status = data.get("status", "")
        err_msg = data.get("error_message", "").lower()
        if api_status in ["OK", "ZERO_RESULTS"]: return "WORKING", "Success"
        if api_status == "REQUEST_DENIED":
            if "not authorized" in err_msg or "not enabled" in err_msg: return "API_NOT_ENABLED", "API disabled"
            if "billing" in err_msg: return "NO_BILLING", "Billing required"
            if "referer" in err_msg or "ip" in err_msg: return "RESTRICTED", "IP/Referer restricted"
            return "REQUEST_DENIED", err_msg[:80]
        return "UNKNOWN", api_status
    except:
        return "UNKNOWN", "Parse error"

# --- Extraction ---
def extract_keys_from_zip(z: zipfile.ZipFile) -> Set[str]:
    keys = set()
    for name in z.namelist():
        try:
            data = z.read(name)
            for m in re.finditer(GOOGLE_KEY_REGEX, data):
                k = m.group(0).decode('utf-8', errors='ignore')
                if len(k) == 39: keys.add(k)
        except: pass
    return keys

def extract_keys(path: Path) -> List[str]:
    keys = set()
    if path.is_dir():
        for p in path.rglob("*.apk"):
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z: keys.update(extract_keys_from_zip(z))
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            keys.update(extract_keys_from_zip(z))
            for name in z.namelist():
                if name.endswith(".apk"):
                    with z.open(name) as f:
                        sub = zipfile.ZipFile(io.BytesIO(f.read()))
                        keys.update(extract_keys_from_zip(sub))
    return sorted(keys)

# --- Core Scanner ---
def test_key(key: str) -> Tuple[str, List[Tuple[str, str, str]], int]:
    results = []
    working = 0
    for func in ALL_TESTS:
        name, status, content = func(key)
        verdict, detail = analyze_response(name, status, content)
        if verdict == "WORKING": working += 1
        results.append((name, verdict, detail))
    return key, results, working

def run_scanner_core(path_str: str, threads: int = 12, verbose: bool = True) -> List[Dict]:
    p = Path(path_str).expanduser()
    if not p.exists(): return []
    keys = extract_keys(p)
    if not keys: return []

    final_results = []
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for future in as_completed({pool.submit(test_key, k): k for k in keys}):
            key, results, working_count = future.result()
            final_results.append({"key": key, "results": results, "working_count": working_count})
            if verbose:
                print(f"{C.H}{'='*60}{C.END}\n{C.BOLD}KEY: {mask_key(key)}{C.END}\n{C.H}{'='*60}{C.END}")
                for name, verdict, detail in results:
                    col = C.G if verdict == "WORKING" else (C.Y if verdict == "API_NOT_ENABLED" else C.R)
                    print(f"  {col}{name.ljust(20)} → {verdict.ljust(15)} {detail}{C.END}")
                print(f"\n  → {working_count}/8 working\n")
    return final_results
