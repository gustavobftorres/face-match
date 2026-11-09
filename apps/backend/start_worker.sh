#!/bin/bash
./venv/bin/celery -A app.core.celery_app worker --loglevel=info
