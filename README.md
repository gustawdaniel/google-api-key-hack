# Google API Key Hunter & Validator

A comprehensive toolkit for extracting and verifying Google API keys from Android application packages (APK, AAB, XAPK, and APKM). Designed for efficiency, automation, and research.

## 🛠 Features

The project is built on a modular architecture to allow both focused manual scans and large-scale automated discovery.

### 1. [core.py](file:///home/daniel/pro/google-api-key-hack/core.py)
The engine of the project. It centralizes all core logic:
- **Smart Extraction**: Uses optimized regex and deep archive traversal (supporting nested APKs in XAPK/APKM).
- **Comprehensive Testing**: Validates keys against multiple Google Maps Platform endpoints (Places New, Geocoding, Directions, Static Maps, etc.).
- **Response Analysis**: Decodes error messages to identify specific causes (billing required, API disabled, IP restrictions, etc.).
- **Security**: Automatically masks sensitive API keys in console output.

### 2. [apk_grok.py](file:///home/daniel/pro/google-api-key-hack/apk_grok.py)
A focused CLI wrapper for `core.py`:
- **Manual Mode**: Ideal for scanning single files or specific paths.
- **Multithreading**: Fast validation of multiple keys found within a single app.
- **Rich Output**: Detailed breakdown of which services are enabled for a found key.

### 3. [apk.scan.py](file:///home/daniel/pro/google-api-key-hack/apk.scan.py)
The automated automation hub with **MongoDB** integration:
- **Differential Scanning**: Calculates SHA256 hashes for all files in the `apps/` directory. It only scans new or modified files.
- **Persistent Storage**: Saves all findings, hashes, and validation results into a local MongoDB instance.
- **Hacker UI**: Features a high-visibility terminal interface with color-coded results (HIT/NONE/SKIP).

### 4. [apk_getter.py](file:///home/daniel/pro/google-api-key-hack/apk_getter.py)
Automated APK discovery tool:
- **Targeting**: Scrapes **APKPure** for trending or specific query results.
- **Bypass**: Uses `cloudscraper` to navigate around bot protections.
- **Automation**: Populates your `apps/` directory with fresh targets for scanning.

## 🗄️ Database Setup (MongoDB)

The project uses a local MongoDB container for persistent storage.

```bash
docker-compose up -d
```

## 🚀 Installation

Ensure you have Python 3.8+ installed.

```bash
pip install requests colorama pymongo cloudscraper beautifulsoup4
```

## 📋 Usage Examples

### Fetch New Apps
```bash
# Download 10 latest apps related to "weather"
python apk_getter.py --query "weather" --limit 10
```

### Run Automated Scan
```bash
# Processes everything in apps/ and saves to MongoDB
python apk.scan.py
```

### Manual Individual Scan
```bash
python apk_grok.py path/to/app.apk
```

## ⚠️ Disclaimer

This tool is for educational purposes and authorized security research only. Using discovered API keys without permission is illegal and unethical. The authors are not responsible for any misuse of this tool.
