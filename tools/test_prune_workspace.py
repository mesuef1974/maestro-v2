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
    return pw.run(apply, evidence=tmp_path / "ev", tmp=tmp_path / "tmp", states=states, worktrees=False, containers=False)


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
