import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from src.models.base import Base


class Chat(Base):
    __tablename__ = "chats"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    messages = Column(Text, nullable=False, default="[]")
    metadata_ = Column("metadata", Text, default="{}")

    version = Column(Integer, default=1)
    current_version = Column(Integer, default=1)

    is_deleted = Column(Boolean, default=False)
    is_dirty = Column(Boolean, default=True)
    remote_id = Column(String(36), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    versions = relationship("ChatVersion", back_populates="chat", foreign_keys="ChatVersion.chat_id")
    branches = relationship("ChatBranch", back_populates="chat")
    tokens = relationship("AccessToken", back_populates="chat")


class ChatVersion(Base):
    __tablename__ = "chat_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("chats.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    messages = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_current = Column(Boolean, default=False)

    chat = relationship("Chat", back_populates="versions", foreign_keys=[chat_id])


class ChatBranch(Base):
    __tablename__ = "chat_branches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("chats.id"), nullable=False)
    name = Column(String(100), nullable=False)
    source_branch_id = Column(String(36), ForeignKey("chat_branches.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chat = relationship("Chat", back_populates="branches", foreign_keys=[chat_id])
    source_branch = relationship("ChatBranch", remote_side=[id], foreign_keys=[source_branch_id])
