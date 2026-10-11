import json

import verify_deploy


def _setup_tree(tmp_path, monkeypatch, commit="abc123"):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("print('hello')\n")

    monkeypatch.setattr(verify_deploy, "ROOT", tmp_path)
    monkeypatch.setattr(verify_deploy, "MANIFEST_PATH", tmp_path / "deploy" / "manifest.json")
    monkeypatch.setattr(verify_deploy, "current_commit", lambda: commit)
    return src_dir


def test_write_then_verify_matches(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    verify_deploy.write_manifest()
    assert verify_deploy.verify() is True


def test_verify_fails_closed_with_no_manifest(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    assert verify_deploy.verify() is False


def test_verify_fails_when_installed_code_drifts_from_manifest(tmp_path, monkeypatch):
    src_dir = _setup_tree(tmp_path, monkeypatch)
    verify_deploy.write_manifest()

    # Simulate an unrecorded hotfix: code changes without regenerating the manifest.
    (src_dir / "app.py").write_text("print('modified without a deploy')\n")

    assert verify_deploy.verify() is False


def test_verify_fails_on_corrupted_manifest_json(tmp_path, monkeypatch):
    _setup_tree(tmp_path, monkeypatch)
    verify_deploy.write_manifest()

    manifest = json.loads(verify_deploy.MANIFEST_PATH.read_text())
    manifest["src_hash"] = "0" * 64  # corrupt it
    verify_deploy.MANIFEST_PATH.write_text(json.dumps(manifest))

    assert verify_deploy.verify() is False
