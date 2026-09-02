"""
Adapter Registry — Factory for resolving IntegrationType to adapter class.

Each adapter self-registers via the @register_adapter decorator.
The pipeline uses get_adapter() to obtain the correct adapter
instance for any integration, without if/elif chains.
"""

from __future__ import annotations

import logging
from typing import Any, Type

from app.core.integration_types import IntegrationType, IntegrationError

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  REGISTRY
# ═══════════════════════════════════════════════════════════════

_ADAPTER_REGISTRY: dict[IntegrationType, Type] = {}


def register_adapter(integration_type: IntegrationType):
    """Decorator to register an adapter class for a given integration type.

    Usage:
        @register_adapter(IntegrationType.REST_API)
        class RestApiAdapter(BaseAdapter):
            ...
    """
    def decorator(cls):
        if integration_type in _ADAPTER_REGISTRY:
            logger.warning(
                f"Overwriting adapter registration for {integration_type.value}: "
                f"{_ADAPTER_REGISTRY[integration_type].__name__} → {cls.__name__}"
            )
        _ADAPTER_REGISTRY[integration_type] = cls
        return cls
    return decorator


def get_adapter(
    integration_type: IntegrationType,
    config: dict[str, Any],
    integration_id: str = "",
):
    """Resolve an IntegrationType to its adapter instance.

    Args:
        integration_type: Which adapter to instantiate.
        config: Type-specific config dict (serialized from Pydantic model).
        integration_id: For error reporting.

    Returns:
        An initialized adapter instance ready for test_connection() or fetch_raw_data().

    Raises:
        IntegrationError: If no adapter is registered for the given type.
    """
    adapter_cls = _ADAPTER_REGISTRY.get(integration_type)
    if adapter_cls is None:
        raise IntegrationError(
            integration_id,
            f"No adapter registered for type '{integration_type.value}'. "
            f"Available: {[t.value for t in _ADAPTER_REGISTRY]}",
        )

    return adapter_cls(config=config, integration_id=integration_id)


def list_registered_adapters() -> dict[str, str]:
    """Return a mapping of registered type → adapter class name.

    Useful for debugging and the /integrations/types endpoint.
    """
    return {
        itype.value: cls.__name__
        for itype, cls in _ADAPTER_REGISTRY.items()
    }


# ═══════════════════════════════════════════════════════════════
#  ADAPTER IMPORTS — Trigger self-registration
# ═══════════════════════════════════════════════════════════════
# Import adapter modules here so that their @register_adapter
# decorators execute and populate the registry.
# This runs once when the registry module is first imported.


def _import_adapters() -> None:
    """Import all adapter modules to trigger registration.

    Separated into a function so imports happen at first use,
    avoiding circular import issues during startup.
    """
    try:
        import app.connectors.rest_adapter  # noqa: F401
    except ImportError:
        logger.debug("REST adapter not available")

    try:
        import app.connectors.file_adapter  # noqa: F401
    except ImportError:
        logger.debug("File adapter not available")

    try:
        import app.connectors.database_adapter  # noqa: F401
    except ImportError:
        logger.debug("Database adapter not available")

    try:
        import app.connectors.webhook_adapter  # noqa: F401
    except ImportError:
        logger.debug("Webhook adapter not available")


_import_adapters()
