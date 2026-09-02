#!/usr/bin/env python3
"""
AI Lab — Omnichannel Reminder & Timer Engine
Gestiona recordatorios y temporizadores con almacenamiento persistente en SQLite,
análisis de tiempo natural/relativo/absoluto y despacho omnicanal:
  - Notificaciones de Telegram
  - Notificaciones de escritorio (notify-send)
  - Avisos visuales Aura (teclado RGB ASUS + lámpara Lux)
  - Anuncios por voz (TTS Piper)
"""

import os
import re
import sys
import time
import json
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

DATA_DIR = Path(os.path.expanduser("~/.local/share/ai-lab"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "reminders.db"


class ReminderEngine:
    """Motor de gestión y despacho de recordatorios y temporizadores."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Inicializa el esquema de base de datos SQLite."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    is_completed INTEGER DEFAULT 0,
                    priority TEXT DEFAULT 'normal', -- normal, important, critical
                    category TEXT DEFAULT 'general', -- timer, task, alarm, dev
                    channels TEXT DEFAULT '["telegram", "desktop", "visual"]',
                    user_id INTEGER DEFAULT 0,
                    repeat_interval TEXT DEFAULT NULL -- e.g., 'daily', 'hourly'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_due_at ON reminders(due_at, is_completed)")
            conn.commit()

    @staticmethod
    def parse_time_expression(time_str: str) -> Optional[datetime]:
        """
        Parsea expresiones de tiempo naturales o relativas en español / formato estándar:
        - "en 15 minutos", "15m", "15 min", "15m", "15 min"
        - "en 2 horas", "2h", "2 hrs"
        - "en 45 segundos", "45s"
        - "a las 17:30", "17:30", "5:30pm", "5:30 pm"
        - "mañana a las 9:00"
        - Formato ISO "YYYY-MM-DD HH:MM:SS"
        """
        now = datetime.now()
        raw = time_str.strip().lower()

        # 1. Minutos relativos: "en 10 min", "10m", "10 minutos"
        m_rel_min = re.search(r'(?:en\s+)?(\d+(?:\.\d+)?)\s*(?:minutos?|mins?|m)\b', raw)
        if m_rel_min:
            mins = float(m_rel_min.group(1))
            return now + timedelta(minutes=mins)

        # 2. Horas relativas: "en 2 horas", "2h", "2 hrs"
        m_rel_hr = re.search(r'(?:en\s+)?(\d+(?:\.\d+)?)\s*(?:horas?|hrs?|h)\b', raw)
        if m_rel_hr:
            hrs = float(m_rel_hr.group(1))
            return now + timedelta(hours=hrs)

        # 3. Segundos relativos: "en 30 segundos", "30s"
        m_rel_sec = re.search(r'(?:en\s+)?(\d+(?:\.\d+)?)\s*(?:segundos?|segs?|s)\b', raw)
        if m_rel_sec:
            secs = float(m_rel_sec.group(1))
            return now + timedelta(seconds=secs)

        # 4. Solo número (asumir minutos por defecto): "15" -> 15 minutos
        if raw.isdigit():
            return now + timedelta(minutes=int(raw))

        # 5. Hora absoluta: "17:30", "a las 17:30", "a las 5:30 pm"
        m_time = re.search(r'(?:a\s+las\s+)?(\d{1,2}):(\d{2})(?:\s*(am|pm))?', raw)
        if m_time:
            hour = int(m_time.group(1))
            minute = int(m_time.group(2))
            meridiem = m_time.group(3)

            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0

            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # Si la hora ya pasó hoy, programar para mañana
            if "mañana" in raw:
                target += timedelta(days=1)
            elif target <= now:
                target += timedelta(days=1)
            return target

        # 6. Formato ISO o datetime estándar
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue

        return None

    def add_reminder(
        self,
        title: str,
        due: str | datetime,
        description: str = "",
        priority: str = "normal",
        category: str = "general",
        channels: List[str] = None,
        user_id: int = 0,
        repeat_interval: Optional[str] = None
    ) -> Dict[str, Any]:
        """Crea y registra un recordatorio o temporizador."""
        if isinstance(due, str):
            parsed_due = self.parse_time_expression(due)
            if not parsed_due:
                raise ValueError(f"No se pudo interpretar el tiempo: '{due}'. Ejemplos: '15m', '2h', '18:30', 'en 45 minutos'")
        elif isinstance(due, datetime):
            parsed_due = due
        else:
            raise ValueError("Parámetro 'due' debe ser str o datetime")

        created_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        due_str = parsed_due.strftime("%Y-%m-%d %H:%M:%S")
        channels_json = json.dumps(channels or ["telegram", "desktop", "visual"])

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reminders (
                    title, description, created_at, due_at, is_completed,
                    priority, category, channels, user_id, repeat_interval
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
            """, (title, description, created_str, due_str, priority, category, channels_json, user_id, repeat_interval))
            rem_id = cursor.lastrowid
            conn.commit()

        delta_sec = max(0, int((parsed_due - datetime.now()).total_seconds()))
        mins_left = delta_sec // 60
        secs_left = delta_sec % 60
        time_hint = f"{mins_left}m {secs_left}s" if mins_left > 0 else f"{secs_left}s"

        return {
            "id": rem_id,
            "title": title,
            "due_at": due_str,
            "time_left": time_hint,
            "priority": priority,
            "category": category,
            "channels": channels or ["telegram", "desktop", "visual"]
        }

    def list_pending_reminders(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lista recordatorios pendientes de vencer."""
        query = "SELECT * FROM reminders WHERE is_completed = 0"
        params = []
        if user_id:
            query += " AND (user_id = ? OR user_id = 0)"
            params.append(user_id)
        query += " ORDER BY due_at ASC"

        results = []
        now = datetime.now()
        with self._get_conn() as conn:
            for row in conn.execute(query, params).fetchall():
                due_dt = datetime.strptime(row["due_at"], "%Y-%m-%d %H:%M:%S")
                delta_sec = int((due_dt - now).total_seconds())
                if delta_sec > 0:
                    mins = delta_sec // 60
                    secs = delta_sec % 60
                    left_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                else:
                    left_str = "Vencido (procesando)"

                results.append({
                    "id": row["id"],
                    "title": row["title"],
                    "description": row["description"],
                    "due_at": row["due_at"],
                    "time_left": left_str,
                    "priority": row["priority"],
                    "category": row["category"]
                })
        return results

    def cancel_reminder(self, reminder_id: int) -> bool:
        """Cancela o elimina un recordatorio por ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()
            return cursor.rowcount > 0

    def dispatch_due_reminders(self, telegram_callback=None) -> List[Dict[str, Any]]:
        """Busca y despacha recordatorios que hayan llegado a su fecha de vencimiento."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        due_items = []

        with self._get_conn() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT * FROM reminders 
                WHERE is_completed = 0 AND due_at <= ?
                ORDER BY due_at ASC
            """, (now_str,)).fetchall()

            for r in rows:
                due_items.append(dict(r))
                cursor.execute("UPDATE reminders SET is_completed = 1 WHERE id = ?", (r["id"],))
            conn.commit()

        # Despachar cada recordatorio por sus canales
        for item in due_items:
            self._trigger_channels(item, telegram_callback)

        return due_items

    def _trigger_channels(self, reminder: dict, telegram_callback=None):
        """Dispara las notificaciones a través de los canales configurados."""
        title = reminder["title"]
        desc = reminder.get("description") or ""
        prio = reminder.get("priority", "normal")
        channels = json.loads(reminder.get("channels") or '["desktop", "visual", "telegram"]')

        # 1. Visual Alert (Teclado ASUS + Lámpara Lux)
        if "visual" in channels:
            try:
                from scripts.tools.visual_notifier import notifier
                notifier.animate(level=prio, duration=4.0 if prio != "normal" else 2.5, include_lamp=True)
            except Exception:
                pass

        # 2. Desktop Notification
        if "desktop" in channels:
            try:
                import subprocess
                body = f"⏰ {title}" + (f"\n{desc}" if desc else "")
                urgency = "critical" if prio == "critical" else "normal"
                subprocess.run(
                    ["notify-send", "-u", urgency, "-a", "AI Lab — Recordatorios", "⏰ RECORDATORIO", body],
                    check=False, timeout=3
                )
            except Exception:
                pass

        # 3. Telegram Message
        if "telegram" in channels and telegram_callback:
            try:
                telegram_callback(reminder)
            except Exception:
                pass

        # 4. Spoken Voice Announcement (bm_george / em_santa por altavoces)
        try:
            from scripts.voice.creative_voice_engine import creative_voice_engine
            # Si el título tiene palabras en inglés o es una alerta de sistema, usar bm_george; de lo contrario em_santa
            announcement = f"Reminder: {title}" if any(w in title.lower() for w in ["check", "run", "build", "meeting", "timer", "alert", "git", "test"]) else f"Recordatorio: {title}"
            chosen_voice = "bm_george" if "Reminder:" in announcement else "em_santa"
            creative_voice_engine.speak_notification(message=announcement, voice=chosen_voice, play_local=True, visual_style=None)
        except Exception:
            pass

    def start_background_watcher(self, interval_sec: float = 3.0, telegram_callback=None):
        """Inicia el bucle de vigilancia en segundo plano."""
        if self._running:
            return

        self._running = True
        def _loop():
            while self._running:
                try:
                    self.dispatch_due_reminders(telegram_callback)
                except Exception as e:
                    print(f"Error en watcher de recordatorios: {e}", file=sys.stderr)
                time.sleep(interval_sec)

        self._worker_thread = threading.Thread(target=_loop, daemon=True)
        self._worker_thread.start()

    def stop_background_watcher(self):
        self._running = False


# Singleton
reminder_engine = ReminderEngine()


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "add":
        t = sys.argv[2] if len(sys.argv) > 2 else "10s"
        m = sys.argv[3] if len(sys.argv) > 3 else "Prueba de temporizador"
        res = reminder_engine.add_reminder(title=m, due=t, priority="important")
        print(f"✅ Recordatorio creado: ID {res['id']} para dentro de {res['time_left']} ({res['due_at']})")
    elif cmd == "list":
        items = reminder_engine.list_pending_reminders()
        print(f"📋 Recordatorios pendientes ({len(items)}):")
        for i in items:
            print(f"  • [#{i['id']}] {i['title']} ➔ Vence en {i['time_left']} ({i['due_at']}) [{i['priority']}]")
