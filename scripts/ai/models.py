"""Spotlight model IDs, dead-ID remap, and vision capability."""

from __future__ import annotations

# No Spotlight / computer-use pin. Fresh installs and dead-ID remaps leave
# the selection empty so restore uses lastAiModel, then the first configured
# catalog model. Computer use uses Config.ai.computerUseModel when set,
# otherwise the current Spotlight/chat model — never a hardcoded CU pin.
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

# Known text-only / non-chat IDs. Unknown models fail *open* for CU grant.
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

_IMAGE_MODALITY_TOKENS = frozenset({"image", "images", "vision", "visual"})
_ROUTER_SLUGS = frozenset({"auto"})


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


def provider_of(spec):
    if isinstance(spec, dict):
        return str(spec.get("provider") or "").strip().lower()
    return ""


def _as_modality_list(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return _split_modality_string(value)
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            text = str(item or "").strip().lower()
            if text:
                out.append(text)
        return out or None
    return None


def _split_modality_string(value):
    if not isinstance(value, str) or not value.strip():
        return None
    left = value.strip().lower().split("->", 1)[0]
    parts = []
    for chunk in left.replace("+", ",").replace("/", ",").replace("|", ",").split(","):
        token = chunk.strip()
        if token:
            parts.append(token)
    return parts or None


def input_modalities_of(item):
    """Lowercased input-modality tokens, or None when the catalog is silent."""
    if not isinstance(item, dict):
        return None
    for key in ("input_modalities", "inputModalities", "input_modality"):
        parsed = _as_modality_list(item.get(key))
        if parsed is not None:
            return parsed
    arch = item.get("architecture")
    if isinstance(arch, dict):
        parsed = _as_modality_list(arch.get("input_modalities") or arch.get("inputModalities"))
        if parsed is not None:
            return parsed
        parsed = _split_modality_string(arch.get("modality") or arch.get("modalities") or "")
        if parsed is not None:
            return parsed
    parsed = _split_modality_string(item.get("modality") or item.get("modalities") or "")
    if parsed is not None:
        return parsed
    return None


def modalities_include_image(mods):
    for token in mods or []:
        low = str(token).strip().lower()
        if low in _IMAGE_MODALITY_TOKENS or "image" in low or "vision" in low:
            return True
    return False


def canonical_model_id(spec):
    """Strip duplicated provider prefixes without dropping OpenRouter author/slug."""
    mid = model_id_of(spec).lower().replace("models/", "").strip()
    if not mid:
        return ""
    provider = provider_of(spec)
    while provider and (mid == provider or mid.startswith(provider + "/")):
        rest = mid[len(provider) :].lstrip("/")
        if rest == mid:
            break
        mid = rest
    parts = [p for p in mid.split("/") if p]
    collapsed = []
    for part in parts:
        if collapsed and collapsed[-1] == part:
            continue
        collapsed.append(part)
    mid = "/".join(collapsed)
    if ":" in mid:
        mid = mid.split(":", 1)[0]
    return mid


def _slug(mid):
    if "/" in mid:
        return mid.rsplit("/", 1)[-1]
    return mid


def _is_router_alias(spec, mid=""):
    """OpenRouter `auto` (and the same id with extra provider prefixes) can see images."""
    mid = mid or canonical_model_id(spec)
    return _slug(mid) in _ROUTER_SLUGS or mid.endswith("/auto")


def _ids_for_match(spec):
    original = model_id_of(spec).lower().replace("models/", "")
    mid = canonical_model_id(spec)
    ids = [original, mid, _slug(mid), _slug(original)]
    out = []
    seen = set()
    for text in ids:
        text = (text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _known_text_only(spec):
    ids = _ids_for_match(spec)
    for text in ids:
        if text in _VISION_DENY_IDS:
            return True
        if "o1-mini" in text or "o3-mini" in text:
            return True
        for needle in _VISION_DENY_SUBSTR:
            if needle in text:
                return True
        if text.startswith("claude-2") or ("instant" in text and "claude" in text):
            return True
    return False


def model_supports_vision(spec):
    """True unless the model is known text-only.

    Computer-use grant fails open: unknown IDs (including OpenRouter `auto`
    and author/slug models like `inception/mercury-2.5`) are allowed. Provider
    `architecture.modality` / `input_modalities` wins when present. Router
    aliases are never blocked solely because the id is `auto`.
    """
    mid = canonical_model_id(spec)
    if not mid and not model_id_of(spec):
        return False
    if _is_router_alias(spec, mid):
        return True
    mods = input_modalities_of(spec) if isinstance(spec, dict) else None
    if mods is not None:
        return modalities_include_image(mods)
    if _known_text_only(spec):
        return False
    return True


def display_model_id(spec):
    mid = canonical_model_id(spec) or model_id_of(spec)
    provider = provider_of(spec)
    if not mid:
        return provider or "(none)"
    if provider and mid != provider and not mid.startswith(provider + "/"):
        return "%s/%s" % (provider, mid)
    return mid


def normalize_computer_use_override(override):
    """Empty / unset override => None (use the chat model)."""
    if override is None or override == "":
        return None
    if isinstance(override, str):
        text = override.strip()
        if not text:
            return None
        return {"model": text, "name": text}
    if isinstance(override, dict):
        if not model_id_of(override):
            return None
        return dict(override)
    return None


def resolve_computer_use_model(chat_model, override):
    """CU model: non-empty override wins, else the current chat/Spotlight spec."""
    if isinstance(chat_model, dict):
        chat = dict(chat_model)
    elif chat_model:
        text = str(chat_model).strip()
        chat = {"model": text, "name": text} if text else {}
    else:
        chat = {}
    spec = normalize_computer_use_override(override)
    return spec if spec is not None else chat


def apply_computer_use_model(ctx):
    """Point ctx.model at the resolved CU spec; snapshot the chat model once."""
    chat = getattr(ctx, "_chat_model", None)
    if not isinstance(chat, dict) or not chat:
        ctx._chat_model = dict(getattr(ctx, "model", None) or {})
        chat = ctx._chat_model
    spec = resolve_computer_use_model(chat, getattr(ctx, "computer_use_model", None))
    ctx.model = dict(spec)
    return spec


def restore_chat_model(ctx):
    """Undo apply_computer_use_model so chat keeps its selected model."""
    chat = getattr(ctx, "_chat_model", None)
    if isinstance(chat, dict) and chat:
        ctx.model = dict(chat)
    ctx._chat_model = {}
    return getattr(ctx, "model", None)


def vision_unsupported_message(spec):
    mid = display_model_id(spec)
    return (
        "Computer use requires a vision-capable model so it can read screenshots. "
        "The current model (%s) does not support images. Pick a vision-capable "
        "computer-use model in Settings (or the Spotlight model if no override is "
        "set) and try again — computer use will not switch models. "
        "Computer use has been ended." % mid
    )
