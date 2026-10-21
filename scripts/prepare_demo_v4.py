"""Prepare two explicitly synthetic v4 demo cases through the running local API."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/acceptance-v4/main-demo.json"


def main(existing=None):
    assert not OUT.exists(), "Preserve the existing demo receipt"
    with httpx.Client(base_url="http://127.0.0.1:8765", trust_env=False, timeout=15) as client:
        health = client.get("/api/health").raise_for_status().json()
        assert health["app_version"] == "2.2.1" and health["offline"]

        def wait(cid):
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                doc = client.get("/api/cases/" + cid).raise_for_status().json()
                if doc["status"] not in ("pending", "running"):
                    assert doc["status"] in ("completed", "partial"), doc["status"]
                    return doc
                time.sleep(0.15)
            raise TimeoutError(cid)

        image = ROOT / "reports/acceptance-v4/browser-new-material.png"
        raw = image.read_bytes()
        if existing:
            cid = existing
        else:
            image_id = client.post("/api/uploads", files={"file": ("material.png", raw, "image/png")}).raise_for_status().json()["image_id"]
            cid = client.post("/api/cases", json={"title": "V4 · скрытый маршрут и сверка адреса", "mode": "synthetic", "materials": [{"image_id": image_id, "source": "Авторский синтетический макет для защиты"}]}).raise_for_status().json()["id"]
        first = wait(cid)
        mat = first["materials"][0]
        assert mat["image_sha256"] == hashlib.sha256(raw).hexdigest()
        assert not first["analysis_assisted"] and first["score"]["value"] == 0
        readings = mat["ocr"]["url_readings"]
        assert readings and not any(row["auto_follow"] for row in readings)
        client.post("/api/cases/" + cid + "/url-corrections", json={"material_id": mat["id"], "analysis_id": first["analysis_id"], "original_url": readings[0]["raw_url"], "corrected_url": "https://go.safetrace.test/r/q7", "comment": "На оригинальном синтетическом изображении адрес перенесён: https://go.safetrace.test и /r/q7. Обе строки визуально сверены; ручная подготовка демонстрации."}).raise_for_status()
        corrected = wait(cid)
        assert corrected["analysis_assisted"] and corrected["score"]["value"] == 80
        client.post("/api/cases/" + cid + "/materials", json={"text": "DEMO. Для новой встречи открыт второй вход. Регистрируйся и забирай бонус: https://go.safetrace.test/r/second", "source": "Вторая самостоятельная синтетическая публикация"}).raise_for_status()
        final = wait(cid)
        assert final["score"]["value"] == 90 and len(final["history"]) == 2
        warning = client.post("/api/cases", json={"title": "V4 · предупреждение с тем же адресом", "mode": "synthetic", "materials": [{"text": "DEMO. Осторожно: мошенники обещают бонус в казино. Не переходите и не переводите деньги. Это предупреждение о рассылке https://go.safetrace.test/r/q7", "source": "Авторский синтетический контрпример"}]}).raise_for_status().json()["id"]
        negative = wait(warning)
        assert negative["score"]["value"] < 65
        result = {"positive_id": cid, "warning_id": warning, "versions": final["versions"], "initial_score": first["score"]["value"], "corrected_score": corrected["score"]["value"], "final_score": final["score"]["value"], "warning_score": negative["score"]["value"], "assisted": True, "history_count": len(final["history"]), "image": str(image.relative_to(ROOT)), "image_sha256": hashlib.sha256(raw).hexdigest(), "method": "Prepared through real local API and real OCR. Explicit synthetic transport. Manual address review is assisted and excluded from automatic evaluation. Reuses the authored browser acceptance image; not a new quality sample."}
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing", help="Resume the explicitly identified initial partial case")
    main(parser.parse_args().existing)
