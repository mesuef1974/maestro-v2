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
MUST = ["العربيّةُ وحدَها", "سيدي", "D-88م", "D-381م", "D-421م", "D-130م", "D-414م", "msg_counter", "ground_truth", "اعتماد المالك"]


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
    assert len(det.encode("utf-8")) > 10000


def test_governing_constant_covers_must():
    for m in MUST:
        assert m in r.GOVERNING, m
