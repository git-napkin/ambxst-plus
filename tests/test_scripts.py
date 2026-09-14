#!/usr/bin/env python3
"""Unit tests for Ambxst[+] Python scripts."""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


try:
    import cryptography  # noqa: F401
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False


@unittest.skipUnless(HAS_CRYPTOGRAPHY, "cryptography not installed")
class TestKeystore(unittest.TestCase):
    """Tests for keystore.py encryption/decryption."""

    @classmethod
    def setUpClass(cls):
        """Import keystore module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "keystore", SCRIPTS_DIR / "keystore.py"
        )
        cls.keystore = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.keystore)

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted text should decrypt back to original."""
        machine_key = b"test-machine-id-1234"
        original = "sk-test-1234567890abcdef"

        encrypted = self.keystore.encrypt(original, machine_key)
        decrypted = self.keystore.decrypt(encrypted, machine_key)

        self.assertEqual(decrypted, original)

    def test_encrypt_produces_different_output(self):
        """Each encryption should produce different output (random salt)."""
        machine_key = b"test-machine-id-1234"
        original = "sk-test-1234567890abcdef"

        enc1 = self.keystore.encrypt(original, machine_key)
        enc2 = self.keystore.encrypt(original, machine_key)

        self.assertNotEqual(enc1, enc2)

    def test_decrypt_invalid_returns_empty(self):
        """Decryption of invalid data should return empty string."""
        machine_key = b"test-machine-id-1234"
        result = self.keystore.decrypt("invalid-base64-data", machine_key)
        self.assertEqual(result, "")

    def test_get_machine_id_fallback(self):
        """get_machine_id should return bytes."""
        result = self.keystore.get_machine_id()
        self.assertIsInstance(result, bytes)
        self.assertTrue(len(result) > 0)


class TestSystemMonitor(unittest.TestCase):
    """Tests for system_monitor.py."""

    @classmethod
    def setUpClass(cls):
        """Import system_monitor module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "system_monitor", SCRIPTS_DIR / "system_monitor.py"
        )
        cls.monitor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.monitor)

    def test_system_monitor_initialization(self):
        """SystemMonitor should initialize with default values."""
        monitor = self.monitor.SystemMonitor(disks=["/"])
        self.assertEqual(monitor.prev_cpu_total, 0)
        self.assertEqual(monitor.prev_cpu_idle, 0)
        self.assertEqual(monitor.monitored_disks, ["/"])

    def test_cpu_usage_in_range(self):
        """CPU usage should be between 0 and 100."""
        monitor = self.monitor.SystemMonitor(disks=["/"])
        # First call returns 0 (no previous data)
        usage = monitor.get_cpu()
        self.assertGreaterEqual(usage, 0.0)
        self.assertLessEqual(usage, 100.0)

    def test_memory_in_range(self):
        """Memory usage should be between 0 and 100."""
        monitor = self.monitor.SystemMonitor(disks=["/"])
        usage, total, used, available = monitor.get_mem()
        self.assertGreaterEqual(usage, 0.0)
        self.assertLessEqual(usage, 100.0)

    def test_disk_usage_returns_dict(self):
        """Disk usage should return a dictionary."""
        monitor = self.monitor.SystemMonitor(disks=["/"])
        usage = monitor.get_disk_usage(["/"])
        self.assertIsInstance(usage, dict)
        self.assertIn("/", usage)


class TestColorpicker(unittest.TestCase):
    """Tests for colorpicker.py."""

    @classmethod
    def setUpClass(cls):
        """Import colorpicker module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "colorpicker", SCRIPTS_DIR / "colorpicker.py"
        )
        cls.colorpicker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.colorpicker)

    def test_cmd_function_exists(self):
        """cmd function should be callable."""
        self.assertTrue(callable(self.colorpicker.cmd))

    def test_main_function_exists(self):
        """main function should be callable."""
        self.assertTrue(callable(self.colorpicker.main))

    def test_notify_shell_returns_false_without_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkfifo(os.path.join(tmp, "ambxst+_ipc.pipe"))
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": tmp}):
                ok = self.colorpicker.notify_shell({"summary": "x", "body": "y"})
            self.assertFalse(ok)

    def test_notify_shell_writes_json_when_reader_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipe = os.path.join(tmp, "ambxst+_ipc.pipe")
            os.mkfifo(pipe)
            got = {}

            def read():
                with open(pipe, "r", encoding="utf-8") as fh:
                    got["line"] = fh.readline()

            reader = threading.Thread(target=read)
            reader.start()
            time.sleep(0.1)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": tmp}):
                ok = self.colorpicker.notify_shell({
                    "summary": "Color Picked",
                    "body": "#fff",
                    "actions": [{"identifier": "hex", "clipboard": "#fff"}],
                })
            reader.join(timeout=2)
            self.assertTrue(ok)
            payload = json.loads(got["line"])
            self.assertEqual(payload["v"], "notify")
            self.assertEqual(payload["summary"], "Color Picked")
            self.assertEqual(payload["actions"][0]["clipboard"], "#fff")


