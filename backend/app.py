import io
import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import evaluations, pipeline, storage
from .config import (
    DATA,
    MAX_IMAGE,
    MODEL_DIR,
    OCR_VERSION,
    PIPELINE_VERSION,
    QR_VERSION,
    ROOT,
    RULE_VERSION,
    allowed_hosts,
    offline,
)
from .exports import package
from .graph import build_graph
from .limits import BodyLimitMiddleware
from .schemas import CaseInput, DecisionInput, MaterialInput

Image.MAX_IMAGE_PIXELS = 12_000_000


@asynccontextmanager
async def lifespan(app):
    storage.init()
    pipeline.recover()
    yield


app = FastAPI(title="SafeTrace KZ", version="2.1.0", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    # Error payloads can themselves contain malformed Unicode in input or keys.
    # Return bounded diagnostics, never echo the entire submitted material.
    def safe(value):
        return str(value)[:200].encode("utf-8", errors="backslashreplace").decode("utf-8")

    errors = [
        {"loc": [safe(part) for part in item["loc"]], "msg": safe(item["msg"]), "type": safe(item["type"])}
        for item in exc.errors()[:20]
    ]
    return JSONResponse(
        {"detail": "Некорректный ввод. Проверьте заполненные поля.", "errors": errors}, status_code=422
    )


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    # Single-user local workstation. Block browser cross-origin mutation and Host rebinding.
    host = request.headers.get("host", "").split(":")[0]
    if host not in ("127.0.0.1", "localhost", "testserver"):
        return JSONResponse({"detail": "Только локальный доступ."}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in (
        f"http://{request.headers.get('host')}",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ):
        return JSONResponse({"detail": "Другой origin запрещен."}, status_code=403)
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"detail": "Некорректный Content-Length."}, status_code=400)
    if content_length > MAX_IMAGE + 1024 * 1024:
        return JSONResponse({"detail": "Запрос слишком большой."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def require_case(case_id):
    doc = storage.get(case_id)
    if not doc:
        raise HTTPException(404, "Случай не найден.")
    return doc


def check_images(materials):
    for mat in materials:
        if mat.image_id and not (DATA / "originals" / mat.image_id).is_file():
            raise HTTPException(422, "Изображение не найдено. Загрузите его перед созданием случая.")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app_version": app.version,
        "versions": {
            "rules": RULE_VERSION, "ocr": OCR_VERSION, "qr": QR_VERSION, "pipeline": PIPELINE_VERSION
        },
        "provider_available": bool(os.getenv("GEMINI_API_KEY")) and not offline(),
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "offline": offline(),
        "allowed_hosts": sorted(allowed_hosts()),
        "ocr_installed": all(
            (MODEL_DIR / m).is_dir() for m in ("PP-OCRv5_mobile_det", "cyrillic_PP-OCRv5_mobile_rec")
        ),
        "local_mode": "OCR + правила + разрешенные переходы; ограниченное понимание контекста",
    }


@app.post("/api/uploads")
async def upload(file: UploadFile):
    data = await file.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise HTTPException(413, "Изображение: не более 8 MiB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            if fmt not in ("PNG", "JPEG", "WEBP"):
                raise ValueError()
            if im.width * im.height > 12_000_000 or min(im.size) < 24:
                raise ValueError()
            im.verify()
    except Exception:
        raise HTTPException(422, "Нужен корректный PNG/JPEG/WebP, от 24 px, до 12 мегапикселей.") from None
    suffix = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
    if (
        sum(p.stat().st_size for p in (DATA / "originals").iterdir() if p.is_file()) + len(data)
        > 512 * 1024 * 1024
    ):
        raise HTTPException(507, "Локальное хранилище оригиналов достигло лимита 512 MiB.")
    image_id = f"{uuid.uuid4().hex}.{suffix}"
    (DATA / "originals" / image_id).write_bytes(data)
    return {"image_id": image_id, "sha256": storage.digest(data), "bytes": len(data)}


@app.get("/api/images/{image_id}")
def image(image_id: str):
    import re

    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|webp)", image_id):
        raise HTTPException(404)
    path = DATA / "originals" / image_id
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/api/cases")
def cases():
    return storage.case_summaries()


@app.post("/api/cases", status_code=201)
def create(payload: CaseInput):
    if payload.mode == "replay":
        raise HTTPException(422, "Повтор сохраненного анализа доступен через демонстрационные случаи.")
    check_images(payload.materials)
    with pipeline.QUEUE_LOCK:
        if len(pipeline.ACTIVE) >= 8:
            raise HTTPException(429, "Очередь заполнена.")
        try:
            doc = pipeline.new_case(payload)
        except storage.OriginalIntegrityError as exc:
            raise HTTPException(422, str(exc)) from None
        pipeline.submit(doc["id"])
    return {"id": doc["id"]}


@app.get("/api/cases/{case_id}")
def detail(case_id: str):
    doc = require_case(case_id)
    return {
        **doc,
        "trace": doc.get("trace") or {"observations": [], "relations": [], "requests": 0},
        "decisions": storage.decisions(case_id),
        "graph": build_graph(doc, storage.graph_peers(doc))
        if doc.get("evidence")
        else {"nodes": [], "edges": [], "evidence": []},
    }


@app.post("/api/cases/{case_id}/materials")
def add(case_id: str, material: MaterialInput):
    require_case(case_id)
    check_images([material])
    try:
        pipeline.add_materials(case_id, [material])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"id": case_id}


