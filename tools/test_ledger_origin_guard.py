"""حارسُ الأصل (D-422م): لا بطاقةَ من نقاشٍ أو عصفٍ أو حكمٍ استشاريّ إلا بنصّ أمر المالك الحرفيّ في owner_confirmations.md."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import ledger
import pytest

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=ledger.DOHA)


@pytest.fixture
def env(tmp_path):
    conf = tmp_path / "owner_confirmations.md"
    conf.write_text(
        "| التاريخ | الجلسة | السؤال | النصّ | الهدف |\n"
        "| 2026-10-12 19:16 | 0101 | سؤال | «افتح بطاقة لتشفير نص المخالفة الان» | — |\n"
        "| 2026-09-30 9:05 | 0101 | سؤال | «افتح بطاقة قديمة للسجل» | — |\n",
        encoding="utf-8",
    )
    return {"path": tmp_path / "events.jsonl", "conf": conf}


def add(env, source="intake", problem="عيبٌ في الشيفرة", **kw):
    kw.setdefault("now", NOW)
    now = kw.pop("now")
    orig = ledger.datetime

    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    ledger.datetime = _Fixed
    try:
        return ledger.add_item(source, "bug", problem, "أثر", "قبول", start="2026-10-12T20:00", priority="P2",
                               path=env["path"], confirmations_path=env["conf"], enforce_origin=True, **kw)
    finally:
        ledger.datetime = orig


def test_origin_is_mandatory(env):
    with pytest.raises(ledger.LedgerError, match="--origin إلزاميّ"):
        add(env)


def test_discussion_text_without_owner_order_is_refused(env):
    with pytest.raises(ledger.LedgerError, match="عصفاً أو نقاشاً"):
        add(env, problem="حكم 0104 على عصف السلوك", origin="defect", evidence="behavior/views.py:309")


def test_owner_source_cannot_claim_defect(env):
    with pytest.raises(ledger.LedgerError, match="أصلُه قولُ المالك"):
        add(env, source="owner", origin="defect", evidence="a.py:1")


def test_advisor_source_needs_owner_order(env):
    with pytest.raises(ledger.LedgerError, match="أصلُه قولُ المالك"):
        add(env, source="advisor", origin="automated")


def test_owner_order_found_verbatim_creates_card(env):
    cid = add(env, source="owner", problem="تشفير نص المخالفة بعد عصف السلوك", origin="discussion",
              owner_order="افتح بطاقة لتشفير نص المخالفة")
    item = ledger.reduce_state(ledger.load_events(env["path"]))[cid]
    assert item["origin"] == "discussion"
    assert item["owner_order_at"].startswith("2026-10-12T19:16")


def test_owner_order_absent_from_record_is_refused(env):
    with pytest.raises(ledger.LedgerError, match="غيرُ موجودٍ حرفيّاً"):
        add(env, source="owner", origin="owner-order", owner_order="قالت 0102 إنّ المالك يريدها")


def test_owner_order_too_short_is_refused(env):
    with pytest.raises(ledger.LedgerError, match="قصيرٌ"):
        add(env, source="owner", origin="owner-order", owner_order="اعتمد")


def test_owner_order_older_than_a_week_is_refused(env):
    with pytest.raises(ledger.LedgerError, match="أقدم من 7 أيام"):
        add(env, source="owner", origin="owner-order", owner_order="افتح بطاقة قديمة للسجل")


def test_defect_needs_a_trace(env):
    with pytest.raises(ledger.LedgerError, match="--parent"):
        add(env, origin="defect")


def test_defect_with_existing_parent_is_accepted(env):
    parent = add(env, source="alert", origin="automated")
    cid = add(env, origin="defect", parent=parent)
    assert ledger.reduce_state(ledger.load_events(env["path"]))[cid]["parent"] == parent


def test_defect_with_unknown_parent_is_refused(env):
    with pytest.raises(ledger.LedgerError, match="ليست بطاقةً"):
        add(env, origin="defect", parent="W-20990101-001")


def test_defect_with_evidence_is_accepted_and_bad_evidence_refused(env):
    assert add(env, origin="defect", evidence="behavior/views.py:309")
    with pytest.raises(ledger.LedgerError, match="مسار:سطر"):
        add(env, origin="defect", evidence="في ملفّ السلوك")


def test_automated_only_for_tool_sources(env):
    with pytest.raises(ledger.LedgerError, match="الأدوات الآليّة"):
        add(env, source="intake", origin="automated")


def test_real_ledger_is_always_guarded_and_temp_is_not(env):
    assert ledger._is_real_ledger(None) is (os.environ.get("LEDGER_PATH") is None)
    assert ledger._is_real_ledger(ledger.ROOT / "ledger" / "events.jsonl")
    assert not ledger._is_real_ledger(env["path"])


def test_cli_without_origin_is_refused_on_real_ledger_shape(tmp_path):
    """بلا --origin يرفض السطرُ بالعربيّة قبل أيّ كتابة؛ نوجّه LEDGER_PATH لملفٍّ مؤقّت ونفرض الحارس بنسخ الدفتر الحقيقيّ مساراً."""
    code = (
        "import sys, ledger; ledger._is_real_ledger = lambda p: True; "
        "sys.argv = ['ledger.py', 'add', '--source', 'intake', '--type', 'bug', '--problem', 'م', '--impact', 'أ', "
        "'--accept', 'ق', '--start', '2026-10-12T20:00', '--priority', 'P2']; ledger.main()"
    )
    env = {**os.environ, "LEDGER_PATH": str(tmp_path / "events.jsonl"), "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, "-c", code], cwd=Path(ledger.__file__).parent, env=env,
                       capture_output=True, encoding="utf-8")
    assert p.returncode != 0 and "--origin إلزاميّ" in p.stderr
    assert not (tmp_path / "events.jsonl").exists()


def test_existing_temp_ledger_callers_still_work(tmp_path):
    assert ledger.add_item("owner", "bug", "م", "أ", "ق", path=tmp_path / "e.jsonl", start="2026-10-02T10:00", priority="P2")
