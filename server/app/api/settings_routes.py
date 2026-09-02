"""
RAVEN Settings API Routes.

Endpoints:
    GET    /settings/credentials/status    — Masked credential configuration status
    POST   /settings/credentials/validate  — Validate configured credentials against live APIs
    GET    /settings/guardrails            — Current auto-pilot guardrail configuration
    PUT    /settings/guardrails            — Update guardrail configuration
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import SystemSettingModel

logger = logging.getLogger(__name__)

settings_router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  CREDENTIAL STATUS
# ═══════════════════════════════════════════════════════════════

CREDENTIAL_MASK_VISIBLE_CHARS = 4
CREDENTIAL_MASK_SUFFIX_CHARS = 2


def _mask_credential(value: str) -> str | None:
    """Mask a credential string, showing only first and last few characters."""
    if not value:
        return None
    if len(value) <= CREDENTIAL_MASK_VISIBLE_CHARS + CREDENTIAL_MASK_SUFFIX_CHARS:
        return "*" * len(value)
    prefix = value[:CREDENTIAL_MASK_VISIBLE_CHARS]
    suffix = value[-CREDENTIAL_MASK_SUFFIX_CHARS:]
    masked_length = len(value) - CREDENTIAL_MASK_VISIBLE_CHARS - CREDENTIAL_MASK_SUFFIX_CHARS
    return f"{prefix}{'*' * min(masked_length, 8)}{suffix}"


@settings_router.get("/credentials/status")
async def get_credentials_status():
    """Return which credentials are configured, with masked previews.

    Does not expose actual credential values. Reads from server-side
    environment configuration only.
    """
    from app.config import settings

    credentials = {
        "gemini_api_key": {
            "label": "Gemini API Key",
            "configured": bool(settings.gemini_api_key),
            "masked": _mask_credential(settings.gemini_api_key),
        },
        "razorpay_key_id": {
            "label": "Razorpay Key ID",
            "configured": bool(settings.razorpay_key_id),
            "masked": _mask_credential(settings.razorpay_key_id),
        },
        "razorpay_key_secret": {
            "label": "Razorpay Key Secret",
            "configured": bool(settings.razorpay_key_secret),
            "masked": _mask_credential(settings.razorpay_key_secret),
        },
        "razorpay_webhook_secret": {
            "label": "Razorpay Webhook Secret",
            "configured": bool(settings.razorpay_webhook_secret),
            "masked": _mask_credential(settings.razorpay_webhook_secret),
        },
    }
    return {"credentials": credentials}


# ═══════════════════════════════════════════════════════════════
#  CREDENTIAL VALIDATION
# ═══════════════════════════════════════════════════════════════

@settings_router.post("/credentials/validate")
async def validate_credentials():
    """Test each configured credential against its respective API.

    Returns pass/fail per credential. Only tests credentials that
    are actually configured (non-empty).
    """
    from app.config import settings

    results = {}

    # ── Gemini API Key ────────────────────────────────────────
    if settings.gemini_api_key:
        try:
            import google.genai as genai
            client = genai.Client(api_key=settings.gemini_api_key)
            models = list(client.models.list())
            results["gemini_api_key"] = {
                "valid": True,
                "message": f"Connected — {len(models)} models available",
            }
        except Exception as exc:
            results["gemini_api_key"] = {
                "valid": False,
                "message": f"Authentication failed: {str(exc)[:120]}",
            }
    else:
        results["gemini_api_key"] = {
            "valid": False,
            "message": "Not configured",
        }

    # ── Razorpay Key ID + Secret ──────────────────────────────
    if settings.razorpay_key_id and settings.razorpay_key_secret:
        try:
            import razorpay
            client = razorpay.Client(
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
            )
            client.payment.all({"count": 1})
            is_test = settings.razorpay_key_id.startswith("rzp_test_")
            mode_label = "Test Mode" if is_test else "Live Mode"
            results["razorpay_key_id"] = {
                "valid": True,
                "message": f"Connected — {mode_label}",
            }
            results["razorpay_key_secret"] = {
                "valid": True,
                "message": f"Authenticated — {mode_label}",
            }
        except Exception as exc:
            error_msg = f"API call failed: {str(exc)[:120]}"
            results["razorpay_key_id"] = {"valid": False, "message": error_msg}
            results["razorpay_key_secret"] = {"valid": False, "message": error_msg}
    else:
        if not settings.razorpay_key_id:
            results["razorpay_key_id"] = {"valid": False, "message": "Not configured"}
        if not settings.razorpay_key_secret:
            results["razorpay_key_secret"] = {"valid": False, "message": "Not configured"}

    # ── Razorpay Webhook Secret ───────────────────────────────
    if settings.razorpay_webhook_secret:
        results["razorpay_webhook_secret"] = {
            "valid": True,
            "message": "Configured (validated on webhook receipt)",
        }
    else:
        results["razorpay_webhook_secret"] = {
            "valid": False,
            "message": "Not configured",
        }

    return {"results": results}


# ═══════════════════════════════════════════════════════════════
#  GUARDRAILS
# ═══════════════════════════════════════════════════════════════

GUARDRAILS_KEY = "guardrails"

DEFAULT_GUARDRAILS: dict[str, Any] = {
    "auto_contest_enabled": True,
    "min_confidence_threshold": 80,
    "max_dispute_amount": 5000000,
    "require_human_review_above": 2500000,
}


class GuardrailsUpdate(BaseModel):
    """Request body for updating guardrail configuration.

    Amount fields accept None to express special semantics:
        max_dispute_amount = None → no cap (any amount eligible)
        require_human_review_above = None → threshold disabled
    """
    auto_contest_enabled: bool = Field(
        default=True,
        description="Whether auto-contest recommendations are enabled.",
    )
    min_confidence_threshold: int = Field(
        default=80,
        ge=50,
        le=100,
        description="Minimum confidence score (%) to auto-recommend contesting.",
    )
    max_dispute_amount: int | None = Field(
        default=5000000,
        ge=0,
        description=(
            "Maximum dispute amount (in paise) eligible for auto-contest. "
            "None means no cap."
        ),
    )
    require_human_review_above: int | None = Field(
        default=2500000,
        ge=0,
        description=(
            "Disputes above this amount (in paise) always require human review. "
            "None means the threshold is disabled."
        ),
    )


def _build_guardrail_warnings(values: dict[str, Any]) -> list[str]:
    """Generate advisory warnings for the given guardrail config.

    Returns a list of human-readable warning strings. Empty list means
    no issues detected. These are informational — they do not block saves.
    """
    warnings: list[str] = []

    max_amount = values.get("max_dispute_amount")
    review_above = values.get("require_human_review_above")

    if (
        max_amount is not None
        and review_above is not None
        and review_above > max_amount
    ):
        warnings.append(
            "Human review threshold (₹{:,}) exceeds max dispute amount (₹{:,}) "
            "— human review will never trigger for auto-contested disputes.".format(
                review_above // 100, max_amount // 100
            )
        )

    if values.get("min_confidence_threshold") == 100:
        warnings.append(
            "Confidence threshold is 100% — no dispute will ever be "
            "auto-recommended for contest."
        )

    if values.get("auto_contest_enabled") and max_amount == 0:
        warnings.append(
            "Auto-contest is enabled but max dispute amount is ₹0 — "
            "no disputes are eligible."
        )

    return warnings


def _get_guardrails(db: Session) -> dict[str, Any]:
    """Load guardrails from DB, falling back to defaults.

    Preserves None values from stored config — does not silently
    replace them with default integers.
    """
    row = db.query(SystemSettingModel).filter_by(key=GUARDRAILS_KEY).first()
    if row and row.value:
        merged = {**DEFAULT_GUARDRAILS}
        for key, stored_value in row.value.items():
            if key in merged:
                merged[key] = stored_value
        return merged
    return {**DEFAULT_GUARDRAILS}


@settings_router.get("/guardrails")
async def get_guardrails(db: Session = Depends(get_db)):
    """Return current auto-pilot guardrail configuration."""
    guardrails = _get_guardrails(db)
    return {
        "guardrails": guardrails,
        "warnings": _build_guardrail_warnings(guardrails),
        "defaults": DEFAULT_GUARDRAILS,
    }


@settings_router.put("/guardrails")
async def update_guardrails(
    body: GuardrailsUpdate,
    db: Session = Depends(get_db),
):
    """Update auto-pilot guardrail configuration.

    Validates input with Pydantic. Persists to the system_settings
    table so values survive server restarts. Returns advisory warnings
    for contradictory or extreme configurations.
    """
    new_values = body.model_dump()

    row = db.query(SystemSettingModel).filter_by(key=GUARDRAILS_KEY).first()
    if row:
        row.value = new_values
    else:
        row = SystemSettingModel(key=GUARDRAILS_KEY, value=new_values)
        db.add(row)

    db.commit()
    db.refresh(row)

    warnings = _build_guardrail_warnings(new_values)
    if warnings:
        logger.warning("Guardrails saved with warnings: %s", warnings)
    else:
        logger.info("Guardrails updated: %s", new_values)

    return {
        "guardrails": row.value,
        "saved": True,
        "warnings": warnings,
    }

