import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import pytest

from scripts.run_server import DataLock, remove_owned_record, run_server

ROOT = Path(__file__).resolve().parents[1]


def holder(directory):
    code = """
import sys
from pathlib import Path
from scripts.run_server import DataLock
with DataLock(Path(sys.argv[1])):
    print('LOCKED', flush=True)
    sys.stdin.readline()
"""
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", code, str(directory)],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout.readline().strip() == "LOCKED"
    return process


def try_lock(directory):
    code = """
import sys
from pathlib import Path
from scripts.run_server import DataLock, DataInUseError
try:
    with DataLock(Path(sys.argv[1])):
        print('ACQUIRED')
except DataInUseError:
    print('BUSY')
    sys.exit(7)
"""
    return subprocess.run(
        [sys.executable, "-c", code, str(directory)], cwd=ROOT, capture_output=True, text=True, timeout=10
    )


@pytest.mark.parametrize("end", ["normal", "killed"])
def test_other_process_is_refused_and_kernel_releases_lock_on_exit(tmp_path, end):
    data = tmp_path / "data"
    process = holder(data)
    try:
        blocked = try_lock(data)
        assert blocked.returncode == 7 and blocked.stdout.strip() == "BUSY"
        if end == "normal":
            process.communicate(input="stop\n", timeout=10)
        else:
            process.kill()
            process.communicate(timeout=10)
        assert (data / ".safetrace.lock").exists()
        fresh = try_lock(data)
        assert fresh.returncode == 0 and fresh.stdout.strip() == "ACQUIRED"
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_separate_data_directories_can_run_independently(tmp_path):
    with DataLock(tmp_path / "first"):
        other = try_lock(tmp_path / "second")
        assert other.returncode == 0


def test_busy_port_is_rejected_before_application_or_recovery(tmp_path):
    data = tmp_path / "data"
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(ValueError, match="занят"):
            run_server(data, occupied.getsockname()[1], "a" * 32, tmp_path / "logs")
    assert not (data / "safetrace.sqlite3").exists()
    assert not (tmp_path / "logs").exists()
    assert try_lock(data).returncode == 0


@pytest.mark.parametrize("run_id,port", [("../outside", 8765), ("a" * 32, 80)])
def test_invalid_launch_parameters_create_no_data(tmp_path, run_id, port):
    with pytest.raises(ValueError):
        run_server(tmp_path / "data", port, run_id, tmp_path / "logs")
    assert list(tmp_path.iterdir()) == []


def test_cleanup_never_removes_a_new_owner_record(tmp_path):
    record = tmp_path / "server-8765.json"
    record.write_text(json.dumps({"run_id": "new-owner", "pid": os.getpid()}))
    remove_owned_record(record, "old-owner")
    assert record.exists()
    remove_owned_record(record, "new-owner")
    assert not record.exists()


def test_lock_rejects_same_directory_spelled_with_parent_segment(tmp_path):
    data = tmp_path / "data"
    with DataLock(data):
        assert try_lock(data / ".." / "data").returncode == 7


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launch-control integration")
def test_powershell_stop_checks_owner_active_queue_then_stops_idle_server(tmp_path):
    import sqlite3
    import uuid

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    run_id = uuid.uuid4().hex
    data = tmp_path / "server-data"
    metadata = ROOT / "logs" / f"server-{port}.json"
    ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    client = build_opener(ProxyHandler({}))
    environment = os.environ | {"SAFETRACE_OFFLINE": "1", "PYTHONIOENCODING": "utf-8"}
    process = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "scripts/run_server.py"),
            "--port",
            str(port),
            "--data-dir",
            str(data),
            "--run-id",
            run_id,
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    def health():
        with client.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            return json.load(response)["status"] == "ok"

    def stop():
        return subprocess.run(
            [
                str(ps),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts/stop.ps1"),
                "-Port",
                str(port),
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=25,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    record_bytes = None
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None, "Server exited before readiness"
            try:
                if health():
                    break
            except (URLError, TimeoutError, ConnectionError):
                time.sleep(0.1)
        else:
            pytest.fail("Server did not become ready")
        record_bytes = metadata.read_bytes()
        record = json.loads(record_bytes)
        assert record["run_id"] == run_id
        metadata.write_text(json.dumps(record | {"run_id": "0" * 32}), encoding="utf-8")
        rejected = stop()
        assert rejected.returncode != 0 and health()
        metadata.write_bytes(record_bytes)
        with sqlite3.connect(data / "safetrace.sqlite3") as connection:
            connection.execute(
                "INSERT INTO cases VALUES ('active-fixture',?)",
                (json.dumps({"id": "active-fixture", "status": "running"}),),
            )
        refused = stop()
        assert refused.returncode != 0 and "analyses are active" in refused.stderr and health()
        with sqlite3.connect(data / "safetrace.sqlite3") as connection:
            connection.execute("DELETE FROM cases WHERE id='active-fixture'")
        stopped = stop()
        assert stopped.returncode == 0, stopped.stderr
        process.wait(timeout=10)
        assert not metadata.exists()
        assert try_lock(data).returncode == 0
    finally:
        if record_bytes and metadata.exists():
            metadata.write_bytes(record_bytes)
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
            )
            process.wait(timeout=10)
        remove_owned_record(metadata, run_id)
