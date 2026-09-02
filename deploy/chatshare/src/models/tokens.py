import uuid
import hashlib
import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from src.models.base import Base


class AccessToken(Base):
    __tablename__ = "access_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String(36), ForeignKey("chats.id"), nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False)
    label = Column(String(100), nullable=True)
    max_views = Column(Integer, nullable=True)
    view_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chat = relationship("Chat", back_populates="tokens", foreign_keys=[chat_id])

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class SyncQueue(Base):
    __tablename__ = "sync_queue"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    operation = Column(String(10), nullable=False)
    table_name = Column(String(50), nullable=False)
    record_id = Column(String(36), nullable=False)
    payload = Column(String, nullable=False)
    status = Column(String(20), default="pending")
    attempt_count = Column(Integer, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
