"""One durable-queue consumer; compose can run 1–4 separate CPU processes."""

import logging
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from backend import pipeline, storage
    from backend import queue_store as queue

    storage.init()
    queue.initialize()
    consumer = os.getenv("HOSTNAME", "worker") + "-" + queue.new_token()[:8]
    while True:
        item = queue.take(consumer)
        if item is None:
            continue
        message_id, payload = item
        case_id, token = payload["case_id"], payload["token"]
        owner = queue.new_token()
        if not queue.lease(case_id, owner):
            continue
        stop = threading.Event()
        lost = threading.Event()

        def heartbeat(stop=stop, lost=lost, case_id=case_id, owner=owner, message_id=message_id):
            while not stop.wait(10):
                try:
                    if not queue.pulse(case_id, owner, message_id, consumer):
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        doc = None

        def checkpoint(document):
            if lost.is_set() or not queue.owns(case_id, owner):
                raise RuntimeError("Execution lease lost")
            if storage.get(case_id).get("queue_job_id") != token:
                raise RuntimeError("Superseded job")
            storage.save(document)

        try:
            doc = storage.get(case_id)
            if doc is None or doc.get("queue_job_id") != token:
                queue.finish(case_id, owner, message_id)
                continue
            if doc["status"] in {"completed", "partial", "cancelled", "error"} and doc.get("queue_finished") == token:
                queue.finish(case_id, owner, message_id)
                continue
            if doc.get("status") == "running":
                doc["status"] = "partial"
                pipeline._archive_analysis(doc)
            doc["queue_attempts"] = doc.get("queue_attempts", 0) + 1
            doc["queue_started_at"] = storage.now()
            doc["queue_worker"] = consumer
            started = time.perf_counter()
            pipeline.analyze(doc, cancelled=lambda: lost.is_set() or queue.cancelled(case_id), checkpoint=checkpoint)
            doc["queue_processing_ms"] = (time.perf_counter() - started) * 1000
            doc["queue_completed_at"] = storage.now()
            doc["queue_finished"] = token
            checkpoint(doc)
            queue.finish(case_id, owner, message_id)
        except Exception as exc:
            logging.warning("Job failed: %s", type(exc).__name__)
            if doc is not None and not lost.is_set() and queue.owns(case_id, owner):
                doc.update(status="error", queue_finished=token)
                doc.setdefault("limitations", []).append("Ошибка исполнителя; оригиналы сохранены, доступен повтор.")
                checkpoint(doc)
                queue.finish(case_id, owner, message_id)
        finally:
            stop.set()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
