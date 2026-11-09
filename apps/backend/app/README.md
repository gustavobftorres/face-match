# Face Recon Drive Backend

## Overview
This is the backend for the Face Recon Drive application. It uses FastAPI, Celery, Redis, and Google Drive API to scan folders for faces matching a target face.

## Modules
- `core`: Configuration and infrastructure.
- `services`: External service integrations (Google Drive, Face Recognition).
- `workers`: Background tasks (Celery).
- `api`: API endpoints and WebSockets.
- `schemas`: Pydantic models.

## Usage
Run the server: `uvicorn app.main:app --reload`
Run the worker: `celery -A app.core.celery_app worker --loglevel=info`
