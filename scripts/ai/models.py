"""Spotlight model IDs, dead-ID remap, and vision capability."""

from __future__ import annotations

# No Spotlight / computer-use pin. Fresh installs and dead-ID remaps leave
# the selection empty so restore uses lastAiModel, then the first configured
# catalog model. Computer use always inherits that current model.
DEFAULT_MODEL_ID = ""
DEFAULT_PROVIDER = ""

DEAD_GEMINI_MODELS = {
    "gemini-2.0-flash": "",
    "gemini-2.0-flash-001": "",
    "gemini-2.0-flash-lite": "",
    "gemini-2.0-flash-lite-001": "",
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

# Text-only / non-chat IDs. Unknown models fail closed.
_VISION_DENY_SUBSTR = (
    "tts",
    "whisper",
    "embed",
    "embedding",
    "imagen",
    "veo",
    "lyria",
    "transcribe",
    "native-audio",
    "image-generation",
    "moderation",
    "dall-e",
    "davinci",
    "babbage",
    "gpt-3.5",
    "text-embedding",
    "rerank",
)

_VISION_DENY_IDS = {
    "o1-mini",
    "o1-preview",
    "o3-mini",
    "o3-mini-high",
    "gpt-4",
    "gpt-4-0314",
    "gpt-4-0613",
    "gpt-4-32k",
    "claude-2",
    "claude-2.0",
    "claude-2.1",
    "claude-instant",
    "claude-instant-1",
}


def remap_dead_model_id(model_id):
    text = str(model_id or "").strip()
    if text in DEAD_GEMINI_MODELS:
        return DEAD_GEMINI_MODELS[text]
    return text


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


def model_id_of(spec):
    if isinstance(spec, dict):
        text = spec.get("model") or spec.get("name") or spec.get("id") or ""
    else:
        text = spec or ""
    return str(text).strip()


def _norm_model_id(spec):
    mid = model_id_of(spec).lower().replace("models/", "")
    if "/" in mid:
        mid = mid.split("/", 1)[-1]
    if ":" in mid:
        mid = mid.split(":", 1)[0]
    return mid


def model_supports_vision(spec):
    """Fail-closed: True only when the id is a known chat+image model."""
    mid = _norm_model_id(spec)
    if not mid:
        return False
    for needle in _VISION_DENY_SUBSTR:
        if needle in mid:
            return False
    if mid in _VISION_DENY_IDS:
        return False
    if "o1-mini" in mid or "o3-mini" in mid:
        return False
    if "llava" in mid or "pixtral" in mid or "moondream" in mid:
        return True
    if "qwen" in mid and "vl" in mid:
        return True
    if "gemma3" in mid or "gemma-3" in mid:
        return True
    if "llama" in mid and "vision" in mid:
        return True
    if "minicpm" in mid:
        return True
    if "vision" in mid:
        return True
    if "gemini" in mid:
        return True
    if "claude" in mid:
        if mid.startswith("claude-2") or "instant" in mid:
            return False
        return True
    if "gpt-4o" in mid or "gpt-4.1" in mid or "gpt-4-turbo" in mid or "gpt-4-vision" in mid:
        return True
    if "gpt-5" in mid:
        return True
    if mid.startswith("o3") or mid.startswith("o4") or mid.startswith("o1"):
        return "mini" not in mid
    return False


def vision_unsupported_message(spec):
    mid = model_id_of(spec) or "(none)"
    return (
        "Computer use requires a vision-capable model so it can read screenshots. "
        "The current model (%s) does not support images. Select a vision model in "
        "Spotlight and try again — computer use will not switch models. "
        "Computer use has been ended." % mid
    )
