import io
import json
import zipfile

from . import storage
from .graph import build_graph
from .report_html import render


def package(doc):
    report = {
        **doc,
        "decisions": storage.decisions(doc["id"]),
        "graph": build_graph(doc, storage.graph_peers(doc)),
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

    files["report.html"] = render(report)
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
