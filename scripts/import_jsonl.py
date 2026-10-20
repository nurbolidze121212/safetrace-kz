"""Client-side local-file JSONL import: the server never reads arbitrary paths."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--title", default="Пакет материалов")
    parser.add_argument("--mode", choices=("local", "synthetic", "cloud"), default="local")
    args = parser.parse_args()
    endpoint = urlsplit(args.base_url)
    if endpoint.scheme != "http" or endpoint.hostname not in ("127.0.0.1", "localhost"):
        parser.error("Import client only uploads to the local SafeTrace service.")
    source = args.file.resolve(strict=True)
    if source.stat().st_size > 512 * 1024:
        parser.error("JSONL limit: 512 KiB")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not 1 <= len(rows) <= 20:
        parser.error("Import 1–20 materials per case.")
    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        for row in rows:
            image = row.pop("image", None)
            if image:
                path = (source.parent / image).resolve(strict=True)
                if not path.is_relative_to(source.parent):
                    parser.error("Image must be inside the JSONL folder.")
                if path.stat().st_size > 8 * 1024 * 1024:
                    parser.error("Image limit: 8 MiB")
                with path.open("rb") as file:
                    upload = client.post("/api/uploads", files={"file": (path.name, file)})
                upload.raise_for_status()
                row["image_id"] = upload.json()["image_id"]
        result = client.post("/api/cases", json={"title": args.title, "mode": args.mode, "materials": rows})
        result.raise_for_status()
        print(args.base_url + "/#case/" + result.json()["id"])


if __name__ == "__main__":
    main()
