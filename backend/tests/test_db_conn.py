class FakeConn:
    def __init__(self, closed=0, fail_rollback=False):
        self.closed = closed
        self.fail_rollback = fail_rollback
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1
        if self.fail_rollback:
            raise Exception("connection already closed")


def test_safe_rollback_no_tira_si_ya_cerro():
    from app.db import _safe_rollback

    dead = FakeConn(closed=1, fail_rollback=True)
    _safe_rollback(dead)
    assert dead.rollbacks == 0

    alive = FakeConn(closed=0)
    _safe_rollback(alive)
    assert alive.rollbacks == 1


def test_safe_rollback_traga_error_de_postgres():
    from app.db import _safe_rollback

    conn = FakeConn(closed=0, fail_rollback=True)
    _safe_rollback(conn)
    assert conn.rollbacks == 1
