FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY server/pyproject.toml ./server/
RUN pip install --no-cache-dir ./server[agent] || pip install --no-cache-dir ./server

# Copy server code
COPY server/ ./server/

# Copy pre-built frontend (run `cd web && npm run build` first)
COPY web/dist/ ./web/dist/

# Environment
ENV PYTHONPATH=/app/server
ENV PYTHONUNBUFFERED=1
ENV RAVEN_DATABASE_URL=sqlite:///./raven.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
