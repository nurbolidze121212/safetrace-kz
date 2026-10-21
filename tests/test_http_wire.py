"""Real local HTTP/TLS bytes through live_fetch; only DNS and socket destination are isolated.

Production IP/hostname checks, request encoding, HTTP parsing and TLS certificate
verification remain active. This is a controlled transport check, not a public-web pilot.
"""

import datetime
import ipaddress
import socket
import ssl
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend import links


@contextmanager
def wire_server(tmp_path, tls=False):
    requests, server_names = [], []
    changed = {"text": "Казино: слоты и депозит"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            requests.append({"path": self.path, "host": self.headers.get("Host")})
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/page?ref=W4")
                self.end_headers()
                return
            if self.path == "/private":
                self.send_response(307)
                self.send_header("Location", "http://127.0.0.1/secret")
                self.end_headers()
                return
            if self.path == "/rebind":
                self.send_response(302)
                self.send_header("Location", "https://changed.test/secret")
                self.end_headers()
                return
            if self.path == "/oversize-header":
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(links.MAX_BODY + 1))
                self.end_headers()
                return
            if self.path == "/oversize-stream":
                body = b"x" * (links.MAX_BODY + 1)
            elif self.path.startswith("/page"):
                body = b'<a href="/final">next</a>'
            else:
                body = changed["text"].encode("cp1251")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=windows-1251")
            if self.path != "/oversize-stream":
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    client_context = None
    if tls:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "wire.test")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("wire.test")]), critical=False)
            .sign(key, hashes.SHA256())
        )
        cert_path, key_path = tmp_path / "server.pem", tmp_path / "server-key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_path), str(key_path))
        context.set_servername_callback(lambda sock, host, ctx: server_names.append(host))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        client_context = ssl.create_default_context(cafile=str(cert_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests, server_names, changed, client_context
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def connect_harness(monkeypatch, port, client_context=None):
    pinned, lookups = [], []
    real_connect, real_resolve = socket.create_connection, links.resolve_public

    def resolver(host, port, **kwargs):
        lookups.append(host)
        ip = "127.0.0.1" if host == "changed.test" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    def connect(address, **kwargs):
        # Socket destination is the ONLY network boundary replaced by this harness.
        # A regression that connects to a hostname instead of the validated IP fails.
        assert address[0] == "93.184.216.34"
        assert ipaddress.ip_address(address[0]).is_global
        assert address[1] in (80, 443)
        pinned.append(address)
        return real_connect(("127.0.0.1", port), **kwargs)

    monkeypatch.setattr(links, "offline", lambda: False)
    monkeypatch.setattr(
        links,
        "resolve_public",
        lambda url: real_resolve(url, {"wire.test", "changed.test", "wrong.test"}, resolver),
    )
    monkeypatch.setattr(links.socket, "create_connection", connect)
    if client_context:
        assert client_context.check_hostname and client_context.verify_mode == ssl.CERT_REQUIRED
        monkeypatch.setattr(links.ssl, "create_default_context", lambda: client_context)
    return pinned, lookups


@pytest.mark.parametrize("tls", [False, True])
def test_real_wire_route_and_changed_destination(tmp_path, monkeypatch, tls):
    with wire_server(tmp_path, tls) as (port, requests, server_names, changed, context):
        pinned, _ = connect_harness(monkeypatch, port, context)
        scheme = "https" if tls else "http"
        url = scheme + "://wire.test/start"
        first = links.trace([url], links.live_fetch)
        assert first["requests"] == 3
        assert not any(o["stop"] for o in first["observations"])
        assert [r["type"] for r in first["relations"]] == ["contains_link", "redirects", "page_link"]
        assert "Казино" in first["observations"][-1]["text"]
        assert all(r["host"] == ("wire.test:443" if tls else "wire.test") for r in requests)
        assert len(pinned) == 3
        if tls:
            assert server_names == ["wire.test"] * 3
        changed["text"] = "Расписание занятий по математике"
        second = links.trace([url], links.live_fetch)
        assert "математике" in second["observations"][-1]["text"]
        assert first["observations"][-1]["body_sha256"] != second["observations"][-1]["body_sha256"]


def test_real_tls_hostname_verification_is_not_disabled(tmp_path, monkeypatch):
    with wire_server(tmp_path, True) as (port, requests, names, _, context):
        connect_harness(monkeypatch, port, context)
        with pytest.raises(ssl.SSLCertVerificationError):
            links.live_fetch("https://wrong.test/")
        assert not requests
        assert names == ["wrong.test"]


@pytest.mark.parametrize("path", ["/private", "/rebind"])
def test_redirect_guard_stops_before_second_socket(tmp_path, monkeypatch, path):
    with wire_server(tmp_path) as (port, requests, _, _, context):
        pinned, lookups = connect_harness(monkeypatch, port, context)
        result = links.trace(["http://wire.test" + path], links.live_fetch)
        assert len(requests) == len(pinned) == 1
        assert result["observations"][-1]["stop"]
        assert "127.0.0.1" not in lookups


@pytest.mark.parametrize("path", ["/oversize-header", "/oversize-stream"])
def test_real_wire_size_limits(tmp_path, monkeypatch, path):
    with wire_server(tmp_path) as (port, _, _, _, context):
        connect_harness(monkeypatch, port, context)
        with pytest.raises(links.LinkBlocked, match="256 KiB"):
            links.live_fetch("http://wire.test" + path)


def test_real_wire_iri_encoding(tmp_path, monkeypatch):
    with wire_server(tmp_path) as (port, requests, _, _, context):
        connect_harness(monkeypatch, port, context)
        url = "http://wire.test/ұтыс?ref=ӘЛІ&encoded=%2F&literal=+#fragment"
        result = links.live_fetch(url)
        assert result[0] == 200
        assert requests[0]["path"] == links.request_target(urlsplit(url), url)
        assert "%D2%B1" in requests[0]["path"] and "fragment" not in requests[0]["path"]
