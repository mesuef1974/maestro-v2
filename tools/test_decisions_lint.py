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
