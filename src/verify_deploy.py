"""Source-to-installed identity check.

Hashes the installed src/ tree and compares it against deploy/manifest.json,
which records the hash expected for a specific git commit. Exits non-zero on
any mismatch or missing manifest — meant to run as a hard gate before the
worker starts and inside the maintenance timer, never silently skipped.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "deploy" / "manifest.json"


def hash_tree(src_dir: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(src_dir.rglob("*.py")):
        h.update(path.relative_to(src_dir).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def current_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def write_manifest() -> None:
    """Run after a deploy, once the new code is in place and trusted."""
    manifest = {"commit": current_commit(), "src_hash": hash_tree(ROOT / "src")}
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"manifest written: {manifest}")


def verify() -> bool:
    if not MANIFEST_PATH.exists():
        print("FAIL: no deploy manifest found — nothing to verify against", file=sys.stderr)
        return False

    manifest = json.loads(MANIFEST_PATH.read_text())
    actual_hash = hash_tree(ROOT / "src")
    actual_commit = current_commit()

    ok = True
    if actual_hash != manifest["src_hash"]:
        print(
            f"FAIL: installed src/ hash {actual_hash[:12]} does not match "
            f"manifest {manifest['src_hash'][:12]} — installed code does not "
            f"match the last recorded deploy",
            file=sys.stderr,
        )
        ok = False
    if actual_commit != manifest["commit"]:
        print(
            f"WARN: HEAD is {actual_commit[:12]}, manifest recorded "
            f"{manifest['commit'][:12]} (hash still matched: {ok})",
            file=sys.stderr,
        )

    if ok:
        print(f"OK: installed src/ matches manifest for commit {actual_commit[:12]}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--write":
        write_manifest()
        sys.exit(0)
    sys.exit(0 if verify() else 1)
