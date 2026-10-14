"""اختبارُ publish_sync.py: التصنيفُ والعرضُ بلا شبكةٍ ولا git (W-20261014-023)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import publish_sync as ps  # noqa: E402


def _pr(n, head, merge):
    return {"number": n, "title": f"طلب {n}", "headRefOid": head * 8, "mergeCommit": {"oid": merge}}


def test_classifies_by_card_state_and_prod_ancestry():
    prs = [_pr(1, "a", "m1"), _pr(2, "b", "m2"), _pr(3, "c", "m3"), _pr(4, "d", "m4")]
    cards = {"aaaaaaaa": ("W-1", "approved"), "bbbbbbbb": ("W-2", "published")}
    d = ps.build_digest("331f3ae6e", prs, cards, lambda c: c != "m4")
    assert [r["pr"] for r in d["pending"]] == [1]
    assert [r["pr"] for r in d["published"]] == [2]
    assert [r["pr"] for r in d["no_card"]] == [3]  # #4 ليس في الإنتاج فلا يظهر
    assert d["prod"] == "331f3ae6"


def test_render_prints_move_command_only_for_pending_and_states_the_limit():
    d = {
        "prod": "331f3ae6",
        "pending": [{"pr": 1, "title": "t", "head": "aaaaaaaa", "card": "W-1", "state": "approved"}],
        "published": [],
        "no_card": [],
    }
    text = ps.render(d)
    assert "ledger.py move W-1 published --head aaaaaaaa --by 0601" in text
    assert "لا قياسَ" in text


def test_cards_by_head_uses_last_state_event():
    ev = [
        {"kind": "state", "id": "W-1", "data": {"state": "approved", "head": "aaaaaaaa11"}},
        {"kind": "state", "id": "W-1", "data": {"state": "published"}},
        {"kind": "note", "id": "W-1", "data": {}},
    ]
    assert ps.cards_by_head(ev) == {"aaaaaaaa": ("W-1", "published")}


def test_merge_without_merge_commit_is_skipped():
    prs = [{"number": 9, "title": "x", "headRefOid": "e" * 40, "mergeCommit": None}]
    d = ps.build_digest("abc", prs, {}, lambda c: True)
    assert d["pending"] == d["published"] == d["no_card"] == []
