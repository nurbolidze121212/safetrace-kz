"""Bound request bodies before multipart/JSON parsing, including chunked requests."""

from starlette.responses import JSONResponse

from .config import MAX_IMAGE


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > MAX_IMAGE + 1024 * 1024:
                response = JSONResponse({"detail": "Запрос превышает 9 MiB."}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body"):
                break
        index = 0

        async def bounded_receive():
            nonlocal index
            if index < len(chunks):
                message = chunks[index]
                index += 1
                return message
            return await receive()

        return await self.app(scope, bounded_receive, send)
