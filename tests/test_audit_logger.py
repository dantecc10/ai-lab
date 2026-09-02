#!/usr/bin/env python3
"""Pruebas unitarias para AuditLogger y trazabilidad."""

import unittest
import tempfile
from pathlib import Path
from scripts.tools.audit_logger import AuditLogger

class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_audit.db"
        self.logger = AuditLogger(db_path=self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_and_get_trace(self):
        trace_id = self.logger.record_trace(
            tool_name="get_system_info",
            arguments={"detail": True},
            duration_ms=15.4,
            success=True,
            error_message="",
            session_id="test_session_1",
            tokens_estimate=12
        )
        self.assertGreater(trace_id, 0)

        traces = self.logger.list_recent_traces(limit=5)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["tool"], "get_system_info")
        self.assertTrue(traces[0]["success"])
        self.assertEqual(traces[0]["duration_ms"], 15.4)

    def test_audit_metrics_calculation(self):
        self.logger.record_trace("get_system_info", {}, 10.0, True)
        self.logger.record_trace("run_command", {"command": "invalid_cmd"}, 5.0, False, "command not found")

        metrics = self.logger.get_metrics(hours=1)
        self.assertEqual(metrics["total_calls"], 2)
        self.assertEqual(metrics["success_rate_pct"], 50.0)
        self.assertEqual(len(metrics["recent_errors"]), 1)
        self.assertEqual(metrics["recent_errors"][0]["tool"], "run_command")

if __name__ == "__main__":
    unittest.main()
