"""Stub computer-use tools. Profile default is Never."""

from __future__ import annotations

from .registry import Tool
from ..execution_profile import ALWAYS_ALLOW, NEVER


class RequestComputerUseTool(Tool):
    name = "request_computer_use"
    user_friendly_name = "Request computer use"
    schema = {
        "description": "Request permission to use the computer. Not implemented.",
        "parameters": {
            "type": "object",
            "properties": {"task_summary": {"type": "string"}},
        },
    }

    def should_autoexecute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return "deny"
        if ctx.profile.computer_use == ALWAYS_ALLOW:
            return True
        return "ask"

    def execute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return {"status": "error", "error": "computer use is disabled"}
        ctx.computer_use_approved = True
        return {
            "status": "error",
            "error": "computer use is not implemented",
        }


class UseComputerTool(Tool):
    name = "use_computer"
    user_friendly_name = "Use computer"
    schema = {
        "description": "Synthesize input / capture screen. Not implemented.",
        "parameters": {
            "type": "object",
            "properties": {
                "actions": {"type": "array"},
                "action_summary": {"type": "string"},
            },
        },
    }

    def should_autoexecute(self, ctx, args):
        if ctx.profile.computer_use == NEVER:
            return "deny"
        if ctx.computer_use_approved or ctx.profile.computer_use == ALWAYS_ALLOW:
            return True
        return "ask"

    def execute(self, ctx, args):
        return {"status": "error", "error": "computer use is not implemented"}
