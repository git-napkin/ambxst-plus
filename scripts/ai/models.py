"""Pinned Spotlight model IDs and catalog filters."""

from __future__ import annotations

DEFAULT_MODEL_ID = "gemini-2.5-flash"
DEFAULT_PROVIDER = "gemini"

DEAD_GEMINI_MODELS = {
    "gemini-2.0-flash": DEFAULT_MODEL_ID,
    "gemini-2.0-flash-001": DEFAULT_MODEL_ID,
    "gemini-2.0-flash-lite": DEFAULT_MODEL_ID,
    "gemini-2.0-flash-lite-001": DEFAULT_MODEL_ID,
}

# Live Gemini catalog noise: not usable as Spotlight chat+tools+vision defaults.
GEMINI_CATALOG_SKIP_SUBSTR = (
    "tts",
    "live",
    "computer-use",
    "imagen",
    "embed",
    "transcribe",
    "veo",
    "lyria",
    "robotics",
    "native-audio",
    "-image",
    "image-generation",
    "omni",
)


def remap_dead_model_id(model_id):
    text = str(model_id or "").strip()
    return DEAD_GEMINI_MODELS.get(text, text)


def gemini_catalog_keep(model_id):
    """True for Gemini chat/vision IDs that belong in the Spotlight picker."""
    mid = str(model_id or "").strip()
    if not mid:
        return False
    low = mid.lower().replace("models/", "")
    if low in DEAD_GEMINI_MODELS or low.startswith("gemini-2.0"):
        return False
    for needle in GEMINI_CATALOG_SKIP_SUBSTR:
        if needle in low:
            return False
    return "gemini" in low or "flash" in low or "pro" in low
