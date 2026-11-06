# ==============================================================================
# SettleTable Production Containerfile
# Single-instance Python WSGI with local CPU ONNX OCR and persistent SQLite WAL
# ==============================================================================

FROM python:3.12-slim AS base

# System dependencies for OpenCV headless, ONNX Runtime, and container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Security: Create non-root application user, group, and cache directories
RUN groupadd -r settletable -g 10001 && \
    useradd -u 10001 -r -g settletable -m -s /sbin/nologin -c "SettleTable User" settletable && \
    mkdir -p /home/settletable/.cache/rapidocr /home/settletable/.cache/numba

# Explicit cache directory configuration for non-root user
ENV RAPIDOCR_CACHE_DIR=/home/settletable/.cache/rapidocr \
    NUMBA_CACHE_DIR=/home/settletable/.cache/numba

WORKDIR /app

# Install Python production server and optional local OCR dependencies
COPY requirements-ocr.txt /app/
RUN pip install --no-cache-dir "gunicorn>=21.2.0" -r requirements-ocr.txt

# Pre-cache RapidOCR ONNX models into image at build time (ensures air-gapped offline startup)
RUN python -c "from rapidocr_onnxruntime import RapidOCR; RapidOCR()"

# Copy application package and operational tools
COPY settletable /app/settletable
COPY tools /app/tools

# Set up persistent data directory for SQLite WAL and receipt photos, fix permissions
RUN mkdir -p /data/receipt_photos && \
    chown -R settletable:settletable /home/settletable /app /data

# Default production environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SETTLETABLE_DB_PATH=/data/settletable.sqlite \
    SETTLETABLE_STORAGE_DIR=/data/receipt_photos \
    SETTLETABLE_SERVER_ORIGIN=http://localhost:8000 \
    SETTLETABLE_ALLOWED_HOSTS=localhost:8000,127.0.0.1:8000,localhost,127.0.0.1

VOLUME ["/data"]
EXPOSE 8000

# Run as unprivileged user
USER settletable

# Internal health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/healthz || exit 1

# Single-process, multi-threaded Gunicorn runner (preserves SQLite WAL single-instance invariants)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "60", "settletable.wsgi:app"]
