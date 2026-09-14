"""Typed subprocess runner. Model flags are hints. No PTY."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time

from .registry import SHELL_DEFAULT_TIMEOUT, SHELL_MAX_TIMEOUT, SHELL_OUTPUT_CAP, Tool
from .friendly import command_tick, labels
from ..execution_profile import can_autoexecute_command, decision_to_autoexecute


def _timeout_of(args):
    wait = args.get("timeout") if args else None
    if wait is None:
        wait = SHELL_DEFAULT_TIMEOUT
    try:
        wait = int(wait)
    except (TypeError, ValueError):
        wait = SHELL_DEFAULT_TIMEOUT
    return max(1, min(wait, SHELL_MAX_TIMEOUT))


def _truncate(data):
    if data is None:
        return "", False
    if isinstance(data, bytes):
        text = data.decode("utf-8", errors="replace")
    else:
        text = str(data)
    if len(text) > SHELL_OUTPUT_CAP:
        return text[:SHELL_OUTPUT_CAP], True
    return text, False


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        try:
            proc.terminate()
        except OSError:
            pass
    deadline = time.monotonic() + 2
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            try:
                proc.kill()
            except OSError:
                pass


def run_argv(ctx, argv, timeout=SHELL_DEFAULT_TIMEOUT, env=None):
    if not argv:
        return {"status": "error", "error": "empty command"}
    proc = subprocess.Popen(
        argv,
        cwd=str(ctx.workspace),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=env,
    )
    if ctx.register_process:
        ctx.register_process(proc)
    ctx.running_procs.append(proc)

    def watch_cancel():
        while proc.poll() is None:
            if ctx.cancelled():
                _kill_group(proc)
                return
            time.sleep(0.05)

    watcher = threading.Thread(target=watch_cancel, daemon=True)
    watcher.start()
    try:
        stdout_b, stderr_b = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        stdout_b, stderr_b = proc.communicate(timeout=2)
        stdout, out_cut = _truncate(stdout_b)
        stderr, err_cut = _truncate(stderr_b)
        return {
            "status": "error",
            "error": "timed out",
            "stdout": stdout,
            "stderr": stderr,
            "truncated": out_cut or err_cut,
            "exit_code": None,
        }
    finally:
        if proc in ctx.running_procs:
            ctx.running_procs.remove(proc)
    if ctx.cancelled():
        return {
            "status": "Cancelled",
            "result": {"variant": "Cancelled"},
            "stdout": _truncate(stdout_b)[0],
            "stderr": _truncate(stderr_b)[0],
        }
    stdout, out_cut = _truncate(stdout_b)
    stderr, err_cut = _truncate(stderr_b)
    return {
        "status": "ok" if proc.returncode == 0 else "error",
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "truncated": out_cut or err_cut,
        "argv": argv,
    }


def command_to_argv(command):
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv:
        return None
    return argv


def run_shell_command(ctx, args):
    command = (args or {}).get("command") or ""
    if not command.strip():
        return {"status": "error", "error": "empty command"}
    timeout = _timeout_of(args)
    argv = command_to_argv(command)
    if argv is None:
        argv = ["bash", "-lc", command]
    return run_argv(ctx, argv, timeout=timeout)


class RunShellCommandTool(Tool):
    name = "run_shell_command"
    user_friendly_name = "Run command"
    schema = {
        "description": "Run a shell command in the workspace. Flags is_read_only and is_risky are hints.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "is_read_only": {"type": "boolean"},
                "is_risky": {"type": "boolean"},
                "wait_until_completion": {"type": "boolean"},
                "rationale": {"type": "string"},
            },
            "required": ["command"],
        },
    }

    def should_autoexecute(self, ctx, args):
        command = (args or {}).get("command") or ""
        is_read_only = (args or {}).get("is_read_only")
        is_risky = (args or {}).get("is_risky")
        return decision_to_autoexecute(
            can_autoexecute_command(
                command,
                ctx.profile,
                ctx,
                is_read_only=is_read_only,
                is_risky=is_risky,
            )
        )

    def execute(self, ctx, args):
        if (args or {}).get("wait_until_completion") is False:
            command = (args or {}).get("command") or ""
            argv = command_to_argv(command) or ["bash", "-lc", command]
            proc = subprocess.Popen(
                argv,
                cwd=str(ctx.workspace),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            ctx.running_procs.append(proc)
            return {"status": "ok", "background": True, "pid": proc.pid}
        return run_shell_command(ctx, args)

    def user_friendly_name_for(self, args):
        label = command_tick((args or {}).get("command") or "")
        if not label:
            return labels("Running command", "Ran command", ask="Run command")
        return labels("Running %s" % label, "Ran %s" % label, ask="Run %s" % label)