class TestDesktopScan(unittest.TestCase):
    def test_scan_lists_folders_files_and_desktop_entries(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "desktop_scan", SCRIPTS_DIR / "desktop_scan.py"
        )
        scan_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan_mod)

        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "Docs"))
            with open(os.path.join(tmp, "notes.txt"), "w") as f:
                f.write("hi")
            with open(os.path.join(tmp, "App.desktop"), "w") as f:
                f.write("[Desktop Entry]\nName=Cool App\nIcon=cool-app\n")
            with open(os.path.join(tmp, ".hidden"), "w") as f:
                f.write("nope")

            items = {item["name"]: item for item in scan_mod.scan(tmp)}
            self.assertIn("Docs", items)
            self.assertEqual(items["Docs"]["type"], "folder")
            self.assertIn("notes.txt", items)
            self.assertIsNone(items["notes.txt"]["type"])
            self.assertEqual(items["Cool App"]["icon"], "cool-app")
            self.assertTrue(items["Cool App"]["isDesktopFile"])
            self.assertNotIn(".hidden", items)


REPO_ROOT = Path(__file__).parent.parent


class TestJustWorksContracts(unittest.TestCase):
    def _read(self, *parts):
        return REPO_ROOT.joinpath(*parts).read_text()

    def test_ipc_pipe_uses_runtime_dir(self):
        cli = self._read("cli.sh")
        shortcuts = self._read("modules/services/GlobalShortcuts.qml")
        self.assertIn('PIPE="${XDG_RUNTIME_DIR:-/tmp}/ambxst+_ipc.pipe"', cli)
        self.assertNotIn('PIPE="/tmp/ambxst+_ipc.pipe"', cli)
        self.assertIn("XDG_RUNTIME_DIR", shortcuts)
        self.assertNotIn('"/tmp/ambxst+_ipc.pipe"', shortcuts)

    def test_loginlock_steals_held_lock(self):
        src = self._read("scripts/loginlock.sh")
        self.assertIn('kill "$pid"', src)
        self.assertNotIn("exit 0", src)

    def test_sleep_monitor_steals_held_lock(self):
        src = self._read("scripts/sleep_monitor.sh")
        self.assertIn('kill "$pid"', src)
        self.assertNotIn("exit 0", src)

    def test_idle_service_restarts_monitors_on_clean_exit(self):
        src = self._read("modules/services/IdleService.qml")
        self.assertNotIn("if (exitCode !== 0)", src)
        self.assertIn("loginLockRestartTimer", src)
        self.assertIn("sleepMonitorRestartTimer", src)

    def test_clock_uses_system_clock_minutes(self):
        src = self._read("modules/bar/clock/Clock.qml")
        self.assertIn("SystemClock", src)
        self.assertIn("SystemClock.Minutes", src)

    def test_idle_inhibitor_uses_argv(self):
        src = self._read("modules/services/IdleInhibitor.qml")
        self.assertIn("idle-inhibitor-create", src)
        self.assertNotIn('["sh", "-c", cmd]', src)
        self.assertNotIn('command: ["sh", "-c", ""]', src)

    def test_camera_watcher_has_restart_cap(self):
        src = self._read("modules/services/CameraService.qml")
        self.assertIn("_restartCap", src)

    def test_camera_service_init_uses_sync_running(self):
        src = self._read("shell.qml")
        self.assertIn("CameraService._syncRunning.toString()", src)
        self.assertNotIn("CameraService.update.toString()", src)

    def test_axctl_restore_focus_reuses_process(self):
        src = self._read("modules/services/AxctlService.qml")
        self.assertNotIn("Qt.createQmlObject", src)

    def test_weather_missing_tools_returns_error_json(self):
        import shutil
        import subprocess

        bash = shutil.which("bash") or "/bin/bash"
        env = os.environ.copy()
        env["PATH"] = "/nonexistent"
        result = subprocess.run(
            [bash, str(SCRIPTS_DIR / "weather.sh")],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout.strip().split("\n")[-1])
        self.assertIn("error", payload)
        self.assertIn("missing", payload["error"])

    def test_bar_popups_are_mutually_exclusive(self):
        popup = self._read("modules/components/BarPopup.qml")
        vis = self._read("modules/services/Visibilities.qml")
        self.assertIn('property string groupId: "bar"', popup)
        self.assertIn("registerBarPopup", vis)
        self.assertIn("barPopupGroups", vis)

    def test_workspace_slide_follows_bar_position(self):
        src = self._read("modules/services/CompositorTomlWriter.qml")
        self.assertIn("slidefadevert 20%", src)
        self.assertIn("workspace_style", src)

    def test_gtk_darkmode_is_optional(self):
        src = self._read("modules/theme/GtkGenerator.qml")
        self.assertIn("axctl darkmode", src)
        self.assertIn("command -v axctl", src)

    def test_zen_theme_writes_plus_cache(self):
        src = self._read("modules/theme/PywalZenGenerator.qml")
        self.assertIn("/ambxst+/pywalzen.css", src)
        colors = self._read("modules/theme/Colors.qml")
        self.assertIn("pywalZenGenerator.generate(colors)", colors)

    def test_screen_recorder_uses_native_capture(self):
        rec = self._read("modules/services/ScreenRecorder.qml")
        tool = self._read("modules/tools/ScreenrecordTool.qml")
        script = REPO_ROOT / "scripts" / "wf-record.sh"
        self.assertIn("wf-record.sh", rec)
        self.assertIn("-fallback-cpu-encoding yes", rec)
        self.assertIn("Notifications.notifyInternal", rec)
        self.assertNotIn('tooltip: "Portal"', tool)
        subprocess.run(["bash", "-n", str(script)], check=True)

    def test_qml_toasts_use_in_shell_notifications(self):
        for rel in (
            "modules/services/PresetsService.qml",
            "modules/services/ScreenRecorder.qml",
            "modules/services/UpdateService.qml",
            "modules/bar/clock/Pomodoro.qml",
            "modules/services/Screenshot.qml",
        ):
            src = self._read(rel)
            self.assertIn("Notifications.notifyInternal", src)
            self.assertNotIn("notify-send", src)

    def test_terminal_is_configurable(self):
        defaults = self._read("config/defaults/system.js")
        config = self._read("config/Config.qml")
        tmux = self._read("modules/widgets/dashboard/tmux/TmuxTab.qml")
        self.assertIn('"terminal": "kitty"', defaults)
        self.assertIn('property string terminal: "kitty"', config)
        self.assertIn("TerminalService.execDetached", tmux)
        self.assertNotIn("kitty -e", tmux)

    def test_cli_json_ipc_and_hyprland_guard(self):
        cli = self._read("cli.sh")
        shortcuts = self._read("modules/services/GlobalShortcuts.qml")
        self.assertIn("wallpaper-set", cli)
        self.assertIn("preset-load", cli)
        self.assertIn("is_nix_store_symlink", cli)
        self.assertIn('case "notify":', shortcuts)
        self.assertIn('case "wallpaper-set":', shortcuts)
        self.assertIn("handleNotifyRequest", shortcuts)

    def test_settings_screen_bound_before_map(self):
        src = self._read("modules/widgets/config/SettingsWindow.qml")
        self.assertIn("screen: screenByName(GlobalStates.settingsTargetScreenName)", src)
        self.assertNotIn("settingsWindow.screen =", src)

    def test_ocr_qr_reuse_screenshot_overlay(self):
        tools = self._read("modules/widgets/tools/ToolsMenu.qml")
        shot = self._read("modules/services/Screenshot.qml")
        self.assertIn('Screenshot.captureMode = "ocr"', tools)
        self.assertIn('Screenshot.captureMode = "qr"', tools)
        self.assertNotIn("ocr.sh", tools)
        self.assertIn("function _runRecognition", shot)


