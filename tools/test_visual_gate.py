"""اختباراتُ البوّابة البصريّة بـHTML ثابتٍ صغير في متصفّحٍ حقيقيّ (chromium) — W-20261009-007."""

from __future__ import annotations

import json
import time

import pytest
import visual_gate as vg

playwright_sync = pytest.importorskip("playwright.sync_api")

CLEAN = """
<main style="padding:16px"><div class="card-qatar" style="padding:16px;margin:0 0 16px;border-radius:14px">
<p style="margin:0;font-size:14px">نص</p></div>
<div class="card-qatar" style="padding:16px;border-radius:14px"><p style="margin:0;font-size:14px">بطاقة ثانية</p></div></main>
"""


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def kinds(browser, html: str, width: int = 1280) -> set[str]:
    page = browser.new_page(viewport={"width": width, "height": 800})
    page.set_content(f"<!doctype html><html><body style='margin:0'>{html}</body></html>")
    found = {v["kind"] for v in vg.measure(page)}
    page.close()
    return found


def test_a_clean_page_has_no_violation(browser):
    assert kinds(browser, CLEAN) == set()


def test_horizontal_scroll_and_overflow_are_reported(browser):
    html = "<main><div style='width:1600px;height:20px;background:#ccc'>عريض</div></main>"
    found = kinds(browser, html, width=375)
    assert {"hscroll", "overflow"} <= found


def test_overlap_between_two_siblings(browser):
    html = (
        "<main><div class='card-qatar' style='height:100px;padding:16px'>أ</div>"
        "<div class='card-qatar' style='height:100px;margin-top:-40px;padding:16px'>ب</div></main>"
    )
    assert "overlap" in kinds(browser, html)


def test_off_scale_spacing_and_radius_on_a_card(browser):
    found = kinds(browser, "<main><div class='card-qatar' style='padding:15px;border-radius:12px'>س</div></main>")
    assert {"spacing", "radius"} <= found


def test_on_scale_values_pass(browser):
    assert kinds(browser, "<main><div class='card-qatar' style='padding:24px;margin:8px;border-radius:16px'>س</div></main>") == set()


def test_font_below_twelve_px(browser):
    assert "font" in kinds(browser, "<main><p style='font-size:10px'>صغير</p></main>")


def test_wide_table_without_wrap_and_with_wrap(browser):
    table = "<table style='width:1500px'><tr><td>خلية</td></tr></table>"
    assert "table" in kinds(browser, f"<main><div>{table}</div></main>", width=375)
    assert "table" not in kinds(browser, f"<main><div class='table-wrap' style='overflow-x:auto'>{table}</div></main>", width=375)


def test_card_with_big_void_is_reported(browser):
    html = "<main><div class='card-qatar' style='height:260px;padding:16px'><p style='margin:0'>سطر</p></div></main>"
    assert "void" in kinds(browser, html)


def test_one_page_gate_runs_under_a_minute(browser):
    started = time.time()
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.set_content(CLEAN)
    vg.measure(page)
    page.close()
    assert time.time() - started < vg.PAGE_BUDGET_SECONDS


def test_classify_justification_and_baseline(monkeypatch):
    v = [{"kind": "font", "selector": "p", "detail": "10px", "count": 2}, {"kind": "void", "selector": "div", "detail": "x", "count": 1}]
    out = vg.classify("/a/|principal", v, {"font": "أيقونة نصّيّة مقصودة"})
    assert [(x["kind"], x["justified"]) for x in out] == [("font", True), ("void", False)]
    monkeypatch.setitem(vg.BASELINE, "/a/|principal", {"void": 1})
    assert all(x["justified"] for x in vg.classify("/a/|principal", v, {"font": "سبب"}))
    assert not vg.classify("/new/|principal", v, {})[0]["justified"]


def write_evidence(folder, head, pages, shots=True):
    folder.mkdir(parents=True)
    for page in pages:
        if shots:
            for name in page["shots"]:
                (folder / name).write_bytes(b"png")
    (folder / "manifest.json").write_text(json.dumps({"card": "W-1", "head": head, "pages": pages}), encoding="utf-8")


def page(violations=(), n=vg.SHOTS_PER_PAGE):
    return {"path": "/p/", "role": "principal", "shots": [f"s{i}.png" for i in range(n)], "violations": list(violations)}


