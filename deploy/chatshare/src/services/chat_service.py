import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.chats import Chat, ChatVersion, ChatBranch


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_chat(self, title: str, messages: list, metadata: dict = None) -> Chat:
        chat = Chat(
            title=title,
            messages=json.dumps(messages),
            metadata_=json.dumps(metadata or {}),
        )
        self.db.add(chat)
        await self.db.flush()

        version = ChatVersion(
            chat_id=chat.id,
            version_number=1,
            messages=json.dumps(messages),
            is_current=True,
        )
        self.db.add(version)

        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    async def edit_chat(self, chat_id: str, messages: list, title: str = None) -> Chat:
        chat = await self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        chat.version += 1
        chat.current_version = chat.version
        chat.messages = json.dumps(messages)
        chat.is_dirty = True
        chat.updated_at = datetime.now(timezone.utc)

        if title:
            chat.title = title

        version = ChatVersion(
            chat_id=chat.id,
            version_number=chat.version,
            messages=json.dumps(messages),
            is_current=True,
        )

        for old_version in await self.db.execute(
            select(ChatVersion).where(ChatVersion.chat_id == chat_id, ChatVersion.is_current == True)
        ):
            old_version.is_current = False

        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    async def get_chat(self, chat_id: str) -> Chat:
        result = await self.db.execute(select(Chat).where(Chat.id == chat_id))
        return result.scalar_one_or_none()

    async def list_chats(self, limit: int = 50, offset: int = 0) -> list[Chat]:
        result = await self.db.execute(
            select(Chat).where(Chat.is_deleted == False).order_by(Chat.updated_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def soft_delete(self, chat_id: str) -> bool:
        chat = await self.get_chat(chat_id)
        if not chat:
            return False
        chat.is_deleted = True
        chat.is_dirty = True
        chat.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True

    async def get_versions(self, chat_id: str) -> list[ChatVersion]:
        result = await self.db.execute(
            select(ChatVersion).where(ChatVersion.chat_id == chat_id).order_by(ChatVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def create_branch(self, chat_id: str, name: str) -> ChatBranch:
        chat = await self.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")

        branch = ChatBranch(chat_id=chat_id, name=name)
        self.db.add(branch)
        await self.db.commit()
        await self.db.refresh(branch)
        return branch

    async def get_dirty_chats(self) -> list[Chat]:
        result = await self.db.execute(select(Chat).where(Chat.is_dirty == True))
        return list(result.scalars().all())

    async def mark_synced(self, chat_id: str, remote_id: str):
        chat = await self.get_chat(chat_id)
        if chat:
            chat.is_dirty = False
            chat.remote_id = remote_id
            chat.last_synced_at = datetime.now(timezone.utc)
            await self.db.commit()
