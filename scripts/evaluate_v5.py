"""Inference-only worker. Never opens annotations or uses reference transcriptions."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

FILES = ["analysis.py", "normalization.py", "image_triage.py", "ocr.py", "ocr_urls.py", "attribution.py",
         "links.py", "pipeline.py", "weights.json", "config.py", "providers.py", "schemas.py",
         "material_identity.py", "qr.py", "storage.py", "queue_store.py", "track_extensions.py"]


def hashes(source):
    return {"backend/" + name: hashlib.sha256((source / "backend" / name).read_bytes()).hexdigest()
            for name in FILES if (source / "backend" / name).exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", default="full", choices=["full", "without_normalization"])
    parser.add_argument("--freeze", type=Path)
    args = parser.parse_args()
    source, dataset = args.source.resolve(), args.dataset.resolve()
    before = hashes(source)
    if args.freeze:
        frozen = json.loads(args.freeze.read_text(encoding="utf-8"))
        assert frozen["analysis_hashes"] == before, "Candidate differs from freeze"
    elif "v5-dev" not in str(dataset):
        raise RuntimeError("Final dataset requires a freeze manifest")
    if args.output.exists():
        raise FileExistsError(args.output)
    input_hashes = {p.relative_to(dataset).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in dataset.rglob("*") if p.is_file() and p.name != "annotations.jsonl"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="safetrace-v5-evaluation-") as temporary:
        os.environ["SAFETRACE_DATA_DIR"] = temporary
        os.environ["SAFETRACE_OFFLINE"] = "1"
        os.environ.pop("SAFETRACE_REDIS_URL", None)
        sys.path.insert(0, str(source))
        from backend import config

        config.MODEL_DIR = args.models.resolve()
        from backend import analysis, pipeline, storage
        from backend.links import SyntheticTransport
        from backend.schemas import CaseInput, MaterialInput

        if args.variant == "without_normalization":
            analysis.lexical_view = lambda text: (text, [(i, i + 1) for i in range(len(text))])
        storage.init()
        inputs = [json.loads(line) for line in (dataset / "inputs.jsonl").read_text(encoding="utf-8").splitlines()]
        pages = json.loads((dataset / "pages.json").read_text(encoding="utf-8"))
        records = []
        for index, item in enumerate(inputs):
            materials = []
            for raw in item["materials"]:
                material = {k: v for k, v in raw.items() if k != "image"}
                if raw.get("image"):
                    image = dataset / raw["image"]
                    image_id = hashlib.sha256(image.read_bytes()).hexdigest()[:32] + image.suffix
                    (Path(temporary) / "originals" / image_id).write_bytes(image.read_bytes())
                    material["image_id"] = image_id
                materials.append(MaterialInput(**material))
            doc = pipeline.new_case(CaseInput(title="Evaluation input", mode="synthetic", materials=materials))
            started = time.perf_counter()
            pipeline.analyze(doc, fetch=SyntheticTransport(pages), use_ocr_cache=False)
            elapsed_ms = (time.perf_counter() - started) * 1000
            # Only observed original text, actual OCR and fetched page content enter ML.
            material_texts = [m.get("text", "") + "\n" + m.get("ocr", {}).get("text", "") for m in doc["materials"]]
            page_texts = [o.get("text", "") for o in doc["trace"]["observations"]]
            record = {"id": item["id"], "score": doc["score"]["value"], "level": doc["score"]["level"],
                      "predicted": int(doc["score"]["value"] >= 65 and doc["sufficient_data"]),
                      "sufficient": doc["sufficient_data"], "status": doc["status"], "elapsed_ms": elapsed_ms,
                      "ml_input": "MESSAGE\n" + "\n".join(material_texts) + "\nDESTINATION\n" + "\n".join(page_texts),
                      "game_evidence": any(c.kind == "gambling" for t in material_texts + page_texts
                                           for c in analysis.local_context({"s": t}).claims),
                      "alternative": any(m["context"]["context"] in analysis.ALTERNATIVES for m in doc["materials"]),
                      "contributions": doc["score"]["contributions"],
                      "ocr": [m.get("ocr", {}) for m in doc["materials"] if m.get("image_id")],
                      "limitations": doc["limitations"]}
            records.append(record)
            if (index + 1) % 16 == 0:
                print(f"{args.variant}: {index + 1}/{len(inputs)}", flush=True)
        assert before == hashes(source), "Analysis code changed during evaluation"
        assert all(hashlib.sha256((dataset / name).read_bytes()).hexdigest() == value
                   for name, value in input_hashes.items()), "Inputs changed during evaluation"
        result = {"variant": args.variant, "analysis_hashes": before, "input_hashes": input_hashes,
                  "versions": {"rules": config.RULE_VERSION, "ocr": config.OCR_VERSION},
                  "records": records, "annotation_access": "none", "ocr_cache": False}
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
            file.write("\n")
        print(json.dumps({"cases": len(records), "output": str(args.output)}))


if __name__ == "__main__":
    main()
