#!/usr/bin/env python3
"""قياسُ نظافة ذاكرة المشروع — قراءةٌ فقط (D-160م).

    python memory_stale.py [--memory DIR] [--json] [--list]

يقيس: حجمَ فهرس MEMORY.md (سطوراً وKB) مقابل السقف (120 سطراً و18KB)، ونسبةَ الملفّات المفهرسة، والذكرياتِ **المسمِّيةَ مساراً مفقوداً**
(مسارٌ بين backticks يبدأ بمجلّد منصّةٍ معروف ولا يوجد على origin/main ولا في مستودع المايسترو) — حدٌّ أدنى للمضلِّل: لا يلتقط دالّةً ولا رايةً ولا حقلاً.
لا يكتب ولا ينقل ولا يحذف؛ الأرشفةُ تقترحها 0103 وتنفّذ بنقلٍ بأمرِ المالك.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MEMORY = Path("C:/Users/mesue/.claude/projects/D--shschool-mvp/memory")
MAESTRO = Path(__file__).resolve().parent.parent
REPO = "D:/shschool_mvp"
INDEX_MAX_LINES, INDEX_MAX_KB = 120, 18
PATH = re.compile(r"`((?:tools|docs|core|operations|api|tests|templates|static|scripts|governance|quality|student_affairs|staff_affairs)/[\w./\-]+\.(?:py|md|html|js|css|json|sh|yml))`")
LINK = re.compile(r"\(([^)]+\.md)\)")


def memory_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.md")]


def unindexed(root: Path, files: list[Path]) -> list[str]:
    idx = (root / "MEMORY.md").read_text(encoding="utf-8", errors="replace")
    linked = {os.path.basename(x) for x in LINK.findall(idx)}
    return sorted({p.name for p in files if p.name != "MEMORY.md" and p.name not in linked})


def tracked_paths(repo: str = REPO) -> set[str]:
    p = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", "origin/main"], capture_output=True, text=True, encoding="utf-8")
    return set(p.stdout.split()) if p.returncode == 0 else set()


def maestro_paths(root: Path = MAESTRO) -> set[str]:
    out = set()
    for r, _, fs in os.walk(root):
        if ".git" in r:
            continue
        for f in fs:
            out.add(os.path.relpath(os.path.join(r, f), root).replace(os.sep, "/"))
    return out


def missing_paths(files: list[Path], existing: set[str]) -> dict[str, list[str]]:
    bad: dict[str, list[str]] = {}
    for p in files:
        for m in set(PATH.findall(p.read_text(encoding="utf-8", errors="replace"))):
            if m not in existing:
                bad.setdefault(p.name, []).append(m)
    return bad


def measure(root: Path = MEMORY, existing: set[str] | None = None) -> dict:
    files = memory_files(root)
    idx = root / "MEMORY.md"
    size_kb = idx.stat().st_size / 1024
    lines = len(idx.read_text(encoding="utf-8", errors="replace").splitlines())
    existing = existing if existing is not None else (tracked_paths() | maestro_paths())
    un = unindexed(root, files)
    bad = missing_paths(files, existing)
    return {
        "files": len(files), "index_kb": round(size_kb, 1), "index_lines": lines,
        "index_over_cap": size_kb > INDEX_MAX_KB or lines > INDEX_MAX_LINES,
        "unindexed": len(un), "indexed_ratio": round(1 - len(un) / max(1, len(files) - 1), 2),
        "memories_naming_missing_path": len(bad), "missing_paths": sum(len(v) for v in bad.values()),
        "_bad": bad, "_unindexed": un,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--memory", default=str(MEMORY))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    m = measure(Path(a.memory))
    pub = {k: v for k, v in m.items() if not k.startswith("_")}
    if a.json:
        print(json.dumps(pub, ensure_ascii=False, indent=2))
        return 0
    print(f"الفهرس: {m['index_kb']}KB / {m['index_lines']} سطراً (السقف {INDEX_MAX_KB}KB و{INDEX_MAX_LINES} سطراً) — {'فوق السقف' if m['index_over_cap'] else 'ضمن السقف'}")
    print(f"ملفّات الذاكرة {m['files']}؛ غيرُ المفهرسة {m['unindexed']} (نسبةُ المفهرس {m['indexed_ratio']})")
    print(f"ذكرياتٌ تسمّي مساراً مفقوداً: {m['memories_naming_missing_path']} ({m['missing_paths']} مساراً) — حدٌّ أدنى للمضلِّل")
    if a.list:
        for f, v in sorted(m["_bad"].items()):
            print(f"  {f}: {', '.join(v[:3])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
