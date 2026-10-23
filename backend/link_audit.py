"""Passive review of saved inputs. No DNS, HTTP, script or file execution."""

import ipaddress
import json
import re
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

from .config import ROOT
from .links import extract_urls
from .storage import digest

VERSION = "link-audit-1.0.1"
MAX_URLS = 100
REFERENCE = ROOT / "fixtures" / "brand-reference.json"
DOWNLOADS = re.compile(r"\.(?:exe|msi|apk|scr|bat|cmd|ps1|vbs|js|jar)$", re.I)
PRIZE = re.compile(r"вы\s+выиграли|получи(?:те)?\s+(?:приз|iphone)|забери(?:те)?\s+приз|ұтып\s+алдыңыз", re.I)
SECRET = re.compile(r"(?:введи(?:те)?|отправь(?:те)?|сообщи(?:те)?|енгізіңіз|жіберіңіз)\s+(?:свой\s+)?(?:пароль|код\s+из\s+(?:смс|sms)|cvv|құпиясөз|sms\s*код)", re.I)
WARNING = re.compile(r"предупрежден|не\s+(?:вводите|сообщайте|отправляйте)|сақ\s+бол|ешкімге\s+берме", re.I)


def load_reference():
    """Return a curated, dated reference, never a discovered site's self-description."""
    try:
        result = json.loads(REFERENCE.read_text(encoding="utf-8"))
        if result.get("schema") != "safetrace-brand-reference-1":
            raise ValueError()
        for brand in result["brands"]:
            assert brand["name"] and brand["aliases"] and brand["domains"] and brand["source"]
            datetime.fromisoformat(brand["review_after"])
        return result, None
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        return {"brands": []}, "Справочник брендов недоступен или повреждён; проверка принадлежности не выполнена."


