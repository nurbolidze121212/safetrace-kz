import json

import pytest

from backend.evaluations import read


def put(root, relative, count):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"test_count": count, "variants": {"full": {"n": count}}}), encoding="utf-8")


def test_history_and_new_test_have_distinct_ids_and_default(tmp_path):
    put(tmp_path, "reports/versions/synthetic-v1/evaluation.json", 80)
    put(tmp_path, "reports/versions/synthetic-v2/regression-v1.json", 80)
    assert read(tmp_path)["evaluation_id"] == "synthetic-v1"
    assert read(tmp_path, "regression-v1")["evaluation_id"] == "regression-v1"
    put(tmp_path, "reports/versions/synthetic-v2/evaluation.json", 84)
    report = read(tmp_path)
    assert report["evaluation_id"] == "synthetic-v2" and report["test_count"] == 84
    assert len(report["available_versions"]) == 3
    put(tmp_path, "reports/versions/synthetic-v3/evaluation.json", 80)
    report = read(tmp_path)
    assert report["evaluation_id"] == "synthetic-v3" and report["test_count"] == 80
    assert len(report["available_versions"]) == 4
    assert read(tmp_path, "synthetic-v2")["test_count"] == 84
    with pytest.raises(ValueError):
        read(tmp_path, "../../.env")


def test_empty_evaluation_is_explicit(tmp_path):
    assert not read(tmp_path)["available"]
