"""Bounded URL observation. Live DNS is checked AND pinned at connection time."""

import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from collections import deque
from urllib.parse import parse_qsl, urldefrag, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .config import MAX_BODY, MAX_DEPTH, MAX_REQUESTS, ROOT, allowed_hosts, offline
from .storage import digest, now


class LinkBlocked(ValueError):
    pass


def validate_url(url: str):
    if len(url) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
        raise LinkBlocked("Неоднозначный или слишком длинный URL")
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError as exc:
        raise LinkBlocked("Некорректный URL") from exc
    if p.scheme not in ("http", "https") or not p.hostname:
        raise LinkBlocked("Разрешены только http/https")
    if p.username is not None or p.password is not None:
        raise LinkBlocked("URL с учетными данными запрещен")
    if port not in (None, 80, 443):
        raise LinkBlocked("Разрешены только порты 80/443")
    host = p.hostname
    if host.endswith(".") or "%" in host:
        raise LinkBlocked("Неоднозначное имя узла")
    try:
        host.encode("ascii")
    except UnicodeEncodeError as exc:
        raise LinkBlocked("Используйте явное ASCII/punycode имя узла") from exc
    return p


def normalized(url):
    p = validate_url(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))


def public_ip(ip):
    addr = ipaddress.ip_address(ip)
    # Reject mapped/transition formats too: public outer addresses can wrap local IPv4.
    if not addr.is_global or getattr(addr, "ipv4_mapped", None) or getattr(addr, "sixtofour", None):
        raise LinkBlocked("Локальный, частный или служебный IP запрещен")
    if getattr(addr, "teredo", None):
        raise LinkBlocked("IPv6 transition адрес запрещен")
    return str(addr)


def resolve_public(url, hosts=None, resolver=socket.getaddrinfo):
    p = validate_url(url)
    host = p.hostname.lower()
    # Reject literal IPs and numeric alternative address forms even with allowlisting.
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise LinkBlocked("Локальное имя запрещено")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise LinkBlocked("IP-адреса в URL не разрешены в live-режиме")
    if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9.]+)", host, re.I):
        raise LinkBlocked("Числовая форма адреса запрещена")
    if host not in (allowed_hosts() if hosts is None else hosts):
        raise LinkBlocked("Домен отсутствует в явном списке разрешенных")
    addresses = resolver(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
    ips = sorted({public_ip(a[4][0]) for a in addresses})
    if not ips:
        raise LinkBlocked("DNS не вернул адрес")
    return p, ips[0]


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, tls):
        super().__init__(host, port=port, timeout=4)
        self.ip, self.tls = ip, tls

    def connect(self):
        sock = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        if self.tls:
            try:
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
            except Exception:
                sock.close()
                raise
        self.sock = sock


