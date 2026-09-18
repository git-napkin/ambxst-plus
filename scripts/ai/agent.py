#!/usr/bin/env python3
"""Stdin JSON / stdout NDJSON agent loop."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from ai.execution_profile import ExecutionProfile
from ai.protocol import ProtocolError, decode_command, encode_event
from ai.providers import get_provider
from ai.tools.read_skill import skill_catalog_names
from ai.tools.registry import AGENT_WAIT, ToolContext, advertised_tool_names, build_registry
from ai.list_models import list_models
from ai.models import DEFAULT_MODEL_ID, DEFAULT_PROVIDER

DEFAULT_SYSTEM = (
    "You are a helpful assistant running on Ambxst[+], a Linux desktop shell. "
    "Prefer specialized tools over guessing. Use grep to locate, then read_files with line ranges. "
    "Edit via apply_file_diffs, not whole-file rewrites. Ask the user when intent is ambiguous."
)

MAX_TOOL_ITERS = 25
_INBOX_STOP = object()
PARALLEL_TOOLS = frozenset(
    {
        "grep",
        "file_glob",
        "read_files",
        "read_skill",
        "exa_search",
        "exa_contents",
    }
)


def flatten_ui_messages(messages):
    """Expand display-only cu_work wrappers before sending history to a model."""
    out = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "cu_work":
            out.extend(flatten_ui_messages(msg.get("items") or []))
            continue
        out.append(msg)
    return out


def _jev_native_outcome(result):
    """Classify a native/tool dispatch result for Jev shortcuts."""
    if not isinstance(result, dict):
        return "error"
    status = result.get("status")
    inner = result.get("result")
    if status == "Cancelled" or (
        result.get("type") == "tool_result"
        and (status == "Cancelled" or (isinstance(inner, dict) and inner.get("variant") == "Cancelled"))
    ):
        return "cancelled"
    if status == "ok":
        return "ok"
    if status == "error" or result.get("error"):
        return "error"
    if isinstance(inner, dict) and inner.get("error"):
        return "error"
    if status in (None, "", "done"):
        return "ok"
    return "error"


MAX_IMAGE_ATTACHMENTS = 2


def _inline_computer_use_skill(skill_dirs):
    for root in skill_dirs or []:
        path = Path(root).expanduser() / "computer-use" / "SKILL.md"
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
    return ""


def prune_image_attachments(messages, keep=MAX_IMAGE_ATTACHMENTS):
    """Drop older screenshot/image payloads; keep the newest `keep` ones.

    Computer-use turns attach a full JPEG on every screenshot. Sending the
    whole pile on later iterations dominates request size and decode time.
    """
    remaining = keep
    out = [None] * len(messages or [])
    for i in range(len(out) - 1, -1, -1):
        msg = messages[i]
        atts = msg.get("attachments") if isinstance(msg, dict) else None
        if not atts:
            out[i] = msg
            continue
        kept = []
        dropped = False
        for att in reversed(atts):
            if isinstance(att, dict) and att.get("type") == "image":
                if remaining > 0:
                    kept.append(att)
                    remaining -= 1
                else:
                    dropped = True
            else:
                kept.append(att)
        kept.reverse()
        if dropped or len(kept) != len(atts):
            msg = dict(msg)
            if kept:
                msg["attachments"] = kept
            else:
                msg.pop("attachments", None)
        out[i] = msg
    return out


class Pending:
    def __init__(self):
        self.event = threading.Event()
        self.kind = None
        self.payload = None

    def resolve(self, kind, payload=None):
        self.kind = kind
        self.payload = payload
        self.event.set()

    def wait(self, timeout=AGENT_WAIT):
        self.event.wait(timeout)
        return self.kind, self.payload


class Agent:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.inbox = Queue()
        self.pending = {}
        self.cancel_event = threading.Event()
        self.stop_event = threading.Event()
        self.ctx = ToolContext()
        self.registry = build_registry(self.ctx)
        self.messages = []
        self.model = {
            "provider": DEFAULT_PROVIDER,
            "model": DEFAULT_MODEL_ID,
            "endpoint": "",
            "name": DEFAULT_MODEL_ID,
        }
        self.system_prompt = DEFAULT_SYSTEM
        self.temperature = None
        self.max_tokens = None
        self.chat_id = ""
        self.computer_use_approved = False
        self.computer_use_nodes = []
        self.computer_use_last_shot = None
        self.computer_use_focus_address = ""
        self._lock = threading.Lock()
        self._busy = threading.Event()

    def emit(self, event):
        line = encode_event(event)
        with self._lock:
            self.stdout.write(line + "\n")
            self.stdout.flush()

    def apply_init(self, payload):
        workspace = payload.get("workspace") or ""
        profile = ExecutionProfile(payload.get("execution_profile") or payload.get("executionProfile") or {})
        skill_dirs = payload.get("skill_dirs") or payload.get("skillDirs") or []
        enabled = payload.get("enabled_tools") or payload.get("enabledTools")
        from ai.jev_judgments import parse_config

        self.ctx = ToolContext(
            workspace=workspace,
            profile=profile,
            skill_dirs=skill_dirs,
            keystore_db=payload.get("keystore_db") or payload.get("keystoreDb") or "",
            enabled_tools=enabled,
            custom_endpoint=payload.get("custom_endpoint") or payload.get("customEndpoint") or "",
            custom_models=payload.get("custom_models") or payload.get("customModels") or [],
            custom_name=payload.get("custom_name") or payload.get("customName") or "",
            ignore_catalog=payload.get("ignore_catalog") or payload.get("ignoreModelCatalog") or {},
            manual_models=payload.get("manual_models") or payload.get("manualModels") or {},
        )
        self.ctx.jev_config = parse_config(payload.get("jev") or {})
        context = payload.get("context") or {}
        self.ctx.autoexecute_any_action = bool(context.get("autoexecute_any_action"))
        self.ctx.cancel_event = self.cancel_event
        self.ctx.emit = self.emit
        self.ctx.wait_for_native = self.wait_for_native
        self.ctx.wait_for_answers = self.wait_for_answers
        self.ctx.register_process = self._register_process
        self.ctx.computer_use_approved = self.computer_use_approved
        self.ctx.computer_use_nodes = list(self.computer_use_nodes)
        self.ctx.computer_use_last_shot = self.computer_use_last_shot
        self.ctx.computer_use_focus_address = getattr(self, "computer_use_focus_address", "") or ""
        user_tools_dir = payload.get("user_tools_dir")
        self.registry = build_registry(self.ctx, user_tools_dir=user_tools_dir)
        self.system_prompt = payload.get("system_prompt") or payload.get("systemPrompt") or DEFAULT_SYSTEM
        self._apply_sampling(payload)
        if payload.get("model"):
            self.model = dict(payload["model"])
        catalog = [n for n in skill_catalog_names(self.ctx.skill_dirs) if n != "computer-use"]
        extra = []
        if catalog:
            extra.append("Available skills: %s. Use read_skill to load one." % ", ".join(catalog))
        extra.append(
            "Use grep to locate, then read_files with line ranges. "
            "Edit via apply_file_diffs, not whole-file rewrites."
        )
        from ai.execution_profile import NEVER

        if self.ctx.profile.computer_use != NEVER:
            skill_text = _inline_computer_use_skill(self.ctx.skill_dirs)
            extra.append(
                skill_text
                or (
                    "Computer use is available. Call request_computer_use first, then use_computer. "
                    "Start with action=snapshot (accessibility tree). Click by element_index. "
                    "action=screenshot is grim JPEG for the agent — not the human overlay. "
                    "Pixel x/y are in the attached image (width x height). "
                    "The session stays granted until Stop, lock, or end_computer_use. "
                    "Set critical=true before payments, sending email, or purchases."
                )
            )
        if extra:
            self.system_prompt = self.system_prompt.rstrip() + "\n\n" + "\n".join(extra)

    def _clear_computer_use(self):
        self.computer_use_approved = False
        self.computer_use_nodes = []
        self.computer_use_last_shot = None
        self.computer_use_focus_address = ""
        self.ctx.computer_use_approved = False
        self.ctx.computer_use_nodes = []
        self.ctx.computer_use_last_shot = None
        self.ctx.computer_use_focus_address = ""

    def _apply_sampling(self, payload):
        if "temperature" in payload:
            value = payload.get("temperature")
            self.temperature = None if value is None else float(value)
        if "max_tokens" in payload or "maxTokens" in payload:
            value = payload.get("max_tokens")
            if value is None:
                value = payload.get("maxTokens")
            self.max_tokens = None if value is None else int(value)

    def _register_process(self, proc):
        self.ctx.running_procs.append(proc)

    def _kill_running(self):
        import os as _os

        for proc in list(self.ctx.running_procs):
            try:
                _os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                try:
                    proc.terminate()
                except OSError:
                    pass

    def wait_for_native(self, call_id, timeout=AGENT_WAIT):
        pending = self.pending.setdefault(call_id, Pending())
        kind, payload = pending.wait(timeout)
        self.pending.pop(call_id, None)
        if kind == "native_result":
            return payload
        return None

    def wait_for_answers(self, call_id, timeout=AGENT_WAIT):
        pending = self.pending.setdefault(call_id, Pending())
        kind, payload = pending.wait(timeout)
        self.pending.pop(call_id, None)
        if kind == "answer_questions":
            return payload
        return None

    def wait_for_approval(self, call_id, timeout=AGENT_WAIT):
        pending = self.pending.setdefault(call_id, Pending())
        kind, payload = pending.wait(timeout)
        self.pending.pop(call_id, None)
        return kind, payload

    def handle_command(self, payload):
        cmd = payload.get("cmd")
        if cmd == "init":
            self.apply_init(payload)
            self.emit({"type": "done", "reason": "init"})
            return
        if cmd == "ping":
            self.emit({"type": "pong"})
            return
        if cmd == "shutdown":
            self.cancel_event.set()
            self._kill_running()
            self.stop_event.set()
            self.emit({"type": "done", "reason": "shutdown"})
            return
        if cmd == "cancel":
            self.cancel_event.set()
            self._kill_running()
            try:
                from ai.computer_use.input import release_held

                release_held()
            except Exception:
                pass
            for pending in list(self.pending.values()):
                pending.resolve("cancel")
            self._clear_computer_use()
            self.emit({"type": "cancelled"})
            return
        if cmd == "approve":
            call_id = payload.get("call_id") or ""
            pending = self.pending.get(call_id)
            if pending:
                pending.resolve("approve")
            return
        if cmd == "reject":
            call_id = payload.get("call_id") or ""
            pending = self.pending.get(call_id)
            if pending:
                pending.resolve("reject")
            return
        if cmd == "answer_questions":
            call_id = payload.get("call_id") or ""
            pending = self.pending.get(call_id)
            if pending:
                pending.resolve("answer_questions", payload.get("answers") or [])
            return
        if cmd == "native_result":
            call_id = payload.get("call_id") or ""
            pending = self.pending.get(call_id)
            if pending:
                pending.resolve("native_result", payload.get("result"))
            return
        if cmd == "set_model":
            if payload.get("model"):
                self.model = dict(payload["model"])
            self._apply_sampling(payload)
            self.emit({"type": "done", "reason": "set_model"})
            return
        if cmd == "set_autoapprove":
            self.ctx.autoexecute_any_action = bool(payload.get("value"))
            self.emit({"type": "done", "reason": "set_autoapprove"})
            return
        if cmd == "load_chat":
            self.messages = flatten_ui_messages(payload.get("messages") or [])
            if not self.messages or payload.get("end_computer_use"):
                self._clear_computer_use()
            self.emit({"type": "done", "reason": "load_chat"})
            return
        if cmd == "end_computer_use":
            self._clear_computer_use()
            try:
                from ai.computer_use.input import release_held

                release_held()
            except Exception:
                pass
            self.emit({"type": "done", "reason": "end_computer_use"})
            return
        if cmd == "list_models":
            try:
                models = list_models(
                    self.ctx,
                    custom_endpoint=self.ctx.custom_endpoint,
                    custom_models=self.ctx.custom_models,
                    custom_name=self.ctx.custom_name,
                    ignore_catalog=self.ctx.ignore_catalog,
                    manual_models=self.ctx.manual_models,
                )
            except Exception as exc:
                self.emit({"type": "error", "error": "list_models: %s" % exc})
                return
            self.emit({"type": "models", "models": models})
            return
        if cmd == "send":
            self._handle_send(payload)
            return
        self.emit({"type": "error", "error": "unhandled cmd: %s" % cmd})

    def _tool_schemas(self):
        names = advertised_tool_names(self.ctx)
        for tool in self.registry._tools.values():
            if tool.name not in names and getattr(tool, "command", None):
                names.append(tool.name)
        return self.registry.schemas(names)

    def _api_key(self):
        provider = (self.model.get("provider") or "").lower()
        key_id = self.model.get("key_id") or provider
        if provider == "ollama":
            return ""
        return self.ctx.get_key(key_id) or self.ctx.get_key(provider)

    def _ensure_system(self):
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = self.system_prompt
            return
        self.messages.insert(0, {"role": "system", "content": self.system_prompt})

    def _jev_try_handle(self):
        from ai.jev_judgments import (
            INTENT_FOCUS_WINDOW,
            MODE_SHADOW,
            config_from_ctx,
            evaluate_intent,
            native_shortcut,
        )

        cfg = config_from_ctx(self.ctx)
        if not cfg.enabled:
            return False
        if self.computer_use_approved:
            return False
        judgment = evaluate_intent(self.ctx)
        if cfg.mode == MODE_SHADOW or not cfg.active:
            return False
        name, args = native_shortcut(self.ctx, judgment)
        if name is None:
            return False
        if name == INTENT_FOCUS_WINDOW:
            return self._jev_focus_window()
        return self._jev_dispatch_native(name, args)

    def _jev_windows_readable(self):
        tool = self.registry.get("get_windows")
        if not tool:
            return False
        return tool.should_autoexecute(self.ctx, {}) is True

    def _jev_focus_window(self):
        from ai.jev_judgments import revalidate_window, select_focus_target, windows_from_native
        from ai.tools.native import native_request

        if not self._jev_windows_readable():
            return False
        listed = native_request(self.ctx, "get_windows", {})
        if _jev_native_outcome(listed) == "cancelled":
            self.emit({"type": "cancelled"})
            return True
        if _jev_native_outcome(listed) != "ok":
            return False
        windows = windows_from_native(listed)
        selected, _reason = select_focus_target(self.ctx, windows)
        if selected is None:
            return False
        self.ctx.jev_revalidating_windows = True
        try:
            if not self._jev_windows_readable():
                return False
            fresh_raw = native_request(self.ctx, "get_windows", {})
        finally:
            self.ctx.jev_revalidating_windows = False
        if _jev_native_outcome(fresh_raw) == "cancelled":
            self.emit({"type": "cancelled"})
            return True
        if _jev_native_outcome(fresh_raw) != "ok":
            return False
        live, _stale = revalidate_window(selected, windows, windows_from_native(fresh_raw))
        if live is None:
            return False
        return self._jev_dispatch_native("focus_window", {"address": live.get("address")})

    def _jev_dispatch_native(self, name, args):
        call_id = "jev_%s" % uuid.uuid4().hex[:12]
        self.emit(
            {
                "type": "tool_call",
                "call_id": call_id,
                "name": name,
                "args": args,
                **self._friendly_event_fields(name, args),
            }
        )
        result = self._dispatch_tool(name, args, call_id)
        emit_result = dict(result) if isinstance(result, dict) else result
        if isinstance(emit_result, dict):
            emit_result.pop("image_base64", None)
        outcome = _jev_native_outcome(result)
        chip = "done" if outcome == "ok" else outcome
        self.emit(
            {
                "type": "tool_result",
                "call_id": call_id,
                "name": name,
                "result": emit_result,
                "status": chip,
            }
        )
        self.messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }
        )
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": json.dumps(emit_result, ensure_ascii=False),
            }
        )
        if outcome == "cancelled":
            self.emit({"type": "cancelled"})
            return True
        if outcome != "ok":
            err = ""
            if isinstance(result, dict):
                err = str(result.get("error") or "")
            self.emit({"type": "error", "error": err or "Native action failed"})
            return True
        self.emit({"type": "done"})
        return True

    def _handle_send(self, payload):
        self.cancel_event.clear()
        text = payload.get("text") or ""
        attachments = payload.get("attachments") or []
        self.chat_id = payload.get("chat_id") or self.chat_id
        self.messages = flatten_ui_messages(self.messages)
        self._ensure_system()
        user_msg = {"role": "user", "content": text}
        if attachments:
            user_msg["attachments"] = attachments
        self.messages.append(user_msg)
        try:
            from ai.jev_judgments import begin_turn

            begin_turn(self.ctx, text)
            if self._jev_try_handle():
                return
            self._run_turn()
        except Exception as exc:
            if self.computer_use_approved:
                self._clear_computer_use()
            self.emit({"type": "error", "error": str(exc)})

    def _max_tool_iters(self):
        if self.computer_use_approved:
            return None
        return MAX_TOOL_ITERS

    def _run_turn(self):
        provider = get_provider(self.model, custom_endpoint=self.ctx.custom_endpoint)
        tools = self._tool_schemas()
        api_key = self._api_key()
        endpoint = self.ctx.custom_endpoint or self.model.get("endpoint") or ""
        iters = 0
        while True:
            cap = self._max_tool_iters()
            if cap is not None and iters >= cap:
                self.emit({"type": "error", "error": "tool iteration limit"})
                return
            iters += 1
            if self.cancel_event.is_set():
                self._clear_computer_use()
                self.emit({"type": "cancelled"})
                return
            assistant_text = []
            tool_calls = []
            self.messages = prune_image_attachments(self.messages)
            for event in provider.stream_chat(
                self.messages,
                tools,
                self.temperature,
                self.max_tokens,
                self.model,
                api_key,
                endpoint=endpoint,
            ):
                if self.cancel_event.is_set():
                    self._clear_computer_use()
                    self.emit({"type": "cancelled"})
                    return
                if event.get("type") == "token":
                    assistant_text.append(event.get("text") or "")
                    self.emit(event)
                elif event.get("type") == "tool_call":
                    tool_calls.append(event)
                elif event.get("type") == "error":
                    if self.computer_use_approved:
                        self._clear_computer_use()
                    self.emit(event)
                    return
            if not tool_calls:
                if assistant_text:
                    self.messages.append({"role": "assistant", "content": "".join(assistant_text)})
                self.emit({"type": "done"})
                return
            openai_calls = []
            tool_messages = []
            prepared = []
            for call in tool_calls:
                call_id = call.get("id") or ("call_%s" % uuid.uuid4().hex[:12])
                name = call.get("name") or ""
                args = call.get("args") or {}
                prepared.append((call_id, name, args))
                call_item = {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
                if call.get("thought_signature"):
                    call_item["thought_signature"] = call["thought_signature"]
                openai_calls.append(call_item)
                self.emit(
                    {
                        "type": "tool_call",
                        "call_id": call_id,
                        "name": name,
                        "args": args,
                        **self._friendly_event_fields(name, args),
                    }
                )
            parallel = len(prepared) > 1 and all(self._tool_parallel_ok(name, args) for _cid, name, args in prepared)
            if parallel:
                with ThreadPoolExecutor(max_workers=min(4, len(prepared))) as pool:
                    futs = [
                        pool.submit(self._execute_approved, name, args, call_id)
                        for call_id, name, args in prepared
                    ]
                    results = [fut.result() for fut in futs]
            else:
                results = [self._dispatch_tool(name, args, call_id) for call_id, name, args in prepared]
            for (call_id, name, _args), result in zip(prepared, results):
                self.computer_use_approved = bool(getattr(self.ctx, "computer_use_approved", False))
                self.computer_use_nodes = list(getattr(self.ctx, "computer_use_nodes", None) or [])
                self.computer_use_last_shot = getattr(self.ctx, "computer_use_last_shot", None)
                self.computer_use_focus_address = getattr(self.ctx, "computer_use_focus_address", "") or ""
                emit_result = dict(result) if isinstance(result, dict) else result
                attachments = []
                if isinstance(emit_result, dict):
                    b64 = emit_result.pop("image_base64", None)
                    if b64:
                        attachments.append(
                            {
                                "type": "image",
                                "base64": b64,
                                "mimeType": emit_result.get("mime_type") or "image/png",
                            }
                        )
                self.emit(
                    {
                        "type": "tool_result",
                        "call_id": call_id,
                        "name": name,
                        "result": emit_result,
                    }
                )
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": json.dumps(emit_result, ensure_ascii=False),
                }
                if attachments:
                    tool_msg["attachments"] = attachments
                tool_messages.append(tool_msg)
            self.messages.append(
                {
                    "role": "assistant",
                    "content": "".join(assistant_text),
                    "tool_calls": openai_calls,
                }
            )
            self.messages.extend(tool_messages)

    def _tool_parallel_ok(self, name, args):
        if name not in PARALLEL_TOOLS:
            return False
        tool = self.registry.get(name)
        if not tool:
            return False
        decision = tool.should_autoexecute(self.ctx, args)
        return decision is True

    def _execute_approved(self, name, args, call_id):
        tool = self.registry.get(name)
        if not tool:
            return {"status": "error", "error": "Unknown tool: %s" % name}
        if self.cancel_event.is_set():
            return tool.cancelled()
        try:
            return tool.execute(self.ctx, args)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _friendly_labels(self, name, args):
        tool = self.registry.get(name)
        if tool and hasattr(tool, "friendly_labels"):
            return tool.friendly_labels(args)
        return {
            "running": getattr(tool, "user_friendly_name", None) or name,
            "done": getattr(tool, "user_friendly_name", None) or name,
            "ask": getattr(tool, "user_friendly_name", None) or name,
        }

    def _friendly_event_fields(self, name, args):
        labels = self._friendly_labels(name, args)
        return {
            "user_friendly_name": labels["running"],
            "user_friendly_done": labels["done"],
        }

    def _dispatch_tool(self, name, args, call_id):
        tool = self.registry.get(name)
        self.ctx.current_call_id = call_id
        if not self.registry.known(name) and name not in self.registry._tools:
            return {"status": "error", "error": "Unknown tool: %s" % name}
        if self.cancel_event.is_set():
            return tool.cancelled()
        decision = tool.should_autoexecute(self.ctx, args)
        if decision == "deny":
            return {"status": "error", "error": "Permission denied"}
        if decision in (False, "ask"):
            friendly = self._friendly_labels(name, args)
            if name == "apply_file_diffs" and hasattr(tool, "preview"):
                preview = tool.preview(self.ctx, args)
                self.emit(
                    {
                        "type": "diff_preview",
                        "call_id": call_id,
                        "name": name,
                        "previews": preview.get("previews") or [],
                        "edits": preview.get("edits") or [],
                        "user_friendly_name": friendly["ask"],
                    }
                )
            elif name != "ask_user_question":
                self.emit(
                    {
                        "type": "approval_required",
                        "call_id": call_id,
                        "name": name,
                        "args": args,
                        "user_friendly_name": friendly["ask"],
                    }
                )
            if name == "ask_user_question":
                return tool.execute(self.ctx, args)
            kind, _payload = self.wait_for_approval(call_id)
            if kind == "reject":
                return {"status": "error", "error": "User rejected the tool call"}
            if kind != "approve":
                return tool.cancelled()
        if self.cancel_event.is_set():
            return tool.cancelled()
        try:
            return tool.execute(self.ctx, args)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def stdin_loop(self):
        try:
            for raw in self.stdin:
                if self.stop_event.is_set():
                    break
                try:
                    payload = decode_command(raw)
                except ProtocolError as exc:
                    self.emit({"type": "error", "error": str(exc)})
                    continue
                if payload.get("cmd") in (
                    "approve",
                    "reject",
                    "answer_questions",
                    "native_result",
                    "cancel",
                    "end_computer_use",
                ):
                    self.handle_command(payload)
                else:
                    self.inbox.put(payload)
                if payload.get("cmd") in ("shutdown",):
                    break
        finally:
            self.inbox.put(_INBOX_STOP)

    def process_forever(self):
        while not self.stop_event.is_set():
            payload = self.inbox.get()
            if payload is _INBOX_STOP:
                break
            cmd = payload.get("cmd")
            if cmd in ("approve", "reject", "answer_questions", "native_result", "cancel", "end_computer_use"):
                self.handle_command(payload)
                continue
            self.handle_command(payload)
            if cmd == "shutdown":
                break

    def run(self):
        reader = threading.Thread(target=self.stdin_loop, daemon=True)
        reader.start()
        self.process_forever()
        reader.join(timeout=1)


def load_config_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "cmd" not in data:
        data = dict(data)
        data["cmd"] = "init"
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ambxst[+] AI agent")
    parser.add_argument("--config", help="JSON init config path")
    args = parser.parse_args(argv)
    agent = Agent()
    if args.config:
        agent.apply_init(load_config_file(args.config))
    agent.run()


if __name__ == "__main__":
    main()
