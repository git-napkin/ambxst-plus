"""Native bridge requests. Do not call QML from Python."""

from __future__ import annotations

from .registry import AGENT_WAIT, Tool
from ..execution_profile import ALWAYS_ALLOW, ALWAYS_ASK
from ..protocol import NATIVE_READ_TOOLS, NATIVE_WRITE_TOOLS

READ_TOOLS = NATIVE_READ_TOOLS
WRITE_TOOLS = NATIVE_WRITE_TOOLS

FRIENDLY = {
    "get_volume": "Get volume",
    "get_brightness": "Get brightness",
    "get_battery": "Get battery",
    "get_weather": "Get weather",
    "get_media": "Get media",
    "get_wifi": "Get wifi",
    "get_clipboard": "Get clipboard",
    "get_windows": "Get windows",
    "get_notifications": "Get notifications",
    "get_notes": "Get notes",
    "set_volume": "Set volume",
    "set_brightness": "Set brightness",
    "toggle_mute": "Toggle mute",
    "notify": "Notify",
    "toggle_night_light": "Toggle night light",
    "lock": "Lock",
    "screenshot": "Screenshot",
    "focus_window": "Focus window",
    "copy_to_clipboard": "Copy to clipboard",
    "load_preset": "Load preset",
}


def native_request(ctx, name, args):
    call_id = ctx.current_call_id or ""
    event = {
        "type": "native_request",
        "call_id": call_id,
        "name": name,
        "args": args or {},
    }
    ctx.emit(event)
    if not ctx.wait_for_native:
        return {"status": "error", "error": "native bridge unavailable"}
    result = ctx.wait_for_native(call_id, timeout=AGENT_WAIT)
    if result is None or ctx.cancelled():
        return {
            "type": "tool_result",
            "tool": name,
            "status": "Cancelled",
            "result": {"variant": "Cancelled"},
        }
    return {"status": "ok", "result": result}


class NativeTool(Tool):
    def __init__(self, name, write=False):
        self.name = name
        self.write = write
        self.user_friendly_name = FRIENDLY.get(name, name)
        self.schema = {
            "description": self.user_friendly_name,
            "parameters": {"type": "object", "properties": {"args": {"type": "object"}}},
        }

    def should_autoexecute(self, ctx, args):
        if self.write:
            if ctx.profile.execute_commands == ALWAYS_ALLOW:
                return True
            if ctx.autoexecute_any_action:
                return True
            if ctx.profile.execute_commands == ALWAYS_ASK:
                return "ask"
            return "ask"
        if ctx.profile.read_files == ALWAYS_ASK:
            return "ask"
        return True

    def execute(self, ctx, args):
        payload = args or {}
        if "args" in payload and isinstance(payload["args"], dict) and set(payload.keys()) == {"args"}:
            payload = payload["args"]
        return native_request(ctx, self.name, payload)


def native_tools():
    tools = [NativeTool(name, write=False) for name in READ_TOOLS]
    tools.extend(NativeTool(name, write=True) for name in WRITE_TOOLS)
    return tools
