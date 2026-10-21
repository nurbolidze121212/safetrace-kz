"""Run one loopback-only SafeTrace process per data directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DataInUseError(RuntimeError):
    pass


class DataLock:
    """A kernel lock survives stale files and is released on process exit."""

    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.stream = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.stream = (self.directory / ".safetrace.lock").open("a+b")
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise DataInUseError("Эта папка данных уже используется другим экземпляром SafeTrace.") from None
        return self

    def __exit__(self, *_):
        if self.stream is not None:
            try:
                self.stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            finally:
                self.stream.close()
                self.stream = None


def reserve_port(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", port))
    except OSError:
        listener.close()
        raise ValueError(f"Порт {port} уже занят или недоступен; сервер не запущен.") from None
    return listener


def remove_owned_record(path: Path, run_id: str):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("run_id") == run_id:
            path.unlink()
    except (FileNotFoundError, ValueError, AttributeError):
        pass


def run_server(data: Path, port: int, run_id: str, logs: Path) -> int:
    if not 1024 <= port <= 65535 or not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Некорректный порт или идентификатор запуска")
    data = data.resolve()
    with DataLock(data), reserve_port(port) as listener:
        # Both guards are held before importing the application or running recovery.
        os.environ["SAFETRACE_DATA_DIR"] = str(data)
        sys.path.insert(0, str(ROOT))
        import uvicorn

        logs.mkdir(parents=True, exist_ok=True)
        record_path = logs / f"server-{port}.json"
        record = {
            "schema": "safetrace-server-1",
            "pid": os.getpid(),
            "run_id": run_id,
            "port": port,
            "data_directory": str(data),
            "project": str(ROOT),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        temporary = logs / f".server-{port}-{run_id}.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        temporary.replace(record_path)
        try:
            server = uvicorn.Server(uvicorn.Config("backend.app:app", host="127.0.0.1", port=port))
            server.run(sockets=[listener])
            return 0 if server.started else 1
        finally:
            remove_owned_record(record_path, run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--run-id", default=uuid.uuid4().hex)
    args = parser.parse_args()
    try:
        # The same configuration resolution is used by the installation check.
        sys.path.insert(0, str(ROOT))
        from scripts.preflight import data_directory, verify_model_path

        verify_model_path(ROOT)
        data = args.data_dir or data_directory(ROOT, None)
        return run_server(data, args.port, args.run_id, ROOT / "logs")
    except (OSError, ValueError, DataInUseError) as error:
        print(f"Не удалось запустить SafeTrace: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
