from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tokens import AccessToken


class TokenService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_token(
        self, chat_id: str, label: str = None, max_views: int = None, expires_hours: int = 72
    ) -> tuple:
        raw_token = AccessToken.generate_token()
        token = AccessToken(
            chat_id=chat_id,
            token_hash=AccessToken.hash_token(raw_token),
            label=label,
            max_views=max_views,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
        )
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        return token, raw_token

    async def validate_token(self, token: str) -> AccessToken:
        token_hash = AccessToken.hash_token(token)
        result = await self.db.execute(select(AccessToken).where(AccessToken.token_hash == token_hash))
        token_obj = result.scalar_one_or_none()

        if not token_obj:
            return None
        if token_obj.is_revoked:
            return None
        if token_obj.expires_at:
            exp = token_obj.expires_at.replace(tzinfo=timezone.utc) if token_obj.expires_at.tzinfo is None else token_obj.expires_at
            if exp < datetime.now(timezone.utc):
                return None
        if token_obj.max_views and token_obj.view_count >= token_obj.max_views:
            return None

        token_obj.view_count += 1
        await self.db.commit()
        return token_obj

    async def revoke_token(self, token_id: str) -> bool:
        result = await self.db.execute(select(AccessToken).where(AccessToken.id == token_id))
        token = result.scalar_one_or_none()
        if not token:
            return False
        token.is_revoked = True
        await self.db.commit()
        return True

    async def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(AccessToken)
            .where(AccessToken.expires_at < now, AccessToken.is_revoked == False)
            .values(is_revoked=True)
        )
        await self.db.commit()
        return result.rowcount
