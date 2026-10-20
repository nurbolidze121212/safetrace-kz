"""Bounded URL observation. Live DNS is checked AND pinned at connection time."""

import codecs
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from collections import deque
from email.message import Message
from urllib.parse import parse_qsl, quote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from .config import MAX_BODY, MAX_DEPTH, MAX_REQUESTS, ROOT, allowed_hosts, offline
from .storage import digest, now


class LinkBlocked(ValueError):
    pass


def validate_url(url: str):
    if len(url) > 2048 or re.search(r"[\s\\\x00-\x1f\x7f]", url):
        raise LinkBlocked("Неоднозначный или слишком длинный URL")
    if re.search(r"%(?![0-9a-fA-F]{2})", url):
        raise LinkBlocked("Некорректное percent-кодирование URL")
    try:
        url.encode("utf-8")
    except UnicodeError as exc:
        raise LinkBlocked("URL содержит некорректный Unicode") from exc
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
    return f"{p.scheme.lower()}://{p.netloc.lower()}" + request_target(p, url)


def request_target(parts, original_url):
    # Preserve existing escapes and query delimiters; encode only the wire target.
    path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
    target = path + ("?" + query if query else "")
    return target + ("?" if empty_query(original_url) else "")


def empty_query(url):
    return url.split("#", 1)[0].endswith("?") and not urlsplit(url).query


def resolve_reference(base, reference):
    resolved = urljoin(base, reference)
    if empty_query(reference):
        p = urlsplit(resolved)
        resolved = urlunsplit((p.scheme, p.netloc, p.path, "", "")) + "?"
        if "#" in reference:
            resolved += "#" + reference.split("#", 1)[1]
    return resolved


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
        target = request_target(p, url)
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
        return response.status, {"content-type": headers["content-type"], "connected-ip": ip}, bytes(body)
    finally:
        conn.close()


class SyntheticTransport:
    """Explicit fixture transport. Never opens a socket; unknown URLs fail closed."""

    def __init__(self, pages=None):
        if pages is None:
            pages = json.loads((ROOT / "fixtures" / "pages.json").read_text(encoding="utf-8"))
        self.pages = {normalized(url): entry for url, entry in pages.items()}

    def __call__(self, url):
        entry = self.pages.get(normalized(url))
        if entry is None:
            raise LinkBlocked("Синтетический стенд: адрес не найден")
        return entry["status"], entry.get("headers", {}), entry.get("body", "").encode()


def _charset(content_type):
    message = Message()
    message["content-type"] = content_type
    return message.get_content_charset()


def page_content(body, base_url, content_type="text/html"):
    """Bounded text extraction, with explicit decoding failures instead of guesses."""
    kind = content_type.split(";", 1)[0].strip().lower()
    result = {"text": "", "links": [], "content_type": content_type, "stop": None}
    if kind not in ("text/html", "text/plain"):
        return {**result, "stop": "Ответ не является HTML или обычным текстом"}
    encoding, source = _charset(content_type), "http"
    if body.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        encoding, source = "utf-32", "bom"
    elif body.startswith(codecs.BOM_UTF8):
        encoding, source = "utf-8-sig", "bom"
    elif body.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding, source = "utf-16", "bom"
    elif not encoding and kind == "text/html":
        # Read declarations, not similarly worded comments or script strings.
        prescan = BeautifulSoup(body[:1024].decode("latin-1"), "html.parser")
        for meta in prescan.find_all("meta"):
            encoding = meta.get("charset")
            if not encoding and meta.get("http-equiv", "").lower() == "content-type":
                encoding = _charset(meta.get("content", ""))
            if encoding:
                source = "meta"
                if encoding.lower() in ("utf-16", "utf-16le", "utf-16be"):
                    encoding = "utf-8"
                break
    if not encoding:
        encoding, source = "utf-8", "default"
    result.update(encoding=encoding[:80], encoding_source=source)
    try:
        codec = codecs.lookup(encoding).name
        # These text codecs cover the RU/KK workflow. Arbitrary Python transform
        # codecs and unsupported encodings must not manufacture page evidence.
        if codec in ("ascii", "iso8859-1"):
            codec = "cp1252"
        if codec not in {
            "utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be",
            "cp1251", "cp1252", "cp866", "koi8-r", "koi8-u", "iso8859-5",
        }:
            raise LookupError
        text = body.decode(codec, errors="strict")
        result["encoding"] = codec
    except (LookupError, UnicodeError):
        result["stop"] = "Кодировка страницы не поддерживается или текст поврежден"
        return result
    if kind == "text/html":
        text, result["links"], metadata = _visible_html(text, base_url)
        result.update(metadata)
    result["text"] = text[:20000]
    if len(text) > 20000:
        result.update(text_truncated=True, content_warning="Текст страницы ограничен 20 000 символами.")
    return result


def visible_html(body, base_url):
    result = page_content(body, base_url)
    return result["text"], result["links"]


