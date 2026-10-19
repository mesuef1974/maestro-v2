"""فحصُ مراجع المواصفة على المصدر (W-20261019-011): بلا شبكة ولا git — الفاحصان محقونان."""

import ground_truth as gt

ITEM = {
    "ref": {"kind": "مشابه", "path": ".github/workflows/quality-gate.yml (وظيفتا axe-a11y وe2e) وscripts/ci_needs_gate.py", "url": "http://localhost:8500/x/a.html"},
    "source_of_truth": "التقرير ci_congestion_report.md؛ الطلب #1087 وquality-gate.yml",
}


def test_references_are_extracted_without_arabic_prefix_urls_or_duplicates():
    refs = gt.spec_references(ITEM)
    assert ("path", ".github/workflows/quality-gate.yml") in refs
    assert ("path", "scripts/ci_needs_gate.py") in refs, "حرفٌ عربيٌّ لاصق («وscripts») ليس من المسار"
    assert ("path", "ci_congestion_report.md") in refs
    assert ("pr", "1087") in refs
    assert not any("a.html" in v for _, v in refs), "رابطُ 8500 لا يُفحص مساراً"
    assert len(refs) == len(set(refs))


def test_all_present_is_clean():
    rows = gt.check_references(ITEM, path_exists=lambda p: True, pr_state=lambda n: "MERGED (shschool_mvp)")
    assert rows and all(ok for _, _, ok, _ in rows)


def test_missing_path_and_unknown_pr_are_flagged():
    rows = gt.check_references(ITEM, path_exists=lambda p: p != "scripts/ci_needs_gate.py", pr_state=lambda n: None)
    bad = {value for _, value, ok, _ in rows if not ok}
    assert bad == {"scripts/ci_needs_gate.py", "#1087"}


def test_item_without_references_gives_no_rows():
    assert gt.check_references({"ref": {}, "source_of_truth": "قرارُ المالك شفهيّاً"}, lambda p: True, lambda n: "OPEN") == []
