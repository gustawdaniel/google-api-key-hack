# --- Stage 1: Build Dashboard ---
FROM node:22-slim AS build-stage
WORKDIR /app/dashboard
RUN npm install -g pnpm
COPY dashboard/package.json ./
# Check if lockfile exists before copying
COPY dashboard/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install
COPY dashboard/ .
RUN pnpm run build

# --- Stage 2: Python App ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libnss3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    motor \
    pymongo \
    curl_cffi \
    beautifulsoup4 \
    rich \
    fastapi \
    "uvicorn[standard]" \
    websockets \
    httpx

# Copy the entire project
COPY . .

# Copy built dashboard from stage 1
COPY --from=build-stage /app/dashboard/dist ./dashboard/dist

RUN mkdir -p apps

# Default entrypoint (overridden in docker-compose)
CMD ["python", "stats.py"]

