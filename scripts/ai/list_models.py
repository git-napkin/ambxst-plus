"""List provider models over HTTPS using KeyStore keys (never curl argv)."""

from __future__ import annotations

import urllib.error
import urllib.request

from .providers.base import models_url, normalize_openai_base
from .providers.openai import DEFAULT_ENDPOINTS

OPENAI_COMPAT = {
    "openai": None,  # list everything from /v1/models
    "openrouter": None,
}


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json_loads(resp.read().decode("utf-8"))


def json_loads(text):
    import json

    return json.loads(text)


def _key_entries(ctx, provider):
    if hasattr(ctx, "list_keys"):
        entries = ctx.list_keys(provider) or []
        if entries:
            return entries
    key = ctx.get_key(provider)
    if key:
        return [{"id": None, "label": "", "api_key": key}]
    return []


def _key_id(provider, entry):
    eid = entry.get("id")
    if eid is None:
        return provider
    return "%s#%s" % (provider, eid)


def _named(label, entry, index, total):
    text = (label or "").strip()
    key_label = (entry.get("label") or "").strip()
    if key_label:
        return "%s · %s" % (text, key_label) if text else key_label
    if total > 1 and text:
        return "%s · %s" % (text, index + 1)
    return text


def _humanize_model_id(mid):
    text = str(mid or "").strip().lstrip("~")
    if not text:
        return ""
    if "/" in text:
        text = text.split("/", 1)[1]
    if ":" in text:
        text = text.split(":", 1)[0]
    parts = []
    for raw in text.replace("_", "-").split("-"):
        if not raw:
            continue
        lower = raw.lower()
        if lower.startswith("gpt") and len(lower) > 3 and lower[3].isdigit():
            parts.append("GPT-" + raw[3:])
        elif lower == "gpt":
            parts.append("GPT")
        elif lower in ("o1", "o3", "o4"):
            parts.append(lower)
        elif lower.isalpha() and len(lower) <= 3:
            parts.append(raw.upper())
        else:
            parts.append(raw[:1].upper() + raw[1:])
    return " ".join(parts) or str(mid)


def _display_name(item, mid):
    for key in ("name", "display_name", "displayName", "title"):
        value = item.get(key) if isinstance(item, dict) else None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned and cleaned != mid:
                return cleaned
    return _humanize_model_id(mid) or mid


def _openai_style(provider, url, key, allow_prefixes=None, key_id=None, name_fn=None, endpoint=""):
    data = _get(url, {"Authorization": "Bearer %s" % key})
    out = []
    root = endpoint or normalize_openai_base(url.replace("/models", ""), default="")
    for item in data.get("data") or []:
        mid = item.get("id") or ""
        if not mid:
            continue
        if allow_prefixes and not any(mid == p or mid.startswith(p + "-") for p in allow_prefixes):
            continue
        display = _display_name(item, mid)
        out.append(
            {
                "name": name_fn(display) if name_fn else display,
                "model": mid,
                "provider": provider,
                "endpoint": root,
                "description": (item.get("description") or provider),
                "requires_key": True,
                "key_id": key_id or provider,
            }
        )
    return out


PROVIDER_ENDPOINTS = {
    "openai": DEFAULT_ENDPOINTS.get("openai") or "https://api.openai.com",
    "openrouter": DEFAULT_ENDPOINTS.get("openrouter") or "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "ollama": "http://127.0.0.1:11434",
}


def _catalog_ignored(ignore_catalog, provider):
    if not ignore_catalog:
        return False
    value = ignore_catalog.get(provider)
    if value is None:
        value = ignore_catalog.get(str(provider).lower())
    return bool(value)


def _manual_items(manual_models, provider):
    if not manual_models:
        return []
    items = manual_models.get(provider)
    if items is None:
        items = manual_models.get(str(provider).lower())
    return items if isinstance(items, list) else []


def _append_manuals(models, provider, items, endpoint, custom_name=""):
    out = list(models)
    for item in items or []:
        if not isinstance(item, dict):
            continue
        mid = (item.get("model") or item.get("id") or "").strip()
        if not mid:
            continue
        display = (item.get("name") or item.get("display_name") or custom_name or "").strip()
        if not display:
            display = _humanize_model_id(mid) or mid
        out = [m for m in out if not (m.get("provider") == provider and m.get("model") == mid)]
        out.append(
            {
                "name": display,
                "model": mid,
                "provider": provider,
                "endpoint": endpoint,
                "description": display,
                "requires_key": provider != "ollama",
                "key_id": provider,
            }
        )
    return out


