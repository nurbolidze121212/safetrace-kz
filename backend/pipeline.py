import io
import logging
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy

from PIL import Image, ImageOps

from . import storage
from .analysis import local_context, normalize_text, score, verify_claims
from .config import DATA, OCR_VERSION, PIPELINE_VERSION, QR_VERSION, RULE_VERSION
from .graph import build_graph
from .links import SyntheticTransport, extract_urls, identifiers, live_fetch, trace
from .ocr import recognize
from .providers import GeminiProvider, LocalProvider, ProviderUnavailable
from .qr import decode as decode_qr

EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="safetrace")
CANCELS: dict[str, threading.Event] = {}
FUTURES: dict[str, Future] = {}
ACTIVE = set()
QUEUE_LOCK = threading.RLock()
STAGES = ["originals", "ocr", "features", "links", "graph", "priority"]
LOGGER = logging.getLogger(__name__)


def _material_record(material):
    mat = material.model_dump(mode="json")
    mat.update(id=uuid.uuid4().hex, original_sha256=storage.digest(mat["text"]))
    if mat.get("image_id"):
        _, mat["image_sha256"] = storage.read_image(mat["image_id"])
    return mat


def new_case(payload):
    case_id = uuid.uuid4().hex
    doc = {
        "id": case_id,
        "title": payload.title,
        "mode": payload.mode,
        "created_at": storage.now(),
        "status": "pending",
        "stage": "originals",
        "progress": 0,
        "materials": [],
        "stages": {stage: "pending" for stage in STAGES},
        "evidence": [],
        "trace": {"observations": [], "relations": [], "requests": 0},
        "limitations": [],
        "history": [],
        "versions": {
            "rules": RULE_VERSION, "ocr": OCR_VERSION, "qr": QR_VERSION, "pipeline": PIPELINE_VERSION
        },
    }
    for m in payload.materials:
        doc["materials"].append(_material_record(m))
    storage.save(doc)
    return doc


def add_materials(case_id, materials):
    with QUEUE_LOCK:
        if case_id in ACTIVE:
            raise ValueError("Дождитесь завершения или отмены текущего анализа.")
        doc = storage.get(case_id)
        if doc is None:
            raise ValueError("Случай не найден.")
        if doc["mode"] == "replay":
            raise ValueError("Сохраненный повтор неизменяем; создайте новый анализ.")
        if len(ACTIVE) >= 8:
            raise ValueError("Очередь заполнена: максимум 8 задач.")
        if len(doc["materials"]) + len(materials) > 20:
            raise ValueError("Не более 20 материалов в случае.")
        previous = deepcopy(doc)
        for material in materials:
            doc["materials"].append(_material_record(material))
        try:
            storage.save(doc)
            submit(case_id)
        except Exception:
            storage.save(previous)
            raise


def submit(case_id):
    with QUEUE_LOCK:
        if case_id in ACTIVE:
            return
        if len(ACTIVE) >= 8:
            raise ValueError("Очередь заполнена: максимум 8 задач.")
        doc = storage.get(case_id)
        if doc is None:
            raise ValueError("Случай не найден.")
        previous = deepcopy(doc)
        last = doc["history"][-1] if doc["history"] else {}
        already_archived = (
            doc.get("analysis_id") == last.get("analysis_id")
            and doc.get("analyzed_at") == last.get("at")
        )
        if doc.get("score") is not None and not already_archived:
            doc["history"].append(
                {
                    "at": doc.get("analyzed_at"),
                    "analysis_id": doc.get("analysis_id"),
                    "score": doc["score"],
                    "trace": doc.get("trace"),
                    "mode": doc["mode"],
                    "evidence": doc.get("evidence"),
                    "materials": [m for m in doc["materials"] if m.get("source_evidence_id")],
                    "versions": doc.get("versions"),
                }
            )
        doc.update(status="pending", stage="originals", progress=0, stages={s: "pending" for s in STAGES})
        ACTIVE.add(case_id)
        CANCELS[case_id] = threading.Event()
        try:
            storage.save(doc)
            FUTURES[case_id] = EXECUTOR.submit(_run, case_id)
        except Exception:
            ACTIVE.discard(case_id)
            CANCELS.pop(case_id, None)
            FUTURES.pop(case_id, None)
            storage.save(previous)
            raise


