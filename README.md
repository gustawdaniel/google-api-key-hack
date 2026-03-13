# Google API Key Hunter & Validator

High-performance, automated pipeline for extracting and validating Google Maps platform API keys from Android packages (APK, XAPK, APKM, AAB). Built for scale and research.

![Dashboard](./docs/dashboard.png)
![Scan](./docs/scan.png)

## 🏗️ Architecture Stack

Robust microservices architecture managed by `docker-compose`.

- **MongoDB**: Central state, job queues, and scan matrices. Mounted to `./mongodb_data` on host for complete persistence across container rebuilds.
- **Dashboard (FastAPI + Svelte)**: Real-time UI at `http://localhost:8000`. WebSocket logs, dynamic vulnerability grids, and rate-throttle bypass toggles.
- **Crawler**: Scrapes APKPure (via `cloudscraper`), dynamically rotating search queries to discover and enqueue new targets.
- **Worker(s)**: Scalable async downloaders handling HTTP 429 backoffs. Spawns the extraction engine on success.
- **Core Engine**: `regex`-optimized archive traversal yielding keys aggressively validated against multiple Maps endpoints.

## 🚀 Quick Start

Spin up the entire cluster:

```bash
docker-compose up -d --build
# Open the Dashboard: http://localhost:8000
```

---

## 🛠️ CLI Operations

While Docker handles distributed scanning and the dashboard UI, local Python CLI tools provide immediate utility for specific workflows.

### Batch Scanning (`apk.scan.py`)
The automated hub for scanning local directories. Differentially scans new files in `./apps/` (by hashing), tests keys, and saves results to MongoDB with a high-visibility terminal UI. **This is the primary script for local operations.**

![Keys](./docs/keys.png)

```bash
# Scan everything in ./apps/
python apk.scan.py
```

### Focused Single-App Inspection (`apk_grok.py`)
Deep-dive into a single target file to grab its payload test results instantly.

```bash
python apk_grok.py path/to/app.apk
```

### Headless Web Spider (`apk_getter.py`)
If you don't run the Docker stack, fetch targets manually.

```bash
python apk_getter.py --query "weather" --limit 10
```

## ⚠️ Disclaimer
Educational use and authorized security research only. Using discovered API keys without permission is illegal and unethical. The authors are not responsible for any misuse.
