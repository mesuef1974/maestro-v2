"""W-20261027-008: ledger.move يفحص الملاحظة وكلَّ الحقول قبل أيّ كتابة؛ الرفضُ لا يترك حالةً مكتوبةً بلا ملاحظتها."""
import ledger
import pytest


@pytest.fixture
def card(tmp_path):
    p = tmp_path / "ev.jsonl"
    cid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-25T10:00", priority="P2")
    return cid, p


def test_too_long_note_is_refused_before_the_state_event_is_written(card):
    cid, p = card
    n = len(ledger.load_events(p))
    with pytest.raises(ledger.LedgerError, match="أطول من"):
        ledger.move(cid, "routed", path=p, note="ن" * (ledger.FIELD_MAX + 1), waive_spec="اختبار", held_by="0301")
    assert len(ledger.load_events(p)) == n  # لا حدثَ حالةٍ ولا ملاحظة
    assert ledger.reduce_state(ledger.load_events(p))[cid]["state"] == "captured"


def test_pii_in_note_is_refused_before_any_write(card):
    cid, p = card
    n = len(ledger.load_events(p))
    with pytest.raises(ledger.LedgerError):
        ledger.move(cid, "routed", path=p, note="تواصل مع someone@example.com", waive_spec="اختبار", held_by="0301")
    assert len(ledger.load_events(p)) == n


def test_valid_note_still_writes_state_then_note(card):
    cid, p = card
    ledger.move(cid, "routed", path=p, note="  توجيه سليم  ", waive_spec="اختبار", held_by="0301")
    events = ledger.load_events(p)
    assert [e["kind"] for e in events[-2:]] == ["state", "note"]
    assert events[-1]["data"]["text"].startswith("توجيه سليم")  # مقصوصة الفراغات ثم يلحقها تدوينُ استثناء المواصفة
    assert ledger.reduce_state(events)[cid]["state"] == "routed"
