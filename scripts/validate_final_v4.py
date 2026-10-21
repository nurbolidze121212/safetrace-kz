"""Pre-prediction data/label and overlap audit; never calls the analyzer or OCR."""

import hashlib
import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets/synthetic-v4"
OUT = ROOT / "reports/versions/synthetic-v4/data-audit.json"


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"https?://[^\s<>]+", " URL ", text)
    text = re.sub(r"\bdemo\b", "", text)
    text = re.sub(r"\b[a-z]*\d+[a-z\d]*\b", " CODE ", text)
    return " ".join(re.findall(r"\w+", text))


def grams(text):
    tokens = text.split()
    return {tuple(tokens[i : i + 3]) for i in range(len(tokens) - 2)}


def main():
    assert not OUT.exists(), "Keep the previous audit"
    assert not (OUT.parent / "v3-unlabelled.json").exists()
    assert not (OUT.parent / "v4-unlabelled.json").exists()
    inputs, annotations = rows(DATA / "inputs.jsonl"), rows(DATA / "annotations.jsonl")
    assert len(inputs) == len(annotations) == 80
    assert [r["id"] for r in inputs] == [r["id"] for r in annotations]
    assert len({r["id"] for r in inputs}) == 80
    assert sum(r["truth"] for r in annotations) == 40
    assert sum(r["image"] for r in annotations) == 32 and sum(r["qr"] for r in annotations) == 8
    image_hashes = set()
    for item, label in zip(inputs, annotations):
        assert len(item["materials"]) == len(label["materials"])
        assert set(item) == {"id", "materials"}
        for mat, truth in zip(item["materials"], label["materials"]):
            assert set(mat) == {"text", "url", "source", "image"}
            if mat["image"]:
                path = (DATA / mat["image"]).resolve()
                assert path.is_relative_to(DATA.resolve()) and path.is_file()
                image_hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
                with Image.open(path) as image:
                    assert image.width * image.height <= 12_000_000
                assert mat["text"] == "" and mat["url"] == ""
            else:
                assert not truth["ocr_urls"] and not truth["qr_payloads"]
            for url in truth["ocr_urls"] + truth["qr_payloads"]:
                assert urlsplit(url).hostname.endswith(".test")
    assert len(image_hashes) == 32
    previous = []
    domains = set()
    for path in (ROOT / "datasets").rglob("*.jsonl"):
        if DATA in path.parents:
            continue
        for row in rows(path):
            text = row.get("reference_text") or row.get("text")
            if text:
                previous.append((str(path.relative_to(ROOT)), row.get("id", ""), normalized(text)))
            for url in re.findall(r"https?://[^\s<>]+", json.dumps(row, ensure_ascii=False)):
                try:
                    domains.add(urlsplit(url).hostname)
                except ValueError:
                    # Historical robustness fixtures intentionally include malformed URLs.
                    continue
    for path in (ROOT / "reports/acceptance-v4").glob("ocr-dev-*.json"):
        for row in json.loads(path.read_text(encoding="utf-8")).get("rows", []):
            previous.append(
                (str(path.relative_to(ROOT)), row["id"], normalized(row["caption"] + " " + row["url"]))
            )
            domains.add(urlsplit(row["url"]).hostname)
    # Also compare text fixtures used by the v4 regression tests.
    for path in (ROOT / "tests").glob("*v4*.py"):
        for text in re.findall(r'"([^"\n]{30,})"', path.read_text(encoding="utf-8")):
            previous.append((str(path.relative_to(ROOT)), "", normalized(text)))
    seen = set()
    previous = [r for r in previous if r[2] and not (r[2] in seen or seen.add(r[2]))]
    flagged, exact = [], []
    current = [(r["id"], normalized(r["reference_text"])) for r in annotations]
    for index, (cid, text) in enumerate(current):
        candidates = previous + [("current-final", other, t) for other, t in current[:index]]
        a = grams(text)
        for origin, other, reference in candidates:
            if text == reference:
                exact.append({"id": cid, "other": other, "origin": origin})
            b = grams(reference)
            jaccard = len(a & b) / len(a | b) if a | b else 0
            ratio = SequenceMatcher(None, text, reference).ratio()
            if ratio >= 0.78 or jaccard >= 0.45:
                flagged.append(
                    {
                        "id": cid,
                        "other": other,
                        "origin": origin,
                        "char_similarity": round(ratio, 4),
                        "trigram_jaccard": round(jaccard, 4),
                        "new_text": text,
                        "prior_text": reference,
                    }
                )
    assert not exact, exact
    new_domains = {
        urlsplit(u).hostname
        for r in annotations
        for m in r["materials"]
        for u in m["ocr_urls"] + m["qr_payloads"]
    }
    new_domains.update(
        urlsplit(u).hostname for u in json.loads((DATA / "pages.json").read_text(encoding="utf-8"))
    )
    assert not new_domains & domains, new_domains & domains
    report = {
        "n": 80,
        "positive": 40,
        "negative": 40,
        "unique_images": 32,
        "qr_cases": 8,
        "languages": dict(Counter(r["language"] for r in annotations)),
        "categories": dict(Counter(r["category"] for r in annotations)),
        "prior_distinct_texts_compared": len(previous),
        "new_domains": len(new_domains),
        "domain_overlap": [],
        "exact_normalized_duplicates": exact,
        "near_duplicate_candidates": flagged,
        "normalization": "NFKC/casefold; URL, alphanumeric codes and DEMO normalized; whitespace/punctuation collapsed. Candidate if SequenceMatcher>=.78 or token-trigram Jaccard>=.45.",
        "limitations": "Automatic similarity is a screening aid, not a guarantee of semantic independence. Review any candidate before predictions; the same author made rules and data.",
    }
    with OUT.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "near_duplicate_candidates"}, ensure_ascii=False, indent=2))
    print("Near-duplicate candidates:", len(flagged))


if __name__ == "__main__":
    main()