def _visible_html(text, base_url):
    soup = BeautifulSoup(text, "html.parser")
    for el in soup(["script", "style", "template", "noscript", "iframe", "object", "svg"]):
        el.decompose()
    metadata = {"document_base": base_url}
    base = soup.find("base", href=True)
    if base:
        metadata["base_href"] = base["href"]
        try:
            metadata["document_base"] = resolve_reference(base_url, base["href"].strip(" \t\r\n\f"))
        except ValueError as exc:
            raise LinkBlocked("Некорректный базовый адрес HTML-страницы") from exc
    for el in list(soup.find_all(True)):
        if el.attrs is not None and (
            el.has_attr("hidden")
            or el.get("aria-hidden") == "true"
            or re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", el.get("style", ""), re.I)
        ):
            el.decompose()
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        label = a.get_text(" ", strip=True)
        href = a["href"].strip(" \t\r\n\f")
        if not label or not href:
            continue
        if re.match(r"^(mailto|tel):", href, re.I):
            metadata["non_web_link_count"] = metadata.get("non_web_link_count", 0) + 1
            continue
        try:
            destination = resolve_reference(metadata["document_base"], href)
        except ValueError:
            destination = href  # The trace will retain and block the malformed URL.
        if href.startswith("#"):
            try:
                if normalized(destination) == normalized(base_url):
                    continue
            except LinkBlocked:
                pass
        if destination not in seen:
            seen.add(destination)
            links.append({"url": destination, "quote": label[:300], "href": a["href"]})
    return soup.get_text(" ", strip=True), links[:8], metadata


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
        pairs = parse_qsl(p.query, keep_blank_values=False, errors="strict")
    except (LinkBlocked, UnicodeError):
        return []
    path = quote(p.path or "/", safe="/%:@!$&'()*+,;=-._~")
    return [
        {
            "domain": p.hostname.lower(),
            "parameter": k,
            "value": v,
            "scope": f"{p.hostname.lower()}|{path}|{k}|{v}",
            "url": url,
        }
        for k, v in pairs
        if k.lower() in ("ref", "referral", "aff", "affiliate", "promo", "code", "partner")
        and 2 <= len(v) <= 100
    ]


def trace(urls, fetch=live_fetch, cancelled=lambda: False):
    queue = deque((u, 0, None, "contains_link", u, (), {}) for u in urls[:12])
    unvisited = [
        {"url": url, "from": None, "type": "contains_link", "reason": "initial_url_limit"}
        for url in urls[12:]
    ]
    seen, observations, relations = {}, [], []
    started, requests = time.monotonic(), 0

    def enqueue_outgoing(observation, ancestors, key):
        url, depth = observation["url"], observation["depth"]
        if observation.get("location"):
            queue.append((observation["location"], depth + 1, url, "redirects",
                          observation["location_header"], (*ancestors, key), {}))
            return
        links = observation.get("links", [])
        if len(links) > 3:
            observation["budget_warning"] = (
                "На странице проверяются первые 3 видимые ссылки; остальные не проверены."
            )
            unvisited.extend(
                {"url": link["url"], "from": url, "type": "page_link", "reason": "page_link_limit"}
                for link in links[3:]
            )
        for link in links[:3]:
            attributes = {"href": link["href"], "document_base": observation["document_base"]}
            if "base_href" in observation:
                attributes["base_href"] = observation["base_href"]
            queue.append((link["url"], depth + 1, url, "page_link", link["quote"], (*ancestors, key), attributes))

    while queue and len(observations) < MAX_REQUESTS and requests < MAX_REQUESTS:
        if cancelled():
            break
        url, depth, parent, relation, quote, ancestors, attributes = queue.popleft()
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
                **attributes,
            }
        )
        try:
            key = normalized(url)
            if key in ancestors:
                observation["stop"] = "Цикл"
                continue
            if depth > MAX_DEPTH:
                observation["stop"] = "Лимит глубины"
                continue
            if time.monotonic() - started > 35:
                observation["stop"] = "Лимит времени случая"
                break
            if key in seen:
                previous = seen[key]
                observation.update({k: v for k, v in previous.items() if k not in ("id", "depth", "url")})
                observation["reused_from"] = previous["id"]
                if url != previous["url"] and not observation["stop"]:
                    enqueue_outgoing(observation, ancestors, key)
                continue
            seen[key] = observation
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
                observation["location"] = resolve_reference(url, headers["location"])
                observation["location_header"] = headers["location"]
                enqueue_outgoing(observation, ancestors, key)
            elif status >= 400:
                observation["stop"] = f"HTTP {status}"
            else:
                observation.update(page_content(body, url, headers.get("content-type", "text/html")))
                if not observation["stop"]:
                    enqueue_outgoing(observation, ancestors, key)
        except (ValueError, OSError, http.client.HTTPException) as exc:
            observation["stop"] = (
                str(exc)[:200] if isinstance(exc, LinkBlocked) else "Сеть недоступна / таймаут"
            )
    unvisited.extend(
        {"url": url, "from": parent, "type": kind, "reason": "case_budget_or_cancellation"}
        for url, _, parent, kind, _, _, _ in queue
    )
    if unvisited and observations:
        warning = "Остались непроверенные ссылки: ограничения обхода или отмена."
        observations[-1]["budget_warning"] = " ".join(
            filter(None, (observations[-1].get("budget_warning"), warning))
        )
    return {"observations": observations, "relations": relations, "requests": requests, "unvisited": unvisited}
