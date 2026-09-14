"""List provider models over HTTPS using KeyStore keys (never curl argv)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

OPENAI_COMPAT = {
    "openai": ("https://api.openai.com/v1/models", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "o1", "o3", "o4"]),
    "groq": ("https://api.groq.com/openai/v1/models", None),
    "mistral": ("https://api.mistral.ai/v1/models", None),
}


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _openai_style(provider, url, key, allow_prefixes=None):
    data = _get(url, {"Authorization": "Bearer %s" % key})
    out = []
    for item in data.get("data") or []:
        mid = item.get("id") or ""
        if allow_prefixes and not any(mid == p or mid.startswith(p + "-") for p in allow_prefixes):
            continue
        out.append(
            {
                "name": mid,
                "model": mid,
                "provider": provider,
                "endpoint": url.replace("/models", ""),
                "description": provider,
                "requires_key": True,
                "key_id": provider,
            }
        )
    return out


def list_models(ctx, custom_endpoint=""):
    models = []
    get_key = ctx.get_key
    gemini = get_key("gemini")
    if gemini:
        try:
            data = _get("https://generativelanguage.googleapis.com/v1beta/models?key=%s" % gemini)
            for item in data.get("models") or []:
                mid = (item.get("name") or "").replace("models/", "")
                if "gemini" in mid or "flash" in mid or "pro" in mid:
                    models.append(
                        {
                            "name": item.get("displayName") or mid,
                            "model": mid,
                            "provider": "gemini",
                            "endpoint": "https://generativelanguage.googleapis.com/v1beta",
                            "description": item.get("description") or "Google Gemini",
                            "requires_key": True,
                            "key_id": "gemini",
                        }
                    )
        except (urllib.error.URLError, ValueError, TimeoutError):
            pass
    for provider, (url, prefixes) in OPENAI_COMPAT.items():
        key = get_key(provider)
        if not key:
            continue
        try:
            models.extend(_openai_style(provider, url, key, prefixes))
        except (urllib.error.URLError, ValueError, TimeoutError):
            pass
    anthropic = get_key("anthropic")
    if anthropic:
        try:
            data = _get(
                "https://api.anthropic.com/v1/models",
                {"x-api-key": anthropic, "anthropic-version": "2023-06-01"},
            )
            for item in data.get("data") or []:
                mid = item.get("id") or ""
                models.append(
                    {
                        "name": item.get("display_name") or mid,
                        "model": mid,
                        "provider": "anthropic",
                        "endpoint": "https://api.anthropic.com",
                        "description": "Anthropic",
                        "requires_key": True,
                        "key_id": "anthropic",
                    }
                )
        except (urllib.error.URLError, ValueError, TimeoutError):
            pass
    if get_key("ollama"):
        try:
            data = _get("http://127.0.0.1:11434/api/tags")
            for item in data.get("models") or []:
                mid = item.get("name") or ""
                models.append(
                    {
                        "name": mid,
                        "model": mid,
                        "provider": "ollama",
                        "endpoint": "http://127.0.0.1:11434",
                        "description": "Ollama",
                        "requires_key": False,
                        "key_id": "ollama",
                    }
                )
        except (urllib.error.URLError, ValueError, TimeoutError):
            pass
    if get_key("minimax"):
        models.append(
            {
                "name": "MiniMax-M2.5",
                "model": "MiniMax-M2.5",
                "provider": "minimax",
                "endpoint": "https://api.minimax.io/v1",
                "description": "MiniMax",
                "requires_key": True,
                "key_id": "minimax",
            }
        )
    if get_key("custom") and custom_endpoint:
        models.append(
            {
                "name": "Custom",
                "model": "custom",
                "provider": "custom",
                "endpoint": custom_endpoint,
                "description": "Custom endpoint",
                "requires_key": True,
                "key_id": "custom",
            }
        )
    return models
