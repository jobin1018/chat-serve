import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, close_db
from app.redis_client import init_redis, close_redis
from app.routers import webhook, menu, orders, broadcast

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up…")
    await init_redis()
    await init_db()
    logger.info("Ready")
    yield
    logger.info("Shutting down…")
    await close_db()
    await close_redis()


app = FastAPI(
    title="WhatsApp Restaurant Ordering Bot",
    description=(
        "Multi-tenant WhatsApp AI ordering system. "
        "Manage menus, orders, and broadcast messages via this Swagger UI."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(broadcast.router)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "healthy"}
