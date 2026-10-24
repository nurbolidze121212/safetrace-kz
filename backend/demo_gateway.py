"""Access boundary for a temporary, shared demonstration (never the personal database)."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import deque
from http.cookies import CookieError, SimpleCookie
from urllib.parse import parse_qs, urlsplit

from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

COOKIE = "__Host-safetrace-demo"
SESSION_SECONDS = 12 * 60 * 60
LOGIN = """<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SafeTrace KZ · Демонстрация</title><style>
*{box-sizing:border-box}body{margin:0;background:#0c1424;color:#eef4ff;
font:17px/1.6 system-ui,sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}
main{max-width:540px;width:100%}small{color:#72e5bc;letter-spacing:.15em}
h1{font-size:clamp(40px,10vw,64px);line-height:1.08;margin:20px 0}
p{color:#b7c6dc}label{display:block;margin:24px 0 8px}
input,button{width:100%;border-radius:12px;padding:16px;font:inherit}
input{background:#17243a;border:1px solid #57718f;color:white}
button{background:#72e5bc;color:#10261e;border:0;font-weight:700;margin-top:14px;cursor:pointer}
aside{border-left:3px solid #72e5bc;padding-left:18px;margin-top:28px;color:#b7c6dc;font-size:14px}
</style><main><small>SAFETRACE KZ / LIVE DEMO</small>
<h1>От сообщения<br>к доказательствам.</h1>
<p>Текст, ссылка или фото → распознавание → причины → карта → решение человека.</p>
<form method="post" action="/demo/login"><label for="code">Код доступа к показу</label>
<input id="code" name="code" type="password" required maxlength="128" autocomplete="off">
<button>Открыть демонстрацию</button></form>
<aside>Общая демонстрационная очередь: участники с кодом видят добавленные материалы.
Используйте учебные примеры без личных данных. OCR и правила работают на компьютере автора.
Внешние сайты и облачные модели в этом показе не вызываются. Ссылка временная;
компьютер должен оставаться включённым.</aside></main></html>"""


class DemoGateway:
    def __init__(self, app, origin: str, code: str, signing_key: str, clock=time.time):
        parts = urlsplit(origin)
        if (parts.scheme != "https" or not parts.hostname or parts.netloc != parts.hostname
                or parts.path or parts.query or parts.fragment or parts.username):
            raise ValueError("Use one exact HTTPS origin, without a path or port")
        if len(code) < 20 or len(signing_key) < 32:
            raise ValueError("Demo secrets must be randomly generated, not short PINs")
        self.app, self.origin, self.host = app, origin, parts.hostname
        self.code, self.key, self.clock = code, signing_key.encode(), clock
        # Global bounded counters avoid trusting client-controlled forwarding headers.
        self.windows = {name: deque() for name in ("login", "write", "read")}

    def permitted(self, kind, limit):
        now = self.clock()
        window = self.windows[kind]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    def signature(self, value):
        return hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()

    def token(self):
        expires = str(int(self.clock()) + SESSION_SECONDS)
        return f"{expires}.{self.signature(expires)}"

    def authenticated(self, raw_cookie):
        try:
            cookies = SimpleCookie()
            cookies.load(raw_cookie)
            value = cookies[COOKIE].value
            expires, signature = value.split(".")
            return (0 < int(expires) - self.clock() <= SESSION_SECONDS
                    and hmac.compare_digest(signature, self.signature(expires)))
        except (CookieError, ValueError, KeyError, TypeError):
            return False

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 1008})

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"cache-control", b"referrer-policy")]
                headers += [(b"cache-control", b"no-store"), (b"x-robots-tag", b"noindex, nofollow"),
                            (b"x-frame-options", b"DENY"), (b"referrer-policy", b"same-origin"),
                            (b"x-content-type-options", b"nosniff")]
                message["headers"] = headers
            await send(message)

        async def fail(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secured_send)

        headers = {}
        for key, value in scope["headers"]:
            key = key.lower()
            if key in headers and key in (b"host", b"origin", b"cookie", b"content-length"):
                return await fail(400, "Duplicate security header")
            headers[key] = value.decode("latin-1")
        if headers.get(b"host") != self.host:
            return await fail(403, "Unknown demo host")
        method, path = scope["method"], scope["path"]
        if method not in ("GET", "HEAD", "POST"):
            return await fail(405, "Method unavailable in demonstration")
        origin = headers.get(b"origin")
        if (origin and origin != self.origin) or (method == "POST" and origin != self.origin):
            return await fail(403, "Use the demonstration page to submit materials")
        if headers.get(b"sec-fetch-site") == "cross-site":
            return await fail(403, "Cross-site request blocked")

        if path == "/demo/login":
            if method in ("GET", "HEAD"):
                return await HTMLResponse(LOGIN)(scope, receive, secured_send)
            if not self.permitted("login", 20):
                return await fail(429, "Too many login attempts; wait one minute")
            body = b""
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body += message.get("body", b"")
                if len(body) > 512:
                    return await fail(413, "Login form too large")
                if not message.get("more_body"):
                    break
            try:
                code = parse_qs(body.decode("utf-8")).get("code", [""])[0]
            except (UnicodeError, ValueError):
                return await fail(400, "Invalid login form")
            if not hmac.compare_digest(code.encode(), self.code.encode()):
                return await fail(401, "Неверный код. Вернитесь назад и повторите ввод.")
            response = RedirectResponse("/#queue", status_code=303)
            response.set_cookie(COOKIE, self.token(), max_age=SESSION_SECONDS,
                                secure=True, httponly=True, samesite="strict", path="/")
            return await response(scope, receive, secured_send)

        if not self.authenticated(headers.get(b"cookie", "")):
            if path == "/":
                return await RedirectResponse("/demo/login", 303)(scope, receive, secured_send)
            return await fail(401, "Откройте главную страницу и введите код демонстрации.")
        if path == "/demo/logout" and method == "POST":
            response = RedirectResponse("/demo/login", 303)
            response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict")
            return await response(scope, receive, secured_send)
        if not self.permitted("write" if method == "POST" else "read", 30 if method == "POST" else 1200):
            return await fail(429, "Демонстрация занята. Повторите через минуту.")
        if path.startswith(("/docs", "/redoc", "/openapi.json")):
            return await fail(404, "Not available in public demonstration")
        # Only this separate process gets the trusted internal Host. The workstation
        # server retains its own loopback boundary and is never the tunnel target.
        internal = dict(scope)
        internal["headers"] = [(k, v) for k, v in scope["headers"]
                               if k.lower() not in (b"host", b"origin", b"forwarded")
                               and not k.lower().startswith(b"x-forwarded-")]
        internal["headers"].append((b"host", b"127.0.0.1"))
        if origin:
            internal["headers"].append((b"origin", b"http://127.0.0.1"))
        await self.app(internal, receive, secured_send)
