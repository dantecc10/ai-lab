import json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models.chats import Chat
from src.models.tokens import AccessToken
from src.config import settings

router = APIRouter()


class TokenSyncData(BaseModel):
    id: str
    token_hash: str
    label: Optional[str] = None
    max_views: Optional[int] = None
    view_count: int = 0
    expires_at: Optional[str] = None
    is_revoked: bool = False
    created_at: Optional[str] = None


class ChatSyncPayload(BaseModel):
    local_id: str
    title: str
    messages: list = []
    metadata: dict = {}
    version: int = 1
    is_deleted: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tokens: List[TokenSyncData] = []


def _verify_api_key(x_api_key: Optional[str] = Header(None)):
    if settings.VPS_API_KEY and settings.VPS_API_KEY.strip():
        if x_api_key != settings.VPS_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid VPS API Key")
    return True


def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


async def _upsert_chat_sync(payload: ChatSyncPayload, db: AsyncSession) -> dict:
    result = await db.execute(select(Chat).where(Chat.id == payload.local_id))
    chat = result.scalar_one_or_none()

    created_dt = _parse_dt(payload.created_at) or datetime.now(timezone.utc)
    updated_dt = _parse_dt(payload.updated_at) or datetime.now(timezone.utc)

    if not chat:
        chat = Chat(
            id=payload.local_id,
            title=payload.title,
            messages=json.dumps(payload.messages, ensure_ascii=False),
            metadata_=json.dumps(payload.metadata, ensure_ascii=False),
            version=payload.version,
            is_deleted=payload.is_deleted,
            is_dirty=False,
            created_at=created_dt,
            updated_at=updated_dt,
        )
        db.add(chat)
    else:
        chat.title = payload.title
        chat.messages = json.dumps(payload.messages, ensure_ascii=False)
        chat.metadata_ = json.dumps(payload.metadata, ensure_ascii=False)
        chat.version = payload.version
        chat.is_deleted = payload.is_deleted
        chat.is_dirty = False
        chat.updated_at = updated_dt

    await db.flush()

    for token_data in payload.tokens:
        tok_res = await db.execute(
            select(AccessToken).where(
                (AccessToken.id == token_data.id) | (AccessToken.token_hash == token_data.token_hash)
            )
        )
        tok = tok_res.scalar_one_or_none()
        exp_dt = _parse_dt(token_data.expires_at)
        tok_created_dt = _parse_dt(token_data.created_at) or datetime.now(timezone.utc)

        if not tok:
            tok = AccessToken(
                id=token_data.id,
                chat_id=chat.id,
                token_hash=token_data.token_hash,
                label=token_data.label,
                max_views=token_data.max_views,
                view_count=token_data.view_count,
                expires_at=exp_dt,
                is_revoked=token_data.is_revoked,
                created_at=tok_created_dt,
            )
            db.add(tok)
        else:
            tok.chat_id = chat.id
            tok.label = token_data.label
            tok.max_views = token_data.max_views
            tok.view_count = token_data.view_count
            tok.expires_at = exp_dt
            tok.is_revoked = token_data.is_revoked

    await db.commit()
    return {"status": "synced", "remote_id": chat.id}


@router.post("/sync/chats", dependencies=[Depends(_verify_api_key)])
async def sync_chat_post(payload: ChatSyncPayload, db: AsyncSession = Depends(get_db)):
    return await _upsert_chat_sync(payload, db)


@router.put("/sync/chats/{chat_id}", dependencies=[Depends(_verify_api_key)])
async def sync_chat_put(chat_id: str, payload: ChatSyncPayload, db: AsyncSession = Depends(get_db)):
    payload.local_id = chat_id
    return await _upsert_chat_sync(payload, db)
