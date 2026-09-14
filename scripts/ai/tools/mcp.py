"""Reserved MCP tool slot. Not implemented in v1."""

from __future__ import annotations

from .registry import Tool


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
