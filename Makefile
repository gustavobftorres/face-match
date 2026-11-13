SHELL := /bin/bash
BACKEND_DIR := apps/backend
FRONTEND_DIR := apps/frontend
VENV := $(BACKEND_DIR)/venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: install install-backend install-frontend dev stop

install: install-backend install-frontend

install-backend:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	CMAKE_ARGS="-DCMAKE_PREFIX_PATH=$$(brew --prefix)" $(PIP) install -r $(BACKEND_DIR)/requirements.txt
	$(PIP) install "setuptools==69.5.1" packaging

install-frontend:
	cd $(FRONTEND_DIR) && npm install

dev:
	brew services start redis 2>/dev/null || true
	cd $(BACKEND_DIR) && source venv/bin/activate && \
		celery -A app.core.celery_app worker --loglevel=info -c 2 > /tmp/face-match-celery.log 2>&1 & \
		uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/face-match-backend.log 2>&1 &
	cd $(FRONTEND_DIR) && npm run dev

stop:
	-kill $$(lsof -ti:8000) 2>/dev/null
	-kill $$(lsof -ti:3000) 2>/dev/null
	-pkill -f "celery.*app.core.celery_app" 2>/dev/null
	brew services stop redis 2>/dev/null || true
	@echo "All services stopped."
