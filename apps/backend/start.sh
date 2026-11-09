#!/bin/bash
set -e

if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

if [[ -z "$REDIS_URL" ]] || [[ "$REDIS_URL" == *"localhost"* ]] || [[ "$REDIS_URL" == *"127.0.0.1"* ]]; then
    if command -v redis-server >/dev/null 2>&1; then
        redis-server --daemonize yes --dir .
    else
        echo "Warning: redis-server not found. Redis-based tasks may fail if REDIS_URL is not an external service."
    fi
fi

echo "Starting Celery worker..."
if command -v nproc >/dev/null 2>&1; then
    CORES=$(nproc)
else
    CORES=2
fi
celery -A app.core.celery_app worker --loglevel=info -c "$CORES" &
echo "Starting FastAPI server..."
PORT=${PORT:-8000}
uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
