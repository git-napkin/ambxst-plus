"""Stdin command / stdout NDJSON event protocol for the AI agent."""

from __future__ import annotations

import json

COMMANDS = frozenset(
    {
        "init",
        "send",
        "approve",
        "reject",
        "cancel",
        "answer_questions",
        "set_model",
        "load_chat",
        "native_result",
        "ping",
        "shutdown",
        "set_autoapprove",
        "list_models",
    }
)

EVENTS = frozenset(
    {
        "token",
        "tool_call",
        "tool_result",
        "approval_required",
        "diff_preview",
        "ask_user_question",
        "native_request",
        "done",
        "error",
        "cancelled",
        "pong",
        "models",
    }
)

NATIVE_READ_TOOLS = (
    "get_volume",
    "get_brightness",
    "get_battery",
    "get_weather",
    "get_media",
    "get_wifi",
    "get_clipboard",
    "get_windows",
    "get_notifications",
    "get_notes",
)

NATIVE_WRITE_TOOLS = (
    "set_volume",
    "set_brightness",
    "toggle_mute",
    "notify",
    "toggle_night_light",
    "lock",
    "screenshot",
    "focus_window",
    "copy_to_clipboard",
    "load_preset",
)

CORE_TOOLS = (
    "read_files",
    "grep",
    "file_glob",
    "apply_file_diffs",
    "run_shell_command",
    "ask_user_question",
    "read_skill",
    "exa_search",
    "exa_contents",
)

RESERVED_TOOLS = (
    "call_mcp_tool",
    "request_computer_use",
    "use_computer",
)

ALL_TOOLS = CORE_TOOLS + NATIVE_READ_TOOLS + NATIVE_WRITE_TOOLS + RESERVED_TOOLS


class ProtocolError(ValueError):
    pass


def cancelled_result(tool_name):
    if tool_name not in ALL_TOOLS:
        raise KeyError("unknown tool: %s" % tool_name)
    return {
        "type": "tool_result",
        "tool": tool_name,
        "status": "Cancelled",
        "result": {"variant": "Cancelled"},
    }


def decode_command(line):
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    text = line.strip()
    if not text:
        raise ProtocolError("empty command")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid json: %s" % exc) from exc
    if not isinstance(payload, dict):
        raise ProtocolError("command must be a JSON object")
    cmd = payload.get("cmd")
    if cmd not in COMMANDS:
        raise ProtocolError("unknown cmd: %s" % cmd)
    return payload


def encode_event(event):
    if not isinstance(event, dict):
        raise ProtocolError("event must be a dict")
    event_type = event.get("type")
    if not event_type:
        raise ProtocolError("event missing type")
    if event_type not in EVENTS:
        raise ProtocolError("unknown event type: %s" % event_type)
    return json.dumps(event, ensure_ascii=False, separators=(",", ":"))


def encode_command(command):
    if not isinstance(command, dict):
        raise ProtocolError("command must be a dict")
    cmd = command.get("cmd")
    if cmd not in COMMANDS:
        raise ProtocolError("unknown cmd: %s" % cmd)
    return json.dumps(command, ensure_ascii=False, separators=(",", ":"))
