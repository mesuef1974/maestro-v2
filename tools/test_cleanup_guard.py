"""اختبار cleanup_guard (W-20261014-001)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cleanup_guard as cg  # noqa: E402

CLEAN = {"evidence": {"bytes": 0}, "tmp": {"files": 0}, "worktrees": {"candidates": []}}


def test_clean_has_no_findings():
    assert cg.findings(CLEAN) == []


def test_each_threshold_reported():
    dirty = {"evidence": {"bytes": 200_000_000}, "tmp": {"files": 2}, "worktrees": {"candidates": [{"path": "x"}]}}
    assert len(cg.findings(dirty)) == 3
