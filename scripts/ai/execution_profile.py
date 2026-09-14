"""Permission gate: denylist > allowlist > auto-approve. Fail closed."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

ALWAYS_ALLOW = "AlwaysAllow"
ALWAYS_ASK = "AlwaysAsk"
AGENT_DECIDES = "AgentDecides"
NEVER = "Never"
ASK_EXCEPT_IN_AUTO_APPROVE = "AskExceptInAutoApprove"

ALLOW = "allow"
ASK = "ask"
DENY = "deny"

ACTION_PERMS = frozenset({ALWAYS_ALLOW, ALWAYS_ASK, AGENT_DECIDES})
ASK_USER_PERMS = frozenset({ALWAYS_ASK, ASK_EXCEPT_IN_AUTO_APPROVE, NEVER})
COMPUTER_USE_PERMS = frozenset({NEVER, ALWAYS_ASK, ALWAYS_ALLOW})

DEFAULT_ALLOWLIST = [
    r"cat(\s.*)?",
    r"echo(\s.*)?",
    r"find .*",
    r"grep(\s.*)?",
    r"ls(\s.*)?",
    r"which .*",
]

DEFAULT_DENYLIST = [
    r"bash(\s.*)?",
    r"fish(\s.*)?",
    r"pwsh(\s.*)?",
    r"sh(\s.*)?",
    r"zsh(\s.*)?",
    r"curl(\s.*)?",
    r"eval(\s.*)?",
    r"exec(\s.*)?",
    r"source(\s.*)?",
    r"wget(\s.*)?",
    r"dig(\s.*)?",
    r"nslookup(\s.*)?",
    r"host(\s.*)?",
    r"ssh(\s.*)?",
    r"scp(\s.*)?",
    r"rsync(\s.*)?",
    r"telnet(\s.*)?",
    r"rm(\s.*)?",
]


def _pick(raw, *names, default=None):
    if not raw:
        return default
    for name in names:
        if name in raw and raw[name] is not None:
            return raw[name]
    return default


def _parse_enum(value, allowed, closed):
    if value in allowed:
        return value
    return closed


def _compile_patterns(patterns):
    compiled = []
    for pat in patterns or []:
        try:
            compiled.append(re.compile(pat))
        except re.error:
            compiled.append(re.compile(re.escape(str(pat))))
    return compiled


class ExecutionProfile:
    def __init__(self, raw=None):
        raw = raw or {}
        self.read_files = _parse_enum(
            _pick(raw, "readFiles", "read_files", default=AGENT_DECIDES),
            ACTION_PERMS,
            ALWAYS_ASK,
        )
        self.apply_code_diffs = _parse_enum(
            _pick(raw, "applyCodeDiffs", "apply_code_diffs", default=ALWAYS_ASK),
            ACTION_PERMS,
            ALWAYS_ASK,
        )
        self.execute_commands = _parse_enum(
            _pick(raw, "executeCommands", "execute_commands", default=ALWAYS_ASK),
            ACTION_PERMS,
            ALWAYS_ASK,
        )
        self.ask_user_question = _parse_enum(
            _pick(raw, "askUserQuestion", "ask_user_question", default=ALWAYS_ASK),
            ASK_USER_PERMS,
            ALWAYS_ASK,
        )
        self.computer_use = _parse_enum(
            _pick(raw, "computerUse", "computer_use", default=NEVER),
            COMPUTER_USE_PERMS,
            NEVER,
        )
        allow = _pick(raw, "commandAllowlist", "command_allowlist", default=None)
        deny = _pick(raw, "commandDenylist", "command_denylist", default=None)
        self.command_allowlist = list(allow) if allow is not None else list(DEFAULT_ALLOWLIST)
        self.command_denylist = list(deny) if deny is not None else list(DEFAULT_DENYLIST)
        dirs = _pick(raw, "directoryAllowlist", "directory_allowlist", default=[]) or []
        self.directory_allowlist = [str(d) for d in dirs]
        web = _pick(raw, "webSearchEnabled", "web_search_enabled", default=True)
        self.web_search_enabled = bool(web)
        self._allow_re = _compile_patterns(self.command_allowlist)
        self._deny_re = _compile_patterns(self.command_denylist)

    def to_dict(self):
        return {
            "readFiles": self.read_files,
            "applyCodeDiffs": self.apply_code_diffs,
            "executeCommands": self.execute_commands,
            "askUserQuestion": self.ask_user_question,
            "computerUse": self.computer_use,
            "commandAllowlist": self.command_allowlist,
            "commandDenylist": self.command_denylist,
            "directoryAllowlist": self.directory_allowlist,
            "webSearchEnabled": self.web_search_enabled,
        }


def normalize_continuations(command):
    return re.sub(r"\\\n", " ", command or "")


def decompose_command(command):
    normalized = normalize_continuations(command)
    has_redirection = False
    segments = []
    buf = []
    quote = None
    i = 0
    n = len(normalized)
    while i < n:
        ch = normalized[i]
        if quote:
            buf.append(ch)
            if ch == quote and (quote == "'" or i == 0 or normalized[i - 1] != "\\"):
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in "<>":
            has_redirection = True
            buf.append(ch)
            i += 1
            continue
        if normalized.startswith("&&", i) or normalized.startswith("||", i):
            seg = "".join(buf).strip()
            if seg:
                segments.append(seg)
            buf = []
            i += 2
            continue
        if ch in "|;":
            seg = "".join(buf).strip()
            if seg:
                segments.append(seg)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        segments.append(tail)
    if not segments:
        segments = [normalized.strip()] if normalized.strip() else []
    return segments, has_redirection


def _normalize_segment(segment):
    try:
        parts = shlex.split(segment)
    except ValueError:
        parts = segment.split()
    if not parts:
        return segment.strip()
    parts[0] = Path(parts[0]).name
    return " ".join(parts)


def _matches_any(segment, compiled):
    normalized = _normalize_segment(segment)
    for regex in compiled:
        if regex.fullmatch(normalized) or regex.fullmatch(segment.strip()):
            return True
    return False


def can_autoexecute_command(command, profile, ctx, is_read_only=None, is_risky=None):
    segments, has_redirection = decompose_command(command)
    if not segments:
        return DENY
    if any(_matches_any(seg, profile._deny_re) for seg in segments):
        return DENY
    if getattr(ctx, "autoexecute_any_action", False):
        return ALLOW
    perm = profile.execute_commands
    if perm == ALWAYS_ALLOW:
        return ALLOW
    allowlisted = all(_matches_any(seg, profile._allow_re) for seg in segments)
    safe_readonly = bool(is_read_only) and not bool(is_risky) and not has_redirection
    if perm == ALWAYS_ASK:
        # Auto-review: allowlist or clearly read-only (model-hinted) commands.
        return ALLOW if allowlisted or safe_readonly else ASK
    if perm == AGENT_DECIDES:
        if is_risky or has_redirection:
            return ASK
        if allowlisted or is_read_only:
            return ALLOW
        return ASK
    return ASK


def _abs_allowed(abs_path, ctx):
    path = Path(abs_path).resolve()
    allowed = [Path(ctx.workspace).resolve()]
    for extra in ctx.profile.directory_allowlist:
        try:
            allowed.append(Path(extra).expanduser().resolve())
        except Exception:
            continue
    for root in allowed:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    temps = getattr(ctx, "temp_read_permissions", set()) or set()
    return str(path) in temps or path in temps


def can_read_files(abs_path, ctx):
    if not _abs_allowed(abs_path, ctx):
        return DENY
    perm = ctx.profile.read_files
    if perm == ALWAYS_ALLOW:
        return ALLOW
    if perm == ALWAYS_ASK:
        temps = getattr(ctx, "temp_read_permissions", set()) or set()
        if str(Path(abs_path).resolve()) in temps:
            return ALLOW
        return ASK
    if perm == AGENT_DECIDES:
        return ALLOW
    return ASK


def can_write_files(abs_path, ctx):
    path = Path(abs_path).resolve()
    try:
        path.relative_to(Path(ctx.workspace).resolve())
    except ValueError:
        extra_ok = False
        for extra in ctx.profile.directory_allowlist:
            try:
                path.relative_to(Path(extra).expanduser().resolve())
                extra_ok = True
                break
            except Exception:
                continue
        if not extra_ok:
            return DENY
    if getattr(ctx, "autoexecute_any_action", False):
        return ALLOW
    perm = ctx.profile.apply_code_diffs
    if perm == ALWAYS_ALLOW:
        return ALLOW
    if perm == ALWAYS_ASK:
        return ASK
    if perm == AGENT_DECIDES:
        return ALLOW
    return ASK


def decision_to_autoexecute(decision):
    if decision == ALLOW:
        return True
    if decision == DENY:
        return "deny"
    return "ask"
