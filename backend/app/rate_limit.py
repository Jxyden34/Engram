import time
from fastapi import HTTPException, Request
from redis import Redis
from app.config import settings
from app.security import client_ip


redis_client = Redis.from_url(settings().redis_url, decode_responses=True)


def check_rate(request: Request, bucket: str, limit: int, window_seconds: int = 60):
    identity = client_ip(request) or "unknown"
    window = int(time.time() // window_seconds)
    key = f"ratelimit:{bucket}:{identity}:{window}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window_seconds + 2)
    if count > limit:
        raise HTTPException(status_code=429, detail="Too many requests")