class TestCliPort(unittest.TestCase):
    CLI = REPO_ROOT / "cli.sh"

    def test_cli_syntax(self):
        subprocess.run(["bash", "-n", str(self.CLI)], check=True)

    def test_help_lists_wallpaper_and_preset(self):
        result = subprocess.run(
            ["bash", str(self.CLI), "help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("wallpaper <file>", result.stdout)
        self.assertIn('preset -l', result.stdout)

    def test_wallpaper_missing_file_fails_before_ipc(self):
        result = subprocess.run(
            ["bash", str(self.CLI), "wallpaper", "/no/such/ambxst-wallpaper.png"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)

    def test_preset_list_runs_without_shell(self):
        result = subprocess.run(
            ["bash", str(self.CLI), "preset", "-l"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("ambxst+ Default", result.stdout)

    def test_nix_store_symlink_detection(self):
        text = self.CLI.read_text()
        match = re.search(r"^is_nix_store_symlink\(\) \{.*?\n\}", text, re.M | re.S)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, "hyprland.lua")
            other = os.path.join(tmp, "plain.lua")
            os.symlink("/nix/store/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee-hypr/hyprland.lua", store)
            os.symlink("/tmp/elsewhere.lua", other)
            probe = match.group(0) + '\nis_nix_store_symlink "$1"\n'
            store_rc = subprocess.run(["bash", "-c", probe, "_", store]).returncode
            other_rc = subprocess.run(["bash", "-c", probe, "_", other]).returncode
            self.assertEqual(store_rc, 0)
            self.assertNotEqual(other_rc, 0)


class TestKeystorePath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "keystore", SCRIPTS_DIR / "keystore.py"
        )
        cls.keystore = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.keystore)

    def test_config_and_data_dirs_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_home = Path(tmp) / "config"
            data_home = Path(tmp) / "data"
            config_db = config_home / "ambxst+" / "keys.db"
            data_db = data_home / "ambxst+" / "keys.db"
            config_db.parent.mkdir(parents=True)
            data_db.parent.mkdir(parents=True)
            env = {"XDG_CONFIG_HOME": str(config_home), "XDG_DATA_HOME": str(data_home)}
            with patch.dict(os.environ, env, clear=False):
                self.assertTrue(self.keystore.is_db_path_allowed(config_db))
                self.assertTrue(self.keystore.is_db_path_allowed(data_db))
                local_share = Path.home() / ".local" / "share" / "ambxst+" / "keys.db"
                self.assertTrue(self.keystore.is_db_path_allowed(local_share))
                outside = Path(tmp) / "other" / "keys.db"
                outside.parent.mkdir()
                self.assertFalse(self.keystore.is_db_path_allowed(outside))

    def test_main_allows_data_dir_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_home = Path(tmp) / "data"
            db = data_home / "ambxst+" / "keys.db"
            db.parent.mkdir(parents=True)
            env = os.environ.copy()
            env["XDG_DATA_HOME"] = str(data_home)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "keystore.py"), str(db), "list"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.strip() or "[]"), [])


