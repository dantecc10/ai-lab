#!/usr/bin/env python3
"""Pruebas unitarias para MultimodalVisionEngine y FullDuplexVoiceEngine (Fase 5)."""

import unittest
import tempfile
from pathlib import Path
from scripts.vision.multimodal_vision import MultimodalVisionEngine
from scripts.voice.full_duplex_engine import FullDuplexVoiceEngine

class TestVoiceAndVision(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.test_img = self.tmp_path / "test_sample.png"
        # Crear un archivo de imagen simple (firma PNG)
        self.test_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_vision_engine_missing_file(self):
        engine = MultimodalVisionEngine()
        with self.assertRaises(FileNotFoundError):
            engine.run_ocr(self.tmp_path / "non_existent.png")

    def test_vision_engine_image_analysis_fallback(self):
        engine = MultimodalVisionEngine(endpoint="http://127.0.0.1:9999/invalid")
        res = engine.analyze_image(self.test_img)
        self.assertIn("Análisis Visual", res)
        self.assertIn(self.test_img.name, res)

    def test_voice_engine_status(self):
        engine = FullDuplexVoiceEngine()
        status = engine.get_status()
        self.assertTrue(status["barge_in_active"])
        self.assertIn("tts_ready", status)
        self.assertIn("stt_whisper_ready", status)
        self.assertIn("whisper_endpoint", status)

    def test_voice_engine_cancel_speech(self):
        engine = FullDuplexVoiceEngine()
        res = engine.cancel_speech()
        self.assertFalse(res)  # No active process initially
        self.assertTrue(engine._interrupted)

    def test_audio_diagnostics_volume(self):
        from scripts.voice.audio_diagnostics import AudioDiagnostics
        vol_info = AudioDiagnostics.get_output_volume()
        self.assertIn("volume_percent", vol_info)
        self.assertIn("is_muted", vol_info)
        self.assertIn("backend", vol_info)
        audible, reason = AudioDiagnostics.check_audibility(notify_if_inaudible=False)
        self.assertIsInstance(audible, bool)
        self.assertIsInstance(reason, str)

    def test_voice_profiles_management(self):
        from scripts.voice.voice_profiles import VoiceProfileManager
        config_path = self.tmp_path / "test-voice.conf"
        mgr = VoiceProfileManager(config_path=config_path)
        active = mgr.get_active_profile()
        self.assertIn("language", active)
        self.assertIn("speed", active)
        
        # Cambiar perfil
        updated = mgr.set_profile("es_ES_castilian", speed=1.1, pitch=0.9)
        self.assertEqual(updated["profile_id"], "es_ES_castilian")
        self.assertEqual(updated["speed"], 1.1)
        self.assertEqual(updated["pitch"], 0.9)
        
        profiles = mgr.list_available_profiles()
        self.assertGreaterEqual(len(profiles), 4)

    def test_desktop_context_engine(self):
        from scripts.vision.desktop_context_engine import DesktopContextEngine
        engine = DesktopContextEngine()
        monitors = engine.list_monitors()
        self.assertIsInstance(monitors, list)
        windows = engine.list_windows()
        self.assertIsInstance(windows, list)

    def test_parakeet_engine_availability(self):
        from scripts.voice.parakeet_engine import ParakeetEngine
        engine = ParakeetEngine()
        self.assertIsInstance(engine.available, bool)
        if engine.available:
            self.assertEqual(engine.model_id, "parakeet-tdt-0.6b-v3")

if __name__ == "__main__":
    unittest.main()
