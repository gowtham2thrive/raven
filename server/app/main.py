"""
RAVEN FastAPI Application.

Entry point: uvicorn app.main:app --reload --port 8000

RAVEN is an evidence investigation and verification system
for chargeback disputes. This is the API layer that
receives Razorpay webhooks and exposes REST endpoints.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    cases_router,
    metrics_router,
    models_router,
    simulator_router,
    stream_router,
    webhooks_router,
)
from app.api.integration_routes import integrations_router
from app.api.settings_routes import settings_router
from app.db.database import Base, engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables. Shutdown: cleanup."""
    logger.info("RAVEN starting up...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    yield
    logger.info("RAVEN shutting down.")


app = FastAPI(
    title="RAVEN",
    description=(
        "Risk Analysis & Verification for Evidence Navigation. "
        "Chargeback investigation and evidence response system."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:5174",   # Vite fallback port
        "http://localhost:3000",   # Next.js dev server
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(cases_router, prefix="/cases", tags=["Cases"])
app.include_router(simulator_router, prefix="/simulator", tags=["Simulator"])
app.include_router(metrics_router, prefix="/metrics", tags=["Metrics"])
app.include_router(models_router, prefix="/models", tags=["Models"])
app.include_router(integrations_router, prefix="/integrations", tags=["Integrations"])
app.include_router(settings_router, prefix="/settings", tags=["Settings"])
app.include_router(stream_router, tags=["Stream"])


@app.get("/health", tags=["System"])
def health():
    """Service health check."""
    from app.config import settings
    return {
        "status": "ok",
        "service": "raven",
        "version": "0.1.0",
        "agent_mode": "adk" if settings.gemini_api_key else "deterministic",
        "agent_model": settings.agent_model if settings.gemini_api_key else None,
    }


# ── Static file serving (production) ──────────────────────────
# Serve the pre-built frontend from ../web/dist/ if it exists.
# In development, the Vite dev server handles the frontend.

from pathlib import Path
from fastapi.staticfiles import StaticFiles

_web_dist = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if _web_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="frontend")
    logger.info(f"Serving frontend from {_web_dist}")