from ai.execution_profile import (
    ALWAYS_ASK,
    ASK,
    DENY,
    NEVER,
    ExecutionProfile,
    can_autoexecute_command,
)
from ai.protocol import (
    ALL_TOOLS,
    cancelled_result,
    decode_command,
    encode_command,
    encode_event,
)
from ai.tools.ask_user_question import AnswerWaiter, AskUserQuestionTool
from ai.tools.apply_file_diffs import apply_file_diffs
from ai.tools.diff_validation import error_already_made, error_missing_file, error_search_mismatch
from ai.tools.exa import EXA_CONTENTS_URL, EXA_SEARCH_URL, ExaContentsTool, ExaSearchTool, shape_contents_body, shape_search_body
from ai.tools.file_glob import file_glob
from ai.tools.grep import grep
from ai.tools.read_files import read_files
from ai.tools.read_skill import discover_skills, skill_catalog_names
from ai.tools.registry import ToolContext


def _ctx(workspace, **kwargs):
    profile = kwargs.pop("profile", None) or ExecutionProfile(kwargs.pop("execution_profile", None))
    ctx = ToolContext(workspace=workspace, profile=profile, **kwargs)
    ctx.emit = lambda _event: None
    return ctx


class TestAiProtocol(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        cmd = {
            "cmd": "send",
            "text": "hello",
            "attachments": [],
            "chat_id": "c1",
        }
        decoded = decode_command(encode_command(cmd))
        self.assertEqual(decoded["cmd"], "send")
        self.assertEqual(decoded["text"], "hello")
        event = encode_event({"type": "token", "text": "hi"})
        self.assertIn('"type":"token"', event)

    def test_init_is_valid_command(self):
        payload = decode_command(
            json.dumps(
                {
                    "cmd": "init",
                    "workspace": "",
                    "system_prompt": "",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "enabled_tools": ["read_files"],
                    "execution_profile": {},
                    "skill_dirs": [],
                    "keystore_db": "",
                    "custom_endpoint": "",
                    "model": {"provider": "gemini", "model": "gemini-2.0-flash"},
                    "context": {},
                }
            )
        )
        self.assertEqual(payload["cmd"], "init")

    def test_list_models_and_models_event(self):
        payload = decode_command(json.dumps({"cmd": "list_models"}))
        self.assertEqual(payload["cmd"], "list_models")
        encoded = encode_event({"type": "models", "models": []})
        self.assertIn('"type":"models"', encoded)

    def test_cancelled_for_every_tool(self):
        for name in ALL_TOOLS:
            result = cancelled_result(name)
            self.assertEqual(result["status"], "Cancelled")
            self.assertEqual(result["result"]["variant"], "Cancelled")
            self.assertEqual(result["tool"], name)
            encoded = encode_event(
                {"type": "cancelled", "tool": name, "result": result["result"]}
            )
            self.assertIn("cancelled", encoded)


class TestReadFiles(unittest.TestCase):
    def test_batch_line_ranges_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.txt"
            b = Path(tmp) / "b.txt"
            a.write_text("one\ntwo\nthree\nfour\n")
            b.write_text("alpha\nbeta\n")
            ctx = _ctx(tmp)
            result = read_files(
                ctx,
                {
                    "files": [
                        {"name": "a.txt", "lines": [{"start": 2, "end": 3}]},
                        {"name": "missing.txt"},
                        {"name": "b.txt"},
                    ]
                },
            )
            names = [item["file_name"] for item in result["files"]]
            self.assertEqual(names, ["a.txt", "b.txt"])
            self.assertEqual(result["files"][0]["content"], "two\nthree\n")
            self.assertEqual(result["files"][0]["line_range"], {"start": 2, "end": 3})
            self.assertEqual(result["files"][0]["line_count"], 4)
            self.assertFalse(result["files"][0]["truncated"])
            self.assertEqual(len(result["failed_files"]), 1)
            self.assertEqual(result["failed_files"][0]["name"], "missing.txt")
            self.assertIn(str(a.resolve()), ctx.temp_read_permissions)

    def test_locations_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "x.txt").write_text("hello\n")
            result = read_files(_ctx(tmp), {"locations": [{"name": "x.txt"}]})
            self.assertEqual(result["files"][0]["content"], "hello\n")


