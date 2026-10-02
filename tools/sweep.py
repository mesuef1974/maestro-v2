#!/usr/bin/env python3
"""الجولةُ الثابتة للمايسترو — ثلاثةُ أسئلةٍ بأمرٍ واحد، قراءةٌ فقط (D-107م).

يُشغَّل عند كلّ «تابع مع الباقي» بدل ردٍّ بلا تقدّم:
  1) طلباتُ الدمج المفتوحة: حالتُها وسطرُ الاعتماد والدمجُ الآليّ والتعارض.
  2) بطاقاتُ P0/P1 التي حان بدؤها وما زالت captured أو routed (عالقة).
  3) بطاقاتٌ معتمَدةٌ أو مدفوعةٌ لم تُدمج/تُنشر بعد.

    python sweep.py [--hours 6]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOHA = timezone(timedelta(hours=3))
LINE = re.compile(r"^(W-\d{8}-\d{3})\s+(P\d)\s+بدء=(\S+)\s+(\w+)\s+(\S+)\s+(.*)$")


def run(cmd: list[str], cwd: str | None = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout or ""


def prs() -> None:
    out = run(["gh", "pr", "list", "--state", "open", "--json", "number,title,mergeable,isDraft,body,autoMergeRequest"],
              cwd="D:/shschool_mvp")
    data = json.loads(out or "[]")
    print(f"== 1) طلباتُ دمجٍ مفتوحة ({len(data)}) ==")
    for d in data:
        body = d.get("body") or ""
        has_line = any("اعتُمد" in ln or "اعتمد المالك" in ln for ln in body.splitlines())
        flags = []
        if d["isDraft"]:
            flags.append("مسوّدة")
        if d["mergeable"] == "CONFLICTING":
            flags.append("تعارضٌ!")
        if not has_line and not d["isDraft"]:
            flags.append("بلا سطر اعتماد")
        if not d.get("autoMergeRequest") and has_line and not d["isDraft"]:
            flags.append("دمجٌ آليّ غيرُ ظاهر (تحقّق بـground_truth pr)")
        print(f"  #{d['number']} {d['mergeable']:<11} {' | '.join(flags) or 'سليم'} — {d['title'][:55]}")


def cards(hours: int) -> None:
    out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "list"])
    now = datetime.now(DOHA)
    stuck, unpublished = [], []
    for ln in out.splitlines():
        m = LINE.match(ln.strip())
        if not m:
            continue
        cid, pr, start, state, _, text = m.groups()
        try:
            started = datetime.fromisoformat(start).replace(tzinfo=DOHA)
        except ValueError:
            continue
        age_h = (now - started).total_seconds() / 3600
        if pr in ("P0", "P1") and state in ("captured", "routed") and age_h >= hours:
            stuck.append((pr, round(age_h), cid, state, text[:60]))
        if state in ("approved", "pushed", "merged"):
            unpublished.append((cid, state, text[:55]))
    print(f"\n== 2) P0/P1 عالقةٌ بعد بدئها بأكثر من {hours} ساعات ({len(stuck)}) ==")
    for pr, age, cid, state, text in sorted(stuck):
        print(f"  {pr} منذ {age} س {cid} [{state}] — {text}")
    print(f"\n== 3) معتمَدةٌ أو مدفوعةٌ أو مدموجةٌ لم تُنشر ({len(unpublished)}) ==")
    for cid, state, text in unpublished:
        print(f"  {cid} [{state}] — {text}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=int, default=6)
    a = ap.parse_args()
    prs()
    cards(a.hours)


if __name__ == "__main__":
    main()
