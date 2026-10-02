from __future__ import annotations

from datetime import datetime, timedelta, timezone

import record_owner_confirmation as rc


def test_row_has_session_quote_and_target():
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    r = rc.row("0408", "W-1", "ادفع | الآن", "", now)
    assert "0408 (إفادةُ جلسة)" in r and "«ادفع / الآن»" in r and "W-1" in r and r.endswith("|\n")


def test_session_pattern():
    assert rc.SESSION.match("0408") and not rc.SESSION.match("abc")
