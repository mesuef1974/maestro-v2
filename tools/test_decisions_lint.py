from __future__ import annotations

import decisions_lint as dl

SAMPLE = """\
- D-1م | 10-01 10:00 | نصٌّ أوّل | أثر | مصدر
- D-2م | 10-01 11:00 | نصٌّ ثانٍ | أثر | مصدر
- D-3م | 10-01 09:00 | نصٌّ ثالثٌ بطابعٍ أسبق | أثر | مصدر
- D-4م | 10-01 12:00 | نصٌّ ثانٍ | أثر | مصدر
- D-6م | 10-01 13:00 | نصٌّ سادس | أثر | مصدر
"""


def test_detects_duplicate_backwards_and_gap():
    notes = dl.lint(dl.parse(SAMPLE))
    joined = "\n".join(notes)
    assert "D-3م: طابعُ زمنٍ أسبقُ" in joined
    assert "D-4م: نصٌّ مكرَّر" in joined
    assert "فجوةٌ في الترقيم بين D-4م وD-6م" in joined


def test_clean_log_has_no_notes():
    clean = "- D-1م | 10-01 10:00 | أ | أثر | م\n- D-2م | 10-01 11:00 | ب | أثر | م\n"
    assert dl.lint(dl.parse(clean)) == []


def test_since_skips_old_entries():
    assert dl.lint(dl.parse(SAMPLE), since=5) == []


def test_suffix_allows_same_number_and_event_time_marks_late_stamp():
    log = (
        "- D-1م | 10-01 10:00 | أ | أثر | م\n"
        "- D-1م-ب | 10-01 11:00 | ب | أثر | م\n"
        "- D-2م | 10-01 09:00 وقتُ الحدث | ج | أثر | م\n"
    )
    assert dl.lint(dl.parse(log)) == []
    dup = log.replace("D-1م-ب", "D-1م")
    assert "رقمٌ مكرَّر" in "\n".join(dl.lint(dl.parse(dup)))




def _log(*nums):
    return "".join(f"- D-{n}م | 10-01 1{i}:00 | نصٌّ رقم {n} {i} | أثر | مصدر\n" for i, n in enumerate(nums))


def test_new_duplicate_number_is_rejected_but_legacy_baseline_passes():
    assert any("D-490م: رقمٌ مكرَّر" in n for n in dl.lint(dl.parse(_log(489, 490, 490))))
    assert not any("رقمٌ مكرَّر" in n for n in dl.lint(dl.parse(_log(476, 476))))  # تكرارٌ تاريخيّ مسموح


def test_real_log_has_no_new_duplicate_number():
    text = (dl.ROOT / "decisions.md").read_text(encoding="utf-8")
    assert [n for n in dl.lint(dl.parse(text)) if "رقمٌ مكرَّر" in n] == []
