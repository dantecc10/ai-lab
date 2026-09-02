#!/usr/bin/env python3
"""Pruebas unitarias de integridad de esquemas MCP."""

import unittest
from scripts.tools.system_mcp_server import TOOLS

class TestMCPToolsSchema(unittest.TestCase):
    def test_mcp_tools_uniqueness_and_structure(self):
        self.assertGreaterEqual(len(TOOLS), 182, f"Se esperaban al menos 182 tools, encontradas {len(TOOLS)}")
        
        tool_names = set()
        for tool in TOOLS:
            name = tool.get("name")
            self.assertTrue(bool(name), "Cada herramienta debe tener un 'name'")
            self.assertNotIn(name, tool_names, f"Herramienta duplicada detectada: {name}")
            tool_names.add(name)

            self.assertIn("description", tool, f"Herramienta '{name}' no tiene 'description'")
            self.assertGreater(len(tool["description"]), 0, f"Descripción vacía en '{name}'")

            self.assertIn("inputSchema", tool, f"Herramienta '{name}' no tiene 'inputSchema'")
            schema = tool["inputSchema"]
            self.assertEqual(schema.get("type"), "object", f"inputSchema de '{name}' debe ser de tipo 'object'")
            self.assertIn("properties", schema, f"inputSchema de '{name}' debe contener 'properties'")

    def test_audit_and_vector_tools_presence(self):
        names = {t["name"] for t in TOOLS}
        self.assertIn("audit_get_metrics", names, "Falta la herramienta audit_get_metrics")
        self.assertIn("audit_list_traces", names, "Falta la herramienta audit_list_traces")
        self.assertIn("workflow_run", names, "Falta la herramienta workflow_run")
        self.assertIn("vector_search", names, "Falta la herramienta vector_search")
        self.assertIn("vector_index_path", names, "Falta la herramienta vector_index_path")
        self.assertIn("vector_remember", names, "Falta la herramienta vector_remember")
        self.assertIn("vector_stats", names, "Falta la herramienta vector_stats")
        self.assertIn("browser_navigate", names, "Falta la herramienta browser_navigate")
        self.assertIn("browser_screenshot", names, "Falta la herramienta browser_screenshot")
        self.assertIn("browser_sync_brave_profile", names, "Falta la herramienta browser_sync_brave_profile")
        self.assertIn("browser_extract_markdown", names, "Falta la herramienta browser_extract_markdown")
        self.assertIn("browser_print_pdf", names, "Falta la herramienta browser_print_pdf")
        self.assertIn("browser_get_links", names, "Falta la herramienta browser_get_links")
        self.assertIn("voice_speak", names, "Falta la herramienta voice_speak")
        self.assertIn("voice_listen", names, "Falta la herramienta voice_listen")
        self.assertIn("vision_analyze_image", names, "Falta la herramienta vision_analyze_image")
        self.assertIn("vision_inspect_screen", names, "Falta la herramienta vision_inspect_screen")
        self.assertIn("desktop_context_explain", names, "Falta la herramienta desktop_context_explain")
        self.assertIn("desktop_list_monitors", names, "Falta la herramienta desktop_list_monitors")
        self.assertIn("audio_check_volume", names, "Falta la herramienta audio_check_volume")
        self.assertIn("voice_set_profile", names, "Falta la herramienta voice_set_profile")
        self.assertIn("voice_conversational_turn", names, "Falta la herramienta voice_conversational_turn")

if __name__ == "__main__":
    unittest.main()
