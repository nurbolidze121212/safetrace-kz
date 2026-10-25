"""Container entry point; Compose publishes this service on host loopback only."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import uvicorn

    from scripts.run_server import DataLock

    data = Path(os.environ.get("SAFETRACE_DATA_DIR", ROOT / "data"))
    with DataLock(data):
        uvicorn.run("backend.app:app", host="0.0.0.0", port=8765, workers=1)


if __name__ == "__main__":
    main()
