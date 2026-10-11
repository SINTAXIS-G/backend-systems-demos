from db import connect, finish_command, start_command, stuck_commands, integrity_check


def test_normal_dispatch_lifecycle(tmp_path):
    conn = connect(tmp_path / "state.db")
    start_command(conn, "cmd-1", '{"op": "noop"}')
    assert len(stuck_commands(conn)) == 1

    finish_command(conn, "cmd-1", ok=True)
    assert stuck_commands(conn) == []

    row = conn.execute("SELECT status FROM commands WHERE id = ?", ("cmd-1",)).fetchone()
    assert row[0] == "done"


def test_crash_mid_command_leaves_stuck_row_not_silently_lost(tmp_path):
    """Simulates a crash: start_command commits, then the process dies
    before finish_command runs. A fresh connection to the same db file
    (standing in for the worker restarting) must still see it as
    in_progress — WAL durability — so recover.sh can surface it."""
    db_path = tmp_path / "state.db"

    conn1 = connect(db_path)
    start_command(conn1, "cmd-crash", '{"op": "will not finish"}')
    conn1.close()  # simulates the process dying right here, no finish_command

    conn2 = connect(db_path)  # simulates the worker restarting
    stuck = stuck_commands(conn2)
    assert len(stuck) == 1
    assert stuck[0]["id"] == "cmd-crash"


def test_integrity_check_reports_ok_on_healthy_db(tmp_path):
    conn = connect(tmp_path / "state.db")
    assert integrity_check(conn) == "ok"
