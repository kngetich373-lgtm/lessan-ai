# or_client.py — Compatibility alias for OmniRoute
#
# All LLM routing now lives in omniroute.py. This module re-exports the
# OmniRoute client behind the same `client` name so existing imports
# (`from or_client import client`) keep working without changes.

from omniroute import (
    OmniRoute,
    client as client,          # noqa: F401 — re-exported singleton
    TEXT_MODELS,
    VISION_MODELS,
)

__all__ = [
    "OmniRoute",
    "client",
    "TEXT_MODELS",
    "VISION_MODELS",
]