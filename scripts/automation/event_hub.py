#!/usr/bin/env python3
"""
AI Lab — Reactive Event Hub & Monitoring Daemon
Monitorea eventos de archivos (inotify/polling), salud de hardware (GPU/RAM)
y dispara flujos de trabajo de forma reactiva y autónoma.
"""

import os
import sys
import time
import json
import sqlite3
import subprocess
import threading
import signal
from pathlib import Path
from datetime import datetime

# Rutas
EVENT_DB = Path.home() / ".local" / "share" / "ai-lab" / "event_history.db"
WATCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "ai-lab" / "incoming"
]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.automation.dag_runner import DAGRunner

class EventHub:
    """Bus de eventos reactivos y monitor de entorno."""

    def __init__(self, watch_dirs: list[Path] | None = None):
        self.watch_dirs = watch_dirs or WATCH_DIRS
        for d in self.watch_dirs:
            d.mkdir(parents=True, exist_ok=True)
        EVENT_DB.parent.mkdir(parents=True, exist_ok=True)
        self.running = False
        self.runner = DAGRunner()
        self._known_files: dict[str, set[str]] = {}
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(EVENT_DB))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL, -- file_created, thermal_alert, memory_alert, webhook
                source TEXT NOT NULL,
                payload_json TEXT,
                action_taken TEXT,
                status TEXT DEFAULT 'processed'
            );
            """)
            conn.commit()

    def log_event(self, event_type: str, source: str, payload: dict, action_taken: str = "") -> int:
        """Registra un evento en la base de datos."""
        with self._get_connection() as conn:
            cur = conn.execute("""
            INSERT INTO event_log (event_type, source, payload_json, action_taken)
            VALUES (?, ?, ?, ?)
            """, (event_type, source, json.dumps(payload, ensure_ascii=False), action_taken))
            conn.commit()
            return cur.lastrowid

    # ── Monitor de Hardware ──────────────────────────────────
    def check_hardware_health(self):
        """Revisa la temperatura de la GPU y uso de swap."""
        # 1. GPU Temp
        try:
            cmd = ["nvidia-smi", "--query-gpu=temperature.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2.0)
            if res.returncode == 0:
                parts = res.stdout.strip().split(",")
                temp_c = float(parts[0].strip())
                mem_used = float(parts[1].strip())
                mem_total = float(parts[2].strip())

                if temp_c >= 82.0:
                    self.log_event("thermal_alert", "nvidia-gpu", {
                        "temp_c": temp_c, "mem_used_mb": mem_used
                    }, "alerta de temperatura disparada")
                    self._send_desktop_notification(
                        "⚠️ ALERTA TÉRMICA GPU",
                        f"Temperatura crítica en GPU: {temp_c}°C. Disminuyendo carga.",
                        "critical"
                    )
        except Exception:
            pass

        # 2. Swap usage
        try:
            with open("/proc/meminfo") as f:
                meminfo = f.read()
            s_total = 0
            s_free = 0
            for line in meminfo.splitlines():
                if line.startswith("SwapTotal:"):
                    s_total = int(line.split()[1])
                elif line.startswith("SwapFree:"):
                    s_free = int(line.split()[1])
            if s_total > 0:
                swap_used_pct = ((s_total - s_free) / s_total) * 100.0
                if swap_used_pct >= 90.0:
                    self.log_event("memory_alert", "linux-swap", {
                        "swap_used_pct": round(swap_used_pct, 1)
                    }, "alerta de saturación de swap")
                    self._send_desktop_notification(
                        "⚠️ ALERTA DE MEMORIA SWAP",
                        f"Uso de swap al {swap_used_pct:.1f}%. Considera reiniciar modelos.",
                        "normal"
                    )
        except Exception:
            pass

    def _send_desktop_notification(self, title: str, message: str, urgency: str = "normal"):
        """Envía notificación nativa de escritorio."""
        try:
            subprocess.run(["notify-send", "-u", urgency, "-a", "AI Lab EventHub", title, message], timeout=2.0)
        except Exception:
            pass

    # ── Monitor de Archivos ──────────────────────────────────
    def scan_directories_for_new_files(self):
        """Escanea directorios vigilados en busca de nuevos archivos."""
        for directory in self.watch_dirs:
            d_str = str(directory)
            if d_str not in self._known_files:
                # Inicializar conjunto de archivos existentes
                try:
                    self._known_files[d_str] = {p.name for p in directory.glob("*") if p.is_file()}
                except Exception:
                    self._known_files[d_str] = set()
                continue

            try:
                current_files = {p.name for p in directory.glob("*") if p.is_file()}
                new_files = current_files - self._known_files[d_str]

                for filename in new_files:
                    file_path = directory / filename
                    # Evitar archivos temporales en descarga (.crdownload, .part)
                    if filename.endswith((".crdownload", ".part", ".tmp")):
                        continue

                    # Registrar evento
                    self.log_event("file_created", d_str, {
                        "filename": filename,
                        "size_bytes": file_path.stat().st_size if file_path.exists() else 0
                    }, "archivo detectado")

                    # Reacción específica
                    if filename.lower().endswith(".pdf"):
                        self._send_desktop_notification(
                            "📄 Nuevo Documento PDF Detectado",
                            f"Archivo '{filename}' listo para análisis o extracción en AI Lab.",
                            "low"
                        )
                    elif filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        self._send_desktop_notification(
                            "🖼️ Nueva Imagen Detectada",
                            f"'{filename}' disponible en el visor local de medios.",
                            "low"
                        )

                self._known_files[d_str] = current_files
            except Exception:
                pass

    def run_loop(self, poll_interval: float = 10.0):
        """Bucle principal de ejecución continua."""
        self.running = True
        print(f"[+] EventHub iniciado. Vigilando {len(self.watch_dirs)} directorios...")
        print(f"[+] Base de datos de eventos: {EVENT_DB}")

        while self.running:
            try:
                self.scan_directories_for_new_files()
                self.check_hardware_health()
                time.sleep(poll_interval)
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as e:
                print(f"[!] Error en bucle EventHub: {e}", file=sys.stderr)
                time.sleep(poll_interval)

        print("[+] EventHub detenido correctamente.")

if __name__ == "__main__":
    hub = EventHub()
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        print("[+] Ejecutando escaneo único...")
        hub.scan_directories_for_new_files()
        hub.check_hardware_health()
        print("[+] Escaneo completado.")
    else:
        hub.run_loop(poll_interval=10.0)
