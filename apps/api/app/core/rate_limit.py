from functools import lru_cache
from time import time

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.abuse import get_client_ip


@lru_cache
def get_redis_client() -> redis.Redis:
    # Un solo cliente (y su pool de conexiones interno) reutilizado durante
    # toda la vida del proceso. Antes se creaba y cerraba una conexion TCP
    # nueva a Redis en CADA request, lo que agrega latencia innecesaria y
    # puede saturar conexiones bajo carga.
    return redis.from_url(settings.redis_url, decode_responses=True)


async def enforce_rate_limit(request: Request) -> None:
    client_ip = get_client_ip(request)
    window = int(time() // 60)
    key = f"rate:{client_ip}:{window}"

    client = get_redis_client()
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, 70)
    if count > settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
