"""اختباراتُ machine_ops (W-20261017-022 المرحلة 1): قراءةٌ فقط، والأصلُ لا يتغيّر، ولا بيانات شخصيّة في التقرير."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from machine_ops import history, report, snapshot  # noqa: E402

PS = "app|running|Up 2 hours\nshschool-dev-db|running|Up\nold|exited|Exited (0)\nidle|running|Up\n"
STATS = "app|12.5%|300MiB / 4GiB\nshschool-dev-db|0.1%|1GiB / 4GiB\nidle|0.0%|40MiB / 4GiB\n"


def test_parse_containers_classifies():
    kinds = {c["name"]: c["kind"] for c in snapshot.parse_containers(PS, STATS)}
    assert kinds == {"app": "حيّة", "shschool-dev-db": "محمية", "old": "متوقّفة", "idle": "خاملة"}


def test_parse_containers_unavailable_is_none():
    assert snapshot.parse_containers(None, None) is None


def test_non_whitelisted_command_refused():
    with pytest.raises(PermissionError):
        snapshot.run_allowed(("docker", "rm", "-f", "x"))


def test_parse_wsl_memory():
    assert snapshot.parse_wsl_memory('"vmmemWSL.exe","1","Services","0","2,097,152 K"\n') == 2.0
    assert snapshot.parse_wsl_memory("INFO: none") is None


def test_report_marks_unmeasured_and_delta():
    a = {"label": "قبل", "host": {"commit_pct": 80.0}, "wsl_memory_gb": None, "containers": None, "unmeasured": ["containers"]}
    b = {"label": "بعد", "host": {"commit_pct": 70.0}, "wsl_memory_gb": None, "containers": [], "unmeasured": []}
    text = report.render(a, b)
    assert "-10%" in text and snapshot.UNMEASURED in text


def test_history_leaves_original_untouched(tmp_path):
    db = tmp_path / "monitor.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE samples (ts INT, commit_pct REAL, ram_pct REAL, avail_gb REAL, disk_free_gb REAL, claude INT, shells INT)")
    con.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?)", [(100, 60.0, 50.0, 8.0, 100.0, 3, 2), (200, 90.0, 70.0, 2.0, 99.0, 4, 2)])
    con.commit()
    before = history.fingerprint(db)
    rows, fp = history.read_samples(db, 0, 1000)
    con.close()
    assert fp["unchanged"] and len(rows) == 2
    s = history.summarize(rows)
    assert s["commit_max"] == 90.0 and s["avail_min_gb"] == 2.0
    assert before == fp["before"]


def test_snapshot_json_has_no_personal_data():
    snap = snapshot.take("اختبار")
    text = json.dumps(snap, ensure_ascii=False)
    for needle in ("C:\\Users", "C:/Users", "mesue", "@"):
        assert needle not in text