class TestGrep(unittest.TestCase):
    def test_returns_paths_and_line_numbers_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "src.py"
            target.write_text("alpha\nsecret needle here\nomega\n")
            result = grep(_ctx(tmp), {"queries": ["needle"], "path": "."})
            self.assertEqual(len(result["results"]), 1)
            hit = result["results"][0]
            self.assertIn("file_path", hit)
            self.assertEqual(hit["matched_lines"], [{"line_number": 2}])
            blob = json.dumps(result)
            self.assertNotIn("secret needle here", blob)

    def test_exit_1_empty_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("nothing to see\n")
            result = grep(_ctx(tmp), {"queries": ["definitely-not-here"], "path": "."})
            self.assertEqual(result["results"], [])

    def test_query_cannot_inject_command_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "pwned"
            (Path(tmp) / "note.txt").write_text("hello\n")
            result = grep(_ctx(tmp), {"queries": ["$(touch pwned)"], "path": "."})
            self.assertFalse(marker.exists())
            self.assertEqual(result["results"], [])
            calls = []
            real_run = subprocess.run

            def wrapped(*args, **kwargs):
                calls.append((args, kwargs))
                return real_run(*args, **kwargs)

            with patch("subprocess.run", side_effect=wrapped):
                grep(_ctx(tmp), {"queries": ["$(whoami)"], "path": "."})
            for args, kwargs in calls:
                self.assertFalse(kwargs.get("shell"))
                argv = args[0] if args else kwargs.get("args")
                self.assertIsInstance(argv, list)


