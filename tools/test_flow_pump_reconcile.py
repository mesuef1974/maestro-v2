from __future__ import annotations

import flow_pump as fp


def test_reconcile_pass_is_display_only_by_default_and_writes_on_flag():
    seen = []
    fp.reconcile_pass(False, lambda cmd: (seen.append(cmd) or (0, "ok")))
    assert len(seen) == 2 and all("--write" not in c for c in seen)
    seen.clear()
    fp.reconcile_pass(True, lambda cmd: (seen.append(cmd) or (0, "ok")))
    assert all("--write" in c for c in seen)


def test_reconcile_failure_never_stops_the_cycle():
    def boom(cmd):
        raise OSError("لا gh")

    lines = fp.reconcile_pass(True, boom)
    assert len(lines) == 2 and all("تعذّر" in x for x in lines)
    lines = fp.reconcile_pass(False, lambda cmd: (3, "فشل"))
    assert all("رمز 3" in x for x in lines)