def list_models(ctx, custom_endpoint="", custom_models=None, custom_name="", ignore_catalog=None, manual_models=None):
    models = []
    ignore_catalog = ignore_catalog if ignore_catalog is not None else getattr(ctx, "ignore_catalog", None) or {}
    manual_models = manual_models if manual_models is not None else getattr(ctx, "manual_models", None) or {}
    if not _catalog_ignored(ignore_catalog, "gemini"):
        gemini_entries = _key_entries(ctx, "gemini")
        for i, entry in enumerate(gemini_entries):
            gemini = entry.get("api_key") or ""
            if not gemini:
                continue
            try:
                data = _get("https://generativelanguage.googleapis.com/v1beta/models?key=%s" % gemini)
                for item in data.get("models") or []:
                    mid = (item.get("name") or "").replace("models/", "")
                    if "gemini" in mid or "flash" in mid or "pro" in mid:
                        display = item.get("displayName") or mid
                        models.append(
                            {
                                "name": _named(display, entry, i, len(gemini_entries)),
                                "model": mid,
                                "provider": "gemini",
                                "endpoint": PROVIDER_ENDPOINTS["gemini"],
                                "description": item.get("description") or "Google Gemini",
                                "requires_key": True,
                                "key_id": _key_id("gemini", entry),
                            }
                        )
            except (urllib.error.URLError, ValueError, TimeoutError):
                pass
    for provider, prefixes in OPENAI_COMPAT.items():
        if _catalog_ignored(ignore_catalog, provider):
            continue
        entries = _key_entries(ctx, provider)
        total = len(entries)
        base = DEFAULT_ENDPOINTS.get(provider) or ""
        url = models_url(base)
        if not url:
            continue
        for i, entry in enumerate(entries):
            key = entry.get("api_key") or ""
            if not key:
                continue
            try:
                models.extend(
                    _openai_style(
                        provider,
                        url,
                        key,
                        prefixes,
                        key_id=_key_id(provider, entry),
                        name_fn=lambda display, e=entry, idx=i, n=total: _named(display, e, idx, n),
                        endpoint=normalize_openai_base(base),
                    )
                )
            except (urllib.error.URLError, ValueError, TimeoutError):
                pass
    if not _catalog_ignored(ignore_catalog, "anthropic"):
        anthropic_entries = _key_entries(ctx, "anthropic")
        for i, entry in enumerate(anthropic_entries):
            anthropic = entry.get("api_key") or ""
            if not anthropic:
                continue
            try:
                data = _get(
                    "https://api.anthropic.com/v1/models",
                    {"x-api-key": anthropic, "anthropic-version": "2023-06-01"},
                )
                for item in data.get("data") or []:
                    mid = item.get("id") or ""
                    display = _display_name(item, mid)
                    models.append(
                        {
                            "name": _named(display, entry, i, len(anthropic_entries)),
                            "model": mid,
                            "provider": "anthropic",
                            "endpoint": PROVIDER_ENDPOINTS["anthropic"],
                            "description": item.get("description") or "Anthropic",
                            "requires_key": True,
                            "key_id": _key_id("anthropic", entry),
                        }
                    )
            except (urllib.error.URLError, ValueError, TimeoutError):
                pass
    if not _catalog_ignored(ignore_catalog, "ollama") and _key_entries(ctx, "ollama"):
        try:
            data = _get("http://127.0.0.1:11434/api/tags")
            for item in data.get("models") or []:
                mid = item.get("name") or ""
                models.append(
                    {
                        "name": _display_name(item, mid),
                        "model": mid,
                        "provider": "ollama",
                        "endpoint": PROVIDER_ENDPOINTS["ollama"],
                        "description": "Ollama",
                        "requires_key": False,
                        "key_id": "ollama",
                    }
                )
        except (urllib.error.URLError, ValueError, TimeoutError):
            pass
    custom_entries = _key_entries(ctx, "custom")
    custom_base = normalize_openai_base(custom_endpoint, default="")
    custom_models_url = models_url(custom_base) if custom_base else ""
    if custom_entries and custom_base and not _catalog_ignored(ignore_catalog, "custom"):
        total = len(custom_entries)
        listed = False
        for i, entry in enumerate(custom_entries):
            key = entry.get("api_key") or ""
            if not key:
                continue
            if custom_models_url:
                try:
                    models.extend(
                        _openai_style(
                            "custom",
                            custom_models_url,
                            key,
                            None,
                            key_id=_key_id("custom", entry),
                            name_fn=lambda display, e=entry, idx=i, n=total: _named(display, e, idx, n),
                            endpoint=custom_base,
                        )
                    )
                    listed = True
                    continue
                except (urllib.error.URLError, ValueError, TimeoutError):
                    pass
            models.append(
                {
                    "name": _named("Custom", entry, i, total),
                    "model": "custom",
                    "provider": "custom",
                    "endpoint": custom_base,
                    "description": "Custom endpoint",
                    "requires_key": True,
                    "key_id": _key_id("custom", entry),
                }
            )
            listed = True
        if not listed:
            pass
    custom_endpoint_resolved = custom_base if custom_base else normalize_openai_base(custom_endpoint, default="")
    for provider, endpoint in PROVIDER_ENDPOINTS.items():
        models = _append_manuals(
            models,
            provider,
            _manual_items(manual_models, provider),
            endpoint,
            custom_name if provider == "custom" else "",
        )
    models = _append_manuals(
        models,
        "custom",
        custom_models or getattr(ctx, "custom_models", None) or [],
        custom_endpoint_resolved,
        custom_name or getattr(ctx, "custom_name", "") or "",
    )
    models = _append_manuals(
        models,
        "custom",
        _manual_items(manual_models, "custom"),
        custom_endpoint_resolved,
        custom_name or getattr(ctx, "custom_name", "") or "",
    )
    return models
