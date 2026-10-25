"""Convert an authorized Telegram JSON export or SRT into bounded local analysis batches."""

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 1000


def telegram(document):
    if not isinstance(document, dict) or not isinstance(document.get("messages"), list):
        raise ValueError("Expected one Telegram chat export with a messages array")
    result, skipped = [], 0
    chat = str(document.get("name", "chat"))[:60]
    chat_id = str(document.get("id", "unknown"))[:25]
    for message in document["messages"]:
        if message.get("type") != "message":
            skipped += 1
            continue
        value = message.get("text", "")
        if isinstance(value, list):
            parts = []
            for entity in value:
                if isinstance(entity, str):
                    parts.append(entity)
                elif isinstance(entity, dict):
                    parts.append(str(entity.get("text", "")))
                    if entity.get("type") == "text_link" and entity.get("href"):
                        parts.append(" (" + str(entity["href"]) + ")")
                else:
                    raise ValueError("Unsupported Telegram text entity")
            value = "".join(parts)
        if not isinstance(value, str):
            raise ValueError("Telegram text must be a string or entity list")
        if not value.strip():
            skipped += 1
            continue
        if len(value) > 20000:
            raise ValueError("One message exceeds 20000 characters; split it explicitly")
        timestamp = message.get("date_unixtime")
        at = datetime.fromtimestamp(int(timestamp), UTC).isoformat() if timestamp is not None else None
        result.append({"source": f"tg:{chat_id}:{chat} / message:{message.get('id', '?')}"[:160],
                       "published_at": at, "text": value})
    return result, {"skipped_service_or_empty": skipped, "media": "Text only; attachments not imported"}


def srt(content, filename="transcript"):
    pattern = re.compile(r"^(\d{2,3}):(\d{2}):(\d{2})[,.](\d{3})$")

    def timestamp(value):
        match = pattern.fullmatch(value)
        if not match:
            raise ValueError("Invalid SRT timestamp")
        h, m, s, ms = map(int, match.groups())
        if m >= 60 or s >= 60:
            raise ValueError("Invalid SRT time range")
        return ((h * 60 + m) * 60 + s) * 1000 + ms

    result, previous = [], -1
    for block in re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip()):
        lines = block.strip().splitlines()
        if lines and lines[0].isdigit():
            lines = lines[1:]
        if len(lines) < 2 or " --> " not in lines[0]:
            raise ValueError("Each SRT cue needs a time range and text")
        start, end = lines[0].split(" --> ", 1)
        start_ms, end_ms = timestamp(start), timestamp(end)
        if start_ms < previous or end_ms <= start_ms:
            raise ValueError("SRT cues must be ordered and end after their start")
        previous = start_ms
        text = "\n".join(lines[1:]).strip()
        if not text or len(text) > 19800:
            raise ValueError("Empty or oversized SRT cue")
        result.append({"source": f"transcript:{filename[:65]} [{start}–{end}]",
                       "text": f"[{start} --> {end}]\n{text}"})
    return result, {"media": "Imported transcript only; speech recognition and video processing not performed"}


def batches(materials, title):
    if not 1 <= len(materials) <= MAX_ITEMS:
        raise ValueError("Use 1–1000 nonempty messages/cues per import")
    return [{"title": f"{title[:140]} · {start // 20 + 1}", "mode": "local",
             "materials": materials[start:start + 20]} for start in range(0, len(materials), 20)]


def submit(payloads, base_url, receipt_path):
    import httpx

    target = urlsplit(base_url)
    if (target.scheme != "http" or target.hostname not in {"localhost", "127.0.0.1"}
            or target.username or target.password or target.query or target.fragment or target.path not in {"", "/"}):
        raise ValueError("Submission only to a local HTTP server")
    # Sequential completion provides backpressure to the bounded single-worker queue.
    with receipt_path.open("x", encoding="utf-8") as receipt, httpx.Client(
        base_url=base_url, trust_env=False, timeout=30
    ) as client:
        for index, payload in enumerate(payloads):
            deadline = time.monotonic() + 600
            while True:
                response = client.post("/api/cases", json=payload)
                if response.status_code != 429:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("Queue remains full; completed IDs are in the receipt")
                time.sleep(1)
            response.raise_for_status()
            case_id = response.json()["id"]
            receipt.write(json.dumps({"batch": index + 1, "id": case_id, "status": "submitted"}) + "\n")
            receipt.flush()
            while time.monotonic() < deadline:
                doc = client.get("/api/cases/" + case_id).raise_for_status().json()
                if doc["status"] not in {"pending", "running"}:
                    receipt.write(json.dumps({"batch": index + 1, "id": case_id, "status": doc["status"]}) + "\n")
                    receipt.flush()
                    if doc["status"] not in {"completed", "partial"}:
                        raise RuntimeError("Analysis failed; inspect the recorded case before resubmitting")
                    break
                time.sleep(0.5)
            else:
                raise TimeoutError("Analysis is still running; ID is in the receipt, do not duplicate it")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", choices=("telegram", "srt"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    if args.input.stat().st_size > MAX_BYTES:
        parser.error("Input limit: 10 MiB")
    content = args.input.read_text(encoding="utf-8-sig")
    try:
        materials, notes = telegram(json.loads(content)) if args.format == "telegram" else srt(content, args.input.name)
        payloads = batches(materials, args.input.stem)
        with args.output.open("x", encoding="utf-8") as output:
            for payload in payloads:
                output.write(json.dumps(payload, ensure_ascii=False) + "\n")
        if args.submit:
            submit(payloads, args.base_url, args.output.with_suffix(".receipt.jsonl"))
        print(json.dumps({"materials": len(materials), "batches": len(payloads), "notes": notes}))
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
