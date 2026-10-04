from __future__ import annotations

import web_citations_audit as w

FULL = """# ext
- الرابط: https://almeezan.qa/LawPage.aspx?id=7121
- تاريخ الجلب: 2026-10-04
- النوع: نصّ نظاميّ
- الثقة: متوسّطة
- حرفيّ أم ملخّص: ملخّص
- ما لم يُتحقَّق منه: النصّ الحرفيّ
"""


def test_normalize_and_external_filter():
    assert w.normalize("https://www.AlMeezan.qa/x/") == "almeezan.qa/x"
    assert not w.is_external("http://localhost:8500/styleguide/")
    assert not w.is_external("https://github.com/org/repo/pull/1")
    assert w.is_external("https://almeezan.qa/LawPage.aspx?id=7121")


def test_registered_and_unregistered(tmp_path):
    sot = tmp_path / "sot"; sot.mkdir()
    (sot / "ext_a.md").write_text(FULL, encoding="utf-8")
    doc = tmp_path / "d.md"
    doc.write_text("انظر https://almeezan.qa/LawPage.aspx?id=7121 وhttps://ico.org.uk/x وhttp://localhost:8500/y", encoding="utf-8")
    r = w.audit([doc], [sot])
    assert r["cited"] == 2 and r["registered"] == 1
    assert list(r["unregistered"]) == ["ico.org.uk/x"] and r["incomplete"] == {}


def test_incomplete_ext_file(tmp_path):
    sot = tmp_path / "sot"; sot.mkdir()
    (sot / "ext_b.md").write_text("# بلا حقول\nنصٌّ فقط", encoding="utf-8")
    r = w.audit([], [sot])
    assert "ext_b.md" in r["incomplete"] and "الثقة" in r["incomplete"]["ext_b.md"]


def test_strict_exit_code(tmp_path):
    sot = tmp_path / "sot"; sot.mkdir()
    doc = tmp_path / "d.md"; doc.write_text("https://x.example.org/a", encoding="utf-8")
    assert w.main(["--sot", str(sot), "--scan", str(doc), "--strict"]) == 1
    assert w.main(["--sot", str(sot), "--scan", str(doc)]) == 0
