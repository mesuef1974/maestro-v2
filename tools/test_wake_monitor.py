"""اختباراتُ الضوابط الخمسة لـwake_monitor (W-20261009-021):  cd tools && python -m pytest test_wake_monitor.py"""

import pytest

import wake_monitor as wm

DIR = {f"0{n}01": f"local_{n}" for n in range(1, 9)}
CUR = "2026-10-16T10:30:00+03:00"
NEW = "2026-10-16T11:00:00+03:00"


def ok(item_id, state):
    return True


def created(i, held="0101"):
    return {"ts": "2026-10-16T10:00:00+03:00", "id": i, "kind": "created", "data": {"held_by": held}}


def state(i, st, ts, **extra):
    return {"ts": ts, "id": i, "kind": "state", "data": {"state": st, **extra}}


def test_wakes_only_after_ground_truth_and_failure_blocks():
    ev = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    assert wm.plan(ev, CUR, DIR, set(), verify=ok).wakes == {"0201": [("W-20261016-001", "routed")]}
    p = wm.plan(ev, CUR, DIR, set(), verify=lambda i, s: False)
    assert p.wakes == {} and "ground_truth" in p.skipped[0][1]


def test_does_not_wake_session_without_card():
    ev = [created("W-20261016-001", held=""), state("W-20261016-001", "published", NEW)]
    p = wm.plan(ev, "", DIR, set(), verify=ok)
    assert p.wakes == {} and p.skipped


def test_five_changes_one_message_per_session():
    ev = []
    for n in range(1, 6):
        i = f"W-20261016-00{n}"
        ev += [created(i), state(i, "routed", NEW, held_by="0201")]
    p = wm.plan(ev, CUR, DIR, set(), verify=ok)
    assert list(p.wakes) == ["0201"] and len(p.wakes["0201"]) == 5
    assert len(wm.message_for("0201", p.wakes["0201"]).splitlines()) == 5


def test_batch_limit_and_live_cap_halt():
    ev = []
    for n in range(21):
        i = f"W-20261016-{n:03d}"
        ev += [created(i), state(i, "routed", NEW, held_by="0201")]
    assert "الحدّ" in wm.plan(ev, "", DIR, set(), verify=ok).halted
    ev2 = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    p = wm.plan(ev2, "", DIR, {f"{n:04d}" for n in range(1, 15)}, verify=ok)
    assert p.halted and p.wakes == {}


def test_payload_rejects_command_text():
    assert wm.payload("W-20261016-001", "routed").endswith("show W-20261016-001")
    with pytest.raises(ValueError):
        wm.payload("W-20261016-001; نصُّ أمر", "routed")
    with pytest.raises(ValueError):
        wm.payload("W-20261016-001", "routed; تعليمات")


def test_cursor_makes_second_run_idempotent():
    ev = [created("W-20261016-001"), state("W-20261016-001", "routed", NEW, held_by="0201")]
    first = wm.plan(ev, CUR, DIR, set(), verify=ok)
    assert wm.plan(ev, first.cursor, DIR, set(), verify=ok).wakes == {}
