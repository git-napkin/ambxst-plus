"""Gemini streamGenerateContent SSE."""

from __future__ import annotations

import json
import urllib.parse

from .base import Provider, iter_lines, post_request


def _contents(messages):
    contents = []
    system = ""
    for msg in messages or []:
        role = msg.get("role") or "user"
        if role == "system":
            system = msg.get("content") or system
            continue
        if role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append({"text": msg["content"]})
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or tc
                args = fn.get("arguments") or tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                fc = {"functionCall": {"name": fn.get("name") or tc.get("name"), "args": args}}
                # gemini-2.5-flash thinking models require the signature on the
                # next turn; thought text itself is dropped (not streamed).
                sig = tc.get("thought_signature") or tc.get("thoughtSignature")
                if sig:
                    fc["thoughtSignature"] = sig
                parts.append(fc)
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
            continue
        if role in ("tool", "function"):
            parts = [
                {
                    "functionResponse": {
                        "name": msg.get("name") or "",
                        "response": {"content": msg.get("content") or ""},
                    }
                }
            ]
            contents.append({"role": "function", "parts": parts})
            # Screenshots as a follow-up user turn (OpenAI-shaped). inline_data
            # on the function role is dropped by some Gemini tool+image paths.
            image_parts = []
            for att in msg.get("attachments") or []:
                if att.get("type") == "image" and att.get("base64"):
                    image_parts.append(
                        {
                            "inline_data": {
                                "mime_type": att.get("mimeType") or att.get("mime_type") or "image/png",
                                "data": att["base64"],
                            }
                        }
                    )
            if image_parts:
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": "Screenshot from %s" % (msg.get("name") or "tool")}] + image_parts,
                    }
                )
            continue
        parts = [{"text": msg.get("content") or ""}]
        for att in msg.get("attachments") or []:
            if att.get("type") == "image" and att.get("base64"):
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": att.get("mimeType") or att.get("mime_type") or "image/png",
                            "data": att["base64"],
                        }
                    }
                )
        contents.append({"role": "user", "parts": parts})
    return system, contents


def _gemini_tools(tools):
    decls = []
    for tool in tools or []:
        decls.append(
            {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    if not decls:
        return None
    return [{"functionDeclarations": decls}]


class GeminiProvider(Provider):
    name = "gemini"

    def stream_chat(self, messages, tools, temperature, max_tokens, model, api_key, endpoint=""):
        spec = model if isinstance(model, dict) else {"model": str(model)}
        model_id = spec.get("model") or spec.get("name") or ""
        base = (endpoint or spec.get("endpoint") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        query = urllib.parse.urlencode({"alt": "sse", "key": api_key or ""})
        url = "%s/models/%s:streamGenerateContent?%s" % (base, model_id, query)
        headers = {"Content-Type": "application/json"}
        system, contents = _contents(messages)
        body = {
            "contents": contents,
        }
        generation = {}
        if temperature is not None:
            generation["temperature"] = temperature
        if max_tokens is not None:
            generation["maxOutputTokens"] = max_tokens
        if generation:
            body["generationConfig"] = generation
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        gemini_tools = _gemini_tools(tools)
        if gemini_tools:
            body["tools"] = gemini_tools
        try:
            response = post_request(url, headers, body)
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return
        try:
            with response:
                call_n = 0
                for line in iter_lines(response):
                    trimmed = line.strip()
                    if trimmed.startswith("data:"):
                        trimmed = trimmed[5:].strip()
                    if not trimmed:
                        continue
                    try:
                        chunk = json.loads(trimmed)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        err = chunk["error"]
                        yield {"type": "error", "error": err.get("message") if isinstance(err, dict) else str(err)}
                        return
                    for cand in chunk.get("candidates") or []:
                        parts = ((cand.get("content") or {}).get("parts")) or []
                        for part in parts:
                            # Drop thought text; keep thoughtSignature on the functionCall.
                            if part.get("thought") and not part.get("functionCall"):
                                continue
                            if part.get("text") and not part.get("thought"):
                                yield {"type": "token", "text": part["text"]}
                            fc = part.get("functionCall")
                            if fc:
                                call_n += 1
                                name = fc.get("name") or "gemini_tool"
                                event = {
                                    "type": "tool_call",
                                    "id": "%s#%d" % (name, call_n),
                                    "name": name,
                                    "args": fc.get("args") or {},
                                }
                                sig = part.get("thoughtSignature") or part.get("thought_signature")
                                if sig:
                                    event["thought_signature"] = sig
                                yield event
        finally:
            try:
                response.close()
            except Exception:
                pass
