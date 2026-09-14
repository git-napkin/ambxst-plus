"""Shared HTTP streaming helpers for providers."""

from __future__ import annotations

import json
import urllib.request


class StreamDelta:
    def __init__(self, kind, text="", tool_call=None, error=None):
        self.kind = kind
        self.text = text
        self.tool_call = tool_call
        self.error = error

    def as_event(self):
        if self.kind == "token":
            return {"type": "token", "text": self.text}
        if self.kind == "tool_call":
            return {"type": "tool_call", **(self.tool_call or {})}
        if self.kind == "error":
            return {"type": "error", "error": self.error or "provider error"}
        return {"type": "done"}


class Provider:
    name = "base"

    def stream_chat(self, messages, tools, temperature, max_tokens, model, api_key, endpoint=""):
        raise NotImplementedError


def post_request(url, headers, body, timeout=120):
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    return urllib.request.urlopen(request, timeout=timeout)


def iter_lines(response):
    while True:
        line = response.readline()
        if not line:
            break
        if isinstance(line, bytes):
            yield line.decode("utf-8", errors="replace")
        else:
            yield line


def normalize_openai_base(base, default="https://api.openai.com"):
    """Accept host, /v1, or legacy /v1/chat/completions and return the API root."""
    text = (base or "").strip().rstrip("/")
    if not text:
        return default or ""
    if text.endswith("/chat/completions"):
        text = text[: -len("/chat/completions")].rstrip("/")
    if text.endswith("/models"):
        text = text[: -len("/models")].rstrip("/")
    return text


def chat_completions_url(base):
    root = normalize_openai_base(base)
    if not root:
        root = "https://api.openai.com"
    if root.endswith("/v1"):
        return root + "/chat/completions"
    return root + "/v1/chat/completions"


def models_url(base):
    root = normalize_openai_base(base, default="")
    if not root:
        return ""
    if root.endswith("/v1"):
        return root + "/models"
    return root + "/v1/models"


def openai_tools(tools):
    formatted = []
    for tool in tools or []:
        formatted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return formatted


def normalize_messages(messages):
    out = []
    for msg in messages or []:
        role = msg.get("role") or "user"
        item = {"role": role, "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            item["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            item["tool_call_id"] = msg["tool_call_id"]
        if msg.get("name"):
            item["name"] = msg["name"]
        if msg.get("attachments"):
            item["attachments"] = msg["attachments"]
        out.append(item)
    return out
