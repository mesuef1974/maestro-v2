"""اختبارُ نواة بطاقات الأدوار (W-20261013-031): لا تسقط قاعدةٌ حاكمة ولا يتجاوز الحجمُ 4 كيلوبايت ولا يضيع نصّ."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import render_role_cards as r  # noqa: E402

CARDS = ROOT / "role_cards"
#: عباراتٌ مفتاحيّةٌ لكلّ قاعدةٍ حاكمةٍ يجب أن تبقى في كلّ نواة.
MUST = ["العربيّةُ وحدَها", "سيدي", "D-88م", "D-381م", "D-421م", "D-130م", "D-414م", "D-447م", "D-468م", "msg_counter", "ground_truth", "اعتماد المالك"]


@pytest.mark.parametrize("sid", r.NUCLEUS_ROLES)
def test_nucleus_size_and_rules(sid):
    text = (CARDS / f"{sid}.md").read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) <= r.NUCLEUS_MAX_BYTES, "النواة تجاوزت 4 كيلوبايت"
    missing = [m for m in MUST if m not in text]
    assert not missing, f"قواعد حاكمة سقطت من النواة: {missing}"


@pytest.mark.parametrize("sid", r.NUCLEUS_ROLES)
def test_details_and_common_keep_full_text(sid):
    det = (CARDS / "details" / f"{sid}.md").read_text(encoding="utf-8")
    common = (CARDS / "COMMON.md").read_text(encoding="utf-8")
    assert r.COMMON.split("\n")[0] in common
    assert "قواعدُ تسري على كلّ الجلسات" in det
    assert len(det.encode("utf-8")) > 5000


def test_governing_constant_covers_must():
    for m in MUST:
        assert m in r.GOVERNING, m


def test_cards_on_disk_equal_a_fresh_generator_run(tmp_path, monkeypatch):
    """لا نصَّ يدويّاً في البطاقات (الجولة 2 من الدمج، 2026-10-21): التوليدُ المباشرُ من tabs.json يعيد كلَّ ملفٍّ كما هو."""
    (tmp_path / "projects" / "schoolos").mkdir(parents=True)
    (tmp_path / "projects" / "schoolos" / "tabs.json").write_bytes((ROOT / "projects" / "schoolos" / "tabs.json").read_bytes())
    monkeypatch.setattr(r, "ROOT", tmp_path)
    monkeypatch.setattr(r, "COMMON", r.COMMON)  # main() يُلحق الأدواتِ بالثابت؛ يُستعاد بعد الاختبار
    monkeypatch.setattr(sys, "argv", ["render_role_cards.py"])
    assert r.main() == 0
    fresh = {p.relative_to(tmp_path / "role_cards").as_posix(): p for p in (tmp_path / "role_cards").rglob("*.md")}
    disk = {p.relative_to(CARDS).as_posix(): p for p in CARDS.rglob("*.md") if not p.relative_to(CARDS).as_posix().startswith("_retired/")}
    assert set(fresh) == set(disk)
    differ = [k for k in fresh if fresh[k].read_text(encoding="utf-8") != disk[k].read_text(encoding="utf-8")]
    assert not differ, f"بطاقاتٌ تختلف عن التوليد المباشر (نصٌّ يدويٌّ أو توليدٌ قديم): {differ}"


def test_round2_texts_live_in_the_source():
    """نصوصٌ كانت يدويّةً أو أُمر بها في الجولة 2 تُولَّد من المصدر."""
    text = {n: (CARDS / n).read_text(encoding="utf-8") for n in ("details/0301.md", "details/0601.md", "details/0701.md", "COMMON.md", "INDEX.md")}
    text.update({k[8:]: v for k, v in list(text.items()) if k.startswith("details/")})
    assert "## ختم مصدر الحقيقة (W-20261020-003، ظلّ)" in text["0301.md"]
    assert "بعد 14:30 وبعد 19:00 (D-429م)" in text["0601.md"] and "(D-429م)" in text["INDEX.md"]
    assert "## إذا توقّف إرسالُك بين الجلسات (قرارُ المالك 2026-10-18)" in text["COMMON.md"]
    assert "## اعتمادُ الرأس لا يُسأل عنه المالك (أمر المالك 2026-10-18)" in text["COMMON.md"]
    assert "معاونوها 0702 (تنفيذ المسنَد) و0703 (توزيع وتتبّع)" in text["0701.md"] or "ومعاونوها: 0702 تنفّذ المسنَد" in text["0701.md"]
    assert "(0701 وحدَها (المستقبِلة))" in (CARDS / "details" / "0702.md").read_text(encoding="utf-8")  # 0702 ميثاقٌ مستقلّ من 2026-10-22
    assert "«القراءة لـ0701»" in text["0701.md"] and "brainstorm_log.py due" in text["0701.md"]
    assert "والعصفُ وتسجيلُه لـ0108" in text["0301.md"] and "brainstorm_log.py add" in (CARDS / "details" / "0108.md").read_text(encoding="utf-8")  # العصف انتقل من 0301 إلى 0108 (2026-10-22)
    assert "حدُّ الرسائل لكلّ جلسة: 600 رسالة" in text["COMMON.md"] and "حدُّ الرسائل 600" in r.COMMON_DIGEST and "150 لكلّ جلسة" not in r.COMMON_DIGEST + r.GOVERNING


def test_gate_and_advisor_charters_split_out_of_0101_into_0106_and_0107():
    """ميثاقا البوابة والمستشار خرجا من 0101 إلى جلستين عند الطلب 0106 و0107 (أمر المالك 2026-10-21، D-455م)،
    فلا «مدمَج من» في تفاصيل 0101 وتحمل بطاقتا الجديدتين نصَّيهما، والنواةُ ≤ 4096 بايت."""
    core = (CARDS / "0101.md").read_text(encoding="utf-8")
    details = (CARDS / "details" / "0101.md").read_text(encoding="utf-8")
    assert "## مدمَج من 0201 ·" not in details and "## مدمَج من 0301 ·" not in details
    assert "role_cards/details/0101.md" in core
    assert len(core.encode("utf-8")) <= 4096
    gate = (CARDS / "details" / "0106.md").read_text(encoding="utf-8")
    advisor = (CARDS / "details" / "0107.md").read_text(encoding="utf-8")
    assert "البلاغات" in gate and "تسليمُ رأسه إلى 0107" in gate
    assert "بوّابةَ المواصفة الكاملة" in advisor and "الفاصل مع 0301 الحوكمة" in advisor
