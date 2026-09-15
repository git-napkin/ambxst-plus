"""Exhaustive tool registry. Unknown tools fail closed."""

from __future__ import annotations

import json
from pathlib import Path

from ..protocol import (
    ALL_TOOLS,
    CORE_TOOLS,
    NATIVE_READ_TOOLS,
    NATIVE_WRITE_TOOLS,
    cancelled_result,
)

GREP_TIMEOUT = 10
GLOB_TIMEOUT = 10
AGENT_WAIT = 120
SHELL_DEFAULT_TIMEOUT = 30
SHELL_MAX_TIMEOUT = 120
SHELL_OUTPUT_CAP = 64 * 1024

USER_TOOLS_DIR = Path.home() / ".config" / "ambxst+" / "ai" / "tools"


class ToolContext:
    def __init__(
        self,
        workspace="",
        profile=None,
        skill_dirs=None,
        keystore_db="",
        enabled_tools=None,
        custom_endpoint="",
        custom_models=None,
        custom_name="",
        ignore_catalog=None,
        manual_models=None,
        http_opener=None,
    ):
        from ..execution_profile import ExecutionProfile

        self.workspace = Path(workspace).expanduser().resolve() if workspace else Path.cwd()
        self.profile = profile or ExecutionProfile()
        self.skill_dirs = [str(Path(d).expanduser()) for d in (skill_dirs or [])]
        self.keystore_db = keystore_db or ""
        self.enabled_tools = list(enabled_tools) if enabled_tools else list(CORE_TOOLS)
        self.custom_endpoint = custom_endpoint or ""
        self.custom_models = list(custom_models) if custom_models else []
        self.custom_name = custom_name or ""
        self.ignore_catalog = dict(ignore_catalog) if ignore_catalog else {}
        self.manual_models = dict(manual_models) if manual_models else {}
        self.http_opener = http_opener
        self.autoexecute_any_action = False
        self.temp_read_permissions = set()
        self.cancel_event = None
        self.emit = lambda _event: None
        self.wait_for_native = None
        self.wait_for_answers = None
        self.register_process = None
        self.computer_use_approved = False
        self.computer_use_nodes = []
        self.computer_use_last_shot = None
        self.current_call_id = ""
        self.api_keys = {}
        self._listed_keys = {}
        self.running_procs = []

    def clear_key_cache(self):
        self.api_keys = {}
        self._listed_keys = {}

    def add_temporary_file_read_permissions(self, abs_path):
        self.temp_read_permissions.add(str(Path(abs_path).resolve()))

    def resolve_path(self, name):
        target = Path(name).expanduser()
        if not target.is_absolute():
            target = self.workspace / target
        return target.resolve()

    def cancelled(self):
        ev = self.cancel_event
        return bool(ev is not None and ev.is_set())

    def _keystore(self):
        try:
            import keystore
        except ImportError:
            from pathlib import Path as _P
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "keystore",
                _P(__file__).resolve().parents[2] / "keystore.py",
            )
            keystore = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(keystore)
        return keystore

    def get_key(self, provider):
        if provider in self.api_keys:
            return self.api_keys[provider]
        if not self.keystore_db:
            return ""
        key = self._keystore().get_provider_key(self.keystore_db, provider)
        self.api_keys[provider] = key
        return key

    def list_keys(self, provider):
        if provider in self._listed_keys:
            return self._listed_keys[provider]
        if not self.keystore_db:
            key = self.api_keys.get(provider) or ""
            entries = [{"id": None, "label": "", "api_key": key}] if key else []
            self._listed_keys[provider] = entries
            return entries
        entries = self._keystore().list_provider_keys(self.keystore_db, provider) or []
        self._listed_keys[provider] = entries
        if entries:
            self.api_keys[provider] = entries[0].get("api_key") or ""
            for entry in entries:
                eid = entry.get("id")
                if eid is None:
                    continue
                self.api_keys["%s#%s" % (provider, eid)] = entry.get("api_key") or ""
        return entries


class Tool:
    name = ""
    user_friendly_name = ""
    schema = {}

    def should_autoexecute(self, ctx, args):
        return True

    def preprocess(self, ctx, args):
        return None

    def execute(self, ctx, args):
        raise NotImplementedError

    def cancelled(self):
        return cancelled_result(self.name)

    def friendly_labels(self, args=None):
        """Return {running, done, ask} strings for the transcript / approval UI."""
        fn = getattr(self, "user_friendly_name_for", None)
        if callable(fn):
            result = fn(args or {})
            if isinstance(result, dict):
                running = result.get("running") or self.user_friendly_name or self.name
                done = result.get("done") or running
                ask = result.get("ask")
                if ask is None:
                    ask = done
                return {"running": running, "done": done, "ask": ask}
            if result:
                return {"running": result, "done": result, "ask": result}
        base = self.user_friendly_name or self.name
        return {"running": base, "done": base, "ask": base}


