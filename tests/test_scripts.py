#!/usr/bin/env python3
"""Unit tests for Ambxst[+] Python scripts."""

import json
import os
import re
import shutil
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
        # Assistant module URI is registered at shell scope so URL-loaded
        # AssistantPopup can resolve sibling types; the PanelWindow itself
        # stays behind Loader.active + Loader.source (not sourceComponent).
        self.assertIn("import qs.modules.widgets.assistant", shell)
        self.assertIn("import qs.modules.sidebar", shell)
        self.assertNotIn("import qs.modules.widgets.overview", shell)
        self.assertNotIn("sourceComponent: AssistantPopup", shell)
        self.assertIn("modules/widgets/assistant/AssistantPopup.qml", shell)
        shortcuts = self._read("modules/services/GlobalShortcuts.qml")
        self.assertNotIn("Ai.stopComputerUse", shortcuts)
        self.assertIn("ComputerUse.stop", shortcuts)
        dash = self._read("modules/widgets/dashboard/Dashboard.qml")
        self.assertIn("sourceComponent: unifiedLauncherComponent", dash)

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
        script_text = script.read_text()
        self.assertIn("wf-record.sh", rec)
        self.assertIn("-fallback-cpu-encoding yes", rec)
        self.assertIn("-cr full", rec)
        self.assertIn("Notifications.notifyInternal", rec)
        self.assertNotIn('tooltip: "Portal"', tool)
        self.assertIn("color_range=pc", script_text)
        self.assertIn("colorspace=bt709", script_text)
        self.assertIn("color_primaries=bt709", script_text)
        self.assertIn("color_trc=bt709", script_text)
        self.assertIn("-x yuv420p", script_text)
        subprocess.run(["bash", "-n", str(script)], check=True)

    def test_screen_recorder_full_range_bt709_tags(self):
        """wf-record.sh color flags write full-range bt.709 metadata, not untagged TV range."""
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg/ffprobe not installed")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tagged.mp4"
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=black:s=160x120:r=1,format=rgb24",
                "-frames:v", "2",
                "-vf", "scale=out_color_matrix=bt709:out_range=full,format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-color_range", "pc",
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                str(out),
            ]
            subprocess.run(cmd, check=True)
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries",
                    "stream=color_range,color_space,color_transfer,color_primaries",
                    "-of", "default=nw=1",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            text = probe.stdout
            self.assertIn("color_range=pc", text)
            self.assertIn("color_space=bt709", text)
            self.assertIn("color_transfer=bt709", text)
            self.assertIn("color_primaries=bt709", text)

    def test_qml_toasts_use_in_shell_notifications(self):
        for rel in (
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

    def test_help_lists_wallpaper(self):
        result = subprocess.run(
            ["bash", str(self.CLI), "help"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("wallpaper <file>", result.stdout)
        self.assertIn("hyprland, niri, mango", result.stdout)
        self.assertNotIn("preset -l", result.stdout)

    def test_wallpaper_missing_file_fails_before_ipc(self):
        result = subprocess.run(
            ["bash", str(self.CLI), "wallpaper", "/no/such/ambxst-wallpaper.png"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)

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

    def test_install_remove_niri_and_mango(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["XDG_CONFIG_HOME"] = str(home / ".config")
            env["XDG_DATA_HOME"] = str(home / ".local" / "share")

            niri = subprocess.run(
                ["bash", str(self.CLI), "install", "niri"],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            kdl = home / ".config" / "niri" / "config.kdl"
            share_kdl = home / ".local" / "share" / "ambxst+" / "niri.kdl"
            self.assertTrue(kdl.is_file(), niri.stdout)
            self.assertIn('include "~/.local/share/ambxst+/niri.kdl"', kdl.read_text())
            self.assertTrue(share_kdl.is_file())

            subprocess.run(
                ["bash", str(self.CLI), "remove", "niri"],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            self.assertNotIn("// Ambxst[+]", kdl.read_text())

            mango = subprocess.run(
                ["bash", str(self.CLI), "install", "mango"],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            conf = home / ".config" / "mango" / "config.conf"
            self.assertTrue(conf.is_file(), mango.stdout)
            self.assertIn("source = ~/.local/share/ambxst+/mango.conf", conf.read_text())
            subprocess.run(
                ["bash", str(self.CLI), "remove", "mango"],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
            self.assertNotIn("# Ambxst[+]", conf.read_text())

    def test_unknown_install_target_fails(self):
        result = subprocess.run(
            ["bash", str(self.CLI), "install", "sway"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("niri", result.stdout + result.stderr)


class TestUpstreamPhaseA(unittest.TestCase):
    def _read(self, rel):
        return (REPO_ROOT / rel).read_text()

    def test_pomodoro_resyncs_timer_inputs(self):
        src = self._read("modules/bar/clock/Pomodoro.qml")
        self.assertIn("function resyncTimerInputs()", src)
        self.assertIn("function resync()", src)
        self.assertIn("Qt.binding(() => tIn.value.toString().padStart(2, '0'))", src)

    def test_lockscreen_unlock_timer_fires_without_animations(self):
        src = self._read("modules/lockscreen/LockScreen.qml")
        self.assertIn("interval: Config.animDuration > 0 ? Config.animDuration * 2 : 1", src)
        self.assertIn("FingerprintService", src)
        self.assertIn("startFingerprintAuth", src)

    def test_monocle_layout_dispatches_axctl(self):
        states = self._read("modules/globals/GlobalStates.qml")
        icons = self._read("modules/theme/Icons.qml")
        actions = self._read("config/KeybindActions.js")
        button = self._read("modules/bar/LayoutSelectorButton.qml")
        self.assertIn('"monocle"', states)
        self.assertIn('["axctl", "layout", "set", layout]', states)
        self.assertIn("readonly property string monocle:", icons)
        self.assertIn('id: "monocle.focus"', actions)
        self.assertIn('case "monocle":', button)

    def test_toml_target_lists_niri_and_mango(self):
        src = self._read("modules/services/CompositorTomlWriter.qml")
        self.assertIn("[target]", src)
        self.assertIn("niri.kdl", src)
        self.assertIn("mango.conf", src)

    def test_live_hl_config_uses_axctl_raw_batch(self):
        src = self._read("modules/services/CompositorConfig.qml")
        self.assertIn("function luaLiteral", src)
        self.assertIn("function dispatchHlConfig", src)
        self.assertIn('"axctl", "config", "raw-batch"', src)
        self.assertIn("eval ", src)
        self.assertIn("GameModeService.toggled", src)

    def test_fedora_copr_and_tmux_tmpdir(self):
        installer = self._read("install.sh")
        cli = self._read("cli.sh")
        self.assertIn("lionheartp/Hyprland", installer)
        self.assertNotIn("solopasha/hyprland", installer)
        self.assertIn("TMUX_TMPDIR", cli)
        self.assertIn('export TMUX_TMPDIR="$XDG_RUNTIME_DIR"', cli)

    def test_gap_analysis_excludes_presets(self):
        src = self._read("docs/upstream-gap-analysis.md")
        self.assertIn("Won't port", src)
        self.assertIn("Official presets", src)
        self.assertIn("Porting progress", src)


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
    model = kwargs.pop("model", {"provider": "openai", "model": "gpt-4o"})
    ctx = ToolContext(workspace=workspace, profile=profile, **kwargs)
    ctx.emit = lambda _event: None
    ctx.model = model
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
                    "model": {"provider": "gemini", "model": "gemini-2.5-flash"},
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

    def test_list_models_forwards_openrouter_input_modalities(self):
        from ai.list_models import list_models

        class Ctx:
            def get_key(self, provider):
                return "sk-or" if provider == "openrouter" else ""

            def list_keys(self, provider):
                if provider != "openrouter":
                    return []
                return [{"id": None, "label": "", "api_key": "sk-or"}]

        def fake_get(url, headers=None, timeout=20):
            self.assertEqual(url, "https://openrouter.ai/api/v1/models")
            return {
                "data": [
                    {
                        "id": "openrouter/auto",
                        "name": "Auto",
                        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
                    },
                    {
                        "id": "inception/mercury-2.5",
                        "name": "Mercury 2.5",
                        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
                    },
                    {
                        "id": "acme/text-only",
                        "name": "Text Only",
                        "architecture": {"modality": "text->text", "input_modalities": ["text"]},
                    },
                ]
            }

        with patch("ai.list_models._get", side_effect=fake_get):
            models = list_models(Ctx())
        by_id = {m["model"]: m for m in models}
        self.assertEqual(by_id["openrouter/auto"]["input_modalities"], ["text", "image"])
        self.assertEqual(by_id["inception/mercury-2.5"]["input_modalities"], ["text", "image"])
        self.assertEqual(by_id["acme/text-only"]["input_modalities"], ["text"])
        from ai.models import model_supports_vision

        self.assertTrue(model_supports_vision(by_id["openrouter/auto"]))
        self.assertTrue(model_supports_vision(by_id["inception/mercury-2.5"]))
        self.assertFalse(model_supports_vision(by_id["acme/text-only"]))

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

    def test_gemini_catalog_filters_non_chat_and_dead_flash(self):
        from ai.list_models import list_models
        from ai.models import DEFAULT_MODEL_ID, gemini_catalog_keep, remap_dead_model_id

        self.assertEqual(DEFAULT_MODEL_ID, "")
        self.assertEqual(remap_dead_model_id("gemini-2.0-flash"), "")
        self.assertEqual(remap_dead_model_id("gemini-2.0-flash-lite-001"), "")
        self.assertEqual(remap_dead_model_id("gemini-2.5-flash"), "gemini-2.5-flash")
        self.assertTrue(gemini_catalog_keep("gemini-2.5-flash"))
        self.assertFalse(gemini_catalog_keep("gemini-2.0-flash"))
        self.assertFalse(gemini_catalog_keep("gemini-2.5-flash-preview-tts"))
        self.assertFalse(gemini_catalog_keep("gemini-2.5-computer-use-preview-10-2025"))
        self.assertFalse(gemini_catalog_keep("gemini-2.0-flash-live-001"))

        class Ctx:
            def get_key(self, provider):
                return "gk" if provider == "gemini" else ""

            def list_keys(self, provider):
                if provider != "gemini":
                    return []
                return [{"id": None, "label": "", "api_key": "gk"}]

        def fake_get(url, headers=None, timeout=20):
            return {
                "models": [
                    {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash"},
                    {"name": "models/gemini-2.0-flash", "displayName": "Dead"},
                    {"name": "models/gemini-2.5-flash-preview-tts", "displayName": "TTS"},
                    {"name": "models/gemini-2.5-computer-use-preview-10-2025", "displayName": "CU"},
                    {"name": "models/imagen-4.0-generate", "displayName": "Imagen"},
                ]
            }

        with patch("ai.list_models._get", side_effect=fake_get):
            models = list_models(Ctx())
        self.assertEqual([m["model"] for m in models if m["provider"] == "gemini"], ["gemini-2.5-flash"])


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
        self.assertEqual(UseComputerTool().should_autoexecute(ask, {"action": "focus"}), True)
        self.assertEqual(UseComputerTool().should_autoexecute(ask, {"action": "click", "name": "Pay now"}), "ask")

        allow = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        self.assertEqual(RequestComputerUseTool().should_autoexecute(allow, {"task_summary": "x"}), True)
        self.assertEqual(UseComputerTool().should_autoexecute(allow, {"action": "click"}), True)
        self.assertEqual(UseComputerTool().should_autoexecute(allow, {"action": "click", "critical": True}), "ask")

    def test_vision_gate_uses_current_model_and_exits(self):
        from unittest.mock import patch
        from io import StringIO
        from ai.agent import Agent
        from ai.models import model_supports_vision
        from ai.tools.computer_use import RequestComputerUseTool, UseComputerTool, VISION_UNSUPPORTED

        self.assertTrue(model_supports_vision({"model": "gpt-4o"}))
        self.assertTrue(model_supports_vision({"model": "claude-sonnet-4-5"}))
        self.assertTrue(model_supports_vision({"model": "gemini-2.5-flash"}))
        self.assertTrue(model_supports_vision("google/gemini-3-flash"))
        self.assertTrue(model_supports_vision("llava:latest"))
        self.assertFalse(model_supports_vision(""))
        self.assertFalse(model_supports_vision({"model": "gpt-3.5-turbo"}))
        self.assertFalse(model_supports_vision({"model": "o3-mini"}))
        self.assertFalse(model_supports_vision("gemini-2.5-flash-preview-tts"))
        self.assertFalse(model_supports_vision({"model": "whisper-1"}))

        native_calls = []

        def native(_ctx, name, args):
            native_calls.append((name, dict(args)))
            return {"ok": True, "locked": False}

        text = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"}, model={"provider": "openai", "model": "gpt-3.5-turbo"})
        with patch("ai.tools.computer_use._native", side_effect=native):
            denied = RequestComputerUseTool().execute(text, {"task_summary": "click the button"})
        self.assertEqual(denied["status"], "error")
        self.assertEqual(denied["code"], VISION_UNSUPPORTED)
        self.assertIn("gpt-3.5-turbo", denied["error"])
        self.assertIn("will not switch models", denied["error"])
        self.assertFalse(text.computer_use_approved)
        self.assertFalse(any(args.get("op") == "begin" for _name, args in native_calls))

        native_calls.clear()
        ok_ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"}, model={"provider": "openai", "model": "gpt-4o"})
        with patch("ai.tools.computer_use._native", side_effect=native), patch(
            "ai.tools.computer_use.atspi.probe", return_value=False
        ), patch("ai.tools.computer_use.doctor.doctor_report", return_value={"can_click": False, "can_type": False}):
            granted = RequestComputerUseTool().execute(ok_ctx, {"task_summary": "click"})
        self.assertEqual(granted["status"], "ok")
        self.assertTrue(ok_ctx.computer_use_approved)
        self.assertTrue(any(args.get("op") == "begin" for _name, args in native_calls))
        self.assertEqual(ok_ctx.model["model"], "gpt-4o")

        native_calls.clear()
        granted_then_blind = _ctx(
            ".",
            execution_profile={"computerUse": "AlwaysAllow"},
            model={"provider": "openai", "model": "gpt-3.5-turbo"},
        )
        granted_then_blind.computer_use_approved = True
        with patch("ai.tools.computer_use._native", side_effect=native):
            shot = UseComputerTool().execute(granted_then_blind, {"action": "screenshot"})
        self.assertEqual(shot["status"], "error")
        self.assertEqual(shot["code"], VISION_UNSUPPORTED)
        self.assertFalse(granted_then_blind.computer_use_approved)
        self.assertTrue(any(args.get("op") == "end" for _name, args in native_calls))
        self.assertFalse(any(args.get("op") == "begin" for _name, args in native_calls))

        stdout = StringIO()
        agent = Agent(stdin=StringIO(), stdout=stdout)
        self.assertEqual(agent.model.get("model"), "")
        self.assertEqual(agent.model.get("provider"), "")
        agent.apply_init(
            {
                "execution_profile": {"computerUse": "AlwaysAllow"},
                "enabled_tools": ["native"],
                "system_prompt": "hi",
                "model": {"provider": "openai", "model": "gpt-4o"},
            }
        )
        self.assertEqual(agent.model["model"], "gpt-4o")
        self.assertEqual(agent.ctx.model["model"], "gpt-4o")
        agent.computer_use_approved = True
        agent.ctx.computer_use_approved = True
        before = dict(agent.model)
        agent.handle_command({"cmd": "set_model", "model": {"provider": "openai", "model": "gpt-3.5-turbo"}})
        self.assertEqual(agent.model["model"], "gpt-3.5-turbo")
        self.assertNotEqual(before["model"], "gpt-3.5-turbo")
        self.assertFalse(agent.computer_use_approved)
        self.assertFalse(agent.ctx.computer_use_approved)
        logged = stdout.getvalue()
        self.assertIn('"type":"error"', logged)
        self.assertIn("vision", logged.lower())
        self.assertIn("will not switch models", logged)

    def test_vision_gate_fail_open_for_router_auto_unknown_and_metadata(self):
        from unittest.mock import patch
        from ai.models import (
            canonical_model_id,
            display_model_id,
            model_supports_vision,
        )
        from ai.tools.computer_use import RequestComputerUseTool, VISION_UNSUPPORTED

        self.assertEqual(canonical_model_id({"provider": "openrouter", "model": "openrouter/auto"}), "auto")
        self.assertEqual(
            canonical_model_id({"provider": "openrouter", "model": "openrouter/openrouter/auto"}),
            "auto",
        )
        self.assertEqual(canonical_model_id("openrouter/openrouter/auto"), "openrouter/auto")
        self.assertEqual(
            canonical_model_id({"provider": "openrouter", "model": "inception/mercury-2.5"}),
            "inception/mercury-2.5",
        )
        self.assertEqual(
            display_model_id({"provider": "openrouter", "model": "openrouter/openrouter/auto"}),
            "openrouter/auto",
        )

        self.assertTrue(model_supports_vision({"provider": "openrouter", "model": "openrouter/auto"}))
        self.assertTrue(model_supports_vision({"provider": "openrouter", "model": "auto"}))
        self.assertTrue(model_supports_vision({"provider": "openrouter", "model": "openrouter/openrouter/auto"}))
        self.assertTrue(model_supports_vision("openrouter/auto"))
        self.assertTrue(model_supports_vision({"provider": "openrouter", "model": "inception/mercury-2.5"}))
        self.assertTrue(model_supports_vision({"provider": "openrouter", "model": "openrouter/inception/mercury-2.5"}))
        self.assertTrue(model_supports_vision({"model": "some-unknown-chat-model"}))
        self.assertTrue(
            model_supports_vision(
                {
                    "provider": "openrouter",
                    "model": "inception/mercury-2.5",
                    "architecture": {
                        "modality": "text+image->text",
                        "input_modalities": ["text", "image"],
                    },
                }
            )
        )

        self.assertFalse(model_supports_vision(""))
        self.assertFalse(model_supports_vision({"provider": "openai", "model": "gpt-3.5-turbo"}))
        self.assertFalse(model_supports_vision({"model": "o3-mini"}))
        self.assertFalse(model_supports_vision({"model": "whisper-1"}))
        self.assertFalse(
            model_supports_vision(
                {
                    "provider": "openrouter",
                    "model": "acme/totally-unknown-text-only",
                    "architecture": {"modality": "text->text", "input_modalities": ["text"]},
                }
            )
        )

        native_calls = []

        def native(_ctx, name, args):
            native_calls.append((name, dict(args)))
            return {"ok": True, "locked": False}

        def _grant(model):
            native_calls.clear()
            ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"}, model=model)
            with patch("ai.tools.computer_use._native", side_effect=native), patch(
                "ai.tools.computer_use.atspi.probe", return_value=False
            ), patch("ai.tools.computer_use.doctor.doctor_report", return_value={"can_click": False}):
                return ctx, RequestComputerUseTool().execute(ctx, {"task_summary": "refresh gmail"})

        auto_ctx, granted = _grant({"provider": "openrouter", "model": "openrouter/auto"})
        self.assertEqual(granted["status"], "ok")
        self.assertTrue(auto_ctx.computer_use_approved)
        self.assertTrue(any(args.get("op") == "begin" for _name, args in native_calls))

        dup_ctx, dup_granted = _grant({"provider": "openrouter", "model": "openrouter/openrouter/auto"})
        self.assertEqual(dup_granted["status"], "ok")
        self.assertTrue(dup_ctx.computer_use_approved)

        mercury_ctx, mercury_granted = _grant({"provider": "openrouter", "model": "inception/mercury-2.5"})
        self.assertEqual(mercury_granted["status"], "ok")
        self.assertTrue(mercury_ctx.computer_use_approved)

        unknown_ctx, unknown_granted = _grant({"provider": "openrouter", "model": "acme/brand-new-chat"})
        self.assertEqual(unknown_granted["status"], "ok")
        self.assertTrue(unknown_ctx.computer_use_approved)

        text_ctx, denied = _grant({"provider": "openai", "model": "gpt-3.5-turbo"})
        self.assertEqual(denied["status"], "error")
        self.assertEqual(denied["code"], VISION_UNSUPPORTED)
        self.assertFalse(text_ctx.computer_use_approved)
        self.assertFalse(any(args.get("op") == "begin" for _name, args in native_calls))

        meta_text_ctx, meta_denied = _grant(
            {
                "provider": "openrouter",
                "model": "acme/totally-unknown-text-only",
                "input_modalities": ["text"],
            }
        )
        self.assertEqual(meta_denied["status"], "error")
        self.assertEqual(meta_denied["code"], VISION_UNSUPPORTED)
        self.assertFalse(meta_text_ctx.computer_use_approved)

    def test_critical_actions_ask_after_grant(self):
        from ai.tools.computer_use import UseComputerTool, action_is_critical
        from ai.tools.native import NativeTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow", "executeCommands": "AlwaysAsk", "readFiles": "AlwaysAsk"})
        ctx.computer_use_approved = True
        self.assertFalse(action_is_critical(ctx, {"action": "focus"}))
        self.assertFalse(action_is_critical(ctx, {"action": "click", "name": "Save"}))
        self.assertTrue(action_is_critical(ctx, {"action": "click", "name": "Pay now"}))
        self.assertTrue(action_is_critical(ctx, {"action": "click", "name": "Send"}))
        self.assertTrue(action_is_critical(ctx, {"action": "click", "action_summary": "send the email"}))
        self.assertTrue(action_is_critical(ctx, {"action": "click", "critical": True}))
        self.assertTrue(action_is_critical(ctx, {"action": "key", "key": "ctrl+enter"}))
        ctx.computer_use_nodes = [{"index": 3, "name": "Checkout"}]
        self.assertTrue(action_is_critical(ctx, {"action": "click", "element_index": 3}))
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, {"action": "focus"}), True)
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, {"action": "click", "name": "Send"}), "ask")
        self.assertEqual(NativeTool("focus_window", write=True).should_autoexecute(ctx, {}), True)
        self.assertEqual(NativeTool("get_windows", write=False).should_autoexecute(ctx, {}), True)

        idle = _ctx(".", execution_profile={"computerUse": "AlwaysAsk", "executeCommands": "AlwaysAsk"})
        self.assertEqual(NativeTool("focus_window", write=True).should_autoexecute(idle, {}), "ask")
        allow = _ctx(".", execution_profile={"computerUse": "AlwaysAllow", "executeCommands": "AlwaysAsk"})
        self.assertEqual(NativeTool("focus_window", write=True).should_autoexecute(allow, {}), True)
        self.assertEqual(NativeTool("lock", write=True).should_autoexecute(allow, {}), "ask")

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
        self.assertNotIn("Read the computer-use skill", agent.system_prompt)

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
        self.assertEqual(slim["frame"], [1, 2, 3, 4])
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
        ):
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

    def test_movecursor_teleports_from_current_position(self):
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
        self.assertEqual(len(lua), 1)
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
        self.assertEqual(out.get("next", {}).get("action"), "screenshot")

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

    def test_wait_notifies_qml_countdown(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        calls = []

        def native(_ctx, name, args):
            calls.append((name, dict(args)))
            return {"ok": True, "user_control": False, "steer_open": False, "locked": False}

        with patch("ai.tools.computer_use._native", side_effect=native), patch(
            "ai.tools.computer_use.time.sleep"
        ) as slept, patch("ai.tools.computer_use.atspi.snapshot_tree", return_value=[]), patch(
            "ai.tools.computer_use._window_list", return_value=[]
        ):
            out = UseComputerTool()._one(ctx, {"action": "wait", "ms": 5000, "observe": "none"})
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["waited_ms"], 5000)
        slept.assert_called_once_with(5.0)
        ops = [(name, args.get("op")) for name, args in calls]
        self.assertIn(("computer_use_session", "gate"), ops)
        self.assertIn(("computer_use_session", "wait_begin"), ops)
        self.assertIn(("computer_use_session", "wait_end"), ops)
        begin = next(args for name, args in calls if args.get("op") == "wait_begin")
        self.assertEqual(begin["ms"], 5000)

    def test_computer_use_hud_driving_contracts(self):
        hud = Path(__file__).parent.parent.joinpath("modules/widgets/assistant/ComputerUseHud.qml").read_text()
        service = Path(__file__).parent.parent.joinpath("modules/services/ComputerUse.qml").read_text()
        self.assertIn("interval: 2500", hud)
        self.assertNotIn("interval: 3000", hud)
        self.assertNotIn('qsTr("Waiting")', hud)
        self.assertIn('qsTr("Waiting for %1s")', hud)
        self.assertIn("id: keySink", hud)
        self.assertIn("function printableFromEvent", hud)
        self.assertIn("function revealOutput", hud)
        self.assertNotIn("bumpHideTimer", hud)
        handle = hud[hud.index("function handleUserKey") : hud.index("function submitSteer")]
        self.assertIn("if (!ch.length)", handle)
        self.assertLess(handle.index("if (!ch.length)"), handle.rindex("hud.openSteer(ch)"))
        reveal = hud[hud.index("function revealOutput") : hud.index("FocusGrab")]
        self.assertIn("hideTimer.restart()", reveal)
        presence = hud[hud.index("function refreshPresence") : hud.index("function revealOutput")]
        tail = presence.rsplit("if (!hud.assistantText.length)", 1)[-1]
        self.assertNotIn("hud.cardVisible = true;", tail)
        chat = hud[hud.index("function onChatModelChanged") : hud.index("function onChatModelChanged") + 160]
        self.assertIn("hud.refreshPresence();", chat)
        self.assertNotIn("hud.revealOutput();", chat)
        session = hud[hud.index("function onSessionActiveChanged") : hud.index("function onUserHasControlChanged")]
        self.assertIn("hud.revealOutput();", session)
        self.assertIn("pointerChrome: ComputerUse.userHasControl", hud)
        self.assertIn("visible: hud.pointerChrome", hud)
        self.assertNotIn('qsTr("Take control")', hud)
        self.assertIn("grantedIdle", service)
        self.assertIn("function markAgentIdle", service)
        self.assertIn("function markAgentDriving", service)
        self.assertIn("grantedIdle", hud)
        self.assertIn("wait_begin", service)
        self.assertIn("wait_end", service)
        self.assertIn("function startWait", service)

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
        self.assertNotIn("inline_data", kinds)
        self.assertEqual(gemini[1]["role"], "user")
        self.assertIn("inline_data", [list(p.keys())[0] for p in gemini[1]["parts"]])

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

    def test_observe_after_click_returns_tree(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        ctx.computer_use_last_shot = {
            "scale": 1,
            "monitor_scale": 1,
            "origin_x": 0,
            "origin_y": 0,
            "crop_x": 0,
            "crop_y": 0,
            "width": 100,
            "height": 100,
        }
        tree = [{"index": 0, "role": "push button", "name": "OK", "actions": [{"name": "click"}], "text": "OK", "states": []}]

        def native(_ctx, name, args):
            if args.get("op") == "gate":
                return {"ok": True, "user_control": False, "steer_open": False, "locked": False}
            if name == "get_windows":
                return {"windows": [{"address": "0x1", "title": "App", "focused": True, "pid": 1}]}
            return {"ok": True}

        with patch("ai.tools.computer_use._native", side_effect=native), patch(
            "ai.tools.computer_use.cu_input.movecursor", return_value=True
        ), patch("ai.tools.computer_use.cu_input.click"), patch(
            "ai.tools.computer_use.atspi.snapshot_tree", return_value=tree
        ):
            out = UseComputerTool()._one(ctx, {"action": "click", "x": 10, "y": 10})
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["tree_usable"])
        self.assertEqual(out["accessibility_tree"][0]["name"], "OK")
        self.assertNotIn("image_base64", out)

    def test_click_falls_back_to_cached_bounds(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        ctx.computer_use_nodes = [
            {
                "index": 0,
                "role": "label",
                "name": "Icon",
                "actions": [],
                "text": "",
                "states": [],
                "bounds": {"x": 10, "y": 20, "width": 40, "height": 10},
            }
        ]
        moved = []
        with patch("ai.tools.computer_use.cu_input.movecursor", side_effect=lambda x, y: moved.append((x, y))), patch(
            "ai.tools.computer_use.cu_input.click"
        ):
            out = UseComputerTool()._dispatch(ctx, "click", {"element_index": 0})
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["implemented"], "bounds")
        self.assertEqual(moved, [(30.0, 25.0)])

    def test_type_does_not_rewalk_focused_element(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        ctx.computer_use_nodes = [{"index": 0, "role": "text", "states": ["focused", "editable"], "supports_editable_text": True}]
        with patch("ai.tools.computer_use._with_inject", side_effect=lambda _ctx, fn: fn()), patch(
            "ai.tools.computer_use.cu_input.type_text", return_value=True
        ), patch("ai.tools.computer_use.atspi.focused_element") as walked:
            out = UseComputerTool()._dispatch(ctx, "type", {"text": "hi"})
        walked.assert_not_called()
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["focused"]["role"], "text")

    def test_actions_batch_honored_with_top_level_action(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        seen = []

        def one(self, ctx, step, observe=True):
            seen.append((step.get("action"), observe))
            return {"status": "ok", "action": step.get("action")}

        with patch.object(UseComputerTool, "_one", one):
            out = UseComputerTool().execute(ctx, {"action": "click", "actions": [{"action": "type", "text": "x"}]})
        self.assertEqual(out["status"], "ok")
        self.assertEqual(seen, [("click", False), ("type", True)])

    def test_snapshot_auto_shots_when_tree_unusable(self):
        from unittest.mock import patch
        from ai.tools.computer_use import UseComputerTool

        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        with patch("ai.tools.computer_use._window_list", return_value=[]), patch(
            "ai.tools.computer_use.atspi.snapshot_tree", return_value=[{"name": "", "actions": [], "text": ""}]
        ), patch(
            "ai.tools.computer_use._capture",
            return_value={"status": "ok", "image_base64": "abc", "mime_type": "image/jpeg", "width": 10, "height": 10},
        ):
            out = UseComputerTool()._dispatch(ctx, "snapshot", {})
        self.assertEqual(out["status"], "ok")
        self.assertFalse(out["tree_usable"])
        self.assertEqual(out["image_base64"], "abc")

    def test_grant_survives_assistant_done(self):
        from io import StringIO
        from unittest.mock import patch
        from ai.agent import Agent

        agent = Agent(stdin=StringIO(), stdout=StringIO())
        agent.apply_init({"execution_profile": {"computerUse": "AlwaysAsk"}, "enabled_tools": ["native"], "system_prompt": "hi"})
        agent.computer_use_approved = True
        agent.ctx.computer_use_approved = True
        events = []
        agent.emit = lambda ev: events.append(ev)

        class Prov:
            def stream_chat(self, *a, **k):
                yield {"type": "token", "text": "clicked"}

        agent.messages = [{"role": "user", "content": "hi"}]
        with patch("ai.agent.get_provider", return_value=Prov()):
            agent._run_turn()
        self.assertTrue(agent.computer_use_approved)
        self.assertTrue(any(ev.get("type") == "done" for ev in events))

    def test_gemini_tool_call_ids_are_unique(self):
        from unittest.mock import patch
        from ai.providers.gemini import GeminiProvider

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def close(self):
                return None

        lines = [
            'data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"use_computer","args":{"action":"click"}}}]}}]}',
            'data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"use_computer","args":{"action":"type"}}}]}}]}',
        ]
        with patch("ai.providers.gemini.post_request", return_value=Resp()), patch(
            "ai.providers.gemini.iter_lines", return_value=lines
        ):
            events = list(GeminiProvider().stream_chat([], [], None, None, {"model": "gemini-2.5-flash"}, "k"))
        ids = [e["id"] for e in events if e.get("type") == "tool_call"]
        self.assertEqual(ids, ["use_computer#1", "use_computer#2"])

    def test_native_window_schemas_and_screenshot_alias(self):
        from unittest.mock import patch
        from ai.tools.native import NativeTool

        windows = NativeTool("get_windows", write=False)
        focus = NativeTool("focus_window", write=True)
        self.assertIn("address", focus.schema["parameters"]["properties"])
        self.assertIn("windows", windows.schema["description"].lower())
        shot = NativeTool("screenshot", write=True)
        self.assertIn("overlay", shot.schema["description"].lower())
        ctx = _ctx(".", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        with patch("ai.tools.computer_use.UseComputerTool") as aliased:
            aliased.return_value.execute.return_value = {"status": "ok", "source": "grim"}
            out = shot.execute(ctx, {})
        self.assertEqual(out["source"], "grim")
        aliased.return_value.execute.assert_called_once()

    def test_inline_skill_and_defaults(self):
        from io import StringIO
        from ai.agent import Agent

        agent = Agent(stdin=StringIO(), stdout=StringIO())
        self.assertEqual(agent.model["model"], "")
        self.assertEqual(agent.model["provider"], "")
        skill_root = Path(__file__).parent.parent / "assets" / "ai" / "skills"
        agent.apply_init(
            {
                "execution_profile": {"computerUse": "AlwaysAsk"},
                "enabled_tools": ["native"],
                "system_prompt": "hi",
                "skill_dirs": [str(skill_root)],
            }
        )
        self.assertIn("action=snapshot", agent.system_prompt)
        self.assertIn("stays granted", agent.system_prompt)
        self.assertNotIn("Read the computer-use skill", agent.system_prompt)
        self.assertNotIn("request_computer_use again", agent.system_prompt)

    def test_doctor_omits_window_dump(self):
        from unittest.mock import patch
        from ai.computer_use.doctor import doctor_report

        with patch("ai.computer_use.doctor.find_ydotool_socket", return_value=""), patch(
            "ai.computer_use.doctor.layer_noscreenshare", return_value=False
        ):
            report = doctor_report(
                native={"screens": [{"name": "eDP-1"}], "windows": [{"title": "Kitty"}], "locked": False},
                atspi_ok=True,
            )
        self.assertNotIn("windows", report)
        self.assertNotIn("screens", report)
        self.assertTrue(report["tree"])
        self.assertIn("can_click", report)


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
        typing = src[src.index('if action == "type"') : src.index('if action == "key"')]
        self.assertNotIn("focused_element", typing)

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
        # Tabs must use module imports + sourceComponent so same-directory
        # types (SchemeSelector, ResourceItem) resolve; bare file Loader.source fails.
        self.assertIn("import qs.modules.widgets.dashboard.wallpapers", dash)
        self.assertIn("import qs.modules.widgets.dashboard.metrics", dash)
        self.assertIn("sourceComponent: wallpapersComponent", dash)
        self.assertIn("sourceComponent: metricsComponent", dash)
        self.assertNotIn('source: Qt.resolvedUrl("wallpapers/WallpapersTab.qml")', dash)
        launcher = Path(__file__).parent.parent.joinpath("modules/widgets/launcher/LauncherView.qml").read_text()
        self.assertIn("import qs.modules.widgets.dashboard.clipboard", launcher)
        self.assertIn("import qs.modules.widgets.dashboard.tmux", launcher)
        self.assertIn("sourceComponent: Component", launcher)
        tools = Path(__file__).parent.parent.joinpath("modules/widgets/tools/ToolsMenuView.qml").read_text()
        self.assertIn("import qs.modules.widgets.tools", tools)
        power = Path(__file__).parent.parent.joinpath("modules/widgets/powermenu/PowerMenuView.qml").read_text()
        self.assertIn("import qs.modules.widgets.powermenu", power)
        notch = Path(__file__).parent.parent.joinpath("modules/notch/NotchContent.qml").read_text()
        self.assertIn("import qs.modules.widgets.launcher", notch)
        self.assertIn("import qs.modules.widgets.tools", notch)
        self.assertIn("sourceComponent: LauncherView {}", notch)
        self.assertIn("sourceComponent: ToolsMenuView {}", notch)
        self.assertNotIn('source: Qt.resolvedUrl("../widgets/launcher/LauncherView.qml")', notch)


class TestJev(unittest.TestCase):
    def setUp(self):
        from ai import jev, jev_judgments

        jev.reset_client_factory()
        jev_judgments.reset_diagnostics()
        self.jev = jev
        self.jj = jev_judgments

    def tearDown(self):
        self.jev.reset_client_factory()
        self.jj.reset_diagnostics()

    def _config(self, mode="active", threshold=0.75):
        return self.jj.parse_config(
            {
                "mode": mode,
                "timeoutMs": 1500,
                "confidenceThreshold": threshold,
                "maxRetries": 1,
            }
        )

    def _ctx(self, mode="active", text="what's the volume", **kwargs):
        ctx = _ctx(".", enabled_tools=kwargs.pop("enabled_tools", ["native"]), **kwargs)
        ctx.jev_config = self._config(mode)
        ctx.api_keys["typesafe"] = "test-key"
        self.jj.begin_turn(ctx, text)
        return ctx

    def _factory(self, client):
        self.jev.set_client_factory(lambda api_key, timeout_s, max_retries: client)
        return client

    def _choice(self, label, confidence=0.92, extra=None):
        probs = {label: confidence}
        if extra:
            probs.update(extra)
        return self.jev.FakeChoice(label, confidence, probs)

    def test_default_config_is_off(self):
        cfg = self.jj.parse_config({})
        self.assertEqual(cfg.mode, self.jj.MODE_OFF)
        self.assertFalse(cfg.enabled)
        self.assertFalse(cfg.active)
        defaults = (Path(__file__).parent.parent / "config/defaults/ai.js").read_text()
        self.assertIn('"mode": "off"', defaults)
        self.assertIn('"jev"', defaults)

    def test_invalid_mode_falls_back_to_off(self):
        self.assertEqual(self.jj.parse_config({"mode": "full-agent"}).mode, self.jj.MODE_OFF)

    def test_normalize_choice_noul_score(self):
        choice = self.jev.normalize_choice(
            self.jev.FakeChoice("native_read", 0.88, {"native_read": 0.88, "conversation": 0.12})
        )
        self.assertEqual(choice.choice, "native_read")
        self.assertAlmostEqual(choice.confidence, 0.88)
        noul = self.jev.normalize_noul(self.jev.FakeNoul(0.73))
        self.assertAlmostEqual(noul.noul, 0.73)
        score = self.jev.normalize_score(self.jev.FakeScore(1.5, 0.8, {0: 0.1, 1: 0.4, 2: 0.5}))
        self.assertAlmostEqual(score.score, 1.5)
        self.assertIsNone(self.jev.normalize_choice(self.jev.FakeChoice("", 0.99)))
        self.assertIsNone(self.jev.normalize_response(self.jev.FakeResponse()))

    def test_missing_key_does_not_open_client(self):
        ctx = _ctx(".")
        ctx.jev_config = self._config("active")
        result = self.jev.ask(ctx, {"request": {"text": "hi"}}, {"intent": {"type": "choice", "criteria": {"a": None}}})
        self.assertEqual(result.status, self.jev.STATUS_MISSING_KEY)
        self.assertFalse(result.ok)

    def test_missing_sdk_when_key_present(self):
        ctx = _ctx(".")
        ctx.api_keys["typesafe"] = "sk-test"
        if self.jev.sdk_available() and self.jev._CLIENT_FACTORY is None:
            # Real SDK is optional; the missing-sdk path is the no-factory import miss.
            pass
        self.jev.reset_client_factory()
        with patch("ai.jev._import_sdk", return_value=None):
            result = self.jev.ask(ctx, {"request": {"text": "hi"}}, {"intent": {"type": "choice", "criteria": {"a": None}}})
        self.assertEqual(result.status, self.jev.STATUS_MISSING_SDK)

    def test_timeout_and_malformed_and_cancel(self):
        ctx = self._ctx()
        client = self._factory(self.jev.FakeClient(error=TimeoutError("deadline")))
        timed = self.jev.ask(ctx, {"request": {"text": "hi"}}, {"intent": {"type": "choice", "criteria": {"a": None}}})
        self.assertEqual(timed.status, self.jev.STATUS_TIMEOUT)
        self.assertEqual(len(client.calls), 1)

        ctx._jev_sdk_client = None
        self._factory(self.jev.FakeClient(response=self.jev.FakeResponse(choices={"intent": self._choice("")})))
        malformed = self.jev.ask(ctx, {"request": {"text": "hi"}}, {"intent": {"type": "choice", "criteria": {"a": None}}})
        self.assertEqual(malformed.status, self.jev.STATUS_MALFORMED)

        ctx.cancel_event = threading.Event()
        ctx.cancel_event.set()
        cancelled = self.jev.ask(ctx, {"request": {"text": "hi"}}, {"intent": {"type": "choice", "criteria": {"a": None}}})
        self.assertEqual(cancelled.status, self.jev.STATUS_CANCELLED)

    def test_off_mode_makes_zero_jev_requests(self):
        calls = []
        self.jev.set_client_factory(lambda *a, **k: calls.append("asked") or self.jev.FakeClient())
        ctx = self._ctx(mode="off", text="what's the volume")
        self.assertIsNone(self.jj.evaluate_intent(ctx))
        self.assertFalse(self.jj.require_critical_review(ctx, {"action": "click", "name": "Save"}, False))
        self.assertIsNone(self.jj.evaluate_windows(ctx, [{"address": "0x1", "title": "Firefox", "class": "firefox"}]))
        self.assertEqual(calls, [])

    def test_shadow_intent_does_not_dispatch(self):
        client = self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_read"),
                        "read_tool": self._choice("get_volume"),
                        "write_tool": self._choice("none"),
                    }
                )
            )
        )
        ctx = self._ctx(mode="shadow", text="what's the volume")
        judgment = self.jj.evaluate_intent(ctx)
        self.assertTrue(judgment.ok)
        name, reason = self.jj.native_shortcut(ctx, judgment)
        self.assertIsNone(name)
        self.assertEqual(reason, "shadow")
        self.assertEqual(len(client.calls), 1)
        state = client.calls[0]["state"]
        self.assertIn("request", state)
        self.assertNotIn("clipboard", state)
        self.assertNotIn("notifications", json.dumps(state))

    def test_active_high_confidence_native_read(self):
        self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_read"),
                        "read_tool": self._choice("get_volume"),
                        "write_tool": self._choice("none"),
                    }
                )
            )
        )
        ctx = self._ctx(mode="active", text="what's the volume")
        judgment = self.jj.evaluate_intent(ctx)
        name, args = self.jj.native_shortcut(ctx, judgment)
        self.assertEqual(name, "get_volume")
        self.assertEqual(args, {})

    def test_low_confidence_falls_back(self):
        self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_read", 0.4),
                        "read_tool": self._choice("get_volume", 0.4),
                        "write_tool": self._choice("none", 0.4),
                    }
                )
            )
        )
        ctx = self._ctx(mode="active", text="do the thing")
        judgment = self.jj.evaluate_intent(ctx)
        name, reason = self.jj.native_shortcut(ctx, judgment)
        self.assertIsNone(name)
        self.assertEqual(reason, "low_confidence")

    def test_unvalidated_write_args_fall_back(self):
        self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_write"),
                        "read_tool": self._choice("none"),
                        "write_tool": self._choice("set_volume"),
                    }
                )
            )
        )
        ctx = self._ctx(mode="active", text="turn it up a bit")
        judgment = self.jj.evaluate_intent(ctx)
        name, reason = self.jj.native_shortcut(ctx, judgment)
        self.assertIsNone(name)
        self.assertEqual(reason, "unvalidated_args")

    def test_validated_volume_write(self):
        self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_write"),
                        "read_tool": self._choice("none"),
                        "write_tool": self._choice("set_volume"),
                    }
                )
            )
        )
        ctx = self._ctx(mode="active", text="set volume to 40%")
        judgment = self.jj.evaluate_intent(ctx)
        name, args = self.jj.native_shortcut(ctx, judgment)
        self.assertEqual(name, "set_volume")
        self.assertAlmostEqual(args["value"], 0.4)

    def test_parse_level_percentages_and_rejects_ambiguous(self):
        parse = self.jj.parse_level
        self.assertAlmostEqual(parse("set volume to 40%"), 0.4)
        self.assertAlmostEqual(parse("set volume to 40 percent"), 0.4)
        self.assertAlmostEqual(parse("set volume to 1"), 0.01)
        self.assertAlmostEqual(parse("set volume to 1%"), 0.01)
        self.assertAlmostEqual(parse("set brightness to 50"), 0.5)
        self.assertAlmostEqual(parse("set volume to max"), 1.0)
        self.assertAlmostEqual(parse("set volume to full"), 1.0)
        self.assertAlmostEqual(parse("turn the volume off"), 0.0)
        self.assertIsNone(parse("set brightness to 0.5"))
        self.assertIsNone(parse("set volume for the full screen app"))
        self.assertIsNone(parse("turn it up a bit"))
        self.assertAlmostEqual(self.jj.write_args_for("set_volume", "set volume to 1")["value"], 0.01)
        self.assertIsNone(self.jj.write_args_for("set_brightness", "set brightness to 0.5"))

    def test_window_none_and_low_confidence_and_stale(self):
        windows = [
            {"address": "0xaaa", "title": "Firefox", "class": "firefox", "pid": 10, "focused": True},
            {"address": "0xbbb", "title": "Kitty", "class": "kitty", "pid": 11, "focused": False},
        ]
        ctx = self._ctx(mode="active", text="focus firefox")
        self._factory(
            self.jev.FakeClient(response=self.jev.FakeResponse(choices={"window": self._choice("none", 0.96)}))
        )
        judgment = self.jj.evaluate_windows(ctx, windows)
        selected, reason = self.jj.resolve_window_choice(judgment, windows, 0.75)
        self.assertIsNone(selected)
        self.assertEqual(reason, "none")

        ctx.jev_window_judgment = None
        ctx.jev_window_fp = None
        ctx._jev_sdk_client = None
        self._factory(
            self.jev.FakeClient(response=self.jev.FakeResponse(choices={"window": self._choice("w0", 0.2)}))
        )
        judgment = self.jj.evaluate_windows(ctx, windows)
        selected, reason = self.jj.resolve_window_choice(judgment, windows, 0.75)
        self.assertIsNone(selected)
        self.assertEqual(reason, "low_confidence")

        live, stale = self.jj.revalidate_window(
            windows[0],
            windows,
            [{"address": "0xccc", "title": "Other", "class": "other", "pid": 12, "focused": True}],
        )
        self.assertIsNone(live)
        self.assertEqual(stale, "stale")

        kept, ok = self.jj.revalidate_window(windows[0], windows, windows)
        self.assertEqual(kept["address"], "0xaaa")
        self.assertEqual(ok, "")

    def test_window_state_omits_addresses(self):
        windows = self.jj.slim_windows(
            [{"address": "0xsecret", "title": "Mail", "class": "thunderbird", "pid": 9, "focused": False}]
        )
        state = self.jj.window_state(self._ctx(text="focus mail"), windows)
        blob = json.dumps(state)
        self.assertNotIn("0xsecret", blob)
        self.assertEqual(state["candidates"][0]["id"], "w0")

    def test_substring_fallback_only_when_jev_unavailable(self):
        windows = [{"address": "0x1", "title": "Firefox Developer Edition", "class": "firefox", "pid": 1, "focused": False}]
        ctx = self._ctx(mode="active", text="focus firefox")
        ctx.jev_window_judgment = self.jev.Judgment(status=self.jev.STATUS_TIMEOUT, error="deadline")
        ctx.jev_window_fp = self.jj.window_fingerprint(self.jj.slim_windows(windows))
        selected, reason = self.jj.select_focus_target(ctx, windows)
        self.assertEqual(selected["address"], "0x1")
        self.assertEqual(reason, "substring")

    def test_substring_skips_command_verbs(self):
        windows = [{"address": "0x1", "title": "Focus To-Do", "class": "focus", "pid": 1, "focused": False}]
        self.assertIsNone(self.jj.substring_window_match("focus", windows))
        ctx = self._ctx(mode="active", text="focus")
        ctx.jev_window_judgment = self.jev.Judgment(status=self.jev.STATUS_TIMEOUT, error="deadline")
        ctx.jev_window_fp = self.jj.window_fingerprint(self.jj.slim_windows(windows))
        selected, reason = self.jj.select_focus_target(ctx, windows)
        self.assertIsNone(selected)
        self.assertEqual(reason, "timeout")

    def test_shadow_leaves_computer_use_approval_unchanged(self):
        from ai.tools.computer_use import UseComputerTool, action_is_critical

        self._factory(self.jev.FakeClient(response=self.jev.FakeResponse(nouls={"critical": self.jev.FakeNoul(0.95)})))
        ctx = self._ctx(
            mode="shadow",
            text="click pay",
            execution_profile={"computerUse": "AlwaysAllow"},
        )
        ctx.computer_use_approved = True
        args = {"action": "click", "name": "Save"}
        self.assertFalse(action_is_critical(ctx, args))
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, args), True)
        self.assertTrue(self.jj.diagnostics())

    def test_explicit_critical_flag_stays_hard_positive(self):
        from ai.tools.computer_use import UseComputerTool, action_is_critical

        self._factory(self.jev.FakeClient(response=self.jev.FakeResponse(nouls={"critical": self.jev.FakeNoul(0.01)})))
        ctx = self._ctx(
            mode="active",
            text="click",
            execution_profile={"computerUse": "AlwaysAllow"},
        )
        ctx.computer_use_approved = True
        args = {"action": "click", "name": "Save", "critical": True}
        self.assertTrue(action_is_critical(ctx, args))
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, args), "ask")

    def test_jev_positive_or_uncertain_forces_review(self):
        from ai.tools.computer_use import UseComputerTool, action_is_critical

        ctx = self._ctx(
            mode="active",
            text="click",
            execution_profile={"computerUse": "AlwaysAllow"},
        )
        ctx.computer_use_approved = True
        args = {"action": "click", "name": "Complete order"}
        self.assertFalse(action_is_critical(ctx, args))

        ctx._jev_sdk_client = None
        ctx.jev_safety_cache = {}
        self._factory(self.jev.FakeClient(response=self.jev.FakeResponse(nouls={"critical": self.jev.FakeNoul(0.91)})))
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, args), "ask")

        ctx._jev_sdk_client = None
        ctx.jev_safety_cache = {}
        self._factory(self.jev.FakeClient(response=self.jev.FakeResponse(nouls={"critical": self.jev.FakeNoul(0.5)})))
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, args), "ask")

        ctx._jev_sdk_client = None
        ctx.jev_safety_cache = {}
        self._factory(self.jev.FakeClient(error=TimeoutError("nope")))
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, args), True)

    def test_jev_never_overrides_never_policy(self):
        from ai.tools.computer_use import UseComputerTool

        self._factory(self.jev.FakeClient(response=self.jev.FakeResponse(nouls={"critical": self.jev.FakeNoul(0.01)})))
        ctx = self._ctx(mode="active", execution_profile={"computerUse": "Never"})
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, {"action": "click", "name": "Pay now"}), "deny")

    def test_routine_actions_skip_jev(self):
        calls = []
        self.jev.set_client_factory(lambda *a, **k: calls.append("asked") or self.jev.FakeClient())
        ctx = self._ctx(mode="active", execution_profile={"computerUse": "AlwaysAllow"})
        ctx.computer_use_approved = True
        from ai.tools.computer_use import UseComputerTool

        self.assertEqual(UseComputerTool().should_autoexecute(ctx, {"action": "snapshot"}), True)
        self.assertEqual(UseComputerTool().should_autoexecute(ctx, {"action": "focus"}), True)
        self.assertEqual(calls, [])

    def test_agent_off_and_shadow_keep_llm_path(self):
        from io import StringIO
        from ai.agent import Agent

        def install(mode):
            agent = Agent(stdin=StringIO(), stdout=StringIO())
            agent.apply_init(
                {
                    "enabled_tools": ["native"],
                    "jev": {"mode": mode, "timeoutMs": 1500, "confidenceThreshold": 0.75},
                    "execution_profile": {},
                    "system_prompt": "hi",
                }
            )
            events = []
            ran = []
            agent.emit = lambda event: events.append(event)
            agent.ctx.emit = agent.emit
            agent._run_turn = lambda: ran.append("llm")
            return agent, events, ran

        client = self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_read"),
                        "read_tool": self._choice("get_volume"),
                        "write_tool": self._choice("none"),
                    }
                )
            )
        )
        off, _events, ran = install("off")
        off._handle_send({"text": "what's the volume"})
        self.assertEqual(ran, ["llm"])
        self.assertEqual(client.calls, [])

        client.calls.clear()
        shadow, events, ran = install("shadow")
        shadow.ctx.api_keys["typesafe"] = "test-key"
        shadow._handle_send({"text": "what's the volume"})
        self.assertEqual(ran, ["llm"])
        self.assertTrue(client.calls)
        self.assertFalse(any(event.get("name") == "get_volume" for event in events))

    def test_agent_active_routes_native_read(self):
        from io import StringIO
        from ai.agent import Agent

        self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_read"),
                        "read_tool": self._choice("get_volume"),
                        "write_tool": self._choice("none"),
                    }
                )
            )
        )
        agent = Agent(stdin=StringIO(), stdout=StringIO())
        agent.apply_init(
            {
                "enabled_tools": ["native"],
                "jev": {"mode": "active", "confidenceThreshold": 0.75},
                "execution_profile": {},
                "system_prompt": "hi",
            }
        )
        events = []
        ran = []
        agent.emit = lambda event: events.append(event)
        agent.ctx.emit = agent.emit
        agent.ctx.api_keys["typesafe"] = "test-key"
        agent.ctx.wait_for_native = lambda call_id, timeout=None: {"volume": 0.4, "muted": False}
        agent._run_turn = lambda: ran.append("llm")
        agent._handle_send({"text": "what's the volume"})
        self.assertEqual(ran, [])
        names = [event.get("name") for event in events if event.get("type") == "tool_call"]
        self.assertEqual(names, ["get_volume"])
        self.assertTrue(any(event.get("type") == "done" for event in events))

    def test_agent_stale_window_falls_back_to_llm(self):
        from io import StringIO
        from ai.agent import Agent

        def respond(state, questions):
            if "window" in questions:
                return self.jev.FakeResponse(choices={"window": self._choice("w0")})
            return self.jev.FakeResponse(
                choices={
                    "intent": self._choice("focus_window"),
                    "read_tool": self._choice("none"),
                    "write_tool": self._choice("none"),
                }
            )

        self._factory(self.jev.FakeClient(response=respond))
        agent = Agent(stdin=StringIO(), stdout=StringIO())
        agent.apply_init(
            {
                "enabled_tools": ["native"],
                "jev": {"mode": "active", "confidenceThreshold": 0.75},
                "execution_profile": {},
                "system_prompt": "hi",
            }
        )
        events = []
        ran = []
        agent.emit = lambda event: events.append(event)
        agent.ctx.emit = agent.emit
        agent.ctx.api_keys["typesafe"] = "test-key"
        results = [
            {"windows": [{"address": "0x1", "title": "Firefox", "class": "firefox", "pid": 1, "focused": False}]},
            {"windows": [{"address": "0x2", "title": "Kitty", "class": "kitty", "pid": 2, "focused": True}]},
        ]

        def wait_native(call_id, timeout=None):
            return results.pop(0)

        agent.ctx.wait_for_native = wait_native
        agent._run_turn = lambda: ran.append("llm")
        agent._handle_send({"text": "focus firefox"})
        self.assertEqual(ran, ["llm"])
        self.assertFalse(any(event.get("name") == "focus_window" for event in events))

    def test_agent_native_error_is_not_done(self):
        from io import StringIO
        from ai.agent import Agent

        self._factory(
            self.jev.FakeClient(
                response=self.jev.FakeResponse(
                    choices={
                        "intent": self._choice("native_write"),
                        "read_tool": self._choice("none"),
                        "write_tool": self._choice("set_volume"),
                    }
                )
            )
        )
        agent = Agent(stdin=StringIO(), stdout=StringIO())
        agent.apply_init(
            {
                "enabled_tools": ["native"],
                "jev": {"mode": "active", "confidenceThreshold": 0.75},
                "execution_profile": {},
                "system_prompt": "hi",
            }
        )
        events = []
        ran = []
        agent.emit = lambda event: events.append(event)
        agent.ctx.emit = agent.emit
        agent.ctx.api_keys["typesafe"] = "test-key"
        agent._dispatch_tool = lambda name, args, call_id: {
            "status": "error",
            "error": "User rejected the tool call",
        }
        agent._run_turn = lambda: ran.append("llm")
        agent._handle_send({"text": "set volume to 40%"})
        self.assertEqual(ran, [])
        self.assertTrue(any(event.get("type") == "error" for event in events))
        self.assertFalse(any(event.get("type") == "done" for event in events))
        results = [event for event in events if event.get("type") == "tool_result"]
        self.assertEqual(results[0].get("status"), "error")

    def test_agent_focus_respects_read_permission(self):
        from io import StringIO
        from ai.agent import Agent

        def respond(state, questions):
            if "window" in questions:
                raise AssertionError("window titles must not be sent when reads require ask")
            return self.jev.FakeResponse(
                choices={
                    "intent": self._choice("focus_window"),
                    "read_tool": self._choice("none"),
                    "write_tool": self._choice("none"),
                }
            )

        self._factory(self.jev.FakeClient(response=respond))
        agent = Agent(stdin=StringIO(), stdout=StringIO())
        agent.apply_init(
            {
                "enabled_tools": ["native"],
                "jev": {"mode": "active", "confidenceThreshold": 0.75},
                "execution_profile": {"readFiles": "AlwaysAsk"},
                "system_prompt": "hi",
            }
        )
        events = []
        ran = []
        native_calls = []
        agent.emit = lambda event: events.append(event)
        agent.ctx.emit = agent.emit
        agent.ctx.api_keys["typesafe"] = "test-key"
        agent.ctx.wait_for_native = lambda call_id, timeout=None: native_calls.append(call_id) or {
            "windows": [{"address": "0x1", "title": "Firefox", "class": "firefox", "pid": 1, "focused": False}]
        }
        agent._run_turn = lambda: ran.append("llm")
        agent._handle_send({"text": "focus firefox"})
        self.assertEqual(ran, ["llm"])
        self.assertEqual(native_calls, [])
        self.assertFalse(any(event.get("name") == "get_windows" for event in events))
        self.assertFalse(any(event.get("name") == "focus_window" for event in events))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TestMessageContentInlineMath(unittest.TestCase):
    """Currency `$` must stay literal; intentional `$...$` math still renders."""

    @classmethod
    def setUpClass(cls):
        cls.js = Path(__file__).parent.parent / "modules/widgets/assistant/message_content.js"
        cls.runner = r"""
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(process.argv[1], "utf8").replace(/^\.pragma library\s*/m, "");
const ctx = {};
vm.createContext(ctx);
vm.runInContext(src, ctx);
const req = JSON.parse(fs.readFileSync(0, "utf8"));
const out = {};
if (Object.prototype.hasOwnProperty.call(req, "substitute"))
    out.substitute = req.substitute.map((t) => ctx.substituteInlineMath(t));
if (Object.prototype.hasOwnProperty.call(req, "split"))
    out.split = req.split.map((t) => ctx.splitParts(t).map((p) => ({ type: p.type, content: p.content })));
if (Object.prototype.hasOwnProperty.call(req, "rich"))
    out.rich = req.rich.map((t) => {
        const parts = ctx.splitParts(t);
        return parts.map((p) => p.type === "text" ? ctx.markdownToRichText(p.content, "monospace") : p);
    });
process.stdout.write(JSON.stringify(out));
"""

    def _eval(self, **payload):
        proc = subprocess.run(
            [shutil.which("node"), "-e", self.runner, str(self.js)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            self.fail(proc.stderr or proc.stdout or f"node exited {proc.returncode}")
        return json.loads(proc.stdout)

    def test_currency_prices_keep_dollar_signs(self):
        cases = [
            "$25",
            "$25 - $30",
            "$292-$314",
            "$398.00",
            "$459.99",
            "from $292-$314",
            'Sony.com: **$459.99** **$398.00** (sale, "$62 off" - all colors)',
            "Amazon: **$398.00**+ new; used/open-box from $292-$314",
            r"\$25 - \$30",
        ]
        out = self._eval(substitute=cases)["substitute"]
        self.assertEqual(out[0], "$25")
        self.assertEqual(out[1], "$25 - $30")
        self.assertEqual(out[2], "$292-$314")
        self.assertEqual(out[3], "$398.00")
        self.assertEqual(out[4], "$459.99")
        self.assertEqual(out[5], "from $292-$314")
        self.assertIn("$459.99", out[6])
        self.assertIn("$398.00", out[6])
        self.assertIn("$62 off", out[6])
        self.assertNotIn("from292", out[7])
        self.assertIn("from $292-$314", out[7])
        self.assertEqual(out[8], "$25 - $30")

    def test_pound_prices_unchanged(self):
        out = self._eval(substitute=["£349.00"])["substitute"]
        self.assertEqual(out[0], "£349.00")

    def test_intentional_inline_math_still_renders(self):
        cases = ["$x$", "$x^2$", "$E=mc^2$", r"\(a + b\)", "The formula is $a + b$ and the price is $25."]
        out = self._eval(substitute=cases)["substitute"]
        self.assertEqual(out[0], "`x`")
        self.assertEqual(out[1], "`x²`")
        self.assertEqual(out[2], "`E=mc²`")
        self.assertEqual(out[3], "`a + b`")
        self.assertEqual(out[4], "The formula is `a + b` and the price is $25.")

    def test_display_math_blocks_still_split(self):
        parts = self._eval(split=["$$x^2$$"])["split"][0]
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["type"], "math")
        self.assertEqual(parts[0]["content"], "x²")

    def test_bold_prices_survive_markdown(self):
        html = self._eval(rich=["**$398.00**"])["rich"][0]
        self.assertEqual(len(html), 1)
        self.assertIn("$398.00", html[0])
        self.assertIn("<b>", html[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
