# Production Hardened Backend Dockerfile
FROM python:3.11-slim

# System setup & security hardening
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Create non-root application user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-create data directories with correct non-root permissions
RUN mkdir -p /app/data/uploads /app/data/attachments /app/data/chroma && \
    chown -R appuser:appgroup /app

# Copy application source code
COPY --chown=appuser:appgroup ./app ./app

# Expose FastAPI port
EXPOSE 8000

# Health check probe using standard Python library (no curl/wget dependency required)
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')" || exit 1

# Execute as non-root user
USER appuser

# Start production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
