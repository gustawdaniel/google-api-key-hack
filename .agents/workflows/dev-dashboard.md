---
description: how to run the dashboard in development mode locally
---

To run the dashboard in development mode with Hot Module Replacement (HMR):

1. **Start the Backend Infrastructure** (MongoDB):
   ```bash
   docker compose up -d mongodb
   ```

2. **Start the Dashboard API Server**:
   Ensure you have the dependencies installed:
   ```bash
   pip install fastapi uvicorn websockets motor pydantic httpx
   ```
   Run the server:
   ```bash
   export MONGO_URI=mongodb://localhost:27017
   python dashboard_server.py
   ```

3. **Start the Vite Dev Server**:
   Open a new terminal, go to the dashboard directory, and run:
   ```bash
   cd dashboard
   pnpm install
   pnpm run dev
   ```

// turbo
4. Access the dashboard at `http://localhost:5173`. It will connect to the API at `:8000` automatically.