@app.post("/api/cases/{case_id}/retry")
def retry(case_id: str):
    doc = require_case(case_id)
    if doc["mode"] == "replay":
        raise HTTPException(409, "Это сохраненный повтор. Создайте новый анализ для новых наблюдений.")
    try:
        pipeline.submit(case_id)
    except ValueError as exc:
        raise HTTPException(429, str(exc)) from None
    return {"id": case_id}


@app.post("/api/cases/{case_id}/cancel")
def cancel(case_id: str):
    require_case(case_id)
    pipeline.cancel(case_id)
    return {"requested": True}


@app.post("/api/cases/{case_id}/decision")
def decide(case_id: str, payload: DecisionInput):
    require_case(case_id)
    storage.add_decision(case_id, payload.decision, payload.comment)
    return storage.decisions(case_id)


@app.get("/api/cases/{case_id}/export")
def export(case_id: str):
    try:
        archive = package(require_case(case_id))
    except storage.OriginalIntegrityError as exc:
        raise HTTPException(409, str(exc) + " Экспорт остановлен; восстановите исходный материал.") from None
    return Response(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="safetrace-{case_id[:8]}.zip"'},
    )


@app.get("/api/evaluation")
def evaluation(version: str | None = None):
    try:
        return evaluations.read(ROOT, version)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


DEMOS = [
    {
        "id": "route",
        "title": "За обещанием бонуса",
        "subtitle": "Публикация → посредник → игровой ресурс",
        "material": {
            "source": "DEMO · @qadam",
            "text": "Вечер может больше. Забирай бонус 200% по коду QALA7. "
            "Переходи: https://go.safetrace.test/r/q7",
        },
    },
    {
        "id": "related",
        "title": "Второй след",
        "subtitle": "Другой материал, тот же ref=QALA7",
        "material": {
            "source": "DEMO · @samal",
            "text": "Бүгінгі мүмкіндік! Тіркел, бонус ал. Ұтыс сені күтеді. "
            "https://go.safetrace.test/r/second",
        },
    },
    {
        "id": "warning",
        "title": "Похожее ≠ продвижение",
        "subtitle": "Предупреждение с тем же адресом",
        "material": {
            "source": "DEMO · @saqbol",
            "text": "Осторожно, мошенники! В сообщении обещают: «Забирай бонус 200%, переходи». "
            "Не переводите деньги: это реклама казино. Алаяқтардан сақ болыңыз! "
            "Пример адреса для разбора: https://go.safetrace.test/r/q7",
        },
    },
]


@app.get("/api/demos")
def demos():
    return [{k: v for k, v in d.items() if k != "material"} for d in DEMOS]


@app.post("/api/demos/{demo_id}")
def demo(demo_id: str, replay: bool = False):
    item = next((d for d in DEMOS if d["id"] == demo_id), None)
    if not item:
        raise HTTPException(404)
    if replay:
        saved = ROOT / "fixtures" / "replays" / f"{demo_id}.json"
        if not saved.exists():
            raise HTTPException(409, "Сохраненный анализ еще не подготовлен.")
        doc = json.loads(saved.read_text(encoding="utf-8"))
        old_id = doc["id"]
        new_id = uuid.uuid4().hex
        # IDs and references are consistently remapped, content/result/observation times preserved.
        doc = json.loads(json.dumps(doc).replace(old_id, new_id))
        doc.update(mode="replay", created_at=storage.now(), replayed_from=old_id)
        doc["limitations"].insert(0, "ПОВТОР СОХРАНЕННОГО АНАЛИЗА: новых запросов OCR/модели/сети нет.")
        storage.save(doc)
        return {"id": doc["id"]}
    return create(
        CaseInput(title=item["title"], mode="synthetic", materials=[MaterialInput(**item["material"])])
    )


@app.post("/api/import")
async def import_jsonl(file: UploadFile):
    raw = await file.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise HTTPException(413, "JSONL до 512 KiB.")
    try:
        rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
        if not 1 <= len(rows) <= 20:
            raise ValueError("От 1 до 20 материалов.")
        materials = [MaterialInput.model_validate(row) for row in rows]
    except Exception:
        raise HTTPException(
            422, "Некорректный JSONL. См. формат в README; пути сервера не принимаются."
        ) from None
    return create(CaseInput(title="Пакет JSONL", materials=materials))


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
