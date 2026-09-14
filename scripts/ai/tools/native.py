"""Native bridge requests. Do not call QML from Python."""

from __future__ import annotations

from .registry import AGENT_WAIT, Tool
from .friendly import labels
from ..execution_profile import ALWAYS_ALLOW, ALWAYS_ASK
from ..protocol import NATIVE_READ_TOOLS, NATIVE_WRITE_TOOLS

READ_TOOLS = NATIVE_READ_TOOLS
WRITE_TOOLS = NATIVE_WRITE_TOOLS

FRIENDLY = {
    "get_volume": labels("Getting volume", "Got volume", ask="Get volume"),
    "get_brightness": labels("Getting brightness", "Got brightness", ask="Get brightness"),
    "get_battery": labels("Getting battery", "Got battery", ask="Get battery"),
    "get_weather": labels("Getting weather", "Got weather", ask="Get weather"),
    "get_media": labels("Getting media", "Got media", ask="Get media"),
    "get_wifi": labels("Getting wifi", "Got wifi", ask="Get wifi"),
    "get_clipboard": labels("Getting clipboard", "Got clipboard", ask="Get clipboard"),
    "get_windows": labels("Getting windows", "Got windows", ask="Get windows"),
    "get_notifications": labels("Getting notifications", "Got notifications", ask="Get notifications"),
    "get_notes": labels("Getting notes", "Got notes", ask="Get notes"),
    "set_volume": labels("Setting volume", "Set volume", ask="Set volume"),
    "set_brightness": labels("Setting brightness", "Set brightness", ask="Set brightness"),
    "toggle_mute": labels("Toggling mute", "Toggled mute", ask="Toggle mute"),
    "notify": labels("Sending notification", "Sent notification", ask="Notify"),
    "toggle_night_light": labels("Toggling night light", "Toggled night light", ask="Toggle night light"),
    "lock": labels("Locking", "Locked", ask="Lock"),
    "screenshot": labels("Taking screenshot", "Took screenshot", ask="Screenshot"),
    "focus_window": labels("Focusing window", "Focused window", ask="Focus window"),
    "copy_to_clipboard": labels("Copying to clipboard", "Copied to clipboard", ask="Copy to clipboard"),
    "load_preset": labels("Loading preset", "Loaded preset", ask="Load preset"),
}


def native_request(ctx, name, args):
    import uuid

    base = ctx.current_call_id or "native"
    call_id = "%s:%s" % (base, uuid.uuid4().hex[:8])
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
        bundle = FRIENDLY.get(name)
        if isinstance(bundle, dict):
            self.user_friendly_name = bundle.get("ask") or bundle.get("done") or name
            self._friendly = bundle
        else:
            self.user_friendly_name = bundle or name
            self._friendly = None
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

    def user_friendly_name_for(self, args):
        if self._friendly:
            return self._friendly
        return self.user_friendly_name


def native_tools():
    tools = [NativeTool(name, write=False) for name in READ_TOOLS]
    tools.extend(NativeTool(name, write=True) for name in WRITE_TOOLS)
    return tools
