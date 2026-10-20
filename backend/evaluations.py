import json


def available(root):
    definitions = [
        (
            "synthetic-v1",
            "Историческая v1 · исходный тест",
            root / "reports/versions/synthetic-v1/evaluation.json",
        ),
        (
            "regression-v1",
            "Ядро v2 · регрессия на test-v1",
            root / "reports/versions/synthetic-v2/regression-v1.json",
        ),
        (
            "synthetic-v2",
            "Ядро v2 · новый синтетический тест",
            root / "reports/versions/synthetic-v2/evaluation.json",
        ),
    ]
    results = []
    for identifier, label, path in definitions:
        if path.is_file():
            report = json.loads(path.read_text(encoding="utf-8"))
            results.append((identifier, label, report))
    return results


def read(root, identifier=None):
    entries = available(root)
    if not entries:
        return {"available": False, "message": "Оценка еще не запускалась."}
    identifiers = {entry[0] for entry in entries}
    identifier = identifier or ("synthetic-v2" if "synthetic-v2" in identifiers else "synthetic-v1")
    selected = next((entry for entry in entries if entry[0] == identifier), None)
    if selected is None:
        raise ValueError("Выбранная оценка не найдена.")
    return {
        **selected[2],
        "available": True,
        "evaluation_id": selected[0],
        "evaluation_label": selected[1],
        "available_versions": [
            {
                "id": key,
                "label": label,
                "test_count": report.get("test_count"),
                "frozen_at": report.get("frozen_at"),
                "rules": report.get("versions", {}).get("rules"),
                "full": report.get("variants", {}).get("full"),
            }
            for key, label, report in entries
        ],
    }
