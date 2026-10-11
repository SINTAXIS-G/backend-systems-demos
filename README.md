# deploy-recovery-demo

A small, self-contained reference implementation of a pattern commonly needed on
long-running Linux research/worker servers: a systemd-managed Python queue worker
with crash-safe SQLite state, a maintenance timer that cannot overlap live work,
and an explicit source-to-installed identity check for deployments.

Built standalone as a portfolio/skills demonstration — not derived from any
commercial codebase.

## Scenario

A Python worker (`queue_worker.py`) drains commands from a file-based queue
directory and records their outcome in SQLite. Two operational problems this
project addresses directly:

1. **"Is the installed code actually what we think it is?"** — `verify_deploy.py`
   hashes the installed source tree and compares it against a manifest recorded
   at deploy time, tied to a specific git commit. A mismatch fails loudly instead
   of silently running stale code.
2. **"Can maintenance and live work collide?"** — the maintenance timer
   (`queue-maintenance.timer` → `queue-maintenance.service`) takes an flock-based
   lock before touching the queue directory or database. The worker takes the
   same lock before dispatching a command. Neither can run while the other holds
   it, so a maintenance pass can never dispatch queued work by accident and a
   live dispatch can never run mid-maintenance.

## Components

- `src/queue_worker.py` — long-running worker. Polls `queue/incoming/`, processes
  one command at a time under an flock, writes result + timestamps to SQLite
  (`state.db`, `journal_mode=WAL`), moves the command file to `queue/done/` or
  `queue/failed/`.
- `src/verify_deploy.py` — computes a deterministic hash of the installed `src/`
  tree and checks it against `deploy/manifest.json` (git commit + expected hash).
  Exits non-zero on mismatch. Meant to run as a pre-flight check before
  `queue-worker.service` starts and inside the maintenance timer.
- `src/db.py` — SQLite setup: WAL mode, busy_timeout, a `commands` table used as
  both the audit log and the crash-recovery source of truth (a command is only
  considered complete once its row is committed with `status='done'`).
- `systemd/queue-worker.service` — runs the worker under its own user, restarts
  on failure, `ExecStartPre` runs `verify_deploy.py`.
- `systemd/queue-maintenance.service` + `.timer` — periodic integrity check
  (`verify_deploy.py` + SQLite `PRAGMA integrity_check` + WAL checkpoint),
  mutually exclusive with the worker via the same lock file.
- `scripts/deploy.sh` — stop worker → wait for in-flight command to finish or
  timeout → update code → regenerate manifest → verify → restart. Fails closed:
  any step failing leaves the previous version running.
- `scripts/recover.sh` — for the "server got into a bad state" case. Checks WAL
  file integrity, reports any command stuck in `status='in_progress'` (crash
  mid-dispatch), and explicitly does **not** auto-resume those — it prints them
  for a human decision, because silently replaying a possibly-already-applied
  side effect is worse than stopping.

## Explicit limitations (deliberately not papered over)

- The lock is a single local `flock` on one file. It prevents worker/maintenance
  overlap on one host; it is not a distributed lock and assumes one server.
- `verify_deploy.py` detects *that* installed code differs from the recorded
  manifest, not *why* — a legitimate hotfix without a manifest regen looks
  identical to drift. The deploy script is the only thing that should regenerate
  the manifest.
- Recovery after a crash mid-command cannot tell whether the command's
  real-world side effect (if any) actually happened — only that the DB row
  wasn't marked done. `recover.sh` surfaces this instead of guessing.

## Running the tests

```bash
pip install -r requirements.txt
pytest -v
```

Tests cover: normal dispatch, WAL durability after a simulated crash
(kill -9 mid-transaction), lock contention between worker and maintenance,
and a deliberately corrupted manifest to confirm `verify_deploy.py` fails closed.
