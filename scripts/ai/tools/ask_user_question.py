"""Ask the user structured questions and wait for answers."""

from __future__ import annotations

import threading

from .registry import AGENT_WAIT, Tool
from .friendly import labels
from ..execution_profile import ASK_EXCEPT_IN_AUTO_APPROVE, NEVER


class AnswerWaiter:
    def __init__(self):
        self.event = threading.Event()
        self.answers = None
        self.cancelled = False

    def provide(self, answers):
        self.answers = answers
        self.event.set()

    def cancel(self):
        self.cancelled = True
        self.event.set()

    def wait(self, timeout=AGENT_WAIT):
        self.event.wait(timeout)
        if self.cancelled:
            return None
        return self.answers


def parse_items(args):
    raw = (args or {}).get("questions") or (args or {}).get("items") or []
    items = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        qtype = item.get("question_type") or item.get("multiple_choice") or {}
        if item.get("options") and not qtype:
            qtype = {
                "is_multiselect": bool(item.get("is_multiselect")),
                "options": item.get("options"),
                "supports_other": bool(item.get("supports_other")),
            }
        options = []
        for opt in qtype.get("options") or []:
            if isinstance(opt, str):
                options.append({"label": opt, "recommended": False})
            elif isinstance(opt, dict):
                options.append(
                    {
                        "label": opt.get("label") or "",
                        "recommended": bool(opt.get("recommended")),
                    }
                )
        items.append(
            {
                "question_id": item.get("question_id") or item.get("id") or "",
                "question": item.get("question") or "",
                "question_type": {
                    "is_multiselect": bool(qtype.get("is_multiselect")),
                    "options": options,
                    "supports_other": bool(qtype.get("supports_other")),
                },
            }
        )
    return items


class AskUserQuestionTool(Tool):
    name = "ask_user_question"
    user_friendly_name = "Ask user"

    schema = {
        "description": "Ask the user one or more multiple-choice questions.",
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_id": {"type": "string"},
                            "question": {"type": "string"},
                            "is_multiselect": {"type": "boolean"},
                            "supports_other": {"type": "boolean"},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "recommended": {"type": "boolean"},
                                    },
                                },
                            },
                        },
                        "required": ["question"],
                    },
                }
            },
            "required": ["questions"],
        },
    }

    def should_autoexecute(self, ctx, args):
        mode = ctx.profile.ask_user_question
        if mode == NEVER:
            return "deny"
        if mode == ASK_EXCEPT_IN_AUTO_APPROVE and ctx.autoexecute_any_action:
            return "deny"
        return "ask"

    def execute(self, ctx, args):
        items = parse_items(args)
        mode = ctx.profile.ask_user_question
        if mode == NEVER:
            return {"status": "skipped", "reason": "Never"}
        if mode == ASK_EXCEPT_IN_AUTO_APPROVE and ctx.autoexecute_any_action:
            return {"status": "skipped", "reason": "AskExceptInAutoApprove"}
        call_id = ctx.current_call_id or (args or {}).get("call_id") or ""
        payload = {
            "type": "ask_user_question",
            "call_id": call_id,
            "items": items,
        }
        payload["user_friendly_name"] = self.friendly_labels(args)["ask"]
        ctx.emit(payload)
        if not ctx.wait_for_answers:
            return self.cancelled()
        answers = ctx.wait_for_answers(call_id, timeout=AGENT_WAIT)
        if answers is None or ctx.cancelled():
            return self.cancelled()
        return {"status": "ok", "answers": answers}

    def user_friendly_name_for(self, args):
        items = parse_items(args)
        n = len(items)
        if n == 1:
            return labels("Asking a question", "Asked a question", ask="Answer a question")
        return labels(
            "Asking %d questions" % n,
            "Asked %d questions" % n,
            ask="Answer %d questions" % n,
        )
