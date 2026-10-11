"""Run by queue-maintenance.timer. Takes the same lock as the worker, so it
can never run concurrently with a live dispatch, then: verifies source
identity, runs a SQLite integrity check, and checkpoints the WAL.

Exits non-zero on any failure so systemd marks the service (and therefore
shows up in `systemctl --failed`) instead of failing silently.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import connect, checkpoint, integrity_check, stuck_commands  # noqa: E402
from lock import LockBusy, exclusive  # noqa: E402
from verify_deploy import verify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "state.db"
LOCK_PATH = ROOT / "run" / "queue.lock"


def main() -> int:
    try:
        with exclusive(LOCK_PATH, blocking=True):
            ok = verify()

            conn = connect(DB_PATH)
            status = integrity_check(conn)
            if status != "ok":
                print(f"FAIL: sqlite integrity_check returned {status!r}", file=sys.stderr)
                ok = False

            stuck = stuck_commands(conn)
            if stuck:
                print(f"NOTE: {len(stuck)} command(s) stuck in_progress — see recover.sh")

            checkpoint(conn)
            conn.close()
    except LockBusy:
        # Shouldn't happen with blocking=True, kept for clarity / future use.
        print("FAIL: could not acquire lock", file=sys.stderr)
        return 1

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
