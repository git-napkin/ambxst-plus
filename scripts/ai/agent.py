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
from pathlib import Path
from queue import Empty, Queue

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from ai.execution_profile import ExecutionProfile
from ai.protocol import ProtocolError, decode_command, encode_event
from ai.providers import get_provider
from ai.tools.read_skill import skill_catalog_names
from ai.tools.registry import AGENT_WAIT, ToolContext, advertised_tool_names, build_registry
from ai.list_models import list_models

DEFAULT_SYSTEM = (
    "You are a helpful assistant running on Ambxst[+], a Linux desktop shell. "
    "Prefer specialized tools over guessing. Use grep to locate, then read_files with line ranges. "
    "Edit via apply_file_diffs, not whole-file rewrites. Ask the user when intent is ambiguous."
)

MAX_TOOL_ITERS = 25
MAX_COMPUTER_USE_ITERS = 500


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
            "provider": "gemini",
            "model": "gemini-2.0-flash",
            "endpoint": "",
            "name": "gemini-2.0-flash",
        }
        self.system_prompt = DEFAULT_SYSTEM
        self.temperature = None
        self.max_tokens = None
        self.chat_id = ""
        self.computer_use_approved = False
        self.computer_use_nodes = []
        self.computer_use_last_shot = None
        self._lock = threading.Lock()
        self._busy = threading.Event()

    def emit(self, event):
        line = encode_event(event)
        self.stdout.write(line + "\n")
        self.stdout.flush()

    def apply_init(self, payload):
        workspace = payload.get("workspace") or ""
        profile = ExecutionProfile(payload.get("execution_profile") or payload.get("executionProfile") or {})
        skill_dirs = payload.get("skill_dirs") or payload.get("skillDirs") or []
        enabled = payload.get("enabled_tools") or payload.get("enabledTools")
        self.ctx = ToolContext(
            workspace=workspace,
            profile=profile,
            skill_dirs=skill_dirs,
            keystore_db=payload.get("keystore_db") or payload.get("keystoreDb") or "",
            enabled_tools=enabled,
            custom_endpoint=payload.get("custom_endpoint") or payload.get("customEndpoint") or "",
            custom_models=payload.get("custom_models") or payload.get("customModels") or [],
            custom_name=payload.get("custom_name") or payload.get("customName") or "",
        )
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
        user_tools_dir = payload.get("user_tools_dir")
        self.registry = build_registry(self.ctx, user_tools_dir=user_tools_dir)
        self.system_prompt = payload.get("system_prompt") or payload.get("systemPrompt") or DEFAULT_SYSTEM
        self._apply_sampling(payload)
        if payload.get("model"):
            self.model = dict(payload["model"])
        catalog = skill_catalog_names(self.ctx.skill_dirs)
        extra = []
        if catalog:
            extra.append("Available skills: %s. Use read_skill to load one." % ", ".join(catalog))
        extra.append(
            "Use grep to locate, then read_files with line ranges. "
            "Edit via apply_file_diffs, not whole-file rewrites."
        )
        from ai.execution_profile import NEVER

        if self.ctx.profile.computer_use != NEVER:
            extra.append(
                "Computer use is available. Call request_computer_use first, then use_computer. "
                "Start with action=snapshot to read the accessibility tree, windows, and focused text. "
                "Click by element_index. Call action=screenshot only if tree_usable is false or you need pixels. "
                "The user-only HUD will not appear in screenshots. Read the computer-use skill for details."
            )
        if extra:
            self.system_prompt = self.system_prompt.rstrip() + "\n\n" + "\n".join(extra)

    def _clear_computer_use(self):
        self.computer_use_approved = False
        self.computer_use_nodes = []
        self.computer_use_last_shot = None
        self.ctx.computer_use_approved = False
        self.ctx.computer_use_nodes = []
        self.ctx.computer_use_last_shot = None

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
            self.messages = list(payload.get("messages") or [])
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
                if hasattr(self.ctx, "clear_key_cache"):
                    self.ctx.clear_key_cache()
                # Keep custom model catalog in sync with the latest init payload.
                models = list_models(
                    self.ctx,
                    custom_endpoint=self.ctx.custom_endpoint,
                    custom_models=self.ctx.custom_models,
                    custom_name=self.ctx.custom_name,
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

    def _handle_send(self, payload):
        self.cancel_event.clear()
        text = payload.get("text") or ""
        attachments = payload.get("attachments") or []
        self.chat_id = payload.get("chat_id") or self.chat_id
        self._ensure_system()
        user_msg = {"role": "user", "content": text}
        if attachments:
            user_msg["attachments"] = attachments
        self.messages.append(user_msg)
        try:
            self._run_turn()
        except Exception as exc:
            self.emit({"type": "error", "error": str(exc)})

    def _max_tool_iters(self):
        if self.computer_use_approved:
            return MAX_COMPUTER_USE_ITERS
        return MAX_TOOL_ITERS

    def _run_turn(self):
        provider = get_provider(self.model, custom_endpoint=self.ctx.custom_endpoint)
        tools = self._tool_schemas()
        api_key = self._api_key()
        endpoint = self.ctx.custom_endpoint or self.model.get("endpoint") or ""
        for _ in range(self._max_tool_iters()):
            if self.cancel_event.is_set():
                self.emit({"type": "cancelled"})
                return
            assistant_text = []
            tool_calls = []
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
                    self.emit({"type": "cancelled"})
                    return
                if event.get("type") == "token":
                    assistant_text.append(event.get("text") or "")
                    self.emit(event)
                elif event.get("type") == "tool_call":
                    tool_calls.append(event)
                elif event.get("type") == "error":
                    self.emit(event)
                    return
            if not tool_calls:
                if assistant_text:
                    self.messages.append({"role": "assistant", "content": "".join(assistant_text)})
                self.emit({"type": "done"})
                return
            openai_calls = []
            tool_messages = []
            for call in tool_calls:
                call_id = call.get("id") or ("call_%s" % uuid.uuid4().hex[:12])
                name = call.get("name") or ""
                args = call.get("args") or {}
                openai_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                )
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
                self.computer_use_approved = bool(getattr(self.ctx, "computer_use_approved", False))
                self.computer_use_nodes = list(getattr(self.ctx, "computer_use_nodes", None) or [])
                self.computer_use_last_shot = getattr(self.ctx, "computer_use_last_shot", None)
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
        self.emit({"type": "error", "error": "tool iteration limit"})

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

    def process_forever(self):
        while not self.stop_event.is_set():
            try:
                payload = self.inbox.get(timeout=0.1)
            except Empty:
                continue
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
