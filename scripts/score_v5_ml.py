"""Frozen ML ablations on full-process observations; never reads labels."""

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from fit_v5_ml import MODEL, combine

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", required=True, choices=["char", "embedding"])
    args = parser.parse_args()
    output = ROOT / f"reports/versions/synthetic-v5/full-plus-{args.kind}.json"
    if output.exists():
        raise FileExistsError(output)
    freeze = json.loads((ROOT / "reports/versions/synthetic-v5/core-freeze.json").read_text(encoding="utf-8"))
    full = json.loads((ROOT / "reports/versions/synthetic-v5/full.json").read_text(encoding="utf-8"))
    assert full["analysis_hashes"] == freeze["analysis_hashes"]
    path = ROOT / f"reports/v5-dev/ml/{args.kind}.joblib"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == freeze["supporting_hashes"][path.relative_to(ROOT).as_posix()]
    data = joblib.load(path)
    assert data["embedding_model"] in (None, MODEL)
    texts = [row["ml_input"] for row in full["records"]]
    if args.kind == "char":
        features = data["vectorizer"].transform(texts)
    else:
        from fastembed import TextEmbedding

        embedder = TextEmbedding(MODEL, cache_dir=str(ROOT / "models/research"), threads=2)
        features = np.array(list(embedder.embed(texts, batch_size=16)))
    probabilities = data["model"].predict_proba(features)[:, 1]
    records = [{"id": row["id"], "predicted": combine(row, float(probability), data["threshold"]),
                "base_predicted": row["predicted"], "raw_model_output_uncalibrated": float(probability),
                "sufficient": row["sufficient"], "score": row["score"], "level": row["level"]}
               for row, probability in zip(full["records"], probabilities, strict=True)]
    output.write_text(json.dumps({"variant": "full_plus_" + args.kind, "threshold_selected_on_dev": data["threshold"],
                                  "deployable_selection": freeze["selected"], "records": records,
                                  "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "analysis_hashes": full["analysis_hashes"], "input_hashes": full["input_hashes"],
                                  "annotation_access": "none"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"variant": args.kind, "cases": len(records), "changed_from_full": sum(r["predicted"] != r["base_predicted"] for r in records)}))


if __name__ == "__main__":
    main()