def live_fetch(url):
    if offline():
        raise LinkBlocked("Офлайн: сетевые запросы выключены")
    p, ip = resolve_public(url)
    conn = PinnedHTTP(p.hostname, ip, p.port or (443 if p.scheme == "https" else 80), p.scheme == "https")
    try:
        target = urlunsplit(("", "", p.path or "/", p.query, ""))
        conn.request(
            "GET",
            target,
            headers={
                "User-Agent": "SafeTraceKZ/1.0 (manual authorized research)",
                "Accept": "text/html,text/plain",
                "Accept-Encoding": "identity",
            },
        )
        response = conn.getresponse()
        headers = {k.lower(): v for k, v in response.getheaders()}
        if response.status in (301, 302, 303, 307, 308):
            return response.status, {"location": headers.get("location", "")}, b""
        kind = headers.get("content-type", "").split(";")[0].strip().lower()
        if kind not in ("text/html", "text/plain"):
            raise LinkBlocked("Ответ не является HTML или обычным текстом")
        if headers.get("content-encoding", "identity") not in ("", "identity"):
            raise LinkBlocked("Сжатый сетевой ответ не поддерживается")
        if int(headers.get("content-length", "0")) > MAX_BODY:
            raise LinkBlocked("Ответ превышает 256 KiB")
        body = bytearray()
        deadline = time.monotonic() + 5
        while len(body) <= MAX_BODY:
            if time.monotonic() > deadline:
                raise LinkBlocked("Истекло время чтения ответа")
            chunk = response.read1(min(16384, MAX_BODY + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        if len(body) > MAX_BODY:
            raise LinkBlocked("Ответ превышает 256 KiB")
        return response.status, {"content-type": kind, "connected-ip": ip}, bytes(body)
    finally:
        conn.close()


class SyntheticTransport:
    """Explicit fixture transport. Never opens a socket; unknown URLs fail closed."""

    def __init__(self, pages=None):
        if pages is None:
            pages = json.loads((ROOT / "fixtures" / "pages.json").read_text(encoding="utf-8"))
        self.pages = pages

    def __call__(self, url):
        validate_url(url)
        entry = self.pages.get(urldefrag(url)[0])
        if entry is None:
            raise LinkBlocked("Синтетический стенд: адрес не найден")
        return entry["status"], entry.get("headers", {}), entry.get("body", "").encode()


def visible_html(body, base_url):
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "html.parser")
    for el in soup(["script", "style", "template", "noscript", "iframe", "object", "svg"]):
        el.decompose()
    for el in list(soup.find_all(True)):
        if el.attrs is not None and (
            el.has_attr("hidden")
            or el.get("aria-hidden") == "true"
            or re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", el.get("style", ""), re.I)
        ):
            el.decompose()
    links = []
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        if label:
            links.append({"url": urljoin(base_url, a["href"]), "quote": label[:300]})
    return soup.get_text(" ", strip=True)[:20000], links[:8]


def extract_urls(text, limit=12):
    urls = []
    for value in re.findall(r"https?://[^\s<>\"'«»]+", text):
        value = value.rstrip(".,;!")
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        urls.append(value)
    return list(dict.fromkeys(urls))[:limit]


def identifiers(url):
    try:
        p = validate_url(url)
    except LinkBlocked:
        return []
    return [
        {
            "domain": p.hostname.lower(),
            "parameter": k.lower(),
            "value": v,
            "scope": f"{p.hostname.lower()}|{p.path or '/'}|{k.lower()}|{v}",
            "url": url,
        }
        for k, v in parse_qsl(p.query, keep_blank_values=False)
        if k.lower() in ("ref", "referral", "aff", "affiliate", "promo", "code", "partner")
        and 2 <= len(v) <= 100
    ]


def trace(urls, fetch=live_fetch, cancelled=lambda: False):
    queue = deque((u, 0, None, "contains_link", u, ()) for u in urls[:12])
    unvisited = [
        {"url": url, "from": None, "type": "contains_link", "reason": "initial_url_limit"}
        for url in urls[12:]
    ]
    seen, observations, relations = {}, [], []
    started, requests = time.monotonic(), 0
    while queue and len(observations) < MAX_REQUESTS and requests < MAX_REQUESTS:
        if cancelled():
            break
        url, depth, parent, relation, quote, ancestors = queue.popleft()
        observation = {
            "id": f"obs-{len(observations)}",
            "url": url,
            "at": now(),
            "status_code": None,
            "text": "",
            "stop": None,
            "depth": depth,
            "method": "synthetic_transport" if isinstance(fetch, SyntheticTransport) else "network",
        }
        observations.append(observation)
        relations.append(
            {
                "from": parent,
                "to": url,
                "type": relation,
                "quote": quote,
                "observation_id": observation["id"],
                "at": observation["at"],
            }
        )
        try:
            key = normalized(url)
            if key in ancestors:
                observation["stop"] = "Цикл"
                continue
            if key in seen:
                previous = seen[key]
                observation.update({k: v for k, v in previous.items() if k not in ("id", "depth")})
                observation["reused_from"] = previous["id"]
                continue
            seen[key] = observation
            if depth > MAX_DEPTH:
                observation["stop"] = "Лимит глубины"
                continue
            if time.monotonic() - started > 35:
                observation["stop"] = "Лимит времени случая"
                break
            observation["attempts"] = []
            for attempt in range(2):
                requests += 1
                try:
                    status, headers, body = fetch(url)
                    observation["attempts"].append({"at": now(), "status_code": status})
                except (OSError, http.client.HTTPException):
                    observation["attempts"].append({"at": now(), "error": "network_error"})
                    if attempt == 0 and requests < MAX_REQUESTS and not cancelled():
                        continue
                    raise
                if (
                    status in (429, 500, 502, 503, 504)
                    and attempt == 0
                    and requests < MAX_REQUESTS
                    and not cancelled()
                ):
                    continue
                break
            observation.update(
                status_code=status, body_sha256=digest(body), connected_ip=headers.get("connected-ip")
            )
            if status in (301, 302, 303, 307, 308):
                if not headers.get("location"):
                    observation["stop"] = "Редирект без Location"
                    continue
                destination = urljoin(url, headers["location"])
                observation["location"] = destination
                queue.append(
                    (destination, depth + 1, url, "redirects", headers["location"], (*ancestors, key))
                )
            elif status >= 400:
                observation["stop"] = f"HTTP {status}"
            else:
                text, links = visible_html(body, url)
                observation.update(text=text, links=links)
                if len(links) > 3:
                    observation["budget_warning"] = (
                        "На странице проверяются первые 3 видимые ссылки; остальные не проверены."
                    )
                    unvisited.extend(
                        {"url": link["url"], "from": url, "type": "page_link", "reason": "page_link_limit"}
                        for link in links[3:]
                    )
                for link in links[:3]:
                    queue.append((link["url"], depth + 1, url, "page_link", link["quote"], (*ancestors, key)))
        except (ValueError, OSError, http.client.HTTPException) as exc:
            observation["stop"] = (
                str(exc)[:200] if isinstance(exc, LinkBlocked) else "Сеть недоступна / таймаут"
            )
    unvisited.extend(
        {"url": url, "from": parent, "type": kind, "reason": "case_budget_or_cancellation"}
        for url, _, parent, kind, _, _ in queue
    )
    if unvisited and observations:
        warning = "Остались непроверенные ссылки: ограничения обхода или отмена."
        observations[-1]["budget_warning"] = " ".join(
            filter(None, (observations[-1].get("budget_warning"), warning))
        )
    return {"observations": observations, "relations": relations, "requests": requests, "unvisited": unvisited}
