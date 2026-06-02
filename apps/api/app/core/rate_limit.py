from time import time

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.services.abuse import get_client_ip


async def enforce_rate_limit(request: Request) -> None:
    client_ip = get_client_ip(request)
    window = int(time() // 60)
    key = f"rate:{client_ip}:{window}"

    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 70)
        if count > settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
    finally:
        await client.aclose()