def test_evidence_missing_wrong_head_empty_and_incomplete(tmp_path):
    ok, msg = vg.evidence_status("W-1", "abcd1234", tmp_path)
    assert not ok and "لا أدلة بصرية للرأس abcd1234" in msg
    write_evidence(tmp_path / "W-1" / "abcd1234", "ffff0000", [page()])
    assert "الـmanifest لرأس" in vg.evidence_status("W-1", "abcd1234", tmp_path)[1]
    write_evidence(tmp_path / "W-1" / "bbbb2222", "bbbb2222", [])
    assert "لا صفحةَ معلنة" in vg.evidence_status("W-1", "bbbb2222", tmp_path)[1]
    write_evidence(tmp_path / "W-1" / "cccc3333", "cccc3333", [page(n=4)])
    assert "ناقصة" in vg.evidence_status("W-1", "cccc3333", tmp_path)[1]


def test_evidence_passes_only_without_unjustified_violations(tmp_path):
    bad = {"kind": "font", "selector": "p", "detail": "10px", "count": 1, "justified": False}
    write_evidence(tmp_path / "W-1" / "dddd4444", "dddd4444", [page([bad])])
    ok, msg = vg.evidence_status("W-1", "dddd4444", tmp_path)
    assert not ok and "غيرُ مبرَّرة" in msg
    good = dict(bad, justified=True, reason="مقصود")
    write_evidence(tmp_path / "W-1" / "eeee5555", "eeee5555", [page([good])])
    assert vg.evidence_status("W-1", "eeee5555", tmp_path)[0]


def _conf(tmp_path, text):
    f = tmp_path / "oc.md"
    f.write_text(text, encoding="utf-8")
    return f


def test_waive_requires_owner_line(tmp_path):
    with pytest.raises(ValueError):
        vg.waive("W-1", "abcd1234", "r", "0101", tmp_path, _conf(tmp_path, "| x | W-1 @abcd1234 |"))


def test_waive_exact_pair_only(tmp_path):
    c = _conf(tmp_path, "| 1 | «هيا» | إعفاء manifest | W-1 @abcd1234 |")
    vg.waive("W-1", "abcd1234", "للمطوّر وحده", "0101", tmp_path, c)
    assert vg.evidence_status("W-1", "abcd1234", tmp_path, c)[0]
    assert not vg.evidence_status("W-1", "ffff0000", tmp_path, c)[0]
    assert not vg.evidence_status("W-2", "abcd1234", tmp_path, c)[0]


def test_waiver_dies_if_owner_line_removed(tmp_path):
    c = _conf(tmp_path, "| إعفاء manifest | W-1 @abcd1234 |")
    vg.waive("W-1", "abcd1234", "r", "0101", tmp_path, c)
    c.write_text("", encoding="utf-8")
    assert not vg.evidence_status("W-1", "abcd1234", tmp_path, c)[0]


def test_waiver_wins_over_existing_bad_manifest(tmp_path):
    folder = tmp_path / "W-1" / "abcd1234"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"head": "abcd1234", "pages": [{"path": "/x", "shots": [], "violations": [{"justified": False}]}]}), encoding="utf-8")
    c = _conf(tmp_path, "| إعفاء manifest | W-1 @abcd1234 |")
    assert not vg.evidence_status("W-1", "abcd1234", tmp_path, c)[0]
    vg.waive("W-1", "abcd1234", "r", "0101", tmp_path, c)
    assert vg.evidence_status("W-1", "abcd1234", tmp_path, c)[0]


def test_voided_line_does_not_waive(tmp_path):
    c = _conf(tmp_path, "| إعفاء manifest | W-1 @abcd1234 |\n| تصحيح | ملغى[W-1@abcd1234] |")
    with pytest.raises(ValueError):
        vg.waive("W-1", "abcd1234", "r", "0101", tmp_path, c)


def test_card_suffix_does_not_match(tmp_path):
    c = _conf(tmp_path, "| إعفاء manifest | W-1-0081 @abcd1234 |")
    with pytest.raises(ValueError):
        vg.waive("W-1-008", "abcd1234", "r", "0101", tmp_path, c)
