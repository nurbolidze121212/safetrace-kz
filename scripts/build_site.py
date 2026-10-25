"""Build a public read-only demo from authored fixtures using real local analysis."""

import json
import os
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="safetrace-site-") as folder:
        os.environ["SAFETRACE_DATA_DIR"] = folder
        os.environ["SAFETRACE_OFFLINE"] = "1"
        sys.path.insert(0, str(ROOT))
        from backend import pipeline, storage
        from backend.exports import package
        from backend.graph import build_graph
        from backend.schemas import CaseInput

        storage.init()
        output = ROOT / "site"
        output.mkdir(exist_ok=True)
        examples = [
            {"title": "Бонус за ссылкой", "materials": [{"source": "DEMO · @qadam", "text":
                "Вечер может больше. Забирай бонус 200% по коду QALA7. Переходи: https://go.safetrace.test/r/q7"}]},
            {"title": "Второй источник", "materials": [{"source": "DEMO · @samal", "text":
                "Бүгінгі мүмкіндік! Тіркел, бонус ал. Ұтыс сені күтеді. https://go.safetrace.test/r/second"}]},
            {"title": "Предупреждение", "materials": [{"source": "DEMO · @saqbol", "text":
                "Осторожно: мошенники обещают бонус в казино. Не переходите и не переводите деньги. "
                "Это предупреждение о рассылке https://go.safetrace.test/r/q7"}]},
        ]
        image_id = uuid.uuid4().hex + ".png"
        with zipfile.ZipFile(ROOT / "reports/message-demo/photo-export.zip") as archived:
            pixels = archived.read("originals/01.png")
        (Path(folder) / "originals" / image_id).write_bytes(pixels)
        (output / "ocr-original.png").write_bytes(pixels)
        examples.append({"title": "Скриншот и OCR", "materials": [{
            "source": "Авторский OCR-макет", "image_id": image_id}]})
        documents = []
        for example in examples:
            doc = pipeline.new_case(CaseInput(mode="synthetic", **example))
            pipeline.analyze(doc, use_ocr_cache=False)
            assert doc["status"] in {"completed", "partial"}, doc["status"]
            storage.save(doc)
            documents.append(doc)
        for index, doc in enumerate(documents):
            doc["graph"] = build_graph(doc, documents)
            doc["download"] = f"case-{index + 1}.zip"
            (output / doc["download"]).write_bytes(package(doc))
            if doc["materials"][0].get("image_id"):
                doc["image_preview"] = "ocr-original.png"
        evaluation = json.loads((ROOT / "reports/versions/synthetic-v4/evaluation.json").read_text())
        data = {"kind": "saved-synthetic-demonstration", "generated_at": storage.now(),
                "cases": documents, "evaluation": {"full": evaluation["variants"]["full"],
                    "slices": {k: v for k, v in evaluation["slices"].items()
                               if k.startswith("language:") or k in {"image", "text"}}}}
        (output / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"cases": len(documents), "scores": [d["score"]["value"] for d in documents],
                          "ocr_lines": len(documents[-1]["materials"][0]["ocr"]["lines"])}))


if __name__ == "__main__":
    main()
