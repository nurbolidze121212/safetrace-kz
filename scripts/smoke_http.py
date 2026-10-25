"""Exercise a disposable local server with a new text case, real OCR and ZIP export."""

import argparse
import io
import json
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {"localhost", "127.0.0.1"}:
        parser.error("Use only a disposable local instance")

    def request(path, body=None, content_type="application/json"):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        req = Request(args.base_url + path, data=data)
        if data is not None:
            req.add_header("Content-Type", content_type)
        with urlopen(req, timeout=30) as response:
            payload = response.read()
            return json.loads(payload) if "json" in response.headers.get("Content-Type", "") else payload

    def analyze(material):
        case_id = request("/api/cases", {
            "title": "Automated installation smoke test", "mode": "synthetic", "materials": [material],
        })["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = request("/api/cases/" + case_id)
            if result["status"] not in {"running", "pending"}:
                assert result["status"] in {"completed", "partial"}, result["status"]
                return result
            time.sleep(0.5)
        raise TimeoutError(case_id)

    health = request("/api/health")
    assert health["ocr_installed"] and health["offline"]
    text_case = analyze({"source": "Authored installation example", "text":
        "DEMO. Регистрируйся и забирай бонус: https://go.safetrace.test/r/q7"})
    assert text_case["score"]["value"] >= 65 and text_case["trace"]["observations"]
    image = Path(__file__).resolve().parents[1] / "datasets/evaluator-v4-smoke/material.png"
    boundary = uuid.uuid4().hex
    multipart = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke.png"'
                 '\r\nContent-Type: image/png\r\n\r\n').encode() + image.read_bytes()
    multipart += f"\r\n--{boundary}--\r\n".encode()
    upload = request("/api/uploads", multipart, "multipart/form-data; boundary=" + boundary)
    image_case = analyze({"image_id": upload["image_id"], "source": "Authored OCR fixture"})
    assert image_case["materials"][0]["ocr"]["lines"], "OCR produced no lines"
    archive = request("/api/cases/" + image_case["id"] + "/export")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert "case.json" in zipped.namelist()
        assert json.loads(zipped.read("case.json"))["id"] == image_case["id"]
    print(json.dumps({"text": "passed", "ocr_lines": len(image_case["materials"][0]["ocr"]["lines"]),
                      "export_bytes": len(archive), "version": health["app_version"]}))


if __name__ == "__main__":
    main()
