"""
RAVEN Server Configuration.

All settings are read from environment variables with the RAVEN_ prefix,
or from a .env file in the server directory.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings — single source of truth for configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="RAVEN_",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────────
    database_url: str = "sqlite:///./raven.db"

    # ── Razorpay ──────────────────────────────────────────────
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ── Agent ─────────────────────────────────────────────────
    gemini_api_key: str = ""
    agent_model: str = "gemini-3.6-flash"  # Configurable model for ADK agent
    agent_max_tool_calls: int = 15
    agent_max_latency_seconds: int = 60
    agent_max_retries: int = 2

    # ── App ───────────────────────────────────────────────────
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    @property
    def is_test_mode(self) -> bool:
        """Detect Razorpay test mode from API key prefix."""
        return self.razorpay_key_id.startswith("rzp_test_")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


# ── Available Models & Pricing Catalog ────────────────────────

AVAILABLE_MODELS = [
    {
        "id": "gemini-3.6-flash",
        "name": "Gemini 3.6 Flash",
        "tier": "Free / Economy",
        "price": "Free Tier / $0.10 per 1M",
        "speed": "⚡ Ultra Fast (~1.5s)",
        "badge": "Recommended",
        "description": "Optimal balance of dispute reasoning speed and cost efficiency.",
        "is_default": True,
    },
    {
        "id": "gemini-2.5-flash-lite",
        "name": "Gemini 2.5 Flash Lite",
        "tier": "Budget",
        "price": "$0.075 per 1M",
        "speed": "⚡⚡ Fastest (~0.8s)",
        "badge": "Lowest Cost",
        "description": "Lightweight model optimized for high-volume standard disputes at minimal cost.",
        "is_default": False,
    },
    {
        "id": "gemini-3.7-flash",
        "name": "Gemini 3.7 Flash",
        "tier": "Hybrid Reasoning",
        "price": "$0.10 per 1M",
        "speed": "⚡ Fast (~2.0s)",
        "badge": "Next-Gen",
        "description": "Next-gen reasoning engine with dynamic thinking for nuanced customer claims.",
        "is_default": False,
    },
    {
        "id": "gemini-2.5-pro",
        "name": "Gemini 2.5 Pro",
        "tier": "Deep Reasoning",
        "price": "$1.25 per 1M",
        "speed": "🧠 Deep (~4.0s)",
        "badge": "High Value",
        "description": "Advanced multi-step reasoning for high-value chargebacks and complex fraud claims.",
        "is_default": False,
    },
]

# Module-level singleton — import this wherever settings are needed
settings = Settings()
