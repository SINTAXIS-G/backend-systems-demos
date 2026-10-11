#!/usr/bin/env bash
# Recovery procedure after a stall, crash, or suspected bad state.
#
# Deliberately does NOT auto-resume stuck commands: a command left
# 'in_progress' means the process died between starting it and recording
# the result, and we cannot tell from the DB alone whether its real-world
# side effect already happened. Auto-replaying it could double-apply that
# side effect, which is worse than a human spending two minutes checking.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== service status =="
systemctl status queue-worker.service --no-pager || true

echo
echo "== source identity =="
python3 src/verify_deploy.py || echo "  -> installed code does not match last deploy manifest"

echo
echo "== sqlite integrity =="
python3 - <<'PY'
import sys
sys.path.insert(0, "src")
from db import connect, integrity_check
conn = connect("state.db")
print(" ", integrity_check(conn))
PY

echo
echo "== commands stuck in_progress (require human decision, not auto-replayed) =="
python3 - <<'PY'
import sys
sys.path.insert(0, "src")
from db import connect, stuck_commands
conn = connect("state.db")
rows = stuck_commands(conn)
if not rows:
    print("  none")
for r in rows:
    print(f"  id={r['id']} started_at={r['started_at']} payload={r['payload']!r}")
PY

echo
echo "Next steps: resolve each stuck command manually (mark done/failed via"
echo "the db, after confirming whether its side effect happened), then:"
echo "  systemctl restart queue-worker.service"
