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
