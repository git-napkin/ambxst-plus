"""Anthropic messages API streaming."""

from __future__ import annotations

import json

from .base import Provider, iter_lines, post_request


def _filter_messages(messages):
    filtered = []
    system = ""
    for msg in messages or []:
        role = msg.get("role") or "user"
        if role == "system":
            system = msg.get("content") or system
            continue
        if role == "tool":
            filtered.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id") or "",
                            "content": msg.get("content") or "",
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or tc
                args = fn.get("arguments") or tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_raw": args}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id") or "",
                        "name": fn.get("name") or tc.get("name") or "",
                        "input": args,
                    }
                )
            filtered.append({"role": "assistant", "content": blocks})
            continue
        filtered.append({"role": "user" if role == "function" else role, "content": msg.get("content") or ""})
    return system, filtered


def _anthropic_tools(tools):
    out = []
    for tool in tools or []:
        out.append(
            {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "input_schema": tool.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


class AnthropicProvider(Provider):
    name = "anthropic"

    def stream_chat(self, messages, tools, temperature, max_tokens, model, api_key, endpoint=""):
        spec = model if isinstance(model, dict) else {"model": str(model)}
        model_id = spec.get("model") or spec.get("name") or ""
        url = (endpoint or spec.get("endpoint") or "https://api.anthropic.com/v1/messages").rstrip("/")
        if not url.endswith("/messages"):
            if url.endswith("/v1"):
                url = url + "/messages"
            else:
                url = url + "/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
        system, filtered = _filter_messages(messages)
        body = {
            "model": model_id,
            "messages": filtered,
            "max_tokens": max_tokens if max_tokens is not None else 8192,
            "stream": True,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if system:
            body["system"] = system
        formatted = _anthropic_tools(tools)
        if formatted:
            body["tools"] = formatted
        try:
            response = post_request(url, headers, body)
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return
        current = None
        try:
            with response:
                for line in iter_lines(response):
                    trimmed = line.strip()
                    if not trimmed.startswith("data:"):
                        continue
                    payload = trimmed[5:].strip()
                    if not payload:
                        continue
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    kind = event.get("type")
                    if kind == "content_block_start":
                        block = event.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            current = {
                                "id": block.get("id") or "",
                                "name": block.get("name") or "",
                                "arguments": "",
                            }
                    elif kind == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield {"type": "token", "text": delta["text"]}
                        elif delta.get("type") == "input_json_delta" and current is not None:
                            current["arguments"] += delta.get("partial_json") or ""
                    elif kind == "content_block_stop":
                        if current is not None:
                            try:
                                args = json.loads(current["arguments"] or "{}")
                            except json.JSONDecodeError:
                                args = {"_raw": current["arguments"]}
                            yield {
                                "type": "tool_call",
                                "id": current["id"],
                                "name": current["name"],
                                "args": args,
                            }
                            current = None
                    elif kind == "error":
                        err = event.get("error") or {}
                        yield {"type": "error", "error": err.get("message") or str(err)}
                        return
        finally:
            try:
                response.close()
            except Exception:
                pass
