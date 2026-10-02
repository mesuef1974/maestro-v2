#!/usr/bin/env python3
"""أين تسأل الجلساتُ المالكَ؟ — جردٌ من سجلّات الجلسات (AskUserQuestion + عباراتُ «هل أرسل/أبلّغ/أدفع/أعمّم…» في نصّ الجلسة).

    python owner_asks_audit.py [--hours 24] [--show 3]

قراءةٌ فقط لسجلّات الجلسات المحلّيّة؛ يطبع لكلّ جلسةٍ: عددَ أسئلة AskUserQuestion، وأمثلةً قصيرة، وعددَ مرّات سؤال المالك في النصّ
عمّا يجب أن يكون آليّاً (إرسالٌ وإبلاغٌ ودفعٌ وتعميمٌ ومتابعة). المبدأ (أمر المالك 2026-10-02): تبادلُ الرسائل والإبلاغُ بالإيداعات آليٌّ؛
لا يُسأل المالكُ عمّا يحسمه الفلو أو التحقّقُ.
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
# عباراتُ سؤالٍ عن فعلٍ يجب أن يكون آليّاً (إرسال/إبلاغ/تعميم/دفع/متابعة)
AUTO_Q = re.compile(r"(هل|أ|أتريد|تريدني|أتأمر|تأمر)[^؟\n]{0,40}(أرسل|أُرسل|أبلّغ|أبلغ|أعمّم|أعمم|أدفع|أتابع|أراسل|أُبلّغ)[^؟\n]{0,80}؟")


def _after(ts: str | None, cutoff: float) -> bool:
    if not cutoff or not ts:
        return True
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() >= cutoff
    except ValueError:
        return True


def scan(path: Path, cutoff: float) -> dict:
    title, asks, auto_q = "", [], []
    for line in path.open(encoding="utf-8", errors="replace"):
        if "AskUserQuestion" not in line and "custom-title" not in line and "؟" not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "custom-title":
            title = o.get("customTitle", title)
        elif o.get("type") == "assistant" and _after(o.get("timestamp"), cutoff):
            for it in (o.get("message", {}).get("content") or []):
                if not isinstance(it, dict):
                    continue
                if it.get("type") == "tool_use" and it.get("name") == "AskUserQuestion":
                    for q in (it.get("input") or {}).get("questions", []):
                        asks.append(str(q.get("question", ""))[:150])
                elif it.get("type") == "text":
                    for m in AUTO_Q.finditer(it.get("text", "")):
                        auto_q.append(m.group(0)[:120])
    return {"title": title or path.stem[:8], "asks": asks, "auto_q": auto_q}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--show", type=int, default=3)
    a = ap.parse_args()
    cutoff = time.time() - a.hours * 3600
    rows = []
    for d in sorted(PROJECTS.glob("D--shschool-mvp*")):
        for f in d.glob("*.jsonl"):
            if f.stat().st_mtime >= cutoff:
                r = scan(f, cutoff)
                if r["asks"] or r["auto_q"]:
                    rows.append(r)
    rows.sort(key=lambda r: -(len(r["asks"]) + len(r["auto_q"])))
    print(f"{'الجلسة':<44}{'أسئلةُ AskUserQuestion':>22}{'سؤالٌ نصّيٌّ عن فعلٍ آليّ':>26}")
    for r in rows:
        print(f"{r['title'][:42]:<44}{len(r['asks']):>22}{len(r['auto_q']):>26}")
        for q in r["asks"][: a.show]:
            print(f"    ؟ {q}")
        for q in r["auto_q"][: a.show]:
            print(f"    ⚠ {q}")
    print(f"\nالمجموع: {sum(len(r['asks']) for r in rows)} سؤالاً مباشراً، {sum(len(r['auto_q']) for r in rows)} سؤالاً نصّيّاً عن فعلٍ آليّ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
