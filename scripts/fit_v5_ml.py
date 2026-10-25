"""Dev-only full-process ML ablation. Never reads a hold-out directory."""

import hashlib
import importlib.metadata
import json
import time
from pathlib import Path

import joblib
import numpy as np
from fastembed import TextEmbedding
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def combine(row, probability, threshold):
    # No ML override of incomplete sources or absent observed gambling evidence.
    if not row["sufficient"]:
        return 0
    if row["predicted"]:
        return int(not (row["alternative"] and probability < 1 - threshold))
    return int(row["game_evidence"] and not row["alternative"] and probability >= threshold)


def metrics(truth, predicted):
    tp = sum(t == p == 1 for t, p in zip(truth, predicted, strict=True))
    fp = sum(t == 0 and p == 1 for t, p in zip(truth, predicted, strict=True))
    fn = sum(t == 1 and p == 0 for t, p in zip(truth, predicted, strict=True))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": len(truth) - tp - fp - fn,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0}


def main():
    directory = ROOT / "reports/v5-dev/ml"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "selection.json"
    if target.exists():
        raise FileExistsError(target)
    annotations = {r["id"]: r for r in map(json.loads, (ROOT / "datasets/v5-dev/annotations.jsonl").read_text(encoding="utf-8").splitlines())}
    rows = json.loads((ROOT / "reports/v5-dev/candidate-1.json").read_text(encoding="utf-8"))["records"]
    train = np.array([i for i, r in enumerate(rows) if annotations[r["id"]]["split"] == "train"])
    validation = np.array([i for i, r in enumerate(rows) if annotations[r["id"]]["split"] == "validation"])
    truth = np.array([annotations[r["id"]]["truth"] for r in rows])
    texts = [r["ml_input"] for r in rows]
    base = metrics(truth[validation].tolist(), [rows[i]["predicted"] for i in validation])
    report = {"input": "Observed message + actual OCR + observed destinations; no reference transcription",
              "split": "192 train / 64 held-out dev-validation; disjoint template families",
              "selection_rule": "F1 strictly improves and FP does not increase; ties keep simpler rules",
              "base": base, "selected": "full_without_ml", "experiments": [],
              "packages": {p: importlib.metadata.version(p) for p in ["scikit-learn", "fastembed", "onnxruntime", "numpy"]}}
    for kind in ("char", "embedding"):
        started = time.perf_counter()
        if kind == "char":
            vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
            vectorizer.fit([texts[i] for i in train])
            features = vectorizer.transform(texts)
        else:
            vectorizer = None
            embedder = TextEmbedding(MODEL, cache_dir=str(ROOT / "models/research"), threads=2)
            features = np.array(list(embedder.embed(texts, batch_size=16)))
        model = LogisticRegression(C=1, class_weight="balanced", max_iter=1000, random_state=42)
        model.fit(features[train], truth[train])
        probabilities = model.predict_proba(features)[:, 1]
        candidates = []
        for threshold in (.5, .65, .8):
            predictions = [combine(rows[i], float(probabilities[i]), threshold) for i in validation]
            candidates.append({"threshold": threshold, **metrics(truth[validation].tolist(), predictions)})
        best = max(candidates, key=lambda x: (x["f1"], -x["fp"], x["threshold"]))
        artifact = directory / (kind + ".joblib")
        joblib.dump({"vectorizer": vectorizer, "model": model, "threshold": best["threshold"],
                     "embedding_model": MODEL if kind == "embedding" else None}, artifact)
        experiment = {"kind": kind, "validation": candidates, "selected_threshold": best["threshold"],
                      "fit_and_transform_seconds": time.perf_counter() - started,
                      "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                      "probabilities": [{"id": rows[i]["id"], "value": float(probabilities[i])} for i in validation]}
        report["experiments"].append(experiment)
        if best["f1"] > base["f1"] and best["fp"] <= base["fp"]:
            report["selected"] = "full_plus_" + kind
            base = best
        print(json.dumps({"kind": kind, "validation": candidates}), flush=True)
    report["embedding_files"] = {p.relative_to(ROOT / "models/research").as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (ROOT / "models/research").rglob("*") if p.is_file() and "/.locks/" not in p.as_posix()}
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Selected:", report["selected"], flush=True)


if __name__ == "__main__":
    main()