class TestFileGlob(unittest.TestCase):
    def test_git_vs_pathlib_backends(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.py").write_text("x\n")
            (root / "skip.txt").write_text("y\n")
            pathlib_result = file_glob(_ctx(tmp), {"patterns": ["*.py"]})
            self.assertEqual(pathlib_result["backend"], "pathlib")
            self.assertIn("keep.py", pathlib_result["paths"])
            self.assertNotIn("skip.txt", pathlib_result["paths"])

            subprocess.run(["git", "init"], cwd=tmp, check=True, capture_output=True)
            subprocess.run(["git", "add", "keep.py"], cwd=tmp, check=True, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
                cwd=tmp,
                check=True,
                capture_output=True,
            )
            (root / "untracked.py").write_text("z\n")
            git_result = file_glob(_ctx(tmp), {"patterns": ["*.py"]})
            self.assertEqual(git_result["backend"], "git")
            self.assertIn("keep.py", git_result["paths"])
            self.assertNotIn("untracked.py", git_result["paths"])


class TestApplyFileDiffs(unittest.TestCase):
    def test_whitespace_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "code.py"
            path.write_text("def  foo():\n    return 1\n")
            result = apply_file_diffs(
                _ctx(tmp),
                {"edits": [{"file": "code.py", "search": "def foo():", "replace": "def bar():"}]},
            )
            self.assertEqual(result["status"], "ok")
            self.assertIn("def bar():", path.read_text())

    def test_nearest_line_numbered_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dup.txt"
            lines = ["TARGET\n"] + ["x\n"] * 48 + ["TARGET\n"]
            path.write_text("".join(lines))
            result = apply_file_diffs(
                _ctx(tmp),
                {"edits": [{"file": "dup.txt", "search": "50|TARGET", "replace": "REPLACED"}]},
            )
            self.assertEqual(result["status"], "ok")
            out = path.read_text().splitlines()
            self.assertEqual(out[0], "TARGET")
            self.assertEqual(out[49], "REPLACED")

    def test_noop_and_overlap_and_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.txt"
            path.write_text("abcdef\n")
            noop = apply_file_diffs(
                _ctx(tmp),
                {"edits": [{"file": "f.txt", "search": "abc", "replace": "abc"}]},
            )
            self.assertEqual(noop["status"], "error")
            self.assertIn("already made", noop["error"])
            self.assertEqual(noop["error"], error_already_made("f.txt"))

            overlap = apply_file_diffs(
                _ctx(tmp),
                {
                    "edits": [
                        {"file": "f.txt", "search": "abc", "replace": "XXX"},
                        {"file": "f.txt", "search": "cde", "replace": "YYY"},
                    ]
                },
            )
            self.assertEqual(overlap["status"], "ok")
            self.assertEqual(path.read_text(), "XXXdef\n")

            missing = apply_file_diffs(
                _ctx(tmp),
                {"edits": [{"file": "nope.txt", "search": "a", "replace": "b"}]},
            )
            self.assertEqual(missing["error"], error_missing_file("nope.txt"))

            mismatch = apply_file_diffs(
                _ctx(tmp),
                {"edits": [{"file": "f.txt", "search": "zzzz-not-in-file", "replace": "b"}]},
            )
            self.assertEqual(mismatch["error"], error_search_mismatch("f.txt", 1))

    def test_failed_hunk_does_not_wedge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ok.txt"
            path.write_text("hello\n")
            ctx = _ctx(tmp)
            first = apply_file_diffs(
                ctx,
                {
                    "edits": [
                        {"file": "ok.txt", "search": "hello", "replace": "world"},
                        {"file": "ok.txt", "search": "not-a-match", "replace": "nope"},
                    ]
                },
            )
            self.assertEqual(first["status"], "error")
            self.assertEqual(path.read_text(), "hello\n")
            second = apply_file_diffs(
                ctx,
                {"edits": [{"file": "ok.txt", "search": "hello", "replace": "world"}]},
            )
            self.assertEqual(second["status"], "ok")
            self.assertEqual(path.read_text(), "world\n")


class TestShellPermissions(unittest.TestCase):
    def test_denylist_beats_session_autoapprove(self):
        ctx = _ctx(".", execution_profile={"executeCommands": "AlwaysAllow"})
        ctx.autoexecute_any_action = True
        self.assertEqual(can_autoexecute_command("rm -rf /tmp/x", ctx.profile, ctx), DENY)

    def test_allowlist_under_always_ask(self):
        ctx = _ctx(".", execution_profile={"executeCommands": "AlwaysAsk"})
        self.assertEqual(can_autoexecute_command("ls -la", ctx.profile, ctx), "allow")
        self.assertEqual(can_autoexecute_command("python3 script.py", ctx.profile, ctx), ASK)

    def test_risky_and_redirection_force_ask(self):
        ctx = _ctx(".", execution_profile={"executeCommands": "AgentDecides"})
        self.assertEqual(
            can_autoexecute_command("ls", ctx.profile, ctx, is_risky=True),
            ASK,
        )
        self.assertEqual(can_autoexecute_command("ls > out.txt", ctx.profile, ctx), ASK)
        self.assertEqual(
            can_autoexecute_command("cat notes.txt", ctx.profile, ctx, is_read_only=True),
            "allow",
        )

    def test_unknown_profile_values_fail_closed(self):
        profile = ExecutionProfile(
            {
                "executeCommands": "TotallyUnknown",
                "readFiles": "nope",
                "applyCodeDiffs": "whatever",
                "askUserQuestion": "??",
                "computerUse": "please",
            }
        )
        self.assertEqual(profile.execute_commands, ALWAYS_ASK)
        self.assertEqual(profile.read_files, ALWAYS_ASK)
        self.assertEqual(profile.apply_code_diffs, ALWAYS_ASK)
        self.assertEqual(profile.ask_user_question, ALWAYS_ASK)
        self.assertEqual(profile.computer_use, NEVER)


class TestAskUserQuestion(unittest.TestCase):
    def test_waits_for_answer_questions(self):
        ctx = _ctx(".")
        waiter = AnswerWaiter()
        ctx.wait_for_answers = lambda call_id, timeout=5: waiter.wait(timeout)
        ctx.current_call_id = "q1"
        captured = []
        ctx.emit = captured.append

        def answer():
            time.sleep(0.05)
            waiter.provide([{"question_id": "color", "answer": "blue"}])

        thread = threading.Thread(target=answer)
        thread.start()
        tool = AskUserQuestionTool()
        result = tool.execute(
            ctx,
            {
                "questions": [
                    {
                        "question_id": "color",
                        "question": "Favorite color?",
                        "options": [{"label": "blue", "recommended": True}],
                    }
                ]
            },
        )
        thread.join(timeout=2)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answers"][0]["answer"], "blue")
        self.assertEqual(captured[0]["type"], "ask_user_question")


class TestReadSkill(unittest.TestCase):
    def test_discovers_direct_skill_md_children_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "volume").mkdir()
            (root / "volume" / "SKILL.md").write_text("# Volume\n")
            (root / "loose.md").write_text("ignore")
            nested = root / "nested" / "deep"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text("# Nested\n")
            (root / "broken").mkdir()
            names = skill_catalog_names([tmp])
            self.assertEqual(names, ["volume"])
            catalog = discover_skills([tmp])
            self.assertIn("volume", catalog)
            self.assertNotIn("nested", catalog)
            self.assertNotIn("loose.md", catalog)


