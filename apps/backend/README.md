---
title: Drive Face Match Backend
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Face Recon Drive Backend

High-performance, concurrent backend service for scanning Google Drive folders and identifying faces using `dlib` and `face_recognition`.

## Architecture
- **FastAPI** — Handles high-concurrency web requests and WebSocket connections.
- **Celery + Redis** — Background worker for CPU-intensive image processing.
- **Google OAuth 2.0** — Secure user authentication and Drive API access without service accounts.

## Local Development (Native)

1. **Install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Environment Variables:** Create a `.env` file from the sample config. Needs `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `REDIS_URL`.

3. **Start Redis:**
   ```bash
   redis-server
   ```

4. **Start the Celery worker:**
   ```bash
   celery -A app.core.celery_app worker --loglevel=info
   ```

5. **Start the API server:**
   ```bash
   uvicorn app.main:app --reload
   ```

### Unified Startup (Recommended)
To start both the API and the Worker in a single terminal:
```bash
chmod +x start.sh
./start.sh
```
> [!NOTE]  
> The worker and API must both be running for scans to progress.

## Local Development (Docker)

To run the entire stack (Redis, API, Worker) cleanly inside isolated containers:

```bash
docker compose up --build
```

## Production Deployment

This backend requires system-level C++ libraries (`cmake`, `libopenblas-dev`) for face recognition. Because of this CPU-intensive requirement, standard free tiers like Vercel or Heroku will fail or time out.

### Hugging Face Spaces (Recommended Free Tier)
1. Push this repository to GitHub.
2. Create a new "Space" on [Hugging Face](https://huggingface.co).
3. Select **Docker** as the environment and connect your GitHub repo.
4. Add your Google OAuth keys to the **Variables and Secrets** settings.
5. Hugging Face will automatically read the `Dockerfile`, install the C++ libraries, boot Redis/Celery via `start.sh`, and run the API.

## Documentation
- `API_DOCS.md` — Full API payloads and WebSocket event reference.
- Module-specific documentation can be found in `README.md` files inside `app/core`, `app/services`, and `app/workers`.
