#!/usr/bin/env python3
"""
AI Lab — Git Sentinel Daemon & Notifier
Ejecuta la revisión periódica del acervo técnico en /media/darkseid/DATA/Repos.
Si detecta cambios sin commitear o commits sin respaldar, envía una alerta
a Telegram y una notificación emergente en el escritorio Linux.
"""

import os
import sys
import sqlite3
import urllib.request
import urllib.parse
import json
import subprocess
from pathlib import Path

# Rutas
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "configs" / "telegram.conf"
DB_PATH = Path.home() / ".local" / "share" / "ai-lab" / "telegram_memory.db"

sys.path.insert(0, str(BASE_DIR / "scripts" / "tools"))
from git_repository_auditor import GitRepositoryAuditor


def get_telegram_config():
    """Lee el token y configuraciones de telegram.conf."""
    token = None
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
    return token


def get_active_telegram_users():
    """Obtiene los IDs de chat más recientes desde la base de datos de Telegram."""
    if not DB_PATH.exists():
        return []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT chat_id FROM telegram_history ORDER BY id DESC LIMIT 5")
            rows = cursor.fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []


def send_telegram_alert(token: str, chat_id: int, message: str):
    """Envía un mensaje de alerta a Telegram vía HTTP POST."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Error enviando alerta a Telegram ({chat_id}): {e}", file=sys.stderr)
        return False


def send_desktop_notification(title: str, body: str):
    """Lanza una notificación emergente nativa de Linux."""
    try:
        subprocess.run(["notify-send", "-a", "AI Lab Sentinel", "-i", "git", title, body], check=False)
    except Exception:
        pass


def run_sentinel():
    """Ejecuta la revisión y notifica si hay anomalías o trabajo no respaldado."""
    auditor = GitRepositoryAuditor()
    data = auditor.audit_all()

    if data.get("error"):
        print(f"Aviso Sentinel: {data['error']}")
        return

    dirty_count = data["dirty_count"]
    unpushed_count = data["unpushed_count"]

    print(f"Sentinel Audit: {data['total']} repos analizados. {dirty_count} sucios, {unpushed_count} unpushed.")

    # Solo alertar si hay cambios pendientes o commits sin subir
    if dirty_count > 0 or unpushed_count > 0:
        report = auditor.generate_report(max_items=12)
        summary_text = f"Tienes {dirty_count} repos con cambios sin commitear y {unpushed_count} con commits pendientes de push."
        
        # 1. Notificación de escritorio
        send_desktop_notification("⚠️ AI Lab Git Sentinel: Código Sin Respaldar", summary_text)

        # 2. Notificación a Telegram
        token = get_telegram_config()
        if token:
            users = get_active_telegram_users()
            for chat_id in users:
                send_telegram_alert(token, chat_id, f"🔔 *Alerta de Respaldo de Código*\n\n{report}")


if __name__ == "__main__":
    run_sentinel()
