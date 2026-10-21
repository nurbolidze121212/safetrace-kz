"""Small actual API workload on a newly started, isolated offline server (port 8769)."""

import hashlib
import io
import json
import time
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/acceptance-v4/runtime.json"


def pixels(index):
    image = Image.new("RGB", (1120, 240), "#fbfaf4")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 27)
    for y, text in [
        (25, "Стенд времени обработки. Өзгеріс сақталады."),
        (75, f"Авторская проверка {index:02d}. Переходи и забирай бонус."),
        (140, "https://go.safetrace.test/r/q7"),
    ]:
        draw.text((25, y), text, font=font, fill="#203040")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main():
    if OUT.exists():
        raise RuntimeError("Keep the existing measured runtime report")
    with httpx.Client(base_url="http://127.0.0.1:8769", trust_env=False, timeout=10) as client:
        health = client.get("/api/health").raise_for_status().json()
        assert health["offline"] and health["app_version"] == "2.2.1"
        assert client.get("/api/cases").raise_for_status().json() == [], "Use a fresh private data directory"

        def create(index):
            content = pixels(index)
            image_id = (
                client.post("/api/uploads", files={"file": ("material.png", content, "image/png")})
                .raise_for_status()
                .json()["image_id"]
            )
            start = time.perf_counter()
            cid = (
                client.post(
                    "/api/cases",
                    json={
                        "title": "Проверка времени",
                        "mode": "synthetic",
                        "materials": [{"image_id": image_id}],
                    },
                )
                .raise_for_status()
                .json()["id"]
            )
            return cid, start, hashlib.sha256(content).hexdigest()

        def wait(jobs):
            remaining = {cid: (start, digest) for cid, start, digest in jobs}
            results, observations = [], []
            deadline = time.perf_counter() + 240
            while remaining:
                if time.perf_counter() > deadline:
                    raise TimeoutError("Acceptance workload did not finish within 240 seconds")
                states = {}
                for cid, (start, digest) in list(remaining.items()):
                    doc = client.get("/api/cases/" + cid).raise_for_status().json()
                    states[cid] = doc["status"]
                    if doc["status"] in ("pending", "running"):
                        continue
                    assert doc["status"] == "completed" and doc["sufficient_data"], doc["limitations"]
                    assert doc["materials"][0]["image_sha256"] == digest
                    results.append(
                        {
                            "case_id": cid,
                            "observed_end_to_end_ms": (time.perf_counter() - start) * 1000,
                            "active_analysis_ms": doc["elapsed_ms"],
                            "queue_wait_ms": max(
                                0,
                                (
                                    datetime.fromisoformat(doc["analyzed_at"])
                                    - datetime.fromisoformat(doc["created_at"])
                                ).total_seconds()
                                * 1000,
                            ),
                            "ocr_cache_hit": doc["materials"][0]["ocr"]["cache_hit"],
                            "ocr_reported_ms": doc["materials"][0]["ocr"].get("elapsed_ms"),
                            "score": doc["score"]["value"],
                            "image_sha256": digest,
                        }
                    )
                    del remaining[cid]
                observations.append(states)
                if remaining:
                    time.sleep(0.1)
            return results, observations

        cold_job = create(1)
        cold, cold_states = wait([cold_job])
        assert not cold[0]["ocr_cache_hit"]
        # Same original, same version, explicit user-equivalent retry.
        start = time.perf_counter()
        client.post("/api/cases/" + cold_job[0] + "/retry").raise_for_status()
        cached, cached_states = wait([(cold_job[0], start, cold_job[2])])
        assert cached[0]["ocr_cache_hit"]
        # The original created_at predates this retry; it is not a queue-wait denominator.
        cached[0]["queue_wait_ms"] = None
        queue_jobs = [create(i) for i in range(2, 8)]
        queued, queue_states = wait(queue_jobs)
        assert all(not row["ocr_cache_hit"] for row in queued)
        assert any("pending" in states.values() for states in queue_states)
        report = {
            "health": health,
            "cold": cold,
            "cached_retry": cached,
            "queue": queued,
            "states": {"cold": cold_states, "cached": cached_states, "queue": queue_states},
            "method": "Fresh isolated offline process; first real image analysis includes lazy primary model load. Then same-case content-cache retry, then six distinct fresh images submitted sequentially without waiting. No cloud or external HTTP. Polling 100 ms adds observation overhead. Queue wait is analyzed_at-created_at only for newly created cases.",
            "limits": "Small technical workload on one Windows CPU machine; not a capacity, concurrent-user or human-speed benchmark.",
        }
        with OUT.open("x", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {key: report[key] for key in ("cold", "cached_retry", "queue")}, ensure_ascii=False, indent=2
            )
        )


if __name__ == "__main__":
    main()
