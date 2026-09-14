"""Ollama /api/chat NDJSON streaming."""

from __future__ import annotations

import json

from .base import Provider, iter_lines, openai_tools, post_request


class OllamaProvider(Provider):
    name = "ollama"

    def stream_chat(self, messages, tools, temperature, max_tokens, model, api_key, endpoint=""):
        spec = model if isinstance(model, dict) else {"model": str(model)}
        model_id = spec.get("model") or spec.get("name") or ""
        base = (endpoint or spec.get("endpoint") or "http://127.0.0.1:11434").rstrip("/")
        url = base if base.endswith("/api/chat") else base + "/api/chat"
        headers = {"Content-Type": "application/json"}
        body = {
            "model": model_id,
            "messages": [
                {"role": m.get("role") or "user", "content": m.get("content") or ""}
                for m in (messages or [])
            ],
            "stream": True,
        }
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            body["options"] = options
        formatted = openai_tools(tools)
        if formatted:
            body["tools"] = formatted
        try:
            response = post_request(url, headers, body)
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return
        try:
            with response:
                for line in iter_lines(response):
                    trimmed = line.strip()
                    if not trimmed:
                        continue
                    try:
                        chunk = json.loads(trimmed)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        yield {"type": "error", "error": str(chunk["error"])}
                        return
                    message = chunk.get("message") or {}
                    text = message.get("content")
                    if text:
                        yield {"type": "token", "text": text}
                    for tc in message.get("tool_calls") or []:
                        fn = tc.get("function") or tc
                        args = fn.get("arguments") or tc.get("args") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"_raw": args}
                        yield {
                            "type": "tool_call",
                            "id": tc.get("id") or fn.get("name") or "ollama_tool",
                            "name": fn.get("name") or "",
                            "args": args,
                        }
                    if chunk.get("done"):
                        return
        finally:
            try:
                response.close()
            except Exception:
                pass
