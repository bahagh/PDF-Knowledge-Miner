## Production-ready Dockerfile: install from requirements-prod.txt
FROM python:3.11-slim AS production

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Prefer a checked-in production requirements file
COPY requirements-prod.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user and data directories
RUN useradd -m appuser || true && \
    mkdir -p data/pdfs data/index && \
    chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app

# Health check (uses curl which is available) - runs as container user
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Use uvicorn directly; --proxy-headers is optional depending on your reverse proxy
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]