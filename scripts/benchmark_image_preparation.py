"""Warm-cache synthetic pipeline benchmark; not OCR inference or network latency."""

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
os.environ["SAFETRACE_DATA_DIR"] = str(ROOT / "data/benchmark-image-preparation")
os.environ["SAFETRACE_OFFLINE"] = "1"

from PIL import Image  # noqa: E402

from backend import pipeline, storage  # noqa: E402
from backend.config import DATA  # noqa: E402
from backend.links import SyntheticTransport  # noqa: E402
from backend.schemas import CaseInput, MaterialInput  # noqa: E402


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signature(doc):
    return {
        "score": doc["score"]["value"],
        "sufficient": doc["sufficient_data"],
        "status": doc["status"],
        "ocr": [m.get("ocr", {}).get("text", "") for m in doc["materials"]],
        "qr": [[c["text"] for c in m.get("qr", {}).get("codes", [])] for m in doc["materials"]],
        "observations": [
            {k: o.get(k) for k in ("url", "status_code", "text", "stop")}
            for o in doc["trace"]["observations"]
        ],
    }


def main(name):
    output = ROOT / "reports/versions/backend-2.1/image-preparation" / name
    output.mkdir(parents=True, exist_ok=False)
    paths = [*(ROOT / "backend").glob("*.py"), ROOT / "backend/weights.json", Path(__file__)]
    before = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths}
    dataset = ROOT / "datasets/synthetic-v2"
    records = [json.loads(s) for s in (dataset / "dev.jsonl").read_text(encoding="utf-8").splitlines()]
    records = [r for r in records if any(m.get("image") for m in r["materials"])][:6]
    pages = json.loads((dataset / "dev-pages.json").read_text(encoding="utf-8"))
    storage.init()
    bases, samples = [], []
    for row in records:
        materials = []
        image_hashes = []
        for raw in row["materials"]:
            fields = {k: v for k, v in raw.items() if k != "image"}
            if raw.get("image"):
                content = (dataset / raw["image"]).read_bytes()
                image_hashes.append(digest(content))
                image_id = digest(content)[:32] + ".jpg"
                target = DATA / "originals" / image_id
                if target.exists():
                    assert target.read_bytes() == content
                else:
                    target.write_bytes(content)
                fields["image_id"] = image_id
            materials.append(MaterialInput(**fields))
        base = pipeline.new_case(CaseInput(title="Материал", mode="synthetic", materials=materials))
        doc = copy.deepcopy(base)
        start = time.perf_counter()
        pipeline.analyze(doc, fetch=SyntheticTransport(pages), use_ocr_cache=True)
        samples.append(
            {
                "id": row["id"],
                "image_sha256": image_hashes,
                "warmup_ms": (time.perf_counter() - start) * 1000,
                "signature": signature(doc),
                "times_ms": [],
            }
        )
        bases.append(base)
    original_save = Image.Image.save
    png_encodes = 0

    def counted_save(self, *args, **kwargs):
        nonlocal png_encodes
        if kwargs.get("format") == "PNG":
            png_encodes += 1
        return original_save(self, *args, **kwargs)

    Image.Image.save = counted_save
    try:
        for _ in range(5):
            for base, sample in zip(bases, samples, strict=True):
                doc = copy.deepcopy(base)
                start = time.perf_counter()
                pipeline.analyze(doc, fetch=SyntheticTransport(pages), use_ocr_cache=True)
                elapsed = (time.perf_counter() - start) * 1000
                assert signature(doc) == sample["signature"]
                sample["times_ms"].append(round(elapsed, 3))
    finally:
        Image.Image.save = original_save
    assert before == {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths}
    times = sorted(t for sample in samples for t in sample["times_ms"])
    result = {
        "name": name,
        "at": storage.now(),
        "core_hashes": before,
        "samples": samples,
        "runs": len(times),
        "png_encodes": png_encodes,
        "median_ms": statistics.median(times),
        "p95_ms": times[math.ceil(0.95 * len(times)) - 1],
        "scope": "Six existing synthetic development image cases, five warm-cache runs each. CPU, synthetic transport; no OCR inference/network timing claim.",
    }
    (output / "measurement.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with zipfile.ZipFile(output / "core-source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in before:
            archive.write(ROOT / name, name)
    print(
        json.dumps({k: result[k] for k in ("runs", "png_encodes", "median_ms", "p95_ms")}, ensure_ascii=False)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.name.replace("-", "").isalnum():
        parser.error("Use a unique simple run name.")
    main(args.name)