def cancel(case_id):
    with QUEUE_LOCK:
        if event := CANCELS.get(case_id):
            event.set()
            future = FUTURES.get(case_id)
            if future is not None and future.cancel():
                # A waiting job has no writer. Persist cancellation and immediately free its slot.
                try:
                    doc = storage.get(case_id)
                    doc.update(status="cancelled", stages={s: "cancelled" for s in STAGES})
                    storage.save(doc)
                finally:
                    ACTIVE.discard(case_id)
                    CANCELS.pop(case_id, None)
                    FUTURES.pop(case_id, None)


def recover():
    for doc in storage.all_cases():
        if doc["status"] in ("pending", "running"):
            doc.update(status="partial", stage="interrupted")
            for key, value in doc["stages"].items():
                if value in ("pending", "running"):
                    doc["stages"][key] = "cancelled"
            doc["limitations"].append("Приложение перезапущено: нажмите «Повторить анализ».")
            storage.save(doc)


def _run(case_id):
    doc = None
    try:
        doc = storage.get(case_id)
        if doc is None:
            raise ValueError("Missing queued case")
        event = CANCELS[case_id]
        analyze(doc, cancelled=event.is_set, checkpoint=storage.save)
    except Exception as exc:
        # Exception text may contain provider credentials or source content; log only safe metadata.
        LOGGER.warning("Analysis %s failed (%s)", case_id, type(exc).__name__)
        try:
            doc = doc or storage.get(case_id)
            if doc is not None:
                doc.update(status="error")
                doc["limitations"].append("Ошибка обработки. Оригиналы сохранены; доступен повтор.")
                for key, value in doc["stages"].items():
                    if value in ("pending", "running"):
                        doc["stages"][key] = "cancelled"
                if doc.get("stage") in doc["stages"]:
                    doc["stages"][doc["stage"]] = "error"
                storage.save(doc)
        except Exception as persist_error:
            LOGGER.warning("Could not persist failure for %s (%s)", case_id, type(persist_error).__name__)
    finally:
        with QUEUE_LOCK:
            ACTIVE.discard(case_id)
            CANCELS.pop(case_id, None)
            FUTURES.pop(case_id, None)


