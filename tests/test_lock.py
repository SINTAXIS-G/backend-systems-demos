import pytest

from lock import LockBusy, exclusive


def test_second_nonblocking_acquire_fails_while_first_holds(tmp_path):
    lock_path = tmp_path / "queue.lock"
    with exclusive(lock_path, blocking=False):
        with pytest.raises(LockBusy):
            with exclusive(lock_path, blocking=False):
                pass  # pragma: no cover - should never get here


def test_lock_released_after_context_exits(tmp_path):
    lock_path = tmp_path / "queue.lock"
    with exclusive(lock_path, blocking=False):
        pass
    # Must succeed now that the first holder released it.
    with exclusive(lock_path, blocking=False):
        pass
