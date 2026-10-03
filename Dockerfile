# --- 1. build the Vue frontend ---
FROM node:20-alpine AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. runtime: FastAPI serves /ws and the built frontend ---
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# /app/data holds the SQLite database (accounts); docker-compose mounts a
# named volume there, which inherits this directory's owner on first use
ENV BRIDGE_DB_PATH=/app/data/bridge.db

RUN useradd -m -r appuser && mkdir -p /app/data && chown -R appuser /app
WORKDIR /app

RUN pip install --upgrade pip
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser backend/ ./backend/
COPY --from=frontend --chown=appuser:appuser /frontend/dist ./frontend/dist

USER appuser

EXPOSE 8000

# Exactly one worker: rooms and games live in this process's memory, so a
# second worker would see a different set of rooms.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
