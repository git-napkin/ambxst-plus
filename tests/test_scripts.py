#!/usr/bin/env python3
"""Unit tests for Ambxst[+] Python scripts."""

import json
import os
import re
import sqlite3
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

    def test_openssl_fallback_roundtrip(self):
        machine_key = b"test-machine-id-1234"
        original = "sk-openrouter-fallback-test"
        blob = self.keystore._openssl_encrypt(original, machine_key)
        self.assertTrue(blob.startswith("o1:"))
        self.assertEqual(self.keystore.decrypt(blob, machine_key), original)

    def test_get_machine_id_fallback(self):
        """get_machine_id should return bytes."""
        result = self.keystore.get_machine_id()
        self.assertIsInstance(result, bytes)
        self.assertTrue(len(result) > 0)

    def _run_keystore(self, db, env, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "keystore.py"), str(db), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_multiple_keys_per_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_home = Path(tmp) / "data"
            db = data_home / "ambxst+" / "keys.db"
            db.parent.mkdir(parents=True)
            env = os.environ.copy()
            env["XDG_DATA_HOME"] = str(data_home)
            first = self._run_keystore(db, env, "add", "openai", "sk-aaa-aaaa", "work")
            second = self._run_keystore(db, env, "add", "openai", "sk-bbb-bbbb", "personal")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            listed = json.loads(self._run_keystore(db, env, "list").stdout)
            self.assertEqual(len(listed), 2)
            self.assertEqual({row["label"] for row in listed}, {"work", "personal"})
            got = json.loads(self._run_keystore(db, env, "get", "openai").stdout)
            self.assertEqual(got["api_key"], "sk-aaa-aaaa")
            by_id = json.loads(
                self._run_keystore(db, env, "get", "openai#%s" % listed[1]["id"]).stdout
            )
            self.assertEqual(by_id["api_key"], "sk-bbb-bbbb")
            with patch.dict(os.environ, env, clear=False):
                self.assertEqual(
                    self.keystore.get_provider_key(str(db), "openai#%s" % listed[1]["id"]),
                    "sk-bbb-bbbb",
                )
            removed = self._run_keystore(db, env, "delete-id", str(listed[0]["id"]))
            self.assertEqual(removed.returncode, 0, removed.stderr)
            remaining = json.loads(self._run_keystore(db, env, "list").stdout)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0]["label"], "personal")

    def test_migrates_legacy_provider_primary_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_home = Path(tmp) / "data"
            db = data_home / "ambxst+" / "keys.db"
            db.parent.mkdir(parents=True)
            env = os.environ.copy()
            env["XDG_DATA_HOME"] = str(data_home)
            conn = sqlite3.connect(str(db))
            conn.execute(
                """
                CREATE TABLE api_keys (
                    provider TEXT PRIMARY KEY,
                    api_key TEXT NOT NULL,
                    endpoint TEXT DEFAULT '',
                    custom_curl TEXT DEFAULT ''
                )
                """
            )
            encrypted = self.keystore.encrypt("sk-legacy", self.keystore.get_machine_id())
            conn.execute(
                "INSERT INTO api_keys (provider, api_key) VALUES (?, ?)",
                ("openai", encrypted),
            )
            conn.commit()
            conn.close()
            listed = json.loads(self._run_keystore(db, env, "list").stdout)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["provider"], "openai")
            self.assertEqual(listed[0]["api_key"], "sk-legacy")
            self.assertIn("id", listed[0])
            extra = self._run_keystore(db, env, "add", "openai", "sk-new", "second")
            self.assertEqual(extra.returncode, 0, extra.stderr)
            listed = json.loads(self._run_keystore(db, env, "list").stdout)
            self.assertEqual(len(listed), 2)


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
        self.assertIn('pipe="${XDG_RUNTIME_DIR:-/tmp}/ambxst+_ipc.pipe"', cli)
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
        src = self._read("modules/services/CameraService.qml")
        self.assertIn("_syncRunning", src)
        self.assertIn("startDelay", src)
        shell = self._read("shell.qml")
        self.assertNotIn("CameraService._syncRunning.toString()", shell)
        self.assertNotIn("CameraService.update.toString()", shell)

    def test_shell_defers_heavy_overlays(self):
        shell = self._read("shell.qml")
        self.assertNotIn("import qs.modules.widgets.assistant", shell)
        self.assertNotIn("import qs.modules.widgets.overview", shell)
        self.assertNotIn("sourceComponent: AssistantPopup", shell)
        self.assertIn("modules/widgets/assistant/AssistantPopup.qml", shell)
        shortcuts = self._read("modules/services/GlobalShortcuts.qml")
        self.assertNotIn("Ai.stopComputerUse", shortcuts)
        self.assertIn("ComputerUse.stop", shortcuts)
        dash = self._read("modules/widgets/dashboard/Dashboard.qml")
        self.assertNotIn("sourceComponent: unifiedLauncherComponent", dash)

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


class TestKeystoreOpensslFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "keystore", SCRIPTS_DIR / "keystore.py"
        )
        cls.keystore = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.keystore)

    def test_openssl_roundtrip_without_cryptography_module(self):
        machine_key = b"test-machine-id-1234"
        original = "sk-openrouter-fallback-test"
        blob = self.keystore._openssl_encrypt(original, machine_key)
        self.assertTrue(blob.startswith("o1:"))
        self.assertEqual(self.keystore.decrypt(blob, machine_key), original)

    def test_add_list_with_system_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_home = Path(tmp) / "data"
            db = data_home / "ambxst+" / "keys.db"
            db.parent.mkdir(parents=True)
            env = os.environ.copy()
            env["XDG_DATA_HOME"] = str(data_home)
            added = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "keystore.py"),
                    str(db),
                    "add",
                    "openrouter",
                    "sk-or-test-key-1234",
                    "work",
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(added.returncode, 0, added.stderr or added.stdout)
            listed = json.loads(
                subprocess.run(
                    [sys.executable, str(SCRIPTS_DIR / "keystore.py"), str(db), "list"],
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                ).stdout
            )
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["provider"], "openrouter")
            self.assertEqual(listed[0]["label"], "work")
            self.assertEqual(listed[0]["api_key"], "sk-or-test-key-1234")


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