def _unknown(name):
    class UnknownTool(Tool):
        def __init__(self, tool_name):
            self.name = tool_name
            self.user_friendly_name = tool_name

        def should_autoexecute(self, ctx, args):
            return "deny"

        def execute(self, ctx, args):
            return {"status": "error", "error": "Unknown tool: %s" % self.name}

        def cancelled(self):
            return {
                "type": "tool_result",
                "tool": self.name,
                "status": "Cancelled",
                "result": {"variant": "Cancelled"},
            }

    return UnknownTool(name)


class Registry:
    def __init__(self, tools=None):
        self._tools = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool):
        self._tools[tool.name] = tool

    def get(self, name):
        tool = self._tools.get(name)
        if tool is None:
            return _unknown(name)
        return tool

    def known(self, name):
        return name in self._tools

    def schemas(self, enabled=None):
        names = list(enabled) if enabled is not None else list(self._tools)
        out = []
        for name in names:
            tool = self._tools.get(name)
            if tool is None:
                continue
            out.append(
                {
                    "name": tool.name,
                    "description": tool.schema.get("description") or tool.user_friendly_name,
                    "parameters": tool.schema.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
        return out

    def names(self):
        return list(self._tools)


class UserArgvTool(Tool):
    def __init__(self, spec):
        self.name = spec["name"]
        self.user_friendly_name = spec.get("user_friendly_name") or spec["name"]
        self.command = list(spec.get("command") or [])
        self.schema = {
            "description": spec.get("description") or self.user_friendly_name,
            "parameters": spec.get("parameters")
            or {"type": "object", "properties": {}},
        }

    def should_autoexecute(self, ctx, args):
        from ..execution_profile import can_autoexecute_command, decision_to_autoexecute

        rendered = " ".join(self._argv(args))
        return decision_to_autoexecute(can_autoexecute_command(rendered, ctx.profile, ctx))

    def _argv(self, args):
        argv = []
        mapping = {str(k): str(v) for k, v in (args or {}).items()}
        for part in self.command:
            text = str(part)
            for key, value in mapping.items():
                text = text.replace("{%s}" % key, value)
            argv.append(text)
        return argv

    def execute(self, ctx, args):
        from .run_shell_command import run_argv

        return run_argv(ctx, self._argv(args), timeout=SHELL_DEFAULT_TIMEOUT)

    def user_friendly_name_for(self, args):
        from .friendly import labels

        base = self.user_friendly_name or self.name
        return labels("Running %s" % base, "Ran %s" % base, ask=base)

    def cancelled(self):
        return {
            "type": "tool_result",
            "tool": self.name,
            "status": "Cancelled",
            "result": {"variant": "Cancelled"},
        }


def load_user_tools(directory=None):
    root = Path(directory) if directory else USER_TOOLS_DIR
    tools = []
    if not root.is_dir():
        return tools
    for path in sorted(root.glob("*.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(spec, dict) or not spec.get("name") or not spec.get("command"):
            continue
        tools.append(UserArgvTool(spec))
    return tools


def build_registry(ctx=None, user_tools_dir=None):
    from .apply_file_diffs import ApplyFileDiffsTool
    from .ask_user_question import AskUserQuestionTool
    from .computer_use import RequestComputerUseTool, UseComputerTool
    from .exa import ExaContentsTool, ExaSearchTool
    from .file_glob import FileGlobTool
    from .grep import GrepTool
    from .mcp import CallMcpTool
    from .native import native_tools
    from .read_files import ReadFilesTool
    from .read_skill import ReadSkillTool
    from .run_shell_command import RunShellCommandTool

    tools = [
        ReadFilesTool(),
        GrepTool(),
        FileGlobTool(),
        ApplyFileDiffsTool(),
        RunShellCommandTool(),
        AskUserQuestionTool(),
        ReadSkillTool(),
        ExaSearchTool(),
        ExaContentsTool(),
        CallMcpTool(),
        RequestComputerUseTool(),
        UseComputerTool(),
    ]
    tools.extend(native_tools())
    tools.extend(load_user_tools(user_tools_dir))
    return Registry(tools)


def advertised_tool_names(ctx):
    enabled = set(ctx.enabled_tools or [])
    names = [n for n in ALL_TOOLS if n in enabled]
    if "native" in enabled:
        names.extend(NATIVE_READ_TOOLS)
        names.extend(NATIVE_WRITE_TOOLS)
    from ..execution_profile import NEVER

    if getattr(ctx.profile, "computer_use", NEVER) != NEVER:
        for reserved in ("request_computer_use", "use_computer"):
            if reserved not in names:
                names.append(reserved)
    seen = set()
    out = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out
