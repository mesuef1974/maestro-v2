"""اختبار prune_workspace (W-20261014-001): العرض لا يحذف، و--apply يحترم الشروط الآمنة."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import prune_workspace as pw  # noqa: E402

OLD = time.time() - 10 * 86400


def mk(root: Path, card: str, head: str, files: dict, mtime: float):
    d = root / card / head
    d.mkdir(parents=True)
    for name, size in files.items():
        (d / name).write_bytes(b"x" * size)
    os.utime(d, (mtime, mtime))
    return d


def run(tmp_path, states, apply=False):
    return pw.run(apply, evidence=tmp_path / "ev", tmp=tmp_path / "tmp", states=states, worktrees=False, containers=False, session_dbs=False)


def test_dry_run_does_not_delete(tmp_path):
    mk(tmp_path / "ev", "W-1", "aaa", {"a.png": 10, "manifest.json": 5}, OLD)
    mk(tmp_path / "ev", "W-1", "bbb", {"b.png": 10}, OLD + 100)
    res = run(tmp_path, {"W-1": "published"})
    assert res["mode"] == "dry-run" and res["evidence"]["files"] >= 1
    assert (tmp_path / "ev/W-1/aaa/a.png").exists()


def test_apply_keeps_manifest_and_text_and_unknown_and_unpublished(tmp_path):
    ev = tmp_path / "ev"
    mk(ev, "W-1", "aaa", {"a.png": 10, "manifest.json": 5, "n.md": 3}, OLD)
    mk(ev, "W-1", "bbb", {"b.png": 10}, OLD + 100)
    mk(ev, "W-2", "ccc", {"c.png": 10}, OLD)  # مجهولة
    mk(ev, "W-3", "ddd", {"d.png": 10}, OLD)  # معتمدة لم تُنشر
    run(tmp_path, {"W-1": "published", "W-3": "approved"}, apply=True)
    assert not (ev / "W-1/aaa/a.png").exists()
    assert (ev / "W-1/aaa/manifest.json").exists() and (ev / "W-1/aaa/n.md").exists()
    assert (ev / "W-2/ccc/c.png").exists() and (ev / "W-3/ddd/d.png").exists()


def test_merged_not_yet_published_is_kept(tmp_path):
    ev = tmp_path / "ev"
    mk(ev, "W-9", "aaa", {"a.png": 10}, OLD)
    run(tmp_path, {"W-9": "merged"}, apply=True)
    assert (ev / "W-9/aaa/a.png").exists()


def test_latest_head_grace_3_days(tmp_path):
    ev = tmp_path / "ev"
    mk(ev, "W-1", "new", {"n.png": 10}, time.time() - 3600)
    run(tmp_path, {"W-1": "published"}, apply=True)
    assert (ev / "W-1/new/n.png").exists()


def test_symlink_and_outside_root_never_deleted(tmp_path):
    ev = tmp_path / "ev"
    d = mk(ev, "W-1", "aaa", {"a.png": 10}, OLD)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"y")
    try:
        os.symlink(outside, d / "link.png")
    except (OSError, NotImplementedError):
        return
    run(tmp_path, {"W-1": "published"}, apply=True)
    assert outside.exists()


def test_tmp_reports_cleared_on_apply_only(tmp_path):
    (tmp_path / "tmp").mkdir()
    (tmp_path / "tmp/r.txt").write_bytes(b"z" * 4)
    run(tmp_path, {})
    assert (tmp_path / "tmp/r.txt").exists()
    pw.LOG = tmp_path / "log.jsonl"
    run(tmp_path, {}, apply=True)
    assert not (tmp_path / "tmp/r.txt").exists() and pw.LOG.exists()


def test_tree_slug_matches_session_db_script():
    assert pw.tree_slug("D:/x/.claude/worktrees/Determined-Golick-5f772e") == "determined_golick_5f772e"
    long = "a" * 39 + "-bcd"  # الحرفُ الأربعون شرطةٌ سفليّة ⇒ تُقصّ كما في `${slug%_}`
    assert pw.tree_slug("D:/x/" + long) == "a" * 39


def test_classify_drops_only_orphans_never_protected_or_connected():
    rows = [
        ("ss_live_tree", 100, 0),
        ("test_ss_live_tree", 50, 0),
        ("ss_gone_tree", 200, 0),
        ("test_ss_gone_tree", 70, 0),
        ("ss_gone_but_connected", 300, 2),
        ("ss_main_preview", 1, 0),
        ("ss_main_preview_g7", 9, 0),
        ("ss_integration_preview", 1, 0),
        ("ss_base_f1f4c06_preview", 1, 0),
        ("shschool_db", 1, 1),
        ("postgres", 1, 1),
        ("template0", 1, 0),
        ("unrelated_db", 1, 0),
    ]
    r = pw.classify_session_dbs(rows, {"live_tree"})
    assert sorted(o["name"] for o in r["orphans"]) == ["ss_gone_tree", "test_ss_gone_tree"]
    assert r["bytes"] == 270 and r["kept_live"] == 2
    assert r["kept_connected"] == ["ss_gone_but_connected"]
    assert r["preview_gens"] == {"count": 1, "bytes": 9}


def test_drop_refuses_protected_and_counts_only_dropped(monkeypatch):
    calls = []
    monkeypatch.setattr(pw, "_psql", lambda sql, container=None: calls.append(sql) or [])
    freed = pw.drop_session_dbs([{"name": "ss_main_preview", "bytes": 5}, {"name": "ss_gone", "bytes": 7}, {"name": 'ss_x"; drop', "bytes": 9}])
    assert freed == 7 and calls == ['DROP DATABASE "ss_gone"']


def test_scan_fails_closed_when_docker_or_git_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no docker")
    monkeypatch.setattr(pw, "_psql", boom)
    r = pw.scan_session_dbs()
    assert r["orphans"] == [] and r["error"] == "no docker"
