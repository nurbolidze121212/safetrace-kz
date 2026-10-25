"""Retrospective text-only comparison; never changes production rules or frozen files."""

import hashlib
import json
import platform
import re
import time
from pathlib import Path

import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_curve
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def text_only(row):
    if any(m.get("image") for m in row["materials"]):
        return None
    # Do not use labels, reference_text, source names, domains or campaign IDs as features.
    value = "\n".join(m.get("text", "") for m in row["materials"])
    return re.sub(r"https?://\S+", " URL ", value).strip()


def metrics(truth, predicted):
    tn, fp, fn, tp = confusion_matrix(truth, predicted, labels=[0, 1]).ravel().tolist()
    return {"n": len(truth), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def main():
    paths = [ROOT / name for name in (
        "datasets/synthetic-v2/dev.jsonl", "datasets/synthetic-v2/dev-annotations.jsonl",
        "datasets/context-v3-dev/inputs.jsonl", "datasets/context-v3-dev/annotations.jsonl",
        "datasets/synthetic-v4/inputs.jsonl", "datasets/synthetic-v4/annotations.jsonl",
        "reports/versions/synthetic-v4/v4-predictions.json")]
    hashes = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    train, labels, seen = [], [], {}
    for inputs, annotations in ((paths[0], paths[1]), (paths[2], paths[3])):
        truth = {r["id"]: r for r in rows(annotations)}
        for row in rows(inputs):
            value = text_only(row)
            if not value:
                continue
            label = truth[row["id"]]["truth"]
            normalized = " ".join(value.casefold().split())
            existing = seen.setdefault(normalized, set())
            if label in existing:
                continue
            # Identical invitations can lead to different destinations. Keep both labels
            # and report the ambiguity instead of selecting the convenient label.
            existing.add(label)
            train.append(value)
            labels.append(label)
    # Parameters fixed here, no search, no final-set threshold selection.
    model = make_pipeline(TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=1,
                                        sublinear_tf=True, max_features=30000),
                          LogisticRegression(C=1, class_weight="balanced", max_iter=1000, random_state=42))
    started = time.perf_counter()
    model.fit(train, labels)
    train_seconds = time.perf_counter() - started
    test = [(r, text_only(r)) for r in rows(paths[4])]
    test = [(r, text) for r, text in test if text]
    overlap = [r["id"] for r, text in test if " ".join(text.casefold().split()) in seen]
    scores = model.predict_proba([text for _, text in test])[:, 1]
    ml = [int(score >= .5) for score in scores]
    annotations = {r["id"]: r for r in rows(paths[5])}
    frozen = {r["id"]: r for r in json.loads(paths[6].read_text(encoding="utf-8")) if r["variant"] == "baseline"}
    truth = [annotations[r["id"]]["truth"] for r, _ in test]
    rules = [frozen[r["id"]]["predicted"] for r, _ in test]
    combined = [int(a or b) for a, b in zip(ml, rules, strict=True)]
    precision, recall, thresholds = precision_recall_curve(truth, scores)
    record = {"protocol": "Retrospective exploratory comparison on already-known synthetic-v4 text cases; NOT an independent final test",
              "limitations": ["Single-author synthetic training and evaluation data", "No hyperparameter or threshold search",
                              "Raw message text only: no destination page, OCR, QR or reference transcription",
                              "Logistic score is not calibrated risk; no classifier deployed", "No claim of generalization to real posts"],
              "train": {"n": len(train), "positives": sum(labels), "seconds": train_seconds,
                        "ambiguous_normalized_texts": sum(len(value) > 1 for value in seen.values())},
              "test_normalized_overlap_ids": overlap, "parameters": {"char_ngrams": [3, 5], "max_features": 30000,
              "C": 1, "class_weight": "balanced", "seed": 42, "threshold": .5, "ensemble": "ML positive OR frozen text-baseline positive"},
              "versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__},
              "results": {"frozen_keyword_baseline": metrics(truth, rules), "tfidf_logistic": metrics(truth, ml),
                          "union": metrics(truth, combined)},
              "average_precision": average_precision_score(truth, scores),
              "precision_recall_curve": {"precision": precision.tolist(), "recall": recall.tolist(), "thresholds": thresholds.tolist()},
              "source_sha256": hashes,
              "predictions": [{"id": row["id"], "language": annotations[row["id"]]["language"], "truth": y,
                               "ml_score": float(score), "ml": p, "rules": rule, "union": joint}
                              for (row, _), y, score, p, rule, joint in zip(test, truth, scores, ml, rules, combined, strict=True)]}
    record["language_slices"] = {language: {
        method: metrics([p["truth"] for p in record["predictions"] if p["language"] == language],
                        [p[method] for p in record["predictions"] if p["language"] == language])
        for method in ("rules", "ml", "union")} for language in sorted({p["language"] for p in record["predictions"]})}
    output = ROOT / "reports/release-2.4/text-baseline.json"
    with output.open("x", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(json.dumps({"train": record["train"], "overlap": overlap, "results": record["results"]}))


if __name__ == "__main__":
    main()
