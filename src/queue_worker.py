"""Long-running worker: drains queue/incoming/, processes one command at a
time under the shared lock, records outcome in SQLite before moving the
command file — so a crash between "DB says done" and "file moved" is
recoverable (recover.sh treats an in_progress DB row as authoritative).
"""
from __future__ import annotations

import json
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import connect, finish_command, start_command  # noqa: E402
from lock import LockBusy, exclusive  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "queue"
INCOMING = QUEUE_DIR / "incoming"
DONE = QUEUE_DIR / "done"
FAILED = QUEUE_DIR / "failed"
DB_PATH = ROOT / "state.db"
LOCK_PATH = ROOT / "run" / "queue.lock"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("queue_worker")

_running = True


def _handle_sigterm(signum, frame):
    global _running
    log.info("received signal %s, finishing current command then exiting", signum)
    _running = False


def run_command(payload: dict) -> None:
    """Placeholder for real work. Raises on simulated failure for testing."""
    if payload.get("fail"):
        raise RuntimeError(payload.get("fail_reason", "simulated failure"))
    time.sleep(payload.get("duration", 0))


def process_one(conn, path: Path) -> None:
    cmd_id = path.stem
    payload = json.loads(path.read_text())

    start_command(conn, cmd_id, path.read_text())
    try:
        run_command(payload)
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
        finish_command(conn, cmd_id, ok=False, error=str(exc))
        path.rename(FAILED / path.name)
        log.error("command %s failed: %s", cmd_id, exc)
        return

    finish_command(conn, cmd_id, ok=True)
    path.rename(DONE / path.name)
    log.info("command %s done", cmd_id)


def main() -> int:
    for d in (INCOMING, DONE, FAILED):
        d.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    conn = connect(DB_PATH)

    while _running:
        pending = sorted(INCOMING.glob("*.json"))
        if not pending:
            time.sleep(1)
            continue

        path = pending[0]
        try:
            with exclusive(LOCK_PATH, blocking=False):
                process_one(conn, path)
        except LockBusy:
            log.info("lock held (maintenance running?), retrying")
            time.sleep(1)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
