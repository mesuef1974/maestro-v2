#!/usr/bin/env python3
"""تسجيلُ شجرة جلسةٍ باسمها في `projects/schoolos/session_names.json` — يقرؤه SessionStart hook (tools/session_identity.py) لتعرف الجلسةُ هويّتَها.

    python session_register.py <اسم-الشجرة> "<0409 · الاسم>"     # يضيف أو يصحّح
    python session_register.py <اسم-الشجرة> --remove              # شجرةُ جلسةٍ مؤرشفة لا تُسمّي أحداً بعدها

سببُها (واقعة 2026-10-04): شجرةُ جلسةٍ مؤرشفة (كانت 0701) أُعيد استعمالها لجلسةٍ جديدة (0409) فسمّاها الـhook 0701 خطأً. يُشغَّلها المايسترو بعد فتح كلّ جلسةٍ
وعند أرشفتها. الاسمُ يبدأ بأربع خانات (رقم الجلسة) ثمّ « · ».
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NAMES = Path(__file__).resolve().parent.parent / "projects" / "schoolos" / "session_names.json"
NAME_RE = re.compile(r"^\d{4} · \S")


def update(names: dict, tree: str, title: str | None) -> dict:
    out = dict(names)
    if title is None:
        out.pop(tree, None)
        return out
    if not NAME_RE.match(title):
        raise ValueError("الاسمُ يبدأ بأربع خانات ثمّ « · » ثمّ الوصف، مثل «0409 · إدارة: امتثال الأدوار (W-020)»")
    out[tree] = title
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tree")
    ap.add_argument("title", nargs="?")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--file", default=str(NAMES))
    a = ap.parse_args(argv)
    path = Path(a.file)
    names = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not a.remove and not a.title:
        ap.error("اسمُ الجلسة مطلوب (أو --remove)")
    try:
        new = update(names, a.tree, None if a.remove else a.title)
    except ValueError as e:
        print(str(e))
        return 1
    path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(("أُزيلت الشجرة " if a.remove else "سُجِّلت الشجرة ") + a.tree + ("" if a.remove else " ← " + a.title))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
