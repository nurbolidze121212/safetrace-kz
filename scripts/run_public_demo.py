"""Run the real application behind a temporary access code, with isolated storage."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def demo_directory(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", name):
        raise ValueError("The demo directory must use a generated ID")
    base = root.resolve() / "data" / "public-demo"
    directory = base / name
    if directory.resolve() != directory or base.resolve() != base:
        raise ValueError("Public demo storage cannot be a symlink/junction")
    marker = directory / ".public-demo-only"
    if directory.exists() and not marker.is_file() and any(directory.iterdir()):
        raise ValueError("Refusing to use existing unmarked data")
    directory.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.write_text("Shared demonstration; never import personal cases.\n", encoding="utf-8")
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--init-origin")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from backend.demo_gateway import DemoGateway
    from scripts.run_server import DataLock, reserve_port

    if args.init_origin:
        config = {"origin": args.init_origin, "code": secrets.token_urlsafe(18),
                  "signing_key": secrets.token_hex(32), "instance": secrets.token_hex(16), "port": args.port}
        DemoGateway(None, config["origin"], config["code"], config["signing_key"])
        args.config.parent.mkdir(parents=True, exist_ok=True)
        with args.config.open("x", encoding="utf-8") as stream:
            json.dump(config, stream)
        print("Demo configuration created; access code is in the local ignored config file.")
        return
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not 1024 <= config["port"] <= 65535 or config["port"] == 8765:
        raise ValueError("Choose a dedicated demo port other than 8765")
    directory = demo_directory(ROOT, config["instance"])
    with DataLock(directory), reserve_port(config["port"]) as listener:
        # Force these before importing config/app; dotenv never overrides them.
        os.environ["SAFETRACE_DATA_DIR"] = str(directory)
        os.environ["SAFETRACE_OFFLINE"] = "1"
        os.environ["SAFETRACE_ALLOWED_HOSTS"] = ""
        from backend.app import app
        from backend.config import DATA, offline

        if DATA != directory or not offline():
            raise RuntimeError("Public demonstration isolation failed")
        import uvicorn

        gateway = DemoGateway(app, config["origin"], config["code"], config["signing_key"])
        uvicorn.Server(uvicorn.Config(gateway, host="127.0.0.1", port=config["port"],
                                     proxy_headers=False, access_log=False)).run(sockets=[listener])


if __name__ == "__main__":
    main()