class TestExaMockHttp(unittest.TestCase):
    def test_request_shaping(self):
        search = shape_search_body({"query": "ambxst", "num_results": 3})
        self.assertEqual(search["query"], "ambxst")
        self.assertEqual(search["numResults"], 3)
        contents = shape_contents_body({"ids": ["https://example.com"]})
        self.assertEqual(contents["ids"], ["https://example.com"])

        class FakeResp:
            def __init__(self, payload):
                self._payload = json.dumps(payload).encode("utf-8")

            def read(self):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class FakeOpener:
            def __init__(self):
                self.requests = []

            def __call__(self, request, timeout=None):
                self.requests.append(request)
                if request.full_url.endswith("/search"):
                    return FakeResp({"results": [{"title": "t", "url": "https://ex", "highlights": ["h"]}]})
                return FakeResp({"results": [{"url": "https://ex", "text": "body"}]})

        opener = FakeOpener()
        ctx = _ctx(".", execution_profile={"webSearchEnabled": True})
        ctx.http_opener = opener
        ctx.api_keys["exa"] = "test-key"
        search_out = ExaSearchTool().execute(ctx, {"query": "hello"})
        self.assertEqual(search_out["status"], "ok")
        self.assertEqual(opener.requests[0].full_url, EXA_SEARCH_URL)
        body = json.loads(opener.requests[0].data.decode("utf-8"))
        self.assertEqual(body["query"], "hello")
        headers = {k.lower(): v for k, v in opener.requests[0].header_items()}
        self.assertEqual(headers.get("x-api-key"), "test-key")

        contents_out = ExaContentsTool().execute(ctx, {"ids": ["https://ex"]})
        self.assertEqual(contents_out["status"], "ok")
        self.assertEqual(opener.requests[1].full_url, EXA_CONTENTS_URL)

        ctx.api_keys["exa"] = ""
        ctx.profile.web_search_enabled = False
        denied = ExaSearchTool().execute(ctx, {"query": "nope"})
        self.assertEqual(denied["status"], "error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
