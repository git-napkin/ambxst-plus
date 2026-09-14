"""Reserved MCP tool slot. Not implemented in v1."""

from __future__ import annotations

from .registry import Tool
from .friendly import labels


class CallMcpTool(Tool):
    name = "call_mcp_tool"
    user_friendly_name = "Call mcp tool"
    schema = {
        "description": "Call an MCP tool. Not implemented.",
        "parameters": {
            "type": "object",
            "properties": {
                "server_id": {"type": "string"},
                "name": {"type": "string"},
                "input": {"type": "object"},
            },
            "required": ["name"],
        },
    }

    def should_autoexecute(self, ctx, args):
        return "deny"

    def execute(self, ctx, args):
        return {"status": "error", "error": "MCP is not implemented"}

    def user_friendly_name_for(self, args):
        name = (args or {}).get("name") or "tool"
        return labels(
            "Calling %s" % name,
            "Called %s" % name,
            ask="Call %s" % name,
        )
