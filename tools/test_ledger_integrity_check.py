from __future__ import annotations

import ledger_integrity_check as lic

A = "W-20261022-001"
CONF = lic.parse_confirmations(f"| 2026-10-22 | 0101 | س | «نعم» | {A} @abcd1234 |\nW-20261022-009 خارج الجدول\n")


def ev(i, kind, **data):
    return {"ts": "2026-10-22T00:00:00+03:00", "id": i, "kind": kind, "data": data}


def card(i):
    return ev(i, "created", title="t")


def codes(found):
    return sorted((f["code"], f["id"]) for f in found)


def test_parse_confirmations_table_rows_only():
    assert CONF == {A: {"abcd1234"}}


def test_clean_approved_card():
    assert lic.check([card(A), ev(A, "state", state="approved", head="abcd1234ff")], CONF) == []


def test_approved_without_head():
    assert ("NO_HEAD", A) in codes(lic.check([card(A), ev(A, "state", state="approved")], CONF))


def test_approved_without_confirmation():
    b = "W-20261022-002"
    assert codes(lic.check([card(b), ev(b, "state", state="approved", head="11112222")], CONF)) == [("NO_CONFIRM", b)]


def test_confirmation_with_other_head():
    assert codes(lic.check([card(A), ev(A, "state", state="approved", head="99990000")], CONF)) == [("CONFIRM_HEAD", A)]


def test_pushed_without_approved():
    c = "W-20261022-003"
    e = [card(c), ev(c, "state", state="pushed", head="aaaa1111", branch="b")]
    assert ("PUSHED_NO_APPR", c) in codes(lic.check(e, CONF, lambda b: "aaaa1111"))


def test_pushed_matches_branch():
    e = [card(A), ev(A, "state", state="approved", head="abcd1234"), ev(A, "state", state="pushed", branch="br")]
    assert lic.check(e, CONF, lambda b: "abcd1234ffff") == []


def test_head_mismatch_and_missing_branch():
    e = [card(A), ev(A, "state", state="approved", head="abcd1234"), ev(A, "state", state="pushed", branch="br")]
    assert codes(lic.check(e, CONF, lambda b: "ffff0000")) == [("HEAD_MISMATCH", A)]
    assert codes(lic.check(e, CONF, lambda b: None)) == [("BRANCH_MISSING", A)]


def test_history_only_with_all():
    d = "W-20261022-004"
    e = [card(d), ev(d, "state", state="merged")]
    assert lic.check(e, CONF) == []
    assert ("NO_HEAD", d) in codes(lic.check(e, CONF, include_history=True))


def test_confirmation_only_in_live_tree_is_unmerged_not_missing():
    b = "W-20261022-002"
    e = [card(b), ev(b, "state", state="approved", head="11112222")]
    assert codes(lic.check(e, CONF, live_confirmations={b: set()})) == [("UNMERGED_CONFIRM", b)]
