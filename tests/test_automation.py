#!/usr/bin/env python3
"""Pruebas unitarias para DAGRunner y EventHub (Fase 2)."""

import unittest
import tempfile
import json
from pathlib import Path
from scripts.automation.dag_runner import DAGRunner
from scripts.automation.event_hub import EventHub

class TestAutomation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.wf_dir = Path(self.tmpdir.name) / "workflows"
        self.wf_dir.mkdir()

        # Crear workflow de prueba
        wf_data = {
            "name": "test_pipeline",
            "description": "Workflow de prueba unitaria",
            "steps": [
                {
                    "id": "step1",
                    "tool": "get_system_info",
                    "args": {}
                }
            ]
        }
        (self.wf_dir / "test_pipeline.json").write_text(json.dumps(wf_data), encoding="utf-8")
        self.runner = DAGRunner(workflow_dirs=[self.wf_dir])

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_list_and_find_workflows(self):
        workflows = self.runner.list_workflows()
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]["name"], "test_pipeline")

        wf_data, path = self.runner.find_workflow("test_pipeline")
        self.assertIsNotNone(wf_data)
        self.assertEqual(len(wf_data["steps"]), 1)

    def test_event_hub_logging(self):
        with tempfile.TemporaryDirectory() as watch_tmp:
            hub = EventHub(watch_dirs=[Path(watch_tmp)])
            event_id = hub.log_event("test_event", "unit_test", {"key": "val"}, "action_ok")
            self.assertGreater(event_id, 0)

if __name__ == "__main__":
    unittest.main()
