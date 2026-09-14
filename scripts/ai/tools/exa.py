"""Exa search/contents over urllib. Injectable opener for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .registry import Tool
from .friendly import labels, path_tick, tick
from ..execution_profile import ALWAYS_ASK

EXA_SEARCH_URL = "https://api.exa.ai/search"
EXA_CONTENTS_URL = "https://api.exa.ai/contents"


def _opener(ctx):
    return ctx.http_opener or urllib.request.urlopen


def post_json(url, payload, headers, opener, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with opener(request, timeout=timeout) as resp:
        raw = resp.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = str(raw)
    return json.loads(text) if text else {}


def _headers(api_key):
    return {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "Accept": "application/json",
    }


def _enabled(ctx):
    if not ctx.profile.web_search_enabled:
        return False, "web search disabled"
    key = ctx.get_key("exa")
    if not key:
        return False, "no Exa API key"
    return True, key


def shape_search_body(args):
    query = (args or {}).get("query") or (args or {}).get("q") or ""
    num = (args or {}).get("num_results") or (args or {}).get("numResults") or 8
    body = {
        "query": query,
        "numResults": int(num),
        "type": (args or {}).get("type") or "auto",
        "contents": {"text": False, "highlights": True},
    }
    if (args or {}).get("include_domains"):
        body["includeDomains"] = list(args["include_domains"])
    return body


def shape_contents_body(args):
    ids = (args or {}).get("ids") or (args or {}).get("urls") or []
    if isinstance(ids, str):
        ids = [ids]
    return {
        "ids": list(ids),
        "text": {"maxCharacters": int((args or {}).get("max_characters") or 8000)},
    }


class ExaSearchTool(Tool):
    name = "exa_search"
    user_friendly_name = "Web search"
    schema = {
        "description": "Search the web with Exa. Returns titles, urls, and highlights.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    }

    def should_autoexecute(self, ctx, args):
        ok, _reason = _enabled(ctx)
        if not ok:
            return "deny"
        if ctx.profile.read_files == ALWAYS_ASK:
            return "ask"
        return True

    def user_friendly_name_for(self, args):
        return labels("Searching", "Searched", ask="Search the web")

    def execute(self, ctx, args):
        ok, info = _enabled(ctx)
        if not ok:
            return {"status": "error", "error": info}
        body = shape_search_body(args)
        try:
            data = post_json(
                EXA_SEARCH_URL,
                body,
                _headers(info),
                _opener(ctx),
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
            return {"status": "error", "error": str(exc)}
        results = []
        for item in data.get("results") or []:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url") or item.get("id"),
                    "highlights": item.get("highlights") or [],
                    "published_date": item.get("publishedDate"),
                }
            )
        return {"status": "ok", "results": results, "request": body}


class ExaContentsTool(Tool):
    name = "exa_contents"
    user_friendly_name = "Fetch page"
    schema = {
        "description": "Fetch page text for Exa result ids/urls.",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["ids"],
        },
    }

    def should_autoexecute(self, ctx, args):
        ok, _reason = _enabled(ctx)
        if not ok:
            return "deny"
        if ctx.profile.read_files == ALWAYS_ASK:
            return "ask"
        return True

    def user_friendly_name_for(self, args):
        ids = (args or {}).get("ids") or (args or {}).get("urls") or []
        if isinstance(ids, str):
            ids = [ids]
        if len(ids) == 1:
            label = path_tick(ids[0]) or tick(ids[0])
            if label:
                return labels(
                    "Fetching %s" % label,
                    "Fetched %s" % label,
                    ask="Fetch %s" % label,
                )
        if len(ids) > 1:
            n = len(ids)
            return labels(
                "Fetching %d pages" % n,
                "Fetched %d pages" % n,
                ask="Fetch %d pages" % n,
            )
        return labels("Fetching page", "Fetched page", ask="Fetch page")

    def execute(self, ctx, args):
        ok, info = _enabled(ctx)
        if not ok:
            return {"status": "error", "error": info}
        body = shape_contents_body(args)
        try:
            data = post_json(
                EXA_CONTENTS_URL,
                body,
                _headers(info),
                _opener(ctx),
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
            return {"status": "error", "error": str(exc)}
        pages = []
        for item in data.get("results") or []:
            text = item.get("text") or ""
            pages.append(
                {
                    "url": item.get("url") or item.get("id"),
                    "title": item.get("title"),
                    "text": text,
                }
            )
        return {"status": "ok", "results": pages, "request": body}
