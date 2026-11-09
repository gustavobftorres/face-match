import logging
import os
from celery import Celery
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

def ensure_ssl_cert_reqs(url: str) -> str:
    if not url:
        return url
    url = url.strip().strip("'").strip('"')
    if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        separator = "&" if "?" in url else "?"
        url += f"{separator}ssl_cert_reqs=CERT_NONE"
    return url

redis_url = ensure_ssl_cert_reqs(settings.REDIS_URL)

# Also ensure any Celery native environment variables are fixed if the user set those instead
if "CELERY_BROKER_URL" in os.environ:
    os.environ["CELERY_BROKER_URL"] = ensure_ssl_cert_reqs(os.environ["CELERY_BROKER_URL"])
if "CELERY_RESULT_BACKEND" in os.environ:
    os.environ["CELERY_RESULT_BACKEND"] = ensure_ssl_cert_reqs(os.environ["CELERY_RESULT_BACKEND"])
# Some HF Spaces configs might use REDIS_URL from os.environ
if "REDIS_URL" in os.environ:
    os.environ["REDIS_URL"] = ensure_ssl_cert_reqs(os.environ["REDIS_URL"])

celery_app = Celery(
    "worker",
    broker=redis_url,
    backend=redis_url,
    broker_use_ssl={"ssl_cert_reqs": "CERT_NONE"} if redis_url.startswith("rediss://") else None,
    redis_backend_use_ssl={"ssl_cert_reqs": "CERT_NONE"} if redis_url.startswith("rediss://") else None,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=360,
    task_time_limit=420,
)
