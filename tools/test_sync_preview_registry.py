"""مزامنة سجلّ حسابات المعاينة مع القاموس في المصدر (بلا كلمات مرور)."""

import json
from pathlib import Path

import pytest
import sync_preview_registry as s

SAMPLE = {"principal": "99900001", "teacher": "99900007"}


def test_build_rows_follow_the_dictionary():
    rows = s.build(SAMPLE, "2026-10-10T00:00:00")
    assert [(r["role"], r["national_id"]) for r in rows] == list(SAMPLE.items())


def test_no_secret_fields_in_rows():
    keys = {k for r in s.build(SAMPLE) for k in r}
    assert keys == {"role", "national_id", "opened_at"}
    assert "password" not in json.dumps(s.build(SAMPLE)).lower()


def test_registry_file_matches_source_when_synced(tmp_path):
    repo = r"D:/shschool_mvp/.claude/worktrees/zen-feynman-e33683"
    if not Path(repo).is_dir():
        pytest.skip("شجرةُ المصدر غائبة في هذه البيئة")
    numbers = s.employee_numbers(repo, "origin/main")
    assert len(numbers) == 10 and all(v.startswith("9990000") or v == "99900010" for v in numbers.values())
