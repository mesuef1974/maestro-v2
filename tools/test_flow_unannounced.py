"""اختباراتُ flow_unannounced (W-20261014-014): عدّ الأوسمة، المبلَّغ لا يُعدّ، والتنسيق المجهول يُبلَّغ عنه."""

import flow_unannounced as fu

SAMPLE = """| v2.14 | 09-29 | D-68م | **(أُبلغت 2026-10-02 في تعميمٍ مجمَّع)** **ما بعد الاعتماد آليّ:** نص
| v2.20 | 10-02 | D-130م | **(مسوّدةٌ للمراجعة — لم تُبلَّغ بعد)** **سياسةُ متى يُسأل المالك:** تفصيل
| v2.23 | 10-02 | D-146م | **(لم تُبلَّغ بعد)** **الاعتمادُ مربوطٌ بالرأس:** تفصيل
| v2.99 | 10-02 | D-999م | سطرٌ بلا وسم إبلاغ
- **v2.26 — 2026-10-10 — مسار المعاينة (D-328م، أمر المالك):** نص
هذا ليس سطر إصدار
"""


def test_pending_announced_and_unknown_are_split():
    rows = fu.parse(SAMPLE)
    by = {r["version"]: r["status"] for r in rows}
    assert by == {"v2.14": fu.ANNOUNCED, "v2.20": fu.PENDING, "v2.23": fu.PENDING, "v2.99": fu.UNKNOWN, "v2.26": fu.UNKNOWN}


def test_announced_is_not_counted_and_decision_is_read():
    rows = [r for r in fu.parse(SAMPLE) if r["status"] == fu.PENDING]
    assert [r["decision"] for r in rows] == ["D-130م", "D-146م"]


def test_notice_has_three_lines_with_title_from_the_line():
    row = next(r for r in fu.parse(SAMPLE) if r["version"] == "v2.23")
    lines = fu.notice(row).splitlines()
    assert len(lines) == 3 and "الاعتمادُ مربوطٌ بالرأس" in lines[0] and "D-146م" in lines[0]


def test_main_prints_count_and_never_writes(tmp_path, capsys):
    f = tmp_path / "flow_changelog.md"
    f.write_text(SAMPLE, encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    assert fu.main(["--file", str(f)]) == 0
    out = capsys.readouterr().out
    assert "لم تُبلَّغ بعد: 2 من 5" in out and "تنسيقٌ غيرُ معروف" in out
    assert f.read_text(encoding="utf-8") == before


def test_real_changelog_baseline_is_measurable():
    rows = fu.parse(fu.CHANGELOG.read_text(encoding="utf-8"))
    assert rows and all(r["status"] in (fu.PENDING, fu.ANNOUNCED, fu.UNKNOWN) for r in rows)
