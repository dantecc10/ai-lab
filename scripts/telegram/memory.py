"""
AI Lab — Telegram Bot Conversation & Long-Term Memory
Maneja el historial de turnos en memoria por usuario/chat y la persistencia en SQLite.
"""

import sqlite3
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

DB_PATH = Path.home() / ".local" / "share" / "ai-lab" / "telegram_memory.db"


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: float
    tool_calls: list | None = None
    tool_call_id: str | None = None
    name: str | None = None


class TelegramMemoryManager:
    """Administrador de memoria a corto y largo plazo para chats de Telegram."""

    def __init__(self, max_turns: int = 20, db_path: Path = DB_PATH):
        self.max_turns = max_turns
        self.db_path = db_path
        self._cache: Dict[int, List[ChatMessage]] = {}
        self._init_db()

    def _init_db(self):
        """Crea las tablas de SQLite si no existen."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telegram_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_id ON telegram_history(chat_id)
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS telegram_user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    voice_reply_enabled INTEGER DEFAULT 0,
                    active_model TEXT,
                    custom_system_prompt TEXT
                )
            """)
            conn.commit()

    def add_message(self, chat_id: int, user_id: int, role: str, content: str, metadata: dict | None = None):
        """Registra un nuevo mensaje en el buffer de memoria y en la base de datos."""
        ts = time.time()
        msg = ChatMessage(role=role, content=content, timestamp=ts)

        if chat_id not in self._cache:
            self._load_cache(chat_id)

        self._cache[chat_id].append(msg)
        # Mantener tamaño máximo en caché (2 mensajes por turno: user + assistant)
        if len(self._cache[chat_id]) > self.max_turns * 2:
            self._cache[chat_id] = self._cache[chat_id][-(self.max_turns * 2):]

        # Guardar en SQLite
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO telegram_history (chat_id, user_id, role, content, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (chat_id, user_id, role, content, ts, json.dumps(metadata or {})))
                conn.commit()
        except Exception as e:
            print(f"[Memory DB Error]: {e}")

    def _load_cache(self, chat_id: int):
        """Carga los últimos turnos desde SQLite a la memoria activa."""
        self._cache[chat_id] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT role, content, timestamp FROM telegram_history
                    WHERE chat_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (chat_id, self.max_turns * 2))
                rows = cursor.fetchall()
                for role, content, ts in reversed(rows):
                    self._cache[chat_id].append(ChatMessage(role=role, content=content, timestamp=ts))
        except Exception as e:
            print(f"[Memory Cache Load Error]: {e}")

    def get_context_messages(self, chat_id: int, system_prompt: str) -> List[Dict[str, str]]:
        """Construye la lista de mensajes con formato OpenAI listos para enviar al LLM."""
        if chat_id not in self._cache:
            self._load_cache(chat_id)

        messages = [{"role": "system", "content": system_prompt}]
        for msg in self._cache[chat_id]:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        return messages

    def get_raw_cache(self, chat_id: int) -> List[ChatMessage]:
        """Obtiene la lista actual de mensajes en caché para un chat."""
        if chat_id not in self._cache:
            self._load_cache(chat_id)
        return list(self._cache.get(chat_id, []))

    def compact_history(self, chat_id: int, summary_text: str, keep_recent_turns: int = 3):
        """Compacta el historial reemplazando los turnos antiguos por una síntesis densa estructurada."""
        if chat_id not in self._cache:
            self._load_cache(chat_id)

        cache = self._cache.get(chat_id, [])
        recent_count = max(2, keep_recent_turns * 2)
        if len(cache) <= recent_count:
            return

        recent_messages = cache[-recent_count:]
        summary_msg = ChatMessage(
            role="system",
            content=f"📝 [RESUMEN DE CONTEXTO AUTO-COMPACTADO]\n{summary_text.strip()}",
            timestamp=time.time()
        )

        self._cache[chat_id] = [summary_msg] + recent_messages

        # Persistir en SQLite
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM telegram_history WHERE chat_id = ?", (chat_id,))
                cursor.execute("""
                    INSERT INTO telegram_history (chat_id, user_id, role, content, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (chat_id, 0, "system", summary_msg.content, summary_msg.timestamp, json.dumps({"compacted": True})))
                for m in recent_messages:
                    cursor.execute("""
                        INSERT INTO telegram_history (chat_id, user_id, role, content, timestamp, metadata)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (chat_id, 0, m.role, m.content, m.timestamp, json.dumps({})))
                conn.commit()
        except Exception as e:
            print(f"[Memory Compact Error]: {e}")

    def clear_history(self, chat_id: int):
        """Limpia el historial activo en memoria y en la base de datos para el chat indicado."""
        self._cache[chat_id] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM telegram_history WHERE chat_id = ?", (chat_id,))
                conn.commit()
        except Exception as e:
            print(f"[Memory Clear Error]: {e}")

    def get_user_preference(self, user_id: int, key: str, default: Any = None) -> Any:
        """Obtiene una preferencia del usuario."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT {key} FROM telegram_user_preferences WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if row is not None and row[0] is not None:
                    return bool(row[0]) if isinstance(default, bool) else row[0]
        except Exception:
            pass
        return default

    def set_user_preference(self, user_id: int, key: str, value: Any):
        """Guarda una preferencia del usuario."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO telegram_user_preferences (user_id) VALUES (?)", (user_id,))
                cursor.execute(f"UPDATE telegram_user_preferences SET {key} = ? WHERE user_id = ?", (int(value) if isinstance(value, bool) else value, user_id))
                conn.commit()
        except Exception as e:
            print(f"[Memory Set Pref Error]: {e}")
