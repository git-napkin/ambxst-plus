"""Bounded Jev judgments: intent, window selection, and computer-use safety.

Code owns routing, candidates, and permissions. Jev only returns typed answers
over minimized state. Shadow mode records privacy-safe diagnostics without
changing dispatch. Active mode may take a high-confidence native shortcut.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass

from . import jev
from .protocol import NATIVE_READ_TOOLS

LOGGER = logging.getLogger("ambxst.jev")

MODE_OFF = "off"
MODE_SHADOW = "shadow"
MODE_ACTIVE = "active"
MODES = (MODE_OFF, MODE_SHADOW, MODE_ACTIVE)

INTENT_NATIVE_READ = "native_read"
INTENT_NATIVE_WRITE = "native_write"
INTENT_FOCUS_WINDOW = "focus_window"
INTENT_CONVERSATION = "conversation"
INTENT_CLARIFY = "clarify"
INTENT_LABELS = (
    INTENT_NATIVE_READ,
    INTENT_NATIVE_WRITE,
    INTENT_FOCUS_WINDOW,
    INTENT_CONVERSATION,
    INTENT_CLARIFY,
)

WINDOW_NONE = "none"
WRITE_NONE = "none"
READ_NONE = "none"

WRITE_CLOSED = (
    "toggle_mute",
    "toggle_night_light",
    "lock",
    "screenshot",
    "set_volume",
    "set_brightness",
)

ROUTINE_CU_ACTIONS = frozenset(
    {
        "screenshot",
        "snapshot",
        "focus",
        "scroll",
        "type",
        "move",
        "wait",
        "cursor",
        "move_window",
        "resize_window",
    }
)

SAFETY_ACTIONS = frozenset({"click", "key", "drag", "perform_action", "set_value"})

NOUL_POSITIVE = 0.6
NOUL_NEGATIVE = 0.4
MULTI_INTENT_GAP = 0.12
MAX_WINDOW_CANDIDATES = 16
DIAGNOSTIC_CAP = 80

DESKTOP_CONTEXT_MARK = "\n\n[Desktop context]\n"

_COUNTERS = defaultdict(int)
_DIAGNOSTICS = []

_PERCENT_RE = re.compile(r"(?i)(?<![0-9.])(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|pct)\b")
_BARE_INT_RE = re.compile(r"(?i)(?<![0-9.])(\d{1,3})(?![0-9.])")
_DECIMAL_RE = re.compile(r"(?<![0-9])\d+\.\d+")
_LEVEL_NEAR = r"(?:volume|brightness|audio|sound|backlight)"
_FOCUSED_RE = re.compile(r"(?im)^Focused window:\s*(.+)$")
_WINDOW_SKIP_TOKENS = frozenset(
    {
        "the",
        "and",
        "for",
        "app",
        "window",
        "windows",
        "please",
        "focus",
        "switch",
        "open",
        "show",
        "bring",
        "raise",
        "activate",
        "goto",
        "into",
        "that",
        "this",
        "with",
        "from",
        "onto",
        "desktop",
        "workspace",
        "move",
        "give",
        "put",
    }
)


@dataclass
class JevConfig:
    mode: str = MODE_OFF
    timeout_ms: int = 1500
    confidence_threshold: float = 0.75
    max_retries: int = 1

    @property
    def timeout_s(self):
        return max(0.25, float(self.timeout_ms) / 1000.0)

    @property
    def enabled(self):
        return self.mode in (MODE_SHADOW, MODE_ACTIVE)

    @property
    def active(self):
        return self.mode == MODE_ACTIVE


def _pick(raw, *names, default=None):
    if not isinstance(raw, dict):
        return default
    for name in names:
        if name in raw and raw[name] is not None:
            return raw[name]
    return default


def parse_config(raw):
    raw = raw or {}
    if not isinstance(raw, dict):
        raw = {}
    mode = str(_pick(raw, "mode", default=MODE_OFF) or MODE_OFF).strip().lower()
    if mode not in MODES:
        mode = MODE_OFF
    try:
        timeout_ms = int(_pick(raw, "timeoutMs", "timeout_ms", default=1500))
    except (TypeError, ValueError):
        timeout_ms = 1500
    timeout_ms = max(250, min(10000, timeout_ms))
    try:
        threshold = float(
            _pick(raw, "confidenceThreshold", "confidence_threshold", default=0.75)
        )
    except (TypeError, ValueError):
        threshold = 0.75
    threshold = max(0.0, min(1.0, threshold))
    try:
        retries = int(_pick(raw, "maxRetries", "max_retries", default=1))
    except (TypeError, ValueError):
        retries = 1
    retries = max(0, min(3, retries))
    return JevConfig(
        mode=mode,
        timeout_ms=timeout_ms,
        confidence_threshold=threshold,
        max_retries=retries,
    )


def config_from_ctx(ctx):
    cached = getattr(ctx, "jev_config", None)
    if isinstance(cached, JevConfig):
        return cached
    return parse_config(cached if isinstance(cached, dict) else {})


def reset_diagnostics():
    _COUNTERS.clear()
    _DIAGNOSTICS.clear()


def counters():
    return dict(_COUNTERS)


def diagnostics():
    return list(_DIAGNOSTICS)


def record_diagnostic(kind, **fields):
    ctx = fields.pop("ctx", None)
    _COUNTERS["%s.asked" % kind] += 1
    status = fields.get("status") or fields.get("outcome") or ""
    if status:
        _COUNTERS["%s.%s" % (kind, status)] += 1
    fallback = fields.get("fallback_reason") or ""
    if fallback:
        _COUNTERS["%s.fallback" % kind] += 1
    row = {"kind": kind}
    skip = {
        "user_text",
        "text",
        "clipboard",
        "notifications",
        "notes",
        "screenshot",
        "address",
    }
    for key, value in fields.items():
        if key in skip:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            row[key] = value
        elif isinstance(value, dict) and key == "probabilities":
            row[key] = {
                str(k): float(v)
                for k, v in list(value.items())[:12]
                if isinstance(v, (int, float))
            }
    _DIAGNOSTICS.append(row)
    if len(_DIAGNOSTICS) > DIAGNOSTIC_CAP:
        del _DIAGNOSTICS[:-DIAGNOSTIC_CAP]
    LOGGER.info(
        "jev %s status=%s outcome=%s confidence=%s latency_ms=%.0f fallback=%s",
        kind,
        row.get("status") or "",
        row.get("outcome") or "",
        row.get("confidence"),
        float(row.get("latency_ms") or 0),
        row.get("fallback_reason") or "none",
    )
    if ctx is not None:
        bucket = getattr(ctx, "jev_diagnostics", None)
        if bucket is None:
            ctx.jev_diagnostics = []
            bucket = ctx.jev_diagnostics
        bucket.append(dict(row))
    return row


def user_request_text(text):
    raw = text or ""
    if DESKTOP_CONTEXT_MARK in raw:
        return raw.split(DESKTOP_CONTEXT_MARK, 1)[0].strip()
    return raw.strip()


def focused_window_fact(text):
    raw = text or ""
    if DESKTOP_CONTEXT_MARK not in raw:
        return None
    tail = raw.split(DESKTOP_CONTEXT_MARK, 1)[1]
    match = _FOCUSED_RE.search(tail)
    if not match:
        return None
    title = match.group(1).strip()
    if not title:
        return None
    return {"title": title[:200]}


def native_enabled(ctx):
    enabled = set(getattr(ctx, "enabled_tools", None) or [])
    return "native" in enabled


def begin_turn(ctx, text):
    raw = text or ""
    ctx.jev_turn_id = uuid.uuid4().hex
    ctx.jev_user_text_raw = raw
    ctx.jev_user_text = user_request_text(raw)
    ctx.jev_focused_window = focused_window_fact(raw)
    ctx.jev_window_fp = None
    ctx.jev_window_judgment = None
    ctx.jev_window_candidates = []
    ctx.jev_intent_judgment = None
    ctx.jev_safety_cache = {}
    if not hasattr(ctx, "jev_diagnostics") or ctx.jev_diagnostics is None:
        ctx.jev_diagnostics = []


def _ask(ctx, state, questions):
    cfg = config_from_ctx(ctx)
    return jev.ask(
        ctx,
        state,
        questions,
        timeout_s=cfg.timeout_s,
        max_retries=cfg.max_retries,
    )


def _choice(judgment, name):
    if not judgment or not judgment.ok:
        return None
    return judgment.answers.get(name)


def _confident(answer, threshold):
    if answer is None or answer.kind != jev.KIND_CHOICE:
        return False
    if not answer.choice:
        return False
    confidence = answer.confidence
    if confidence is None:
        return False
    return confidence >= threshold


def _unique_choice(answer, threshold):
    if not _confident(answer, threshold):
        return False
    ranked = sorted((answer.probabilities or {}).items(), key=lambda item: item[1], reverse=True)
    if len(ranked) >= 2 and (ranked[0][1] - ranked[1][1]) < MULTI_INTENT_GAP:
        return False
    return True


def intent_questions():
    read_criteria = {name: {"what": "Read %s from the live desktop" % name.replace("_", " ")} for name in NATIVE_READ_TOOLS}
    read_criteria[READ_NONE] = {
        "what": "Not a desktop status read, or the read target is unclear",
        "not_for": "A clear request for volume, brightness, battery, weather, media, wifi, clipboard, windows, notifications, or notes",
    }
    write_criteria = {
        "toggle_mute": {"what": "Mute or unmute audio", "not_for": "Changing volume to a specific level"},
        "toggle_night_light": {"what": "Toggle night light or blue light filter"},
        "lock": {"what": "Lock the session now", "not_for": "A question about the lock screen"},
        "screenshot": {"what": "Take a screenshot", "not_for": "Describe what is on screen without capturing it"},
        "set_volume": {"what": "Set speakers or sink volume to a specific level"},
        "set_brightness": {"what": "Set display brightness to a specific level"},
        WRITE_NONE: {
            "what": "Not a closed-set desktop write, or it would need generated text or an invented command",
            "not_for": "Mute, night light, lock, screenshot, set volume, or set brightness",
        },
    }
    return {
        "intent": {
            "type": "choice",
            "instructions": {
                "question": "What is the primary thing the user wants the desktop shell to do?",
                "focus": "Pick one handler. Prefer conversation when the request needs files, web search, reasoning, or generated content.",
            },
            "criteria": {
                INTENT_NATIVE_READ: {
                    "what": "Read current desktop state (volume, brightness, battery, weather, media, wifi, clipboard, windows, notifications, notes)",
                    "not_for": "Changing those values, focusing a window, or open-ended chat",
                    "examples": ["what's the volume", "battery level", "which windows are open"],
                },
                INTENT_NATIVE_WRITE: {
                    "what": "A closed-set desktop write: mute, night light, lock, screenshot, set volume, set brightness",
                    "not_for": "Focusing a window, sending notifications with generated text, or shell commands",
                    "examples": ["mute", "lock the screen", "set volume to 40%"],
                },
                INTENT_FOCUS_WINDOW: {
                    "what": "Bring an already-open window to the front",
                    "not_for": "Listing windows, launching apps, or computer-use clicking",
                    "examples": ["focus firefox", "switch to the terminal"],
                },
                INTENT_CONVERSATION: {
                    "what": "Chat, coding, search, files, computer use, or anything that needs the LLM tool loop",
                    "not_for": "A single obvious desktop read, write, or window focus",
                    "examples": ["explain this error", "edit main.py", "click the pay button"],
                },
                INTENT_CLARIFY: {
                    "what": "The request is too ambiguous to choose a single handler",
                    "not_for": "A request that clearly matches one of the other options",
                    "examples": ["do the thing", "that window"],
                },
            },
        },
        "read_tool": {
            "type": "choice",
            "instructions": {
                "question": "If this is a desktop status read, which native read tool matches `request.text`?",
                "focus": "Choose none unless the user clearly wants that live value.",
            },
            "criteria": read_criteria,
        },
        "write_tool": {
            "type": "choice",
            "instructions": {
                "question": "If this is a closed-set desktop write, which native write tool matches `request.text`?",
                "focus": "Choose none when arguments would have to be invented or the action is not listed.",
            },
            "criteria": write_criteria,
        },
    }


def intent_state(ctx, text=None):
    request = text if text is not None else getattr(ctx, "jev_user_text", "") or ""
    focused = focused_window_fact(getattr(ctx, "jev_user_text_raw", None) or "")
    if focused is None:
        focused = getattr(ctx, "jev_focused_window", None)
    state = {
        "request": {
            "text": request[:2000],
            "id": getattr(ctx, "jev_turn_id", "") or "",
        }
    }
    if focused:
        state["desktop"] = {
            "focused_window": {
                "title": str(focused.get("title") or "")[:200],
                "class": str(focused.get("class") or focused.get("class_name") or "")[:120],
            }
        }
    return state


def evaluate_intent(ctx, text=None):
    cfg = config_from_ctx(ctx)
    if not cfg.enabled:
        return None
    request = user_request_text(text if text is not None else getattr(ctx, "jev_user_text", "") or "")
    if not request:
        return None
    judgment = _ask(ctx, intent_state(ctx, request), intent_questions())
    answer = _choice(judgment, "intent")
    outcome = answer.choice if answer else ""
    fallback = ""
    if judgment is None:
        fallback = "unavailable"
    elif not judgment.ok:
        fallback = judgment.status
    elif not _unique_choice(answer, cfg.confidence_threshold):
        fallback = "low_confidence" if answer else "malformed"
    ctx.jev_intent_judgment = judgment
    record_diagnostic(
        "intent",
        ctx=ctx,
        status=judgment.status if judgment else "unavailable",
        outcome=outcome,
        confidence=None if answer is None else answer.confidence,
        latency_ms=judgment.latency_ms if judgment else 0,
        fallback_reason=fallback,
        probabilities=answer.probabilities if answer else {},
    )
    return judgment


def _ratio_from_percent(number):
    if 0 <= number <= 100:
        return number / 100.0
    return None


def parse_level(text):
    """Parse a volume/brightness level as a 0-1 ratio.

    Bare integers are percentages (1 → 1%, not 100%). Decimals without `%`
    and incidental words like `full`/`off` are rejected unless they sit next
    to volume/brightness language.
    """
    raw = text or ""
    match = _PERCENT_RE.search(raw)
    if match:
        return _ratio_from_percent(float(match.group(1)))
    lowered = raw.lower()
    if re.search(r"\b(max|maximum|loudest)\b", lowered):
        return 1.0
    if re.search(r"\bhalf\b", lowered):
        return 0.5
    if re.search(r"\b(min|minimum)\b", lowered):
        return 0.0
    if re.search(rf"\b(?:{_LEVEL_NEAR}\s+(?:to\s+)?full|full\s+{_LEVEL_NEAR})\b", lowered):
        return 1.0
    if re.search(
        rf"\b(?:{_LEVEL_NEAR}\s+(?:to\s+)?(?:off|silent|mute[d]?)|(?:off|silent|mute[d]?)\s+{_LEVEL_NEAR})\b",
        lowered,
    ):
        return 0.0
    if _DECIMAL_RE.search(raw):
        return None
    matches = _BARE_INT_RE.findall(raw)
    if len(matches) != 1:
        return None
    return _ratio_from_percent(int(matches[0]))


def write_args_for(tool_name, text):
    if tool_name in ("toggle_mute", "toggle_night_light", "lock", "screenshot"):
        return {}
    if tool_name in ("set_volume", "set_brightness"):
        level = parse_level(text)
        if level is None:
            return None
        return {"value": level}
    return None


def slim_windows(raw_windows, limit=MAX_WINDOW_CANDIDATES):
    records = []
    seen = set()
    for item in raw_windows or []:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or item.get("window_id") or "").strip()
        if not address or address in seen:
            continue
        seen.add(address)
        records.append(
            {
                "address": address,
                "title": str(item.get("title") or "")[:200],
                "class": str(item.get("class") or item.get("class_name") or "")[:120],
                "pid": int(item.get("pid") or 0) if str(item.get("pid") or "0").lstrip("-").isdigit() else 0,
                "focused": bool(item.get("focused") or item.get("is_focused")),
            }
        )
    records.sort(key=lambda row: (not row["focused"], row["title"].lower()))
    return records[: max(1, int(limit))]


def windows_from_native(result):
    if not isinstance(result, dict):
        return []
    inner = result.get("result") if isinstance(result.get("result"), dict) else result
    windows = inner.get("windows") if isinstance(inner, dict) else None
    if windows is None and isinstance(result.get("windows"), list):
        windows = result.get("windows")
    return slim_windows(windows or [])


def window_fingerprint(windows):
    return tuple(sorted(row["address"] for row in windows or [] if row.get("address")))


def _window_match_tokens(query):
    tokens = [part for part in re.split(r"\s+", (query or "").strip().lower()) if len(part) >= 3]
    return [token for token in tokens if token not in _WINDOW_SKIP_TOKENS]


def substring_window_match(query, windows):
    tokens = _window_match_tokens(query)
    if not tokens:
        return None
    remainder = " ".join(tokens)
    hits = []
    for row in windows or []:
        title = (row.get("title") or "").lower()
        cls = (row.get("class") or "").lower()
        matched = False
        if title and (remainder in title or title in remainder):
            matched = True
        elif cls and (remainder in cls or cls in remainder):
            matched = True
        elif any(token in title or token in cls for token in tokens):
            matched = True
        if matched:
            hits.append(row)
    if len(hits) == 1:
        return hits[0]
    return None


def window_questions(windows):
    criteria = {
        WINDOW_NONE: {
            "what": "No listed window is a unique, intended match",
            "not_for": "A single listed window clearly matching the request",
        }
    }
    for index, row in enumerate(windows):
        label = "w%s" % index
        criteria[label] = {
            "title": row.get("title") or "",
            "class": row.get("class") or "",
            "focused": bool(row.get("focused")),
            "what": "The user wants this open window: %s (%s)"
            % (row.get("title") or "(untitled)", row.get("class") or "unknown"),
        }
    return {
        "window": {
            "type": "choice",
            "instructions": {
                "question": "Which live window in `candidates` should be focused for `request.text`?",
                "focus": "Choose none unless exactly one listed candidate is intended. Never invent a window.",
            },
            "criteria": criteria,
        }
    }


def window_state(ctx, windows, text=None):
    request = text if text is not None else getattr(ctx, "jev_user_text", "") or ""
    return {
        "request": {
            "text": request[:2000],
            "id": getattr(ctx, "jev_turn_id", "") or "",
        },
        "candidates": [
            {
                "id": "w%s" % index,
                "title": row.get("title") or "",
                "class": row.get("class") or "",
                "focused": bool(row.get("focused")),
            }
            for index, row in enumerate(windows)
        ],
    }


def evaluate_windows(ctx, windows, text=None):
    cfg = config_from_ctx(ctx)
    if not cfg.enabled:
        return None
    capped = slim_windows(windows)
    fingerprint = window_fingerprint(capped)
    prior = getattr(ctx, "jev_window_judgment", None)
    if prior is not None and getattr(ctx, "jev_window_fp", None) == fingerprint:
        return prior
    if not capped:
        judgment = jev.Judgment(status=jev.STATUS_SKIPPED, error="no windows")
        ctx.jev_window_judgment = judgment
        ctx.jev_window_fp = fingerprint
        record_diagnostic(
            "window",
            ctx=ctx,
            status=judgment.status,
            outcome=WINDOW_NONE,
            fallback_reason="no_candidates",
        )
        return judgment
    judgment = _ask(ctx, window_state(ctx, capped, text), window_questions(capped))
    answer = _choice(judgment, "window")
    outcome = answer.choice if answer else ""
    fallback = ""
    if not judgment.ok:
        fallback = judgment.status
    elif outcome == WINDOW_NONE:
        fallback = "none"
    elif not _unique_choice(answer, cfg.confidence_threshold):
        fallback = "low_confidence"
    elif not str(outcome).startswith("w"):
        fallback = "malformed"
    ctx.jev_window_judgment = judgment
    ctx.jev_window_fp = fingerprint
    ctx.jev_window_candidates = capped
    record_diagnostic(
        "window",
        ctx=ctx,
        status=judgment.status,
        outcome=outcome if outcome == WINDOW_NONE else "candidate",
        confidence=None if answer is None else answer.confidence,
        latency_ms=judgment.latency_ms,
        fallback_reason=fallback,
        candidate_count=len(capped),
    )
    return judgment


def resolve_window_choice(judgment, windows, threshold):
    windows = slim_windows(windows)
    if not judgment or not judgment.ok:
        return None, "unavailable" if not judgment else judgment.status
    answer = judgment.answers.get("window")
    if answer is None:
        return None, "malformed"
    choice = answer.choice or ""
    if choice == WINDOW_NONE:
        return None, "none"
    if not _unique_choice(answer, threshold):
        return None, "low_confidence"
    if not choice.startswith("w"):
        return None, "malformed"
    try:
        index = int(choice[1:])
    except ValueError:
        return None, "malformed"
    if index < 0 or index >= len(windows):
        return None, "stale"
    return windows[index], ""


def revalidate_window(selected, previous, fresh):
    if not selected or not selected.get("address"):
        return None, "malformed"
    prev_fp = window_fingerprint(previous)
    fresh_fp = window_fingerprint(fresh)
    if prev_fp != fresh_fp:
        return None, "stale"
    address = selected["address"]
    hits = [row for row in fresh if row.get("address") == address]
    if len(hits) != 1:
        return None, "stale"
    return hits[0], ""


def shadow_windows_from_native(ctx, result):
    cfg = config_from_ctx(ctx)
    if not cfg.enabled:
        return
    if getattr(ctx, "jev_revalidating_windows", False):
        return
    windows = windows_from_native(result)
    evaluate_windows(ctx, windows)


def note_focus_window_dispatch(ctx, args):
    judgment = getattr(ctx, "jev_window_judgment", None)
    if judgment is None:
        return
    address = str((args or {}).get("address") or "")
    windows = getattr(ctx, "jev_window_candidates", None) or []
    selected, reason = resolve_window_choice(
        judgment, windows, config_from_ctx(ctx).confidence_threshold
    )
    agreed = bool(selected and selected.get("address") == address)
    record_diagnostic(
        "window_compare",
        ctx=ctx,
        status="ok" if agreed else "disagree",
        outcome="agree" if agreed else "disagree",
        fallback_reason=reason,
    )


def safety_questions():
    return {
        "critical": {
            "type": "noul",
            "instructions": {
                "question": "Would performing `action` on `target` be a potentially irreversible desktop action?",
                "focus": "Yes for paying, purchasing, sending email or messages, transferring money, deleting an account, or similar commits. No for ordinary clicks, edits, or navigation.",
            },
            "criteria": {
                "true": {
                    "what": "Commits money, a message, an order, an account deletion, or another hard-to-undo action",
                    "examples": ["click Pay now", "press Ctrl+Enter to send the email"],
                },
                "false": {
                    "what": "Ordinary UI use that is not a commit of money, mail, or destruction",
                    "examples": ["click Save", "click the Back button"],
                },
            },
        }
    }


def safety_state(ctx, args):
    args = args or {}
    label = ""
    idx = args.get("element_index")
    if idx not in (None, ""):
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = None
        for node in getattr(ctx, "computer_use_nodes", None) or []:
            if node.get("index") == idx:
                label = str(node.get("name") or "")
                break
    focused = getattr(ctx, "jev_focused_window", None) or {}
    flags = []
    if args.get("critical") is True:
        flags.append("critical")
    if args.get("requires_confirmation") is True:
        flags.append("requires_confirmation")
    return {
        "request": {"id": getattr(ctx, "jev_turn_id", "") or ""},
        "action": {
            "name": str(args.get("action") or "")[:80],
            "summary": str(args.get("action_summary") or "")[:400],
            "key": str(args.get("key") or args.get("keys") or "")[:80],
        },
        "target": {
            "label": (label or str(args.get("name") or args.get("text") or ""))[:200],
            "role": str(args.get("role") or "")[:80],
            "application": str(focused.get("class") or focused.get("title") or "")[:120],
        },
        "flags": flags,
    }


def _safety_cache_key(args):
    args = args or {}
    return (
        str(args.get("action") or ""),
        str(args.get("action_summary") or ""),
        str(args.get("name") or ""),
        str(args.get("element_index") or ""),
        str(args.get("key") or args.get("keys") or ""),
        str(args.get("role") or ""),
    )


def evaluate_safety(ctx, args):
    cfg = config_from_ctx(ctx)
    if not cfg.enabled:
        return None
    action = str((args or {}).get("action") or "").strip()
    if action in ROUTINE_CU_ACTIONS or action not in SAFETY_ACTIONS:
        return None
    cache = getattr(ctx, "jev_safety_cache", None)
    if cache is None:
        ctx.jev_safety_cache = {}
        cache = ctx.jev_safety_cache
    key = _safety_cache_key(args)
    if key in cache:
        return cache[key]
    judgment = _ask(ctx, safety_state(ctx, args), safety_questions())
    cache[key] = judgment
    answer = judgment.answers.get("critical") if judgment and judgment.ok else None
    noul = answer.noul if answer else None
    fallback = "" if judgment.ok else judgment.status
    record_diagnostic(
        "safety",
        ctx=ctx,
        status=judgment.status,
        outcome="critical" if noul is not None and noul >= NOUL_POSITIVE else "ok",
        noul=noul,
        latency_ms=judgment.latency_ms,
        fallback_reason=fallback,
        action=action,
    )
    return judgment


def safety_forces_review(judgment):
    """True when Jev is positive or uncertain. False on failure (caller keeps regex)."""
    if judgment is None or not judgment.ok:
        return False
    answer = judgment.answers.get("critical")
    if answer is None or answer.noul is None:
        return False
    if answer.noul >= NOUL_POSITIVE:
        return True
    if answer.noul > NOUL_NEGATIVE:
        return True
    return False


def require_critical_review(ctx, args, regex_critical):
    """Jev may only add review. Regex/flag positives always stay critical."""
    cfg = config_from_ctx(ctx)
    if regex_critical:
        if cfg.enabled:
            evaluate_safety(ctx, args)
        return True
    if not cfg.enabled:
        return False
    judgment = evaluate_safety(ctx, args)
    if cfg.active and safety_forces_review(judgment):
        return True
    if cfg.mode == MODE_SHADOW:
        safety_forces_review(judgment)
    return False


def native_shortcut(ctx, judgment):
    """Return (tool_name, args) or (None, fallback_reason)."""
    cfg = config_from_ctx(ctx)
    if not cfg.active:
        return None, "shadow" if cfg.mode == MODE_SHADOW else "off"
    if not native_enabled(ctx):
        return None, "native_disabled"
    if getattr(ctx, "computer_use_approved", False):
        return None, "computer_use_session"
    if not judgment or not judgment.ok:
        return None, judgment.status if judgment else "unavailable"
    intent = judgment.answers.get("intent")
    if not _unique_choice(intent, cfg.confidence_threshold):
        return None, "low_confidence"
    choice = intent.choice
    request = getattr(ctx, "jev_user_text", "") or ""
    if choice == INTENT_CONVERSATION:
        return None, "conversation"
    if choice == INTENT_CLARIFY:
        return None, "clarify"
    if choice == INTENT_NATIVE_READ:
        read = judgment.answers.get("read_tool")
        if not _unique_choice(read, cfg.confidence_threshold) or read.choice == READ_NONE:
            return None, "low_confidence"
        if read.choice not in NATIVE_READ_TOOLS:
            return None, "malformed"
        return read.choice, {}
    if choice == INTENT_NATIVE_WRITE:
        write = judgment.answers.get("write_tool")
        if not _unique_choice(write, cfg.confidence_threshold) or write.choice == WRITE_NONE:
            return None, "low_confidence"
        if write.choice not in WRITE_CLOSED:
            return None, "malformed"
        args = write_args_for(write.choice, request)
        if args is None:
            return None, "unvalidated_args"
        return write.choice, args
    if choice == INTENT_FOCUS_WINDOW:
        return INTENT_FOCUS_WINDOW, {}
    return None, "conversation"


def select_focus_target(ctx, windows, fresh_windows=None):
    cfg = config_from_ctx(ctx)
    capped = slim_windows(windows)
    judgment = evaluate_windows(ctx, capped)
    selected, reason = resolve_window_choice(judgment, capped, cfg.confidence_threshold)
    if selected is None:
        fallback = substring_window_match(getattr(ctx, "jev_user_text", "") or "", capped)
        if fallback and not reason:
            reason = "none"
        if fallback and reason in ("unavailable", "timeout", "missing_key", "missing_sdk", "error", "cancelled"):
            return fallback, "substring"
        return None, reason or "low_confidence"
    live = slim_windows(fresh_windows if fresh_windows is not None else capped)
    return revalidate_window(selected, capped, live)
