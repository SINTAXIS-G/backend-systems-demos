import json

import queue_worker
from db import connect


def test_process_one_success_moves_file_to_done(tmp_path, monkeypatch):
    monkeypatch.setattr(queue_worker, "DONE", tmp_path / "done")
    monkeypatch.setattr(queue_worker, "FAILED", tmp_path / "failed")
    queue_worker.DONE.mkdir()
    queue_worker.FAILED.mkdir()

    conn = connect(tmp_path / "state.db")
    cmd_path = tmp_path / "ok-cmd.json"
    cmd_path.write_text(json.dumps({"op": "noop"}))

    queue_worker.process_one(conn, cmd_path)

    assert not cmd_path.exists()
    assert (queue_worker.DONE / "ok-cmd.json").exists()
    row = conn.execute("SELECT status FROM commands WHERE id = ?", ("ok-cmd",)).fetchone()
    assert row[0] == "done"


def test_process_one_failure_moves_file_to_failed_and_records_error(tmp_path, monkeypatch):
    monkeypatch.setattr(queue_worker, "DONE", tmp_path / "done")
    monkeypatch.setattr(queue_worker, "FAILED", tmp_path / "failed")
    queue_worker.DONE.mkdir()
    queue_worker.FAILED.mkdir()

    conn = connect(tmp_path / "state.db")
    cmd_path = tmp_path / "bad-cmd.json"
    cmd_path.write_text(json.dumps({"fail": True, "fail_reason": "disk full"}))

    queue_worker.process_one(conn, cmd_path)

    assert not cmd_path.exists()
    assert (queue_worker.FAILED / "bad-cmd.json").exists()
    row = conn.execute(
        "SELECT status, error FROM commands WHERE id = ?", ("bad-cmd",)
    ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "disk full"
