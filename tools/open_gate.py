#!/usr/bin/env python3
"""بوّابةُ فتح الجلسات المرنة — قراءةٌ فقط؛ تقول «أسنِد» أو «افتح الآن» أو «انتظر» ولا تفتح شيئاً (تجربةٌ باتّفاق المالك 09-29).

الترتيب: مانعُ التسمية/السعة ← جلسةٌ حيّةٌ صالحةٌ للإسناد بالوسم نفسِه (دائماً قبل الفتح، حتى P0) ← الذاكرة.

    python open_gate.py --tag إدارة --task "تسريبُ بيانات PII" --code W-028 --priority P0
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MAESTRO = Path(os.environ.get("MAESTRO_HOME", "C:/Users/mesue/delivery_manager_work"))
sys.path.insert(0, str(MAESTRO / "tools"))
sys.path.insert(0, str(MAESTRO / "skills" / "maestro-spawn" / "scripts"))
import spawn_preflight as sp  # noqa: E402
import watch_once as wo  # noqa: E402


def assignable_with_tag(sessions: list[dict], tag: str, live_titles: set[str] | None = None) -> list[dict]:
    """جلساتُ 04 الصالحةُ للإسناد بوسمٍ واحد — الوسمُ يُقرأ من الاسم «04SS · <وسم>: <مهمّة>»؛ وتُستبعد المؤرشفةُ (ليست في members)."""
    out = []
    for s in sessions:
        name = s.get("session", "")
        if live_titles is not None and name not in live_titles:
            continue
        head, _, rest = name.partition(" · ")
        if head[:2] == "04" and rest.startswith(f"{tag}:") and s.get("assignable"):
            out.append(s)
    return out


def decide(pre: dict, assignable: list[dict], band: str | None, priority: str | None) -> dict:
    if not pre["ok"]:
        return {"verdict": "لا تفتح", "why": pre["blockers"]}
    if assignable:
        best = min(assignable, key=lambda s: (s.get("wip", 0), s.get("context_mb", 0)))
        return {"verdict": "أسنِد", "why": [f"جلسةٌ حيّةٌ صالحةٌ بالوسم نفسِه: {best['session']} — الإسنادُ قبل الفتح دائماً"]}
    if band in ("red", "critical"):
        if priority == "P0":
            return {"verdict": "افتح بحذر", "why": [
                f"الذاكرةُ {band} ولا جلسةَ صالحةٌ للإسناد؛ P0 وحدَه يمرّ: اطلب من أخفّ جلسةٍ خاملةٍ إيقافَ حاويتها (لا أوقفها بيدي) ثمّ أعِد القياس قبل الفتح"]}
        return {"verdict": "انتظر", "why": [f"الذاكرةُ {band} ولا جلسةَ صالحةٌ للإسناد؛ يبقى الطلبُ في الطابور حتى ترتاح الذاكرة أو تتحرّر جلسة"]}
    return {"verdict": "افتح الآن", "why": ["لا جلسةَ صالحةٌ للإسناد بالوسم، والذاكرةُ تسمح"]}


def busy_titles(max_open: int = 1) -> set[str]:
    """عناوينُ الجلسات التي عندها أكثرُ من max_open بطاقةٍ غيرِ منتهية في السجلّ — لا تُقترَح للإسناد (الوسمُ وحدَه لا يكفي)."""
    import re
    import ledger
    final = {"closed", "merged", "published", "deferred"}
    counts: dict[str, int] = {}
    for item in ledger.reduce_state(ledger.load_events()).values():
        if item.get("state") in final:
            continue
        for title in _titles_for(item):
            counts[title] = counts.get(title, 0) + 1
    return {t for t, n in counts.items() if n > max_open}


def _titles_for(item: dict) -> list[str]:
    """جلساتُ 04 الحيّة التي يذكر عنوانُها رمزَ البطاقة الأخير (W-003 ← -003)."""
    import re
    base = MAESTRO / "projects" / "schoolos"
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    members = next(t for t in tabs["tabs"] if t.get("number") == "04")["members"]
    tail = item["id"].rsplit("-", 1)[-1]
    return [m for m in members if re.search(rf"W-{tail}|/{tail}", m)]


def load_sessions() -> list[dict]:
    proc = subprocess.run([sys.executable, str(MAESTRO / "tools" / "session_load_v2.py"), "--json", "--no-fetch"],
                          capture_output=True, encoding="utf-8", errors="replace", check=False)
    try:
        return json.loads(proc.stdout)["sessions"]
    except (json.JSONDecodeError, KeyError):
        return []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--priority", choices=("P0", "P1", "P2", "P3"))
    args = ap.parse_args()
    base = MAESTRO / "projects" / "schoolos"
    tabs = json.loads((base / "tabs.json").read_text(encoding="utf-8"))
    th = json.loads((base / "thresholds.json").read_text(encoding="utf-8"))
    free = wo.free_memory_gb()
    per_tab = tabs["session_policy"]["serial"]["per_tab_next"]["04"]
    reserved = {r["number"]: r["title"] for r in sp.active_reservations(per_tab)}  # بطاقاتٌ صدرت ولم تُفتح بعد
    pre = sp.preflight(None, args.tag, args.task, args.code, "", tabs, th, free, reserved)
    band = pre["memory"]["band"] if pre["memory"] else None
    live = set(next(t for t in tabs["tabs"] if t.get("number") == "04")["members"])
    live = live - busy_titles()
    result = decide(pre, assignable_with_tag(load_sessions(), args.tag, live), band, args.priority)
    result.update({"title": pre["title"], "memory": pre["memory"], "live_04": f"{pre['live_04']}/{pre['live_cap_04']}",
                   "measure": "قِس الذاكرة مرّتين بعد أيّ فتح: فوراً، ثمّ بعد 10 دقائق (العبءُ يظهر عند أوّل عملٍ فعليّ)"})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
