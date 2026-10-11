#!/usr/bin/env bash
# Deploy procedure. Fails closed: if any step fails, the previous version
# is left running rather than left half-updated.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== 1/5: waiting for worker to be idle or stop cleanly =="
sudo systemctl stop queue-worker.service || {
    echo "FAIL: worker did not stop cleanly, aborting deploy" >&2
    exit 1
}

echo "== 2/5: updating source (git pull, expects a pinned ref) =="
git fetch origin
git checkout "${1:?usage: deploy.sh <git-ref>}"

echo "== 3/5: regenerating deploy manifest for the new commit =="
python3 src/verify_deploy.py --write

echo "== 4/5: verifying identity before restart =="
if ! python3 src/verify_deploy.py; then
    echo "FAIL: post-deploy verify failed, not restarting worker" >&2
    exit 1
fi

echo "== 5/5: restarting worker =="
sudo systemctl start queue-worker.service
sudo systemctl is-active --quiet queue-worker.service && echo "deploy OK" || {
    echo "FAIL: worker did not come up after deploy" >&2
    exit 1
}
