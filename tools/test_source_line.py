"""سطرُ المصدر المقروء في approval_check وground_truth: المسارُ المطلقُ وتاريخُ آخر تعديل."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import approval_check  # noqa: E402
import ground_truth  # noqa: E402


def test_source_line_names_absolute_path_and_mtime():
    for mod in (approval_check, ground_truth):
        line = mod.source_line()
        assert "المصدر المقروء:" in line
        assert str(mod.ROOT / "owner_confirmations.md") in line


def test_source_line_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(approval_check, "ROOT", tmp_path)
    assert "غير موجود" in approval_check.source_line()
