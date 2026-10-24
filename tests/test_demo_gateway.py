from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backend.demo_gateway import COOKIE, SESSION_SECONDS, DemoGateway
from scripts.run_public_demo import demo_directory

ORIGIN = "https://demo.example"
CODE = "test-code-only-not-a-deployed-secret"
KEY = "test-key-only-not-a-deployed-secret"


def client(clock=lambda: 1000):
    async def endpoint(request: Request):
        return JSONResponse({"host": request.headers["host"], "origin": request.headers.get("origin"),
                             "forwarded": request.headers.get("x-forwarded-host"), "real_app": True})
    inner = Starlette(routes=[Route("/{path:path}", endpoint, methods=["GET", "POST"])])
    gateway = DemoGateway(inner, ORIGIN, CODE, KEY, clock)
    return TestClient(gateway, base_url=ORIGIN, follow_redirects=False), gateway


def login(c):
    return c.post("/demo/login", data={"code": CODE}, headers={"origin": ORIGIN})


@pytest.mark.parametrize("path", ["/api/cases", "/api/images/a.png", "/assets/app.js", "/openapi.json"])
def test_all_data_and_assets_require_authentication(path):
    c, _ = client()
    assert c.get(path).status_code == 401
    assert c.post(path, headers={"origin": ORIGIN}).status_code == 401


def test_login_and_real_application_forwarding():
    c, _ = client()
    assert c.get("/").headers["location"] == "/demo/login"
    page = c.get("/demo/login")
    assert "Общая демонстрационная очередь" in page.text
    # no-referrer makes browsers send Origin:null for native form POSTs.
    assert page.headers["referrer-policy"] == "same-origin"
    result = login(c)
    assert result.status_code == 303
    cookie = result.headers["set-cookie"]
    assert all(part in cookie for part in ("Secure", "HttpOnly", "SameSite=strict", "Path=/"))
    result = c.post("/api/cases", headers={"origin": ORIGIN, "x-forwarded-host": "evil.example"})
    assert result.json() == {"host": "127.0.0.1", "origin": "http://127.0.0.1",
                             "forwarded": None, "real_app": True}
    assert result.headers["cache-control"] == "no-store"
    assert c.get("/docs").status_code == 404


@pytest.mark.parametrize("headers", [{}, {"origin": "https://evil.example"}, {"origin": "null"},
                                     {"origin": ORIGIN, "sec-fetch-site": "cross-site"}])
def test_mutations_require_same_origin_even_with_session(headers):
    c, _ = client()
    login(c)
    assert c.post("/api/cases", headers=headers).status_code == 403
    assert c.post("/demo/login", data={"code": CODE}, headers=headers).status_code == 403


def test_host_spoofing_and_duplicate_origin():
    c, _ = client()
    login(c)
    assert c.get("/api/cases", headers={"host": "evil.example"}).status_code == 403
    assert c.post("/api/cases", headers=[("origin", ORIGIN), ("origin", ORIGIN)]).status_code == 400


def test_wrong_tampered_expired_and_logged_out_sessions():
    now = [1000]
    c, gateway = client(lambda: now[0])
    assert c.post("/demo/login", data={"code": "wrong"}, headers={"origin": ORIGIN}).status_code == 401
    token = gateway.token()
    for value in ("junk", token[:-1] + ("0" if token[-1] != "0" else "1"), "99999999999.x"):
        assert not gateway.authenticated(f"{COOKIE}={value}")
    login(c)
    now[0] += SESSION_SECONDS + 1
    assert c.get("/api/cases").status_code == 401
    login(c)
    assert c.post("/demo/logout", headers={"origin": ORIGIN}).status_code == 303
    assert c.get("/api/cases").status_code == 401


def test_login_body_is_bounded_even_when_chunked():
    c, _ = client()
    result = c.post("/demo/login", content=iter([b"code=", b"a" * 600]), headers={"origin": ORIGIN})
    assert result.status_code == 413


def test_rate_limits_recover_and_forwarded_ip_does_not_bypass():
    now = [1000]
    c, _ = client(lambda: now[0])
    for _ in range(20):
        assert c.post("/demo/login", data={"code": "wrong"}, headers={"origin": ORIGIN}).status_code == 401
    assert login(c).status_code == 429
    now[0] += 61
    assert login(c).status_code == 303
    for _ in range(30):
        assert c.post("/api/cases", headers={"origin": ORIGIN}).status_code == 200
    assert c.post("/api/cases", headers={"origin": ORIGIN, "x-forwarded-for": "1.2.3.4"}).status_code == 429
    now[0] += 61
    assert c.post("/api/cases", headers={"origin": ORIGIN}).status_code == 200


@pytest.mark.parametrize("origin", ["http://demo.example", "https://demo.example/path",
                                    "https://demo.example:443", "https://user@demo.example"])
def test_invalid_public_origins_rejected(origin):
    with pytest.raises(ValueError):
        DemoGateway(None, origin, CODE, KEY)


def test_storage_is_new_and_isolated_from_personal_files(tmp_path):
    personal = tmp_path / "data" / "safetrace.sqlite3"
    personal.parent.mkdir()
    personal.write_bytes(b"private database")
    name = "a" * 32
    dedicated = demo_directory(tmp_path, name)
    assert dedicated == tmp_path / "data" / "public-demo" / name
    assert demo_directory(tmp_path, name) == dedicated
    assert personal.read_bytes() == b"private database"
    with pytest.raises(ValueError):
        demo_directory(tmp_path, "../../data")
    unmarked: Path = tmp_path / "data" / "public-demo" / ("b" * 32)
    unmarked.mkdir()
    (unmarked / "safetrace.sqlite3").write_bytes(b"do not expose")
    with pytest.raises(ValueError, match="unmarked"):
        demo_directory(tmp_path, "b" * 32)
