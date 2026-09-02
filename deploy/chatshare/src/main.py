import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.database import init_db, async_session
from src.routers.chats import router as chats_router
from src.routers.view import router as view_router
from src.routers.sync import router as sync_router
from src.routers.media import router as media_router
from src.routers.audit import router as audit_router
from src.services.token_service import TokenService
from src.services.sync_service import SyncService
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatmanager")


async def token_expiration_worker():
    while True:
        try:
            async with async_session() as db:
                svc = TokenService(db)
                cleaned = await svc.cleanup_expired()
                if cleaned:
                    logger.info(f"Cleaned {cleaned} expired tokens")
        except Exception as e:
            logger.error(f"Token worker error: {e}")
        await asyncio.sleep(settings.TOKEN_CHECK_INTERVAL)


async def sync_worker():
    while True:
        try:
            async with async_session() as db:
                svc = SyncService(db)
                pushed = await svc.push_dirty_chats()
                if pushed:
                    logger.info(f"Synced {pushed} chats to VPS")
        except Exception as e:
            logger.error(f"Sync worker error: {e}")
        await asyncio.sleep(settings.SYNC_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info(f"Database initialized at {settings.db_path}")

    t1 = asyncio.create_task(token_expiration_worker())
    t2 = asyncio.create_task(sync_worker())
    logger.info("Workers started")

    yield

    t1.cancel()
    t2.cancel()


app = FastAPI(
    title="ChatShare",
    version="1.0.0",
    lifespan=lifespan,
)

# Habilitar CORS completo para consumo local desde llama-server (puerto 9090) y Open WebUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chats_router, prefix="/api/v1", tags=["chats"])
app.include_router(sync_router, prefix="/api/v1", tags=["sync"])
app.include_router(media_router, prefix="/api/v1", tags=["media"])
app.include_router(view_router, tags=["view"])
app.include_router(audit_router, tags=["audit"])


@app.get("/health")
async def health():
    return {"status": "ok"}
