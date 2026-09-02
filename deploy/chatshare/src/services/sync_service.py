import json
import httpx
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.chats import Chat
from src.models.tokens import AccessToken, SyncQueue
from src.config import settings


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def push_dirty_chats(self) -> int:
        result = await self.db.execute(select(Chat).where(Chat.is_dirty == True))
        dirty_chats = list(result.scalars().all())
        pushed = 0

        async with httpx.AsyncClient(timeout=30) as client:
            for chat in dirty_chats:
                try:
                    tok_res = await self.db.execute(select(AccessToken).where(AccessToken.chat_id == chat.id))
                    tokens = list(tok_res.scalars().all())
                    tokens_data = [
                        {
                            "id": t.id,
                            "token_hash": t.token_hash,
                            "label": t.label,
                            "max_views": t.max_views,
                            "view_count": t.view_count,
                            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                            "is_revoked": t.is_revoked,
                            "created_at": t.created_at.isoformat() if t.created_at else None,
                        }
                        for t in tokens
                    ]

                    messages_parsed = json.loads(chat.messages) if isinstance(chat.messages, str) else chat.messages
                    metadata_parsed = json.loads(chat.metadata_) if isinstance(chat.metadata_, str) else chat.metadata_

                    payload = {
                        "local_id": chat.id,
                        "title": chat.title,
                        "messages": messages_parsed,
                        "metadata": metadata_parsed,
                        "version": chat.version,
                        "is_deleted": chat.is_deleted,
                        "created_at": chat.created_at.isoformat() if chat.created_at else None,
                        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
                        "tokens": tokens_data,
                    }

                    headers = {}
                    if settings.VPS_API_KEY:
                        headers["X-API-Key"] = settings.VPS_API_KEY

                    if chat.remote_id:
                        resp = await client.put(
                            f"{settings.VPS_URL}/api/v1/sync/chats/{chat.remote_id}",
                            json=payload,
                            headers=headers,
                        )
                    else:
                        resp = await client.post(
                            f"{settings.VPS_URL}/api/v1/sync/chats",
                            json=payload,
                            headers=headers,
                        )

                    if resp.status_code in (200, 201):
                        data = resp.json()
                        chat.is_dirty = False
                        chat.remote_id = data.get("remote_id", chat.remote_id or chat.id)
                        chat.last_synced_at = datetime.now(timezone.utc)
                        pushed += 1
                except Exception:
                    pass

        await self.db.commit()
        return pushed
