"""Bound incoming bodies before JSON decoding or multipart disk spooling."""
from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.formparsers import MultiPartException

from app.config import settings


def request_limit(path: str) -> int:
    cfg = settings()
    if path == "/api/v1/documents":
        return cfg.max_upload_mb * 1024 * 1024 + 64 * 1024
    if path == "/api/v1/documents/bulk":
        return cfg.bulk_max_total_mb * 1024 * 1024 + 1024 * 1024
    if path.startswith("/oauth/"):
        return 16 * 1024
    # Capture accepts up to capture_max_chars, including JSON Unicode escapes.
    return max(4 * 1024 * 1024, cfg.capture_max_chars * 6 + 64 * 1024)


class RequestLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, send)
        limit = request_limit(scope["path"])
        headers = dict(scope.get("headers", []))
        if b"content-length" in headers:
            try:
                size = int(headers[b"content-length"])
                if size < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(scope, receive, send)
            if size > limit:
                return await JSONResponse({"detail": "Request body exceeds the configured limit"}, status_code=413)(scope, receive, send)
        received = 0
        started = False
        exceeded = False

        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    if headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data"):
                        # Let Starlette close every partially spooled file before
                        # it converts this parser failure into an HTTP response.
                        raise MultiPartException("Request body exceeds the configured limit")
                    raise HTTPException(status_code=413, detail="Request body exceeds the configured limit")
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if exceeded:
                    message = {**message, "status": 413}
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
        except HTTPException as exc:
            if started:
                raise
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)(scope, receive, send)
        except MultiPartException:
            if started:
                raise
            await JSONResponse({"detail": "Request body exceeds the configured limit"}, status_code=413)(scope, receive, send)
