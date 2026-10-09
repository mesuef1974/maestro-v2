#!/usr/bin/env python3
"""دليلُ عناوين الجلسات: رقمُ الجلسة ← معرّفُها `local_<uuid>` الحيّ (0102، 2026-10-09).

    python session_directory.py            # كلُّ الجلسات غير المؤرشفة: رقم ومعرّف واسم
    python session_directory.py 0101       # معرّفُ جلسةٍ واحدة (يُطبع المعرّفُ وحده)
    python session_directory.py --json     # للسكربتات

السبب (قياس 2026-10-09): الإرسال بالاسم يصل الصندوقَ ولا يوقظ جلسةً خاملة، والإرسال بالمعرّف `local_<uuid>` يوقظها؛
والمعرّفُ لا يُعرف إلا من `list_sessions` أو من `from` في رسالةٍ واردة، فكانت الجلساتُ تضلّ وتُوجَّه يدوياً.
المصدر: ملفّاتُ جلسات تطبيق Claude على القرص (sessionId وtitle وisArchived وlastActivityAt). قراءةٌ فقط.
عند تكرار الرقم (جلسةٌ أُعيد تشغيلُها) يُختار الأحدثُ نشاطاً.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

BASE = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code-sessions"
NUM = re.compile(r"^\s*(\d{4})\b")


def entries() -> dict[str, dict]:
    best: dict[str, dict] = {}
    for f in BASE.glob("*/*/local_*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m = NUM.match(str(d.get("title", "")))
        if not m or d.get("isArchived") or not str(d.get("worktreePath", d.get("cwd", ""))).replace("\\", "/").count("shschool_mvp"):
            continue
        num, act = m.group(1), int(d.get("lastActivityAt") or 0)
        if num not in best or act > best[num]["at"]:
            best[num] = {"id": d["sessionId"], "title": d["title"], "at": act}
    return dict(sorted(best.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("number", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    e = entries()
    if a.number:
        if a.number not in e:
            print(f"لا جلسةَ حيّةً بالرقم {a.number}", file=sys.stderr)
            return 1
        print(e[a.number]["id"])
    elif a.json:
        print(json.dumps({k: v["id"] for k, v in e.items()}, ensure_ascii=False))
    else:
        for k, v in e.items():
            print(f"{k}  {v['id']}  {v['title'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
