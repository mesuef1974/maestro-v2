#!/usr/bin/env python3
"""هل تصل الرسائلُ إلى الجلسات وهل تعمل؟ — من إيصالات تطبيق Claude على القرص (0102، 2026-10-09). قراءةٌ فقط.

    python session_reachability.py [--hours 12]

لكلّ جلسةٍ حيّةٍ (غير مؤرشفة): وضعُ الأذونات، رسائلُ واردةٌ محجوزة (peerInbound)، خمولُها منذ آخر نشاط،
وإيصالاتُ كلِّ ما أُرسل إليها خلال المدّة: كم وصل (delivered) وكم لم يصل (undelivered) وكم قُرئ وزمنُ القراءة.
الحكمُ: ✘ لا تصل (آخرُ إيصالٍ undelivered أو محجوزٌ وارد)، ⚠ لم تُقرأ رسائلُها، ✔ تصل وتقرأ، · لا إيصالَ في المدّة.
لا يرسل شيئاً: لا اختبارَ بالإرسال فيه (قاعدةُ منع الرشق)؛ يُختبر المشتبهُ فيه وحده بإرسالٍ يدويّ.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

BASE = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code-sessions"
NUM = re.compile(r"^\s*(\d{4})\b")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=12)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    now = time.time() * 1000
    live: dict[str, dict] = {}
    allf = []
    for f in glob.glob(str(BASE / "*" / "*" / "local_*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        allf.append(d)
        m = NUM.match(str(d.get("title", "")))
        if m and not d.get("isArchived") and "shschool_mvp" in str(d.get("cwd", "")).replace("\\", "/"):
            n = m.group(1)
            if n not in live or int(d.get("lastActivityAt") or 0) > int(live[n].get("lastActivityAt") or 0):
                live[n] = d
    since = now - a.hours * 3600000
    by_target: dict[str, list] = {}
    for d in allf:
        for r in d.get("peerReceipts") or []:
            if r.get("sentAt", 0) >= since:
                by_target.setdefault(r.get("targetSessionId"), []).append(r)
    for n in sorted(live):
        d = live[n]
        recs = sorted(by_target.get(d["sessionId"], []), key=lambda r: r["sentAt"])
        und = sum(1 for r in recs if r.get("delivery") != "delivered")
        read = [r for r in recs if r.get("readAt")]
        lag = round(sum(r["readAt"] - r["sentAt"] for r in read) / len(read) / 60000, 1) if read else None
        held = d.get("peerInbound")
        held_n = len(held) if isinstance(held, list) else 0
        idle = round((now - int(d.get("lastActivityAt") or 0)) / 60000)
        if held_n or (recs and recs[-1].get("delivery") != "delivered"):
            mark = "✘"
        elif recs and not read:
            mark = "⚠"
        elif recs:
            mark = "✔"
        else:
            mark = "·"
        print(f"{mark} {n} وضع={d.get('permissionMode')} خمول={idle}د محجوز={held_n} إيصالات={len(recs)} لم تصل={und} قُرئ={len(read)}"
              + (f" متوسّط القراءة={lag}د" if lag is not None else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
