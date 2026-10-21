"""اتجاهُ القول (الموجة 0.2، D-453م): سطرٌ نصُّه رفضٌ لا يُحسب اعتماداً ولو حمل البطاقةَ والرأس."""

from __future__ import annotations

from pathlib import Path

import approval_check as ac
import record_owner_confirmation as rc

CARD = "W-20261021-901"
HEAD = "abcdef12"


def _file(tmp_path: Path, quote: str) -> Path:
    f = tmp_path / "owner_confirmations.md"
    f.write_text(rc.row("0501", CARD, quote, "", head=HEAD, source="مباشر"), encoding="utf-8")
    return f


def test_refusal_line_is_not_approval(tmp_path):
    f = _file(tmp_path, "لا، ارفضه ولا تدمج")
    ev = ac.confirmations_evidence(CARD, HEAD, enforce=True, path=f)
    assert [st for _, st in ev] == ["rejected"]


def test_approving_rows_exclude_refusal(tmp_path, monkeypatch):
    f = _file(tmp_path, "لا، ارفضه ولا تدمج")
    monkeypatch.setattr(ac, "ROOT", f.parent)
    assert ac._approving_rows(CARD, HEAD) == []


def test_approval_line_still_ok(tmp_path):
    for q in ("اعتمد", "ادفع", "نعم أوقف الشرط", "لا مانع", "لا تعديل في الانتاج نجح التوليد ادفع اعتمد"):
        ev = ac.confirmations_evidence(CARD, HEAD, enforce=True, path=_file(tmp_path, q))
        assert [st for _, st in ev] == ["ok"], q


def test_refusal_variants():
    for q in ("لا", "لا تدمج قبل المعاينة", "لا تعتمد", "ارفضه", "مرفوض", "غير موافق", "لا، لا تعتمد"):
        assert ac.quote_refusal(q), q


def test_question_context_in_parentheses_is_ignored():
    assert not ac.quote_refusal("اعتمد (ردّاً على: هل ترفض هذا الرأس؟)")


def test_stale_head_stays_stale_even_if_refusal(tmp_path):
    ev = ac.confirmations_evidence(CARD, "99999999", enforce=True, path=_file(tmp_path, "لا، ارفضه"))
    assert [st for _, st in ev] == ["stale"]


def test_real_confirmations_file_has_no_false_refusal():
    rows = [ln for ln in (ac.ROOT / "owner_confirmations.md").read_text(encoding="utf-8").splitlines() if ln.startswith("|")]
    assert [ln for ln in rows if ac.quote_refusal(ac.row_quote(ln)) and "رفض" not in ln and "ارفض" not in ln] == []
