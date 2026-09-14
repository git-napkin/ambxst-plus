"""Human-readable tool call labels for the transcript UI."""

from __future__ import annotations

import os
import shlex


def tick(text, limit=40):
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "`%s`" % text


def command_tick(command, limit=40):
    text = " ".join(str(command or "").split())
    if not text:
        return ""
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    if not parts:
        return tick(text, limit)
    bits = [os.path.basename(parts[0]) or parts[0]]
    for part in parts[1:]:
        candidate = " ".join(bits + [part])
        if len(candidate) > limit:
            bits.append("…")
            break
        bits.append(part)
    return tick(" ".join(bits), limit)


def path_tick(path, limit=40):
    raw = str(path or "").rstrip("/")
    if not raw:
        return ""
    base = os.path.basename(raw) or raw
    return tick(base, limit)


def labels(running, done, ask=None):
    return {
        "running": running,
        "done": done,
        "ask": ask if ask is not None else done,
    }
