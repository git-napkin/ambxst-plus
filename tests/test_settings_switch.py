#!/usr/bin/env python3
"""Contract tests for SettingsSwitch visual language (square + StyledRect)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWITCH = ROOT / "modules" / "components" / "SettingsSwitch.qml"


class TestSettingsSwitchVisualLanguage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SWITCH.read_text()

    def test_track_and_thumb_are_styled_rects(self):
        self.assertGreaterEqual(self.source.count("StyledRect {"), 2)

    def test_uses_shell_radius_not_capsule(self):
        self.assertIn("Styling.radius(-4)", self.source)
        self.assertIsNone(re.search(r"radius:\s*(height|width)\s*/\s*2", self.source))

    def test_on_off_use_theme_variants(self):
        self.assertIn('"primary"', self.source)
        self.assertIn('"internalbg"', self.source)
        self.assertIn('"overprimary"', self.source)
        self.assertIn('"common"', self.source)

    def test_call_sites_do_not_override_geometry_or_color(self):
        overrides = []
        for path in (ROOT / "modules").rglob("*.qml"):
            if path.name == "SettingsSwitch.qml":
                continue
            text = path.read_text()
            if "SettingsSwitch {" not in text:
                continue
            for block in re.findall(r"SettingsSwitch \{.*?\n\s*\}", text, re.S):
                if re.search(r"\b(color|radius|variant|trackWidth|thumbSize)\s*:", block):
                    overrides.append(f"{path.relative_to(ROOT)}: {block.strip()[:80]}")
        self.assertEqual(overrides, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
