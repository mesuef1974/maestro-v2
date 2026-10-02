#!/usr/bin/env python3
"""فحصٌ آليٌّ لقاعدة «العربيّةُ وحدَها»: أوصافُ الأدوات وملخّصاتُ SendMessage ذاتُ الحروف اللاتينيّة الغالبة، لكلّ جلسةٍ مشروع المدرسة.

    python lang_audit.py [--hours 24] [--ratio 0.6]

قراءةٌ فقط لسجلّات الجلسات المحلّيّة (~/.claude/projects/D--shschool-mvp*)؛ يطبع عدّاً لكلّ جلسةٍ ومثالاً قصيراً واحداً (≤60 حرفاً)،
ولا يكتب شيئاً. يخرج برمز 1 إن وُجد خرق. D-102م: التذكيرُ لا يكفي لأنّ المخالفةَ في حقلٍ لا يراه أحد.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
TOOLS = {"Bash", "PowerShell", "Agent", "Monitor", "SendMessage", "Glob", "Grep", "Read", "Edit", "Write"}
FIELDS = ("description", "summary")
LATIN = re.compile(r"[A-Za-z]")
ARABIC = re.compile(r"[؀-ۿ]")


def _after(ts: str | None, cutoff: float) -> bool:
    if not cutoff or not ts:
        return True
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() >= cutoff
    except ValueError:
        return True


IDENT_A = re.compile(r"[A-Za-z0-9_./\\#~:-]*[0-9_/\\#~][A-Za-z0-9_./\\#~:-]*")
IDENT_B = re.compile(r"[A-Za-z0-9]+(?:[.:-][A-Za-z0-9]+)+")


def latin_dominant(text: str, ratio: float) -> bool:
    text = IDENT_B.sub(" ", IDENT_A.sub(" ", text))  # المعرّفاتُ والمساراتُ ورموزُ الطلبات ليست «إنجليزيّةً»
    lat, ara = len(LATIN.findall(text)), len(ARABIC.findall(text))
    letters = lat + ara
    return letters >= 12 and lat / letters > ratio


def scan(path: Path, ratio: float, cutoff: float = 0.0) -> tuple[str, int, int, str]:
    title, checked, bad, sample = "", 0, 0, ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "custom-title":
            title = o.get("customTitle", title)
        elif o.get("type") == "assistant" and _after(o.get("timestamp"), cutoff):
            for it in (o.get("message", {}).get("content") or []):
                if isinstance(it, dict) and it.get("type") == "tool_use" and it.get("name") in TOOLS:
                    for f in FIELDS:
                        v = (it.get("input") or {}).get(f)
                        if isinstance(v, str) and v.strip():
                            checked += 1
                            if latin_dominant(v, ratio):
                                bad += 1
                                sample = sample or v[:60]
    return title or path.stem[:8], checked, bad, sample


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--ratio", type=float, default=0.6)
    a = ap.parse_args()
    cutoff = time.time() - a.hours * 3600
    total_bad = 0
    print(f"{'الجلسة':<44}{'مفحوص':>7}{'مخالف':>7}  مثال")
    for d in sorted(PROJECTS.glob("D--shschool-mvp*")):
        for f in d.glob("*.jsonl"):
            if f.stat().st_mtime < cutoff:
                continue
            title, checked, bad, sample = scan(f, a.ratio, cutoff)
            if checked:
                total_bad += bad
                print(f"{title[:42]:<44}{checked:>7}{bad:>7}  {sample}")
    print(f"\nالمجموع المخالف: {total_bad}")
    return 1 if total_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