def build_audit(case, reference=None, at=None):
    at = at or datetime.now(timezone.utc)
    reference_error = None
    if reference is None:
        reference, reference_error = load_reference()
    evidence = {e["id"]: e for e in case.get("evidence", [])}
    sources, urls, held = [], {}, []

    def add_url(url, ids):
        if url and isinstance(url, str):
            urls.setdefault(url, set()).update(i for i in ids if i in evidence)

    for material in case.get("materials", []):
        text_ids = [eid for eid in material.get("content_evidence_ids", [])
                    if evidence.get(eid, {}).get("method") == "source_text"]
        text = material.get("text", "")
        if text:
            sources.append((text, text_ids, (material.get("context") or {}).get("context")))
        ocr = material.get("ocr") or {}
        if ocr.get("text"):
            ids = [line.get("evidence_id") for line in ocr.get("lines", [])]
            sources.append((ocr["text"], ids, (material.get("context") or {}).get("context")))
        url_ids = [eid for eid, item in evidence.items()
                   if item.get("material_id") == material.get("id") and item.get("method") == "source_text"]
        add_url(material.get("url"), url_ids)
        for url in extract_urls(text, limit=1000):
            add_url(url, [eid for eid in url_ids if url in evidence[eid].get("quote", "")])
        for review in material.get("url_reviews", []):
            if review.get("needs_review") and not review.get("selected_url"):
                held.append(review["raw_url"])
            else:
                add_url(review.get("selected_url") or review.get("raw_url"), review.get("source_evidence_ids", []))
        for code in (material.get("qr") or {}).get("codes", []):
            if code.get("valid_url"):
                add_url(code.get("text"), [code.get("evidence_id")])
    observations = (case.get("trace") or {}).get("observations", [])
    by_url = {}
    for observation in observations:
        add_url(observation.get("url"), [observation.get("evidence_id")])
        by_url.setdefault(observation.get("url"), []).append(observation)
        if observation.get("text"):
            sources.append((observation["text"], [observation.get("evidence_id")], (observation.get("context") or {}).get("context")))

    findings, results = [], []

    def finding(code, title, detail, quote, ids=(), url=None, source=None):
        item = {"id": "audit-" + digest(code + str(url) + quote)[:16], "code": code,
                "title": title, "detail": detail, "quote": quote,
                "evidence_ids": sorted({i for i in ids if i in evidence}), "url": url, "reference": source}
        existing = next((f for f in findings if f["id"] == item["id"]), None)
        if existing is None:
            findings.append(item)
        else:
            # One displayed signal can have several independently supporting sources.
            existing["evidence_ids"] = sorted(set(existing["evidence_ids"]) | set(item["evidence_ids"]))
        return item["id"]

    for url, ids in list(urls.items())[:MAX_URLS]:
        row = {"url": url, "host": "", "unicode_host": "", "observed": any(not o.get("stop") and o.get("status_code") is not None for o in by_url.get(url, [])), "finding_ids": [], "brands": [], "evidence_ids": sorted(ids)}

        def flag(code, title, detail, quote=url, source=None):
            row["finding_ids"].append(finding(code, title, detail, quote, ids, url, source))

        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower().rstrip(".")
            if parts.scheme not in ("http", "https") or not host:
                raise ValueError()
            row["host"] = host
            try:
                row["unicode_host"] = host.encode("ascii").decode("idna")
            except (UnicodeError, ValueError):
                row["unicode_host"] = host
            if parts.username is not None:
                flag("userinfo", "Имя перед @ не определяет сайт", "Фактический узел находится после @. Такой URL не разрешён сетевым обходчиком.")
            if parts.scheme == "http":
                flag("http", "Адрес использует HTTP", "Соединение этого адреса не защищено HTTPS. Само по себе это не доказательство мошенничества.")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                flag("ip_host", "Вместо домена указан IP-адрес", "Имя организации из такого адреса не устанавливается; IP сам по себе не означает угрозу.")
            if any(label.startswith("xn--") for label in host.split(".")):
                flag("idn", "Международное имя домена", "Сверьте ASCII и Unicode написание. Punycode используется и обычными сайтами; это не вердикт о фишинге.")
            if DOWNLOADS.search(unquote(parts.path)):
                flag("download", "Адрес похож на загрузку программы или скрипта", "Содержимое не скачивалось и не исполнялось. По расширению нельзя определить наличие вируса.")
            for brand in reference.get("brands", []):
                matched = any(host == d or host.endswith("." + d) for d in brand["domains"])
                embedded = any(d in host and not matched for d in brand["domains"])
                expired = at.date() > datetime.fromisoformat(brand["review_after"]).date()
                if matched:
                    row["brands"].append({"name": brand["name"], "status": "reference_expired" if expired else "domain_match", "source": brand["source"], "checked_at": brand["checked_at"], "review_after": brand["review_after"]})
                elif embedded:
                    flag("embedded_brand_domain", "Известный домен встроен в чужое имя", f"Узел {host} не принадлежит дереву домена {', '.join(brand['domains'])}. Возможна имитация имени; владелец не установлен." + (" Справочник требует обновления." if expired else ""), host, brand["source"])
        except ValueError:
            flag("invalid_url", "Адрес нельзя однозначно разобрать", "Сетевой запрос не выполнялся; требуется сверка исходника.")
        results.append(row)

    for text, ids, context in sources:
        prize, secret = PRIZE.search(text), SECRET.search(text)
        if prize and secret and context not in ("warning", "news", "education") and not WARNING.search(text):
            # Quote the actual independent matches; do not invent a combined sentence.
            finding("prize_secret", "Обещание приза вместе с запросом секрета", "В одном источнике найдены обещание выигрыша и просьба сообщить пароль/код. Это повод для проверки, не подтверждение кражи данных.", prize.group() + " […] " + secret.group(), ids)

    review_codes = {"userinfo", "embedded_brand_domain", "prize_secret", "invalid_url"}
    active = case.get("status") in ("pending", "running", "error", "cancelled")
    return {
        "schema": VERSION, "case_id": case["id"], "analysis_id": case.get("analysis_id"),
        "source_analyzed_at": case.get("analyzed_at"), "generated_at": at.isoformat(),
        "mode": case.get("mode"), "status": "source_incomplete" if active else "needs_review" if any(f["code"] in review_codes for f in findings) else "no_selected_indicators",
        "probability": None, "network_requests": 0, "urls": results, "findings": findings,
        "coverage": {"urls_checked": len(results), "urls_available": len(urls), "observed_urls": sum(r["observed"] for r in results), "held_ocr_urls": len(held), "truncated": len(urls) > MAX_URLS},
        "held_ocr_urls": held,
        "checks": [
            {"name": "Структура URL", "status": "checked" if results else "no_data", "detail": "HTTP, IP, Unicode/punycode, имя перед @, расширение файла."},
            {"name": "Имитация известного домена", "status": "unavailable" if reference_error else "limited", "detail": reference_error or f"Справочник: {len(reference.get('brands', []))} бренд(ов). Совпадение имени не подтверждает честность бизнеса или лицензию."},
            {"name": "Приз и запрос пароля/кода", "status": "limited", "detail": "Узкие локальные шаблоны RU/KK по сохранённому тексту; независимая точность не измерена."},
            {"name": "Базы фишинга и вредоносных URL", "status": "not_connected", "detail": "Внешние базы угроз не подключены. Совпадение или отсутствие совпадения не проверялось."},
            {"name": "Антивирус и исполнение страницы", "status": "not_implemented", "detail": "Файлы и JavaScript не исполняются. Наличие вируса не установлено."},
            {"name": "Организация и лицензия казино", "status": "not_verified", "detail": "Владелец, лицензия, выплаты и подлинность казино не подтверждены. Игорные признаки оцениваются отдельно в основном анализе."},
        ],
        "limitations": ["Экспериментальный пассивный разбор, не сертификат безопасности.", "Процент вероятности не вычисляется: калиброванной модели для этих угроз нет.", "Нет новых сетевых запросов: используются введённые адреса и сохранённые наблюдения.", "Нет признаков по выбранным правилам не означает отсутствие мошенничества."] + ([reference_error] if reference_error else []),
    }
