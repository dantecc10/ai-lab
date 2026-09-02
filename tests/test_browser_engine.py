#!/usr/bin/env python3
"""Pruebas unitarias para BrowserEngine y BraveIdentitySync (Fase 4)."""

import unittest
import tempfile
from pathlib import Path
from scripts.tools.browser_engine import BraveIdentitySync, BrowserEngine

class TestBrowserEngine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.src_dir = Path(self.tmpdir.name) / "Brave-Source"
        self.dst_dir = Path(self.tmpdir.name) / "Brave-Target"

        # Crear perfil simulado de Brave
        profile_dir = self.src_dir / "Default" / "Network"
        profile_dir.mkdir(parents=True)
        (self.src_dir / "Local State").write_text("{}", encoding="utf-8")
        (profile_dir / "Cookies").write_bytes(b"SQLite format 3\x00mock_cookie_data")
        (self.src_dir / "Default" / "Preferences").write_text('{"theme": "dark"}', encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_brave_profile_sync(self):
        res = BraveIdentitySync.sync_profile(
            source_dir=self.src_dir,
            target_dir=self.dst_dir,
            profile_name="Default"
        )
        self.assertTrue(res["success"])
        self.assertIn("Local State", res["synced_items"])
        self.assertIn("Network/Cookies", res["synced_items"])
        self.assertTrue((self.dst_dir / "Default" / "Network" / "Cookies").exists())

    def test_browser_engine_initialization(self):
        engine = BrowserEngine(port=9999, user_data_dir=self.dst_dir)
        status = engine.get_status()
        self.assertEqual(status["cdp_port"], 9999)
        self.assertIn("user_data_dir", status)
        self.assertFalse(status["browser_active"])
        tabs = engine.list_tabs()
        self.assertEqual(tabs, [])

if __name__ == "__main__":
    unittest.main()
