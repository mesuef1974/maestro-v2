"""اختباراتُ مصنِّف إعادات الاعتماد (W-20261016-016)."""

import reapproval_causes as rc


def ev(card, head):
    return {"id": card, "kind": "state", "ts": "2026-10-16T10:00:00+03:00", "data": {"state": "approved", "head": head}}


def test_classify_each_cause():
    assert rc.classify_paths(["templates/a.html"]) == "واجهة"
    assert rc.classify_paths(["core/migrations/0001_x.py", "core/a.py"]) == "هجرة"
    assert rc.classify_paths(["core/a.py"]) == "كود"
    assert rc.classify_paths(["tests/test_a.py"]) == "اختبارات فقط"
    assert rc.classify_paths(["docs/a.md", "README.md"]) == "وثائق فقط"
    assert rc.classify_paths([]) == "غير معروف"


def test_pairs_only_for_different_heads():
    events = [ev("A", "h1"), ev("A", "h1"), ev("A", "h2"), ev("B", "h9")]
    assert rc.pairs(events) == [("A", "h1", "h2")]


def test_unknown_when_head_missing_or_diff_fails():
    events = [ev("A", None), ev("A", "h2"), ev("B", "h1"), ev("B", "h2")]
    out = rc.classify_all(events, "x", differ=lambda repo, o, n: None)
    assert [c for _, c in out] == ["غير معروف", "غير معروف"]


class ExcludeMainTest(__import__("unittest").TestCase):
    def test_empty_own_diff_is_main_merge_only(self):
        ev = [
            {"id": "C", "kind": "state", "data": {"state": "approved", "head": "aaaa"}},
            {"id": "C", "kind": "state", "data": {"state": "approved", "head": "bbbb"}},
        ]
        res = rc.classify_all(ev, ".", lambda r, o, n: [])
        self.assertEqual(res, [("C", "دمج main فقط")])
