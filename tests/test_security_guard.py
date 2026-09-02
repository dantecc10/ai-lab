#!/usr/bin/env python3
"""Pruebas unitarias para SecurityGuard y políticas de seguridad."""

import unittest
from scripts.tools.security_guard import SecurityGuard

class TestSecurityGuard(unittest.TestCase):
    def setUp(self):
        self.guard = SecurityGuard()

    def test_safe_tool_execution(self):
        res = self.guard.evaluate_execution("get_system_info", {})
        self.assertTrue(res["allowed"])
        self.assertEqual(res["risk"], "safe")
        self.assertFalse(res["requires_confirmation"])

    def test_high_risk_tool_requires_confirmation(self):
        res = self.guard.evaluate_execution("system_shutdown", {"action": "reboot"}, user_confirmed=False)
        self.assertFalse(res["allowed"])
        self.assertEqual(res["risk"], "high_risk")
        self.assertTrue(res["requires_confirmation"])

    def test_high_risk_tool_allowed_with_confirmation(self):
        res = self.guard.evaluate_execution("system_shutdown", {"action": "reboot"}, user_confirmed=True)
        self.assertTrue(res["allowed"])
        self.assertEqual(res["risk"], "high_risk")
        self.assertFalse(res["requires_confirmation"])

    def test_blocked_dangerous_command_rm_root(self):
        res = self.guard.evaluate_execution("run_command", {"command": "rm -rf / --no-preserve-root"})
        self.assertFalse(res["allowed"])
        self.assertEqual(res["risk"], "blocked")
        self.assertIn("patrón destructivo detectado", res["reason"])

    def test_blocked_dangerous_command_fork_bomb(self):
        res = self.guard.evaluate_execution("run_command", {"command": ":(){ :|:& };:"})
        self.assertFalse(res["allowed"])
        self.assertEqual(res["risk"], "blocked")

    def test_safe_run_command_allowed(self):
        res = self.guard.evaluate_execution("run_command", {"command": "ls -la /tmp"}, user_confirmed=True)
        self.assertTrue(res["allowed"])
        self.assertEqual(res["risk"], "high_risk")

if __name__ == "__main__":
    unittest.main()
