FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    SAFETRACE_OFFLINE=1 SAFETRACE_DATA_DIR=/app/data \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY models-manifest.json ./
COPY scripts/prepare_models.py scripts/prepare_models.py
RUN python scripts/prepare_models.py
COPY backend/ backend/
COPY scripts/ scripts/
COPY fixtures/ fixtures/
COPY datasets/ datasets/
COPY reports/versions/ reports/versions/
COPY reports/EVALUATION*.md reports/
COPY --from=frontend /build/frontend/dist frontend/dist/
RUN useradd --create-home --uid 10001 safetrace && mkdir -p data && chown -R safetrace:safetrace /app
USER safetrace
EXPOSE 8765
HEALTHCHECK --interval=20s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=4)"
CMD ["python", "scripts/run_container.py"]
