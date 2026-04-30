import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None


async def init_redis():
    global _redis
    _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await _redis.ping()
    logger.info("Redis connected")


async def close_redis():
    if _redis:
        await _redis.aclose()
        logger.info("Redis closed")


def get_redis() -> aioredis.Redis:
    return _redis


# ── Deduplication ─────────────────────────────────────────────────────────────

async def is_duplicate(message_id: str) -> bool:
    """Returns True if already processed (duplicate). Uses SET NX for atomic check."""
    result = await _redis.set(f"processed:{message_id}", "1", ex=60, nx=True)
    return result is None


# ── Conversation history ──────────────────────────────────────────────────────

CONV_TTL = 3600  # 1 hour
MAX_HISTORY = 20  # 10 exchanges = 20 messages


async def get_conversation_history(conv_key: str) -> list[dict]:
    data = await _redis.get(conv_key)
    if data:
        return json.loads(data)
    return []


async def update_conversation_history(conv_key: str, user_msg: str, assistant_msg: str):
    history = await get_conversation_history(conv_key)
    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_msg})
    history = history[-MAX_HISTORY:]
    await _redis.set(conv_key, json.dumps(history), ex=CONV_TTL)


async def clear_conversation(conv_key: str):
    await _redis.delete(conv_key)
