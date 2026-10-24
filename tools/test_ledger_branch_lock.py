"""حارسا W-20261025-002: بطاقةٌ حيّةٌ واحدةٌ على الفرع، وقفلُ الرأس عند تدوين pushed — بلا شبكة."""

from __future__ import annotations

import ledger
import pytest


def _add(path, branch=""):
    return ledger.add_item("owner", "tool", "سكربت", "أ", "ق", start="2026-10-20T09:00", priority="P2", path=path, branch=branch)


def test_second_card_on_live_branch_is_rejected_and_names_existing(tmp_path):
    p = tmp_path / "e.jsonl"
    first = _add(p, "claude/x")
    with pytest.raises(ledger.LedgerError, match=first):
        _add(p, "claude/x")


def test_second_card_accepted_after_first_is_closed(tmp_path):
    p = tmp_path / "e.jsonl"
    first = _add(p, "claude/x")
    ledger.append_event("state", first, {"state": "closed", "by": "0101"}, p)
    assert _add(p, "claude/x")


def test_other_branch_and_no_branch_are_free(tmp_path):
    p = tmp_path / "e.jsonl"
    _add(p, "claude/x")
    assert _add(p, "claude/y")
    assert _add(p) and _add(p)


def test_move_binding_branch_rejects_when_taken(tmp_path):
    p = tmp_path / "e.jsonl"
    _add(p, "claude/x")
    other = _add(p)
    with pytest.raises(ledger.LedgerError, match="بطاقةٌ حيّة"):
        ledger.move(other, "routed", path=p, by="0101", held_by="0701", branch="claude/x")


def test_merged_card_frees_the_branch():
    items = {"A": {"branch": "b", "state": "merged"}}
    ledger.check_branch_free(items, "B", "b")


def test_head_lock_rejects_pushed_with_other_head():
    item = {"approved_head": "abcdef12"}
    with pytest.raises(ledger.LedgerError, match="قفلُ الرأس"):
        ledger.check_head_lock(item, "pushed", "99999999")


def test_head_lock_accepts_same_head_and_unapproved_and_other_states():
    ledger.check_head_lock({"approved_head": "abcdef12"}, "pushed", "abcdef12aa")
    ledger.check_head_lock({}, "pushed", "99999999")
    ledger.check_head_lock({"approved_head": "abcdef12"}, "merged", "99999999")
