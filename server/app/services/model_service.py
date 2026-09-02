"""Dynamic Model Discovery Service.

Fetches available Gemini models directly from Google's API via client.models.list()
and dynamically infers pricing tier, speed, and capability metadata.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Cache store
_CACHED_MODELS: list[dict[str, Any]] = []
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS = 3600.0  # 1 hour cache


def _infer_model_metadata(model_id: str, display_name: str | None, description: str | None) -> dict[str, Any]:
    """Dynamically infer pricing tier, speed rating, and badges from model id."""
    name_clean = model_id.replace("models/", "")
    lower = name_clean.lower()

    # Determine Tier & Pricing
    if "flash-lite" in lower or "lite" in lower:
        tier = "Ultra Low Cost"
        price = "$0.075 per 1M tokens"
        speed = "⚡⚡ Instant (~0.8s)"
        badge = "Lowest Cost"
    elif "pro" in lower or "deep-research" in lower:
        tier = "Deep Reasoning"
        price = "$1.25 per 1M tokens"
        speed = "🧠 Deep (~3.5s - 5s)"
        badge = "High Value"
    elif "3.7" in lower or "omni" in lower:
        tier = "Hybrid Reasoning"
        price = "$0.10 per 1M tokens"
        speed = "⚡ Fast (~2.0s)"
        badge = "Next-Gen"
    elif "flash" in lower or "3.6" in lower:
        tier = "Free Tier / Fast"
        price = "Free Tier / $0.10 per 1M"
        speed = "⚡ Ultra Fast (~1.5s)"
        badge = "Recommended"
    else:
        tier = "Standard"
        price = "Standard Tier"
        speed = "⚡ Fast"
        badge = "General"

    formatted_name = display_name or name_clean.replace("-", " ").title()

    # Default description if not provided by Google
    desc = description or f"Google {formatted_name} model for automated dispute reasoning."
    if "flash" in lower and "Recommended" in badge:
        desc = "Optimal balance of dispute reasoning speed and cost efficiency."
    elif "lite" in lower:
        desc = "Lightweight model optimized for high-volume standard disputes at minimal cost."
    elif "pro" in lower:
        desc = "Advanced multi-step reasoning for high-value chargebacks and complex fraud claims."
    elif "3.7" in lower:
        desc = "Next-gen reasoning engine with dynamic thinking for nuanced customer claims."

    return {
        "id": name_clean,
        "name": formatted_name,
        "tier": tier,
        "price": price,
        "speed": speed,
        "badge": badge,
        "description": desc,
        "is_default": name_clean == settings.agent_model,
    }


def get_dynamic_available_models() -> list[dict[str, Any]]:
    """Retrieve available models dynamically from Google API with fallback."""
    global _CACHED_MODELS, _CACHE_TIMESTAMP

    # Return cached if within TTL
    now = time.time()
    if _CACHED_MODELS and (now - _CACHE_TIMESTAMP < _CACHE_TTL_SECONDS):
        return _CACHED_MODELS

    if not settings.gemini_api_key:
        from app.config import AVAILABLE_MODELS
        return AVAILABLE_MODELS

    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        discovered: list[dict[str, Any]] = []
        excluded_keywords = [
            "image", "tts", "audio", "transcribe", "embedding",
            "robotics", "computer-use", "banana", "lyria", "live", "preview-customtools",
        ]

        # Prioritized primary models to place at top of list
        top_tier_keys = [
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
        ]

        for m in client.models.list():
            model_id = m.name.replace("models/", "")
            lower = model_id.lower()

            # Filter for generation models that support function/tool calling
            if any(k in lower for k in excluded_keywords):
                continue
            if not ("flash" in lower or "pro" in lower):
                continue

            meta = _infer_model_metadata(
                model_id=model_id,
                display_name=getattr(m, "display_name", None),
                description=getattr(m, "description", None),
            )
            discovered.append(meta)

        if discovered:
            # Sort: prioritized keys first, then alphabetical
            def sort_key(item: dict[str, Any]) -> tuple[int, str]:
                item_id = item["id"]
                if item_id in top_tier_keys:
                    return (top_tier_keys.index(item_id), item_id)
                return (100, item_id)

            discovered.sort(key=sort_key)
            _CACHED_MODELS = discovered
            _CACHE_TIMESTAMP = now
            logger.info(f"Dynamically loaded {len(discovered)} models live from Google API")
            return _CACHED_MODELS

    except Exception as e:
        logger.warning(f"Failed to fetch models dynamically from Google API: {e}. Using fallback.")

    from app.config import AVAILABLE_MODELS
    return AVAILABLE_MODELS
