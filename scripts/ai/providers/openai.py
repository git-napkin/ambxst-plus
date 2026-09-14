"""OpenAI-compatible chat completions (OpenAI, OpenRouter, Groq, Mistral, MiniMax, custom)."""

from __future__ import annotations

import json

from .base import Provider, chat_completions_url, iter_lines, normalize_openai_base, openai_tools, post_request

DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "minimax": "https://api.minimax.io",
    "custom": "",
}


def _format_messages(messages):
    formatted = []
    for msg in messages or []:
        role = msg.get("role") or "user"
        if role == "tool":
            formatted.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id") or "",
                    "content": msg.get("content") or "",
                    "name": msg.get("name") or "",
                }
            )
            attachments = msg.get("attachments") or []
            if attachments:
                parts = [{"type": "text", "text": "Screenshot from %s" % (msg.get("name") or "tool")}]
                for att in attachments:
                    if att.get("type") == "image" and att.get("base64"):
                        mime = att.get("mimeType") or att.get("mime_type") or "image/png"
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:%s;base64,%s" % (mime, att["base64"])},
                            }
                        )
                formatted.append({"role": "user", "content": parts})
            continue
        attachments = msg.get("attachments") or []
        if attachments:
            parts = [{"type": "text", "text": msg.get("content") or ""}]
            for att in attachments:
                if att.get("type") == "image" and att.get("base64"):
                    mime = att.get("mimeType") or att.get("mime_type") or "image/png"
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:%s;base64,%s" % (mime, att["base64"])
                            },
                        }
                    )
            formatted.append({"role": role, "content": parts})
            continue
        item = {"role": role, "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            item["tool_calls"] = msg["tool_calls"]
        formatted.append(item)
    return formatted


class OpenAIProvider(Provider):
    name = "openai"

    def stream_chat(self, messages, tools, temperature, max_tokens, model, api_key, endpoint=""):
        spec = model if isinstance(model, dict) else {"model": str(model)}
        provider = (spec.get("provider") or "openai").lower()
        model_id = spec.get("model") or spec.get("name") or ""
        base = endpoint or spec.get("endpoint") or DEFAULT_ENDPOINTS.get(provider) or "https://api.openai.com"
        base = normalize_openai_base(base)
        url = chat_completions_url(base)
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % (api_key or ""),
        }
        body = {
            "model": model_id,
            "messages": _format_messages(messages),
            "stream": True,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        formatted_tools = openai_tools(tools)
        if formatted_tools:
            body["tools"] = formatted_tools
        try:
            response = post_request(url, headers, body)
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return
        pending = {}
        try:
            with response:
                for line in iter_lines(response):
                    trimmed = line.strip()
                    if not trimmed or trimmed.startswith("event:"):
                        continue
                    if trimmed.startswith("data:"):
                        trimmed = trimmed[5:].strip()
                    if trimmed == "[DONE]":
                        break
                    try:
                        chunk = json.loads(trimmed)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        err = chunk["error"]
                        yield {"type": "error", "error": err.get("message") if isinstance(err, dict) else str(err)}
                        return
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield {"type": "token", "text": text}
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        slot = pending.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]
        finally:
            try:
                response.close()
            except Exception:
                pass
        for idx in sorted(pending):
            slot = pending[idx]
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw": slot["arguments"]}
            yield {
                "type": "tool_call",
                "id": slot["id"] or "call_%s" % idx,
                "name": slot["name"],
                "args": args,
            }
