#!/usr/bin/env python3
"""جردُ التنظيف: أشجارُ العمل والحاويات والصور — **عرضٌ فقط** (0102، 2026-10-08).

    python housekeeping.py

لا يحذف شيئاً. الحذفُ بأمر المالك وبعد عرض قائمة الأسماء (القاعدة: «بعد الأحد، بالأسماء أوّلاً»).
"""
from __future__ import annotations

import subprocess

REPO = "D:/shschool_mvp"


def sh(*c, cwd=None):
    r = subprocess.run(c, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    return r.stdout.strip()


def main():
    print("== أشجار العمل")
    n = 0
    for blk in sh("git", "worktree", "list", "--porcelain", cwd=REPO).split("\n\n"):
        p = dict(line.split(" ", 1) for line in blk.splitlines() if " " in line)
        path, br = p.get("worktree"), p.get("branch", "").replace("refs/heads/", "")
        if not path or "worktrees" not in path:
            continue
        n += 1
        dirty = bool(sh("git", "status", "--porcelain", cwd=path))
        pushed = bool(br) and bool(sh("git", "branch", "-r", "--contains", p.get("HEAD", "HEAD"), cwd=REPO))
        print(f"  {path.split('/')[-1]:32} {br[-34:]:34} {'متّسخة' if dirty else 'نظيفة'} {'مدفوعة' if pushed else 'محلّيّة-فقط'}")
    print(f"  المجموع {n}")
    print("== الحاويات")
    print(sh("docker", "ps", "-a", "--format", "  {{.Names}}\t{{.Status}}\t{{.Image}}"))
    print("== القرص")
    print(sh("docker", "system", "df"))
    dang = sh("docker", "images", "-f", "dangling=true", "-q")
    print("  صورٌ بلا وسم:", len(dang.split()) if dang else 0)


main()
