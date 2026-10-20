import html
import io
import json
import zipfile

from . import storage
from .graph import build_graph


def package(doc):
    report = {
        **doc,
        "decisions": storage.decisions(doc["id"]),
        "graph": build_graph(doc, storage.all_cases()),
    }
    files = {"case.json": json.dumps(report, ensure_ascii=False, indent=2).encode()}
    for i, material in enumerate(doc["materials"], 1):
        if material.get("original_sha256") and storage.digest(material["text"]) != material["original_sha256"]:
            raise storage.OriginalIntegrityError(f"Оригинал текста материала {i} изменен: SHA-256 не совпадает.")
        files[f"originals/{i:02d}-text.txt"] = material["text"].encode()
        if material.get("image_id"):
            data, _ = storage.read_image(material["image_id"], material.get("image_sha256"))
            suffix = material["image_id"].rsplit(".", 1)[1]
            files[f"originals/{i:02d}.{suffix}"] = data

    def esc(value):
        return html.escape(str(value), quote=True)

    body = [
        "<!doctype html><html lang='ru'><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<title>SafeTrace KZ — досье</title><style>",
        "body{max-width:1000px;margin:40px auto;padding:20px;font:16px/1.6 Arial;color:#152528}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f4f4;padding:16px}"
        "h2{border-top:1px solid #ccd;padding-top:20px}small{color:#465f64}</style>",
        f"<h1>{esc(doc['title'])}</h1><p>SafeTrace KZ · {esc(doc['mode'])} · {esc(doc['created_at'])}</p>",
        f"<p>Статус: {esc(doc['status'])}. Индекс: {esc((doc.get('score') or {}).get('value', 'нет результата'))}/100.</p>",
        "<p>Индекс приоритета ручной проверки. Не юридическое заключение.</p>",
        "<h2>Ограничения</h2><ul>" + "".join(f"<li>{esc(x)}</li>" for x in doc["limitations"]) + "</ul>",
    ]
    for i, material in enumerate(doc["materials"], 1):
        body += [
            f"<h2>Материал {i}: {esc(material['source'])}</h2>",
            f"<pre>{esc(material['text'])}\n{esc(material['url'])}</pre>",
        ]
        if material.get("ocr"):
            body.append(
                f"<h3>OCR ({esc(material['ocr']['model'])})</h3><pre>{esc(material['ocr']['text'])}</pre>"
            )
        if material.get("qr", {}).get("codes"):
            body.append(
                "<h3>QR-коды</h3><pre>"
                + esc(json.dumps(material["qr"], ensure_ascii=False, indent=2))
                + "</pre>"
            )
    for name, value in [
        ("Причины приоритета", doc.get("score")),
        ("Извлеченные признаки", doc.get("context")),
        ("Наблюдения переходов", doc.get("trace")),
        ("Доказательная база", report["graph"]["evidence"]),
        ("Граф", report["graph"]),
        ("История ручной проверки", report["decisions"]),
        ("Предыдущие автоматические анализы", doc["history"]),
    ]:
        body += [
            f"<h2>{name}</h2>",
            "<pre>" + esc(json.dumps(value, ensure_ascii=False, indent=2)) + "</pre>",
        ]
    body.append(
        "<h2>Целостность</h2><p>SHA-256 фиксирует целостность файлов после сохранения. "
        "Он не удостоверяет истинность, автора, независимое время или юридическую допустимость.</p></html>"
    )
    files["report.html"] = "\n".join(body).encode()
    manifest = {
        "schema": "safetrace-export-1",
        "created_at": storage.now(),
        "files": [
            {"path": name, "bytes": len(data), "sha256": storage.digest(data)} for name, data in files.items()
        ],
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()
