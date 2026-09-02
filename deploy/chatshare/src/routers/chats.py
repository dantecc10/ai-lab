import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.chat_service import ChatService
from src.services.token_service import TokenService
from src.config import settings

router = APIRouter()


class ChatCreateRequest(BaseModel):
    title: str
    messages: list = []
    metadata: dict = {}


class ChatEditRequest(BaseModel):
    messages: list
    title: Optional[str] = None


class ChatBranchRequest(BaseModel):
    name: str


class TokenCreateRequest(BaseModel):
    label: Optional[str] = None
    max_views: Optional[int] = None
    expires_hours: int = 72


@router.post("/chats")
async def create_chat(req: ChatCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    chat = await svc.create_chat(req.title, req.messages, req.metadata)
    return {"id": chat.id, "title": chat.title, "version": chat.version}


@router.get("/chats")
async def list_chats(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    chats = await svc.list_chats(limit, offset)
    return [{"id": c.id, "title": c.title, "version": c.version, "updated_at": c.updated_at.isoformat()} for c in chats]


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    chat = await svc.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    return {
        "id": chat.id,
        "title": chat.title,
        "messages": json.loads(chat.messages),
        "version": chat.version,
        "created_at": chat.created_at.isoformat(),
        "updated_at": chat.updated_at.isoformat(),
    }


@router.put("/chats/{chat_id}")
async def edit_chat(chat_id: str, req: ChatEditRequest, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    chat = await svc.edit_chat(chat_id, req.messages, req.title)
    return {"id": chat.id, "version": chat.version}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    ok = await svc.soft_delete(chat_id)
    if not ok:
        raise HTTPException(404, "Chat not found")
    return {"deleted": True}


@router.get("/chats/{chat_id}/versions")
async def get_versions(chat_id: str, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    versions = await svc.get_versions(chat_id)
    return [{"version": v.version_number, "is_current": v.is_current, "created_at": v.created_at.isoformat()} for v in versions]


@router.post("/chats/{chat_id}/branches")
async def create_branch(chat_id: str, req: ChatBranchRequest, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    branch = await svc.create_branch(chat_id, req.name)
    return {"id": branch.id, "name": branch.name}


@router.post("/chats/{chat_id}/share")
async def share_chat(chat_id: str, req: TokenCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = ChatService(db)
    chat = await svc.get_chat(chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")

    token_svc = TokenService(db)
    token_obj, raw_token = await token_svc.create_token(
        chat_id=chat_id,
        label=req.label,
        max_views=req.max_views,
        expires_hours=req.expires_hours,
    )
    chat.is_dirty = True
    await db.commit()

    return {
        "token": raw_token,
        "token_id": token_obj.id,
        "url": f"{settings.VPS_URL}/view/{chat_id}?token={raw_token}",
        "expires_at": token_obj.expires_at.isoformat(),
    }


@router.post("/tokens/{token_id}/revoke")
async def revoke_token(token_id: str, db: AsyncSession = Depends(get_db)):
    svc = TokenService(db)
    ok = await svc.revoke_token(token_id)
    if not ok:
        raise HTTPException(404, "Token not found")
    return {"revoked": True}