class TestOpenAiBaseUrls(unittest.TestCase):
    def test_normalize_and_models_url(self):
        from ai.providers.base import chat_completions_url, models_url, normalize_openai_base

        self.assertEqual(
            normalize_openai_base("https://api.example.com/v1/chat/completions"),
            "https://api.example.com/v1",
        )
        self.assertEqual(
            normalize_openai_base("https://api.example.com/v1/"),
            "https://api.example.com/v1",
        )
        self.assertEqual(
            models_url("https://openrouter.ai/api/v1"),
            "https://openrouter.ai/api/v1/models",
        )
        self.assertEqual(
            models_url("https://api.openai.com"),
            "https://api.openai.com/v1/models",
        )
        self.assertEqual(
            chat_completions_url("https://api.example.com/v1"),
            "https://api.example.com/v1/chat/completions",
        )
        self.assertEqual(
            chat_completions_url("https://api.example.com/v1/chat/completions"),
            "https://api.example.com/v1/chat/completions",
        )

    def test_list_models_fetches_custom_v1_models(self):
        from ai.list_models import list_models

        class Ctx:
            def get_key(self, provider):
                return "sk-custom" if provider == "custom" else ""

            def list_keys(self, provider):
                if provider != "custom":
                    return []
                return [{"id": 1, "label": "work", "api_key": "sk-custom"}]

        calls = []

        def fake_get(url, headers=None, timeout=20):
            calls.append(url)
            return {"data": [{"id": "local-llama"}, {"id": "local-coder"}]}

        with patch("ai.list_models._get", side_effect=fake_get):
            models = list_models(Ctx(), custom_endpoint="https://example.com/v1")
        self.assertEqual(calls, ["https://example.com/v1/models"])
        self.assertEqual([m["model"] for m in models], ["local-llama", "local-coder"])
        self.assertEqual(models[0]["name"], "Local Llama · work")
        self.assertTrue(all(m["provider"] == "custom" for m in models))
        self.assertTrue(all(m["endpoint"] == "https://example.com/v1" for m in models))

    def test_manual_custom_models_override_display_name(self):
        from ai.list_models import list_models

        class Ctx:
            def get_key(self, provider):
                return ""

            def list_keys(self, provider):
                return []

        models = list_models(
            Ctx(),
            custom_endpoint="https://example.com/v1",
            custom_models=[{"model": "local-llama", "name": "House Llama"}],
            custom_name="Homelab",
        )
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["model"], "local-llama")
        self.assertEqual(models[0]["name"], "House Llama")
        self.assertEqual(models[0]["provider"], "custom")

    def test_ignore_catalog_skips_custom_v1_models(self):
        from ai.list_models import list_models

        class Ctx:
            def get_key(self, provider):
                return "sk-custom" if provider == "custom" else ""

            def list_keys(self, provider):
                if provider != "custom":
                    return []
                return [{"id": 1, "label": "work", "api_key": "sk-custom"}]

        calls = []

        def fake_get(url, headers=None, timeout=20):
            calls.append(url)
            return {"data": [{"id": "local-llama"}, {"id": "local-coder"}]}

        with patch("ai.list_models._get", side_effect=fake_get):
            models = list_models(
                Ctx(),
                custom_endpoint="https://example.com/v1",
                ignore_catalog={"custom": True},
                manual_models={"custom": [{"model": "only-this", "name": "Pinned"}]},
            )
        self.assertEqual(calls, [])
        self.assertEqual([m["model"] for m in models], ["only-this"])
        self.assertEqual(models[0]["name"], "Pinned")

    def test_ignore_catalog_skips_openai_and_keeps_manuals(self):
        from ai.list_models import list_models

        class Ctx:
            def get_key(self, provider):
                return "sk-openai" if provider == "openai" else ""

            def list_keys(self, provider):
                if provider != "openai":
                    return []
                return [{"id": 1, "label": "home", "api_key": "sk-openai"}]

        calls = []

        def fake_get(url, headers=None, timeout=20):
            calls.append(url)
            return {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}

        with patch("ai.list_models._get", side_effect=fake_get):
            models = list_models(
                Ctx(),
                ignore_catalog={"openai": True},
                manual_models={"openai": [{"model": "gpt-4.1", "name": "GPT 4.1"}]},
            )
        self.assertEqual(calls, [])
        self.assertEqual([m["model"] for m in models], ["gpt-4.1"])
        self.assertEqual(models[0]["provider"], "openai")
        self.assertEqual(models[0]["name"], "GPT 4.1")

    def test_manual_models_override_catalog_display_name(self):
        from ai.list_models import list_models

        class Ctx:
            def get_key(self, provider):
                return "sk-custom" if provider == "custom" else ""

            def list_keys(self, provider):
                if provider != "custom":
                    return []
                return [{"id": 1, "label": "work", "api_key": "sk-custom"}]

        def fake_get(url, headers=None, timeout=20):
            return {"data": [{"id": "local-llama"}, {"id": "local-coder"}]}

        with patch("ai.list_models._get", side_effect=fake_get):
            models = list_models(
                Ctx(),
                custom_endpoint="https://example.com/v1",
                manual_models={"custom": [{"model": "local-llama", "name": "House Llama"}]},
            )
        self.assertEqual([m["model"] for m in models], ["local-coder", "local-llama"])
        llama = [m for m in models if m["model"] == "local-llama"][0]
        self.assertEqual(llama["name"], "House Llama")

    def test_openai_style_prefers_api_display_name(self):
        from ai.list_models import _display_name, _humanize_model_id

        self.assertEqual(
            _display_name({"id": "openai/gpt-4o", "name": "GPT-4o"}, "openai/gpt-4o"),
            "GPT-4o",
        )
        self.assertEqual(
            _humanize_model_id("~openai/gpt-luna-latest"),
            "GPT Luna Latest",
        )


    def test_list_keys_cache_clears(self):
        from ai.tools.registry import ToolContext

        ctx = ToolContext()
        ctx._listed_keys["openrouter"] = [{"id": 1, "label": "", "api_key": "stale"}]
        ctx.api_keys["openrouter"] = "stale"
        ctx.clear_key_cache()
        self.assertEqual(ctx._listed_keys, {})
        self.assertEqual(ctx.api_keys, {})


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
        self.assertEqual(
            can_autoexecute_command("uname -r", ctx.profile, ctx, is_read_only=True),
            "allow",
        )
        self.assertEqual(
            can_autoexecute_command("uname -r > /tmp/x", ctx.profile, ctx, is_read_only=True),
            ASK,
        )

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


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class TestComputerUse(unittest.TestCase):
    def test_policy_advertise(self):
        from ai.tools.registry import advertised_tool_names
        from ai.tools.computer_use import RequestComputerUseTool, UseComputerTool

        never = _ctx(".", execution_profile={"computerUse": "Never"})
        names = advertised_tool_names(never)
        self.assertNotIn("request_computer_use", names)
        self.assertNotIn("use_computer", names)
        self.assertEqual(RequestComputerUseTool().should_autoexecute(never, {"task_summary": "x"}), "deny")
        denied = RequestComputerUseTool().execute(never, {"task_summary": "x"})
        self.assertEqual(denied["status"], "error")

        ask = _ctx(".", execution_profile={"computerUse": "AlwaysAsk"})
        names = advertised_tool_names(ask)
        self.assertIn("request_computer_use", names)
        self.assertIn("use_computer", names)
        self.assertEqual(RequestComputerUseTool().should_autoexecute(ask, {"task_summary": "x"}), "ask")
        self.assertEqual(UseComputerTool().should_autoexecute(ask, {"action": "snapshot"}), "ask")
        ask.computer_use_approved = True
        self.assertEqual(UseComputerTool().should_autoexecute(ask, {"action": "snapshot"}), True)

        allow = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        self.assertEqual(RequestComputerUseTool().should_autoexecute(allow, {"task_summary": "x"}), True)
        self.assertEqual(UseComputerTool().should_autoexecute(allow, {"action": "click"}), True)

    def test_grant_survives_apply_init(self):
        from io import StringIO
        from ai.agent import Agent

        agent = Agent(stdin=StringIO(), stdout=StringIO())
        payload = {
            "execution_profile": {"computerUse": "AlwaysAsk"},
            "enabled_tools": ["native"],
            "system_prompt": "hi",
        }
        agent.apply_init(payload)
        agent.computer_use_approved = True
        agent.computer_use_nodes = [{"index": 0, "name": "Save"}]
        agent.computer_use_last_shot = {"scale": 0.5, "monitor_scale": 1}
        agent.apply_init(payload)
        self.assertTrue(agent.computer_use_approved)
        self.assertTrue(agent.ctx.computer_use_approved)
        self.assertEqual(agent.ctx.computer_use_nodes[0]["name"], "Save")
        self.assertEqual(agent.ctx.computer_use_last_shot["scale"], 0.5)
        self.assertIn("Computer use is available", agent.system_prompt)

        agent.handle_command({"cmd": "end_computer_use"})
        self.assertFalse(agent.computer_use_approved)
        self.assertEqual(agent.computer_use_nodes, [])

        agent.computer_use_approved = True
        agent.ctx.computer_use_approved = True
        agent.handle_command({"cmd": "cancel"})
        self.assertFalse(agent.computer_use_approved)
        self.assertFalse(agent.ctx.computer_use_approved)

    def test_preview_to_logical_per_monitor(self):
        from ai.computer_use.coords import preview_to_logical

        x, y = preview_to_logical(
            100,
            50,
            {
                "scale": 0.5,
                "monitor_scale": 1,
                "origin_x": 0,
                "origin_y": 0,
                "crop_x": 0,
                "crop_y": 0,
            },
        )
        self.assertEqual((x, y), (200, 100))
        x, y = preview_to_logical(
            10,
            10,
            {
                "scale": 0.5,
                "monitor_scale": 2,
                "origin_x": 100,
                "origin_y": 200,
                "crop_x": 40,
                "crop_y": 80,
            },
        )
        self.assertEqual((x, y), (100 + int(round((10 / 0.5 + 40) / 2)), 200 + int(round((10 / 0.5 + 80) / 2))))

    def test_payload_caps(self):
        from ai.computer_use.screenshot import (
            ABSOLUTE_MAX_BYTES,
            ABSOLUTE_MAX_DIMENSION,
            DEFAULT_JPEG_QUALITY,
            DEFAULT_MAX_BYTES,
            DEFAULT_MAX_DIMENSION,
            MIN_MAX_BYTES,
            _clamp_bytes,
            _clamp_dim,
            identify_size,
            prepare_payload,
        )

        self.assertEqual(DEFAULT_MAX_DIMENSION, 1280)
        self.assertEqual(DEFAULT_JPEG_QUALITY, 70)
        self.assertEqual(_clamp_dim(99999, 1920), ABSOLUTE_MAX_DIMENSION)
        self.assertEqual(_clamp_bytes(10), MIN_MAX_BYTES)
        self.assertEqual(_clamp_bytes(None), DEFAULT_MAX_BYTES)
        self.assertEqual(_clamp_bytes(99 * 1024 * 1024), ABSOLUTE_MAX_BYTES)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "px.png"
            path.write_bytes(PNG_1X1)
            self.assertEqual(identify_size(str(path)), (1, 1))
            payload = prepare_payload(str(path), max_width=1920, max_bytes=2 * 1024 * 1024)
            self.assertEqual(payload["coordinate_width"], 1)
            self.assertEqual(payload["scale"], 1.0)
            self.assertNotIn("\n", payload["image_base64"])
            self.assertLessEqual(payload["bytes"], payload["max_bytes"])
            self.assertEqual(payload["mime_type"], "image/png")

    def test_compact_tree_and_selectors(self):
        from ai.computer_use.atspi import _states_from_flags, compact_tree, resolve_node

        nodes = [
            {"index": 0, "depth": 0, "parent_index": None, "name": "App", "role": "application", "actions": [], "text": "", "states": []},
            {"index": 1, "depth": 2, "parent_index": 0, "name": "", "role": "filler", "actions": [], "text": "", "states": []},
            {"index": 2, "depth": 2, "parent_index": 0, "name": "Save", "role": "push button", "actions": [{"name": "click"}], "text": "", "states": []},
        ]
        out = compact_tree(nodes)
        self.assertEqual([n["index"] for n in out], list(range(len(out))))
        self.assertTrue(any(n.get("name") == "Save" for n in out))
        self.assertFalse(any(n.get("role") == "filler" for n in out))
        node, err = resolve_node([], {"element_index": 0})
        self.assertIsNone(node)
        self.assertIn("snapshot", err.lower())
        twins = [
            {"index": 0, "role": "push button", "name": "OK", "text": "", "states": []},
            {"index": 1, "role": "push button", "name": "OK", "text": "", "states": []},
        ]
        node, err = resolve_node(twins, {"role": "push button", "name": "OK"})
        self.assertIsNone(node)
        self.assertIn("Ambiguous", err)
        self.assertIn("focused", _states_from_flags([1 << 12, 0]))

    def test_select_app_roots_pid_and_public_tree(self):
        from ai.computer_use.atspi import public_tree, select_app_roots, slim_node, tree_usable

        apps = [
            {"path": "/a", "pid": 10, "name": "Firefox", "role": "application"},
            {"path": "/b", "pid": 20, "name": "Kitty", "role": "application"},
        ]
        self.assertEqual(select_app_roots(apps, want_pid=20), ["/b"])
        self.assertEqual(select_app_roots(apps, want_name="firefox"), ["/a"])
        fat = {
            "index": 3,
            "parent_index": 0,
            "role": "push button",
            "name": "Save",
            "states": ["enabled", "sensitive", "showing", "visible"],
            "actions": [{"name": "click", "description": "press"}],
            "text": "x" * 500,
            "object_ref": "/org/a11y/atspi/accessible/3",
            "bounds": {"x": 1, "y": 2, "width": 3, "height": 4},
        }
        slim = slim_node(fat)
        self.assertNotIn("object_ref", slim)
        self.assertNotIn("bounds", slim)
        self.assertEqual(slim["actions"], ["click"])
        self.assertEqual(len(slim["text"]), 200)
        public = public_tree([fat] * 200)
        self.assertEqual(len(public), 150)
        self.assertTrue(tree_usable([fat]))
        self.assertFalse(tree_usable([{"name": "", "actions": [], "text": ""}]))
        from ai.computer_use.atspi import is_shell_app, _ref_parts

        self.assertTrue(is_shell_app({"name": "ambxst+", "role": "application"}))
        self.assertTrue(is_shell_app({"name": "quickshell", "role": ""}))
        self.assertFalse(is_shell_app({"name": "Firefox", "role": "application"}))
        self.assertEqual(
            select_app_roots(
                [
                    {"path": "/qs", "pid": 1, "name": "ambxst+", "role": "application"},
                    {"path": "/a", "pid": 10, "name": "Firefox", "role": "application"},
                ]
            ),
            ["/a"],
        )
        self.assertEqual(
            select_app_roots(
                [
                    {"path": "/a", "pid": 10, "name": "Firefox", "role": "application"},
                ],
                want_pid=99,
            ),
            [],
        )
        self.assertEqual(_ref_parts((":1.42", "/org/a11y/atspi/accessible/2")), (":1.42", "/org/a11y/atspi/accessible/2"))

    def test_snapshot_has_no_image_by_default(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool, _maybe_shot

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        ctx.computer_use_nodes = []
        windows = [{"address": "0x1", "title": "Kitty", "class": "kitty", "pid": 9, "focused": True}]
        tree = [
            {
                "index": 0,
                "role": "push button",
                "name": "Save",
                "actions": [{"name": "click"}],
                "text": "",
                "states": ["enabled"],
                "object_ref": "/a",
                "bounds": {"x": 1, "y": 1, "width": 8, "height": 8},
            }
        ]
        with patch("ai.tools.computer_use._native", return_value={"windows": windows}), patch(
            "ai.tools.computer_use.atspi.snapshot_tree", return_value=tree
        ), patch("ai.tools.computer_use.atspi.focused_element", return_value={"role": "push button", "name": "Save"}):
            out = UseComputerTool()._dispatch(ctx, "snapshot", {})
        self.assertEqual(out["status"], "ok")
        self.assertNotIn("image_base64", out)
        self.assertTrue(out["tree_usable"])
        self.assertEqual(out["accessibility_tree"][0]["name"], "Save")
        self.assertNotIn("object_ref", out["accessibility_tree"][0])
        follow = _maybe_shot(ctx, {"action": "click"}, {"status": "ok", "implemented": "atspi"})
        self.assertNotIn("image_base64", follow)

    def test_doctor_socket_probe_order_and_unverified_noscreenshare(self):
        from unittest.mock import patch
        from ai.computer_use.doctor import doctor_report, parse_layers_noscreenshare, ydotool_socket_candidates

        cands = ydotool_socket_candidates("/pref.sock")
        self.assertEqual(cands[0], "/pref.sock")
        self.assertIn("/tmp/.ydotool_socket", cands)
        self.assertIn("/run/ydotoold/socket", cands)
        with patch("ai.computer_use.doctor.find_ydotool_socket", return_value=""), patch(
            "ai.computer_use.doctor.layer_noscreenshare", return_value=False
        ):
            report = doctor_report(
                native={
                    "noscreenshare": True,
                    "screens": [{"name": "eDP-1", "scale": 1}],
                    "focused_window": {"title": "Kitty"},
                    "locked": False,
                },
                atspi_ok=False,
            )
        self.assertFalse(report["noscreenshare"])
        self.assertTrue(report["hide_for_capture"])
        self.assertFalse(report["can_click"])
        self.assertIn("coordinate_space", report)
        flagged, found = parse_layers_noscreenshare(
            {"eDP-1": [{"levels": {"2": [{"namespace": "ambxst+:computer-use", "no_screen_share": True}]}}]},
        )
        self.assertTrue(found)
        self.assertTrue(flagged)

    def test_flatten_cu_work_messages(self):
        from ai.agent import flatten_ui_messages

        flat = flatten_ui_messages(
            [
                {"role": "user", "content": "open kitty"},
                {
                    "role": "cu_work",
                    "durationMs": 3200,
                    "items": [
                        {"role": "tool_call", "name": "use_computer"},
                        {"role": "assistant", "content": "clicking"},
                    ],
                },
                {"role": "assistant", "content": "done"},
            ]
        )
        self.assertEqual([m["role"] for m in flat], ["user", "tool_call", "assistant", "assistant"])
        self.assertEqual(flat[-1]["content"], "done")

    def test_movecursor_prefers_hyprland_lua_dispatcher(self):
        from unittest.mock import patch
        from ai.computer_use import input as cu_input

        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))

            class Result:
                returncode = 0
                stdout = b"ok"
                stderr = b""

            return Result()

        with patch.object(cu_input, "_run", side_effect=fake_run), patch.object(
            cu_input, "cursor_position", return_value=(400, 500)
        ), patch(
            "ai.computer_use.input.shutil.which",
            side_effect=lambda n: "/usr/bin/" + n if n in ("hyprctl", "axctl") else None,
        ), patch("ai.computer_use.input.time.sleep"):
            self.assertTrue(cu_input.movecursor(400, 500))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "dispatch")
        self.assertIn("hl.dsp.cursor.move", calls[0][2])
        self.assertIn("400", calls[0][2])
        self.assertIn("500", calls[0][2])

    def test_movecursor_surfaces_hyprland_and_axctl_errors(self):
        from unittest.mock import patch
        from ai.computer_use import input as cu_input

        def fake_run(argv, **kwargs):
            joined = " ".join(str(a) for a in argv)

            class Result:
                returncode = 7
                stdout = b"error: 3 ')' expected near '400'"
                stderr = b""

            if "move-cursor" in joined:
                Result.returncode = 0
                Result.stdout = b"Error: method not found"
            return Result()

        with patch.object(cu_input, "_run", side_effect=fake_run), patch.object(
            cu_input, "cursor_position", return_value=(400, 400)
        ), patch(
            "ai.computer_use.input.shutil.which",
            side_effect=lambda n: "/usr/bin/" + n if n in ("hyprctl", "axctl") else None,
        ), patch("ai.computer_use.input.time.sleep"):
            with self.assertRaises(RuntimeError) as raised:
                cu_input.movecursor(400, 400)
        text = str(raised.exception)
        self.assertIn("movecursor failed", text)
        self.assertIn("method not found", text)

    def test_movecursor_eases_from_current_position(self):
        from unittest.mock import patch
        from ai.computer_use import input as cu_input

        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))

            class Result:
                returncode = 0
                stdout = b"ok"
                stderr = b""

            return Result()

        with patch.object(cu_input, "_run", side_effect=fake_run), patch.object(
            cu_input, "cursor_position", return_value=(0, 0)
        ), patch(
            "ai.computer_use.input.shutil.which",
            side_effect=lambda n: "/usr/bin/" + n if n in ("hyprctl", "axctl") else None,
        ), patch("ai.computer_use.input.time.sleep"):
            self.assertTrue(cu_input.movecursor(400, 500))
        lua = [c for c in calls if len(c) > 2 and "hl.dsp.cursor.move" in str(c[2])]
        self.assertGreaterEqual(len(lua), cu_input.MOVE_STEPS_MIN)
        self.assertIn("400", lua[-1][2])
        self.assertIn("500", lua[-1][2])

    def test_pixel_click_requires_last_shot(self):
        from ai.tools.computer_use import PIXEL_SHOT_NEEDED, UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        out = UseComputerTool()._dispatch(ctx, "click", {"x": 10, "y": 10})
        self.assertEqual(out["status"], "error")
        self.assertIn("screenshot", out["error"].lower())
        self.assertEqual(out["error"], PIXEL_SHOT_NEEDED)

    def test_click_echoes_preview_coords(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        ctx.computer_use_last_shot = {
            "scale": 0.5,
            "monitor_scale": 1,
            "origin_x": 0,
            "origin_y": 0,
            "crop_x": 0,
            "crop_y": 0,
            "width": 1280,
            "height": 720,
        }
        with patch("ai.tools.computer_use.cu_input.movecursor", return_value=True), patch(
            "ai.tools.computer_use.cu_input.click"
        ):
            out = UseComputerTool()._dispatch(ctx, "click", {"x": 100, "y": 50})
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["x"], 100)
        self.assertEqual(out["y"], 50)
        self.assertEqual(out["logical_x"], 200)
        self.assertEqual(out["logical_y"], 100)

    def test_steer_open_blocks_mutating_actions(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        with patch(
            "ai.tools.computer_use._native",
            return_value={"user_control": False, "steer_open": True, "locked": False},
        ):
            out = UseComputerTool()._one(ctx, {"action": "click", "x": 1, "y": 1})
        self.assertEqual(out["status"], "error")
        self.assertIn("steer", out["error"].lower())

    def test_computer_use_no_iter_cap(self):
        from io import StringIO
        from unittest.mock import patch
        from ai.agent import MAX_TOOL_ITERS, Agent

        agent = Agent(stdin=StringIO(), stdout=StringIO())
        payload = {
            "execution_profile": {"computerUse": "AlwaysAsk"},
            "enabled_tools": ["native"],
            "system_prompt": "hi",
            "model": {"provider": "openai", "model": "x"},
        }
        agent.apply_init(payload)
        agent.computer_use_approved = True
        agent.ctx.computer_use_approved = True
        self.assertIsNone(agent._max_tool_iters())
        agent.computer_use_approved = False
        agent.ctx.computer_use_approved = False
        self.assertEqual(agent._max_tool_iters(), MAX_TOOL_ITERS)

        class Prov:
            def __init__(self):
                self.n = 0

            def stream_chat(self, *a, **k):
                self.n += 1
                if self.n <= 26:
                    yield {"type": "tool_call", "id": "c%d" % self.n, "name": "wait", "args": {}}
                else:
                    yield {"type": "token", "text": "ok"}

        agent.computer_use_approved = True
        agent.ctx.computer_use_approved = True
        agent.messages = [{"role": "user", "content": "hi"}]
        events = []
        agent.emit = lambda ev: events.append(ev)
        agent._dispatch_tool = lambda *a, **k: {"status": "ok"}
        with patch("ai.agent.get_provider", return_value=Prov()):
            agent._run_turn()
        self.assertFalse(any(ev.get("error") == "tool iteration limit" for ev in events))
        self.assertTrue(any(ev.get("type") == "done" for ev in events))

    def test_provider_image_fixtures(self):
        from ai.providers.anthropic import _filter_messages
        from ai.providers.gemini import _contents
        from ai.providers.openai import _format_messages

        tool_msg = {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "use_computer",
            "content": "{\"status\": \"ok\"}",
            "attachments": [{"type": "image", "base64": "aaa", "mimeType": "image/png"}],
        }
        _system, anthropic = _filter_messages([tool_msg])
        block = anthropic[0]["content"][0]
        self.assertEqual(block["type"], "tool_result")
        self.assertTrue(any(item.get("type") == "image" for item in block["content"]))

        openai = _format_messages([tool_msg])
        self.assertEqual(openai[0]["role"], "tool")
        self.assertEqual(openai[1]["role"], "user")
        self.assertTrue(any(p.get("type") == "image_url" for p in openai[1]["content"]))

        _sys, gemini = _contents([tool_msg])
        kinds = [list(p.keys())[0] for p in gemini[0]["parts"]]
        self.assertIn("functionResponse", kinds)
        self.assertIn("inline_data", kinds)

    def test_window_resolve_priority(self):
        from ai.computer_use.windows import resolve_window

        windows = [
            {"address": "0x1", "class": "firefox", "title": "Mozilla Firefox", "pid": 10},
            {"address": "0x2", "class": "kitty", "title": "zsh", "pid": 20, "terminal": {"tty": "/dev/pts/3", "pid": 20, "command": "zsh", "cwd": "/tmp"}},
        ]
        self.assertEqual(resolve_window(windows, {"address": "0x2"})["pid"], 20)
        self.assertEqual(resolve_window(windows, {"tty": "pts/3"})["address"], "0x2")
        self.assertEqual(resolve_window(windows, {"pid": 10})["class"], "firefox")
        self.assertEqual(resolve_window(windows, {"title": "firefox"})["address"], "0x1")


class TestPerformanceContracts(unittest.TestCase):
    def test_ffmpeg_seeks_before_decode(self):
        from thumbgen import video_ffmpeg_cmd

        cmd = video_ffmpeg_cmd("in.mp4", "out.jpg", "scale=140:140")
        self.assertLess(cmd.index("-ss"), cmd.index("-i"))
        self.assertIn("-an", cmd)
        lockwall = (SCRIPTS_DIR / "lockwall.py").read_text()
        desktop = (SCRIPTS_DIR / "desktop_thumbgen.py").read_text()
        for src in (lockwall, desktop):
            ss = src.index('"-ss"') if '"-ss"' in src else src.index("'-ss'")
            ii = src.index('"-i"') if '"-i"' in src else src.index("'-i'")
            self.assertLess(ss, ii)

    def test_camera_monitor_uses_readlink(self):
        src = (SCRIPTS_DIR / "camera_monitor.py").read_text()
        self.assertIn("os.readlink", src)
        self.assertIn("os.scandir", src)
        self.assertNotIn("os.stat(os.path.join(fd_dir", src)

    def test_list_models_keeps_key_cache(self):
        src = (SCRIPTS_DIR / "ai" / "agent.py").read_text()
        self.assertNotIn("clear_key_cache()", src)

    def test_snapshot_reuses_tree_for_focus(self):
        src = (SCRIPTS_DIR / "ai" / "tools" / "computer_use.py").read_text()
        self.assertIn("focused_from_nodes", src)
        snapshot = src[src.index('if action == "snapshot"') : src.index('if action == "click"')]
        self.assertNotIn("focused_element", snapshot)

    def test_skill_catalog_names_skips_content(self):
        from ai.tools.read_skill import skill_catalog_names

        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "fast"
            skill.mkdir()
            (skill / "SKILL.md").write_text("# Fast\n" + ("x" * 100000))
            self.assertEqual(skill_catalog_names([tmp]), ["fast"])

    def test_weather_caches_geoip(self):
        src = (SCRIPTS_DIR / "weather.sh").read_text()
        self.assertIn("geoip.json", src)
        self.assertIn("GEOIP_TTL", src)
        self.assertNotIn("--retry 2", src)

    def test_clipboard_insert_skips_full_slurp(self):
        src = (SCRIPTS_DIR / "clipboard_insert.sh").read_text()
        self.assertNotIn("CONTENT=$(cat", src)
        self.assertIn("head -c 97", src)
        self.assertIn("readfile", src)

    def test_desktop_scan_uses_scandir(self):
        src = (SCRIPTS_DIR / "desktop_scan.py").read_text()
        self.assertIn("os.scandir", src)
        self.assertNotIn("os.listdir", src)

    def test_prune_image_attachments_keeps_newest(self):
        from ai.agent import prune_image_attachments

        msgs = [
            {"role": "user", "content": "a", "attachments": [{"type": "image", "base64": "old"}]},
            {"role": "assistant", "content": "ok"},
            {"role": "tool", "content": "{}", "attachments": [{"type": "image", "base64": "mid"}]},
            {"role": "tool", "content": "{}", "attachments": [{"type": "image", "base64": "new"}]},
        ]
        pruned = prune_image_attachments(msgs, keep=2)
        self.assertNotIn("attachments", pruned[0])
        self.assertEqual(pruned[2]["attachments"][0]["base64"], "mid")
        self.assertEqual(pruned[3]["attachments"][0]["base64"], "new")

    def test_wavyline_is_not_frame_bound(self):
        src = Path(__file__).parent.parent.joinpath("modules/components/WavyLine.qml").read_text()
        self.assertNotIn("FrameAnimation", src)
        self.assertIn("interval: 32", src)
        self.assertIn("Config.performance.wavyLine", src)

    def test_dashboard_tabs_use_string_source(self):
        dash = Path(__file__).parent.parent.joinpath("modules/widgets/dashboard/Dashboard.qml").read_text()
        self.assertNotIn("import qs.modules.widgets.dashboard.wallpapers", dash)
        self.assertNotIn("import qs.modules.widgets.dashboard.metrics", dash)
        self.assertIn('source: "wallpapers/WallpapersTab.qml"', dash)
        launcher = Path(__file__).parent.parent.joinpath("modules/widgets/launcher/LauncherView.qml").read_text()
        self.assertNotIn("import \"../dashboard/clipboard\"", launcher)
        self.assertIn("../dashboard/clipboard/ClipboardTab.qml", launcher)


if __name__ == "__main__":
    unittest.main(verbosity=2)
