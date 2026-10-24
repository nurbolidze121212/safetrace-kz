"""Exercise the real OCR application through the gateway in an isolated in-process test."""

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
directory = ROOT / "tmp" / f"public-demo-check-{secrets.token_hex(8)}"
os.environ["SAFETRACE_DATA_DIR"] = str(directory)
os.environ["SAFETRACE_OFFLINE"] = "1"
os.environ["SAFETRACE_ALLOWED_HOSTS"] = ""


def main():
    from starlette.testclient import TestClient

    from backend.app import app
    from backend.demo_gateway import DemoGateway

    report_path = ROOT / "reports" / "public-demo-2026-10-24" / "local-integration.json"
    origin = "https://demo.example"
    code = secrets.token_urlsafe(18)
    gateway = DemoGateway(app, origin, code, secrets.token_hex(32))
    private_db = ROOT / "data" / "safetrace.sqlite3"
    before = hashlib.sha256(private_db.read_bytes()).hexdigest() if private_db.exists() else None
    with TestClient(gateway, base_url=origin, follow_redirects=False) as client:
        assert client.get("/api/cases").status_code == 401
        assert client.post("/demo/login", data={"code": code}, headers={"origin": origin}).status_code == 303
        health = client.get("/api/health").json()
        assert health["offline"] and not health["provider_available"]
        assert client.get("/api/cases").json() == []
        assert client.get("/").status_code == 200
        with (ROOT / "examples" / "import" / "picture.png").open("rb") as stream:
            upload = client.post("/api/uploads", files={"file": ("photo.png", stream, "image/png")},
                                 headers={"origin": origin})
        assert upload.status_code == 200, upload.text
        start = time.monotonic()
        result = client.post("/api/cases", json={"title": "Gateway: photo-only verification",
                             "mode": "synthetic", "materials": [{"image_id": upload.json()["image_id"],
                                                                       "source": "Authored test fixture"}]},
                             headers={"origin": origin})
        assert result.status_code == 201, result.text
        case_id = result.json()["id"]
        while time.monotonic() - start < 180:
            case = client.get(f"/api/cases/{case_id}").json()
            if case["status"] not in ("pending", "running"):
                break
            time.sleep(0.5)
        elapsed = round(time.monotonic() - start, 2)
        assert case["status"] in ("completed", "partial"), case["status"]
        assert case.get("evidence") and case["graph"]["nodes"]
        audit = client.get(f"/api/cases/{case_id}/link-audit").json()
        assert audit["network_requests"] == 0 and audit["probability"] is None
        export = client.get(f"/api/cases/{case_id}/export")
        assert export.status_code == 200 and export.content[:2] == b"PK"
    after = hashlib.sha256(private_db.read_bytes()).hexdigest() if private_db.exists() else None
    assert before == after
    report = {"verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "In-process HTTPS ASGI test; NOT an external deployment or physical phone test",
              "health": health, "photo_only_status": case["status"], "elapsed_seconds": elapsed,
              "evidence_count": len(case["evidence"]), "graph_nodes": len(case["graph"]["nodes"]),
              "export_bytes": len(export.content), "private_database_unchanged": before == after,
              "audit_network_requests": audit["network_requests"], "audit_probability": audit["probability"]}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
