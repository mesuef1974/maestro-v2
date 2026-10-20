from __future__ import annotations

from datetime import datetime, timedelta, timezone

import record_owner_confirmation as rc


def test_row_has_session_quote_and_target():
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    r = rc.row("0405", "W-1", "ادفع | الآن", "", now)
    assert "0405 (إفادةُ جلسة)" in r and "«ادفع / الآن»" in r and "W-1" in r and r.endswith("|\n")


def test_session_pattern():
    assert rc.SESSION.match("0405") and not rc.SESSION.match("abc")


def test_window_order_row_is_tagged_and_found_without_head():
    now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone(timedelta(hours=3)))
    r = rc.row("0601", "#1170", "ادمج الآن", "", now, source="مباشر", window=True)
    assert rc.WINDOW_TAG in r and "@" not in r
    assert rc.window_order_present(r, "#1170")
    assert not rc.window_order_present(r, "#117") and not rc.window_order_present(r, "#11700")


def test_plain_row_is_not_a_window_order():
    r = rc.row("0601", "#1170", "ادفع", "", head="abcdef12", source="مباشر")
    assert not rc.window_order_present(r, "#1170")


STANDING = (
    "| 2026-10-18 10:00 | 0101 (إفادةُ جلسة) مصدره: مباشر | q | «نعم، دائم» | standing-head-approval |\n"
    "| 2026-10-18 10:01 | 0101 (إفادةُ جلسة) مصدره: مباشر | q | «نعم، دائم يغني (Recommended)» | delegations-no-expiry |\n"
)
OK_ITEM = {"state": "ready_for_review", "files": ["tools/ledger_reconcile.py"], "files_allowed": ["tools/test_x.py"]}
REVIEWED = "راجعتُ الفرق: أداة قراءة فقط واختباراتها"


def _problem(item=OK_ITEM, diff=("tools/x.py",), head="abcdef12", now="abcdef1234567890", reviewed=REVIEWED, session="0101"):
    return rc.delegation_problem(item, "W-1", head, list(diff), now, reviewed, session)


def test_delegation_accepts_a_tools_only_diff_at_the_reviewed_head():
    assert _problem() is None


def test_delegation_is_for_0101_only_and_needs_a_review_text_and_matching_head():
    assert "0101" in _problem(session="0405")
    assert "--reviewed" in _problem(reviewed="قصير")
    assert "≠" in _problem(now="99999999aaaa")
    assert "بعده" in _problem(item={**OK_ITEM, "state": "approved"})
    assert "غيرُ موجودة" in _problem(item=None)
    assert "لا فرقَ" in _problem(diff=())


def test_delegation_refuses_ui_security_migration_governing_and_approval_chain_paths():
    for path in (
        "templates/dashboard/a.html",
        "static/css/x.css",
        "operations/migrations/0001_x.py",
        "core/capabilities.py",
        "CLAUDE.md",
        ".claude/rules/migrations.md",
        "docs/governance/flow.md",
        "tools/approval_check.py",
        "tools/record_owner_confirmation.py",
        "tools/ledger.py",
        "owner_confirmations.md",
    ):
        assert "يمسّ ما لا يُفوَّض" in _problem(diff=(path,)), path
    assert "يمسّ" in _problem(item={**OK_ITEM, "files": ["core/capabilities.py"]})  # من ملفّات البطاقة لا الفرق وحدَه


def test_standing_quote_comes_from_the_owners_two_recorded_lines_only():
    assert rc.standing_quote(STANDING)[0] == "دائم يغني"
    for text in ("", STANDING.splitlines()[0] + "\n", STANDING.replace("مصدره: مباشر", "مصدره: نقلاً عن 0101")):
        try:
            rc.standing_quote(text)
        except ValueError:
            continue
        raise AssertionError("قُبل نصٌّ لم يقله المالك")
