import secrets
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    DATA_DIR: Path = Field(default_factory=lambda: Path.home() / ".local" / "share" / "chatmanager")
    DB_PATH: Optional[str] = None
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_hex(32))
    LOCAL_PORT: int = 9095
    SYNC_INTERVAL: int = 30
    TOKEN_CHECK_INTERVAL: int = 300
    VPS_URL: str = "https://ai.castelancarpinteyro.com"
    VPS_API_KEY: str = ""
    DEFAULT_TOKEN_EXPIRY_HOURS: int = 72
    MAX_TOKEN_EXPIRY_HOURS: int = 720

    class Config:
        env_file = ".env"

    def model_post_init(self, __context):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if self.DB_PATH is None:
            self._db_path_obj = self.DATA_DIR / "chats.db"
        else:
            self._db_path_obj = Path(self.DB_PATH)
        key_file = self.DATA_DIR / "secret_key"
        if key_file.exists():
            self.SECRET_KEY = key_file.read_text().strip()
        else:
            key_file.write_text(self.SECRET_KEY)
            key_file.chmod(0o600)

    @property
    def db_path(self) -> Path:
        return self._db_path_obj


settings = Settings()