def analyze(
    doc, cancelled=lambda: False, checkpoint=lambda doc: None, variant="full", fetch=None, use_ocr_cache=True
):
    started = time.perf_counter()
    # A new attempt owns a new evidence namespace. Keep originals/history, never derived old fields.
    for key in ("score", "sufficient_data", "elapsed_ms", "context", "claims", "rejected_claims", "provider", "graph"):
        doc.pop(key, None)
    for mat in doc["materials"]:
        for key in (
            "source_evidence_id", "normalized_text", "ocr", "qr", "urls", "promo_codes",
            "content_evidence_ids", "reachable_urls", "score", "context", "sufficient_data", "urls_limited",
            "image_integrity_failed", "text_integrity_failed",
        ):
            mat.pop(key, None)
    doc.update(
        evidence=[],
        limitations=[],
        identifiers=[],
        analyzed_at=storage.now(),
        status="running",
        stage="originals",
        progress=0,
        stages={stage: "pending" for stage in STAGES},
        trace={"observations": [], "relations": []},
        versions={
            "rules": RULE_VERSION, "ocr": OCR_VERSION, "qr": QR_VERSION, "pipeline": PIPELINE_VERSION
        },
    )
    doc["analysis_id"] = uuid.uuid4().hex[:12]
    if doc["mode"] in ("synthetic", "replay"):
        doc["limitations"].append("Синтетический стенд: материалы и страницы созданы для демонстрации.")
    doc["limitations"].append("Индекс не является вероятностью нарушения или юридическим заключением.")
    sources, urls, images, counter = {}, [], [], 0

    def evidence(quote, source_id, method, **extra):
        nonlocal counter
        counter += 1
        eid = f"{doc['id']}-{doc['analysis_id']}-e{counter}"
        doc["evidence"].append(
            {
                "id": eid,
                "quote": quote,
                "source_id": source_id,
                "method": method,
                "at": storage.now(),
                **extra,
            }
        )
        return eid

    def stage(name):
        if cancelled():
            doc["status"] = "cancelled"
            for key, value in doc["stages"].items():
                if value in ("pending", "running"):
                    doc["stages"][key] = "cancelled"
            checkpoint(doc)
            return False
        previous = doc.get("stage")
        if previous in doc["stages"] and doc["stages"][previous] == "running":
            doc["stages"][previous] = "completed"
        doc.update(stage=name, progress=round(STAGES.index(name) / len(STAGES) * 100))
        doc["stages"][name] = "running"
        checkpoint(doc)
        return True

    if not stage("originals"):
        return doc
    for mat in doc["materials"]:
        if mat.get("original_sha256") and storage.digest(mat["text"]) != mat["original_sha256"]:
            mat["text_integrity_failed"] = True
            sources[mat["id"]] = ""
            doc["stages"]["originals"] = "partial"
            doc["limitations"].append("Оригинал текста изменен: SHA-256 не совпадает. Этот материал не анализировался.")
            continue
        mat["source_evidence_id"] = evidence(
            mat["source"],
            mat["id"],
            "user_supplied",
            material_id=mat["id"],
            note="Источник заявлен при импорте; авторство не проверено.",
        )
        sources[mat["id"]] = mat["text"] + ("\n" + mat["url"] if mat["url"] else "")
        mat["normalized_text"] = normalize_text(mat["text"])
    if not stage("ocr"):
        return doc
    for mat in doc["materials"]:
        if mat.get("text_integrity_failed"):
            continue
        mat.pop("ocr", None)
        mat.pop("qr", None)
        if mat.get("image_id") and variant != "baseline":
            try:
                _, fingerprint = storage.read_image(mat["image_id"], mat.get("image_sha256"))
                mat["image_sha256"] = fingerprint
            except storage.OriginalIntegrityError as exc:
                mat["image_integrity_failed"] = True
                doc["limitations"].append(str(exc) + " Анализ этого изображения пропущен.")
                doc["stages"]["ocr"] = "partial"
                continue
            try:
                path = DATA / "originals" / mat["image_id"]
                mat["ocr"] = recognize(path, use_cache=use_ocr_cache)
                source_id = mat["id"] + "-ocr"
                sources[source_id] = mat["ocr"]["text"]
                for line in mat["ocr"]["lines"]:
                    line["evidence_id"] = evidence(
                        line["text"],
                        source_id,
                        "ocr",
                        material_id=mat["id"],
                        polygon=line["polygon"],
                        confidence=line["confidence"],
                    )
                if not mat["ocr"]["lines"]:
                    doc["limitations"].append("OCR не нашел читаемый текст.")
                with Image.open(path) as im:
                    buffer = io.BytesIO()
                    clean = ImageOps.exif_transpose(im).convert("RGB")
                    clean.thumbnail((1600, 1600))
                    clean.save(buffer, format="PNG")
                    if len(images) < 2:
                        images.append(buffer.getvalue())
            except Exception:
                doc["limitations"].append(
                    "OCR недоступен для одного изображения; остальные материалы обработаны."
                )
                doc["stages"]["ocr"] = "partial"
            try:
                mat["qr"] = decode_qr(DATA / "originals" / mat["image_id"], use_cache=use_ocr_cache)
                for code in mat["qr"]["codes"]:
                    code["evidence_id"] = evidence(
                        code["text"],
                        mat["id"] + "-qr",
                        "qr_decode",
                        material_id=mat["id"],
                        polygon=code["polygon"],
                        note=code["reason"] or "Адрес декодирован из QR; безопасность проверяется отдельно.",
                    )
            except Exception:
                doc["limitations"].append("QR-коды одного изображения не удалось проверить.")
                doc["stages"]["ocr"] = "partial"
        if cancelled():
            stage("features")
            return doc
    if not stage("features"):
        return doc
    provider = GeminiProvider() if doc["mode"] == "cloud" else LocalProvider()
    method = "cloud_model" if doc["mode"] == "cloud" else "local_rule"
    try:
        context = provider.extract(sources, images)
    except ProviderUnavailable as exc:
        doc["limitations"].append(str(exc))
        context = LocalProvider().extract(sources)
        method = "local_rule"
        doc["stages"]["features"] = "partial"
    claims, rejected = verify_claims(context, sources)
    if method == "local_rule" and len(doc["materials"]) > 1:
        claims = []
        for mat in doc["materials"]:
            own_sources = {
                key: text for key, text in sources.items() if key in (mat["id"], mat["id"] + "-ocr")
            }
            verified, _ = verify_claims(local_context(own_sources), own_sources)
            claims.extend(verified)
    if method == "cloud_model" and (len(doc["materials"]) > 2 or sum(map(len, sources.values())) > 40000):
        doc["limitations"].append(
            "Облачный бюджет: не более двух изображений и 40 000 символов за вызов; большой пакет требует разделения."
        )
        doc["stages"]["features"] = "partial"
    for claim in claims:
        claim["evidence_id"] = evidence(
            claim["quote"],
            claim["source_id"],
            method,
            start=claim["start"],
            end=claim["end"],
            material_id=claim["source_id"].removesuffix("-ocr"),
        )
    doc.update(context=context.model_dump(), claims=claims, rejected_claims=rejected, provider=method)
    doc["limitations"].extend(context.limitations)
    if rejected:
        doc["limitations"].append(f"Отклонено цитат без совпадения с источником: {len(rejected)}.")
    for mat in doc["materials"]:
        mat["urls"] = []
        mat["promo_codes"] = []
        mat["content_evidence_ids"] = []
        if mat.get("text_integrity_failed"):
            continue
        for source_id in (mat["id"], mat["id"] + "-ocr"):
            if sources.get(source_id, "").strip():
                mat["content_evidence_ids"].append(
                    evidence(
                        sources[source_id],
                        source_id,
                        "ocr" if source_id.endswith("-ocr") else "source_text",
                        material_id=mat["id"],
                    )
                )
            for match in re.finditer(
                r"\b(?:промокод|код|promo\s*code)\s*[:=]?\s*([A-Za-zА-Яа-я0-9]{3,32})",
                sources.get(source_id, ""),
                re.I,
            ):
                code = match.group(1)
                eid = evidence(
                    match.group(),
                    source_id,
                    "source_text",
                    material_id=mat["id"],
                    note="Код из текста без подтвержденной области назначения.",
                )
                mat["promo_codes"].append({"value": code, "evidence_id": eid})
            extracted = extract_urls(
                mat["text"] if source_id == mat["id"] else sources.get(source_id, ""), limit=13
            )
            if len(extracted) > 12:
                mat["urls_limited"] = True
                doc["stages"]["features"] = "partial"
                doc["limitations"].append(
                    "Из одного текстового/OCR-источника извлечены первые 12 ссылок; остальные не проверены."
                )
            for url in extracted[:12]:
                mat["urls"].append(url)
                evidence(
                    url,
                    source_id,
                    "ocr" if source_id.endswith("-ocr") else "source_text",
                    material_id=mat["id"],
                )
        if mat["url"]:
            mat["urls"].append(mat["url"])
            evidence(
                mat["url"],
                mat["id"],
                "source_text",
                material_id=mat["id"],
                note="Адрес из отдельного поля URL сохранен без обрезки параметров.",
            )
        for code in mat.get("qr", {}).get("codes", []):
            mat["content_evidence_ids"].append(code["evidence_id"])
            if code["valid_url"]:
                mat["urls"].append(code["text"])
        mat["urls"] = list(dict.fromkeys(mat["urls"]))
        urls.extend(mat["urls"])
    if not stage("links"):
        return doc
    if variant == "full":
        fetch = fetch or (SyntheticTransport() if doc["mode"] == "synthetic" else live_fetch)
        doc["trace"] = trace(list(dict.fromkeys(urls)), fetch, cancelled)
    page_claims = []
    for obs in doc["trace"]["observations"]:
        obs["evidence_id"] = evidence(
            obs.get("text") or obs.get("location") or obs.get("stop") or "",
            obs["url"],
            obs["method"],
            url=obs["url"],
            status_code=obs["status_code"],
            observation_id=obs["id"],
        )
        if obs["stop"]:
            doc["stages"]["links"] = "partial"
            doc["limitations"].append(f"Непроверенный участок: {obs['stop']}")
        if obs.get("budget_warning"):
            doc["limitations"].append(obs["budget_warning"])
            doc["stages"]["links"] = "partial"
        if obs.get("content_warning"):
            doc["limitations"].append(obs["content_warning"])
            doc["stages"]["links"] = "partial"
        if obs["text"]:
            pc, _ = verify_claims(local_context({obs["url"]: obs["text"]}), {obs["url"]: obs["text"]})
            for claim in pc:
                claim["evidence_id"] = evidence(
                    claim["quote"],
                    obs["url"],
                    "local_rule",
                    start=claim["start"],
                    end=claim["end"],
                    url=obs["url"],
                )
            page_claims.extend(pc)
    by_obs = {o["id"]: o for o in doc["trace"]["observations"]}
    for rel in doc["trace"]["relations"]:
        obs = by_obs[rel["observation_id"]]
        rel["method"] = obs["method"]
        rel["evidence_id"] = evidence(
            rel["quote"],
            rel["from"] or rel["to"],
            rel["method"],
            url=rel["from"] or rel["to"],
            relation=rel["type"],
            **{key: rel[key] for key in ("href", "base_href", "document_base") if key in rel},
        )
    # Reachability from each original material keeps scoped identifiers attributable.
    for mat in doc["materials"]:
        reachable = set(mat["urls"])
        for _ in range(6):
            for rel in doc["trace"]["relations"]:
                if rel["from"] in reachable:
                    reachable.add(rel["to"])
        mat["reachable_urls"] = sorted(reachable)
        for obs in doc["trace"]["observations"]:
            has_outgoing = any(r["from"] == obs["url"] for r in doc["trace"]["relations"])
            if (
                obs["url"] in reachable
                and obs["status_code"]
                and 200 <= obs["status_code"] < 300
                and not has_outgoing
                and not obs.get("stop")
            ):
                for token in identifiers(obs["url"]):
                    entry = {**token, "material_id": mat["id"], "evidence_id": obs["evidence_id"]}
                    if entry not in doc["identifiers"]:
                        doc["identifiers"].append(entry)
    if not stage("graph"):
        return doc
    doc["graph"] = build_graph(doc)
    if not stage("priority"):
        return doc
    scopes = {}
    for token in doc["identifiers"]:
        scopes.setdefault(token["scope"], set()).add(token["material_id"])
    material_scores = []
    for mat in doc["materials"]:
        own_sources = {key: text for key, text in sources.items() if key in (mat["id"], mat["id"] + "-ocr")}
        own_claims = [c for c in claims if c["source_id"] in own_sources]
        own_pages = [c for c in page_claims if c["source_id"] in mat["reachable_urls"]]
        own_context = local_context(own_sources)
        repeated = any(mat["id"] in ids and len(ids) > 1 for ids in scopes.values())
        mat["score"] = score(own_claims, own_pages, own_context.context, repeated, own_context.contradictions)
        mat["context"] = own_context.model_dump()
        own_observations = [o for o in doc["trace"]["observations"] if o["url"] in mat["reachable_urls"]]
        any_page = any(o["text"] for o in own_observations)
        missing_route = (bool(mat["urls"]) and not any_page) or any(
            o.get("stop") or o.get("text_truncated") for o in own_observations
        ) or mat.get("urls_limited", False) or any(
            item["url"] in mat["urls"] or item["from"] in mat["reachable_urls"]
            for item in doc["trace"].get("unvisited", [])
        )
        strong_source_context = any(c["kind"] == "gambling" for c in own_claims) or own_context.context in (
            "warning",
            "news",
            "education",
            "free_game",
        )
        mat["sufficient_data"] = (
            bool(any(t.strip() for t in own_sources.values()))
            and not mat.get("image_integrity_failed")
            and not (missing_route and not strong_source_context and variant == "full")
        )
        material_scores.append(mat["score"])
    doc["score"] = max(material_scores, key=lambda s: s["value"])
    doc["score"]["aggregation"] = (
        "Максимальный приоритет отдельного материала; признаки разных материалов не смешиваются."
    )
    if variant == "baseline":
        hit = bool(re.search(r"казино|casino|слот|ставк|фриспин|құмар", "\n".join(sources.values()), re.I))
        doc["score"].update(value=100 if hit else 0, level="high" if hit else "low")
    enough = all(m["sufficient_data"] for m in doc["materials"])
    if not enough:
        doc["limitations"].append(
            "Не хватает данных: отсутствие подтвержденного назначения не означает низкий риск."
        )
    doc["sufficient_data"] = enough
    doc["stages"]["priority"] = "completed"
    doc.update(
        status="partial"
        if any(s == "partial" for s in doc["stages"].values()) or not enough
        else "completed",
        progress=100,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    doc["limitations"] = list(dict.fromkeys(doc["limitations"]))
    checkpoint(doc)
    return doc
