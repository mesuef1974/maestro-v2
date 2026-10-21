#!/usr/bin/env python3
"""سجلُّ بوّابة الجمعة V2 (A1–A10) والحكمُ منها — (0102، 2026-10-08).
القائمة: docs/v2_friday_gate_checklist_2026-10-08.html

    python gate_check.py status
    python gate_check.py set A1 pass "قابل، 0 مخالفة، 7 دقائق"      # pass | fail | nonblocking
    python gate_check.py a8 <رقم الطلب>                              # A8 آليّاً من gh pr checks

الحكم: No-Go إن فشل أيٌّ من A1..A6 أو A8..A10؛ A7 يُسجَّل ولا يحجب إن نجح A1.
لا يُنفّذ هذا السكربتُ فحصاً على 8500 ولا الإنتاج: يسجّل النتيجةَ ويحكم. A5 (اعتمادُ المالك) لا يُسجَّل بغير اعتماده الصريح.
فحصا التبكير: A1 حتى الجمعة 24:00 (مُدَّ من 12:00 بأمر المالك 10-08) وA2+A3+A4 السبت 02:00، وGo/No-Go السبت 04:00 (احتياطي تلقائي: الجدول الحالي المربوط؛ D-288م مقترح 0101).
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

F = Path(__file__).with_name("gate_state_2026-10-09.json")
IDS = [f"A{i}" for i in range(1, 11)]
EARLY = {"24:00 (مُدَّ من 12:00 بأمر المالك 10-08)": ["A1"], "السبت 02:00": ["A2", "A3", "A4"]}


def load():
    return json.loads(F.read_text(encoding="utf-8")) if F.exists() else {}


def save(s):
    F.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%m-%d %H:%M")


def verdict(s):
    bad = [i for i in IDS if i != "A7" and s.get(i, {}).get("r") == "fail"]
    if s.get("A7", {}).get("r") == "fail" and s.get("A1", {}).get("r") != "pass":
        bad.append("A7")
    missing = [i for i in IDS if i not in s]
    if bad:
        return "No-Go: " + ",".join(bad)
    return "معلّق: ينقص " + ",".join(missing) if missing else "Go"


def main():
    a = sys.argv[1:]
    s = load()
    if a[:1] == ["set"]:
        s[a[1]] = {"r": a[2], "note": a[3] if len(a) > 3 else "", "at": now()}
        save(s)
    elif a[:1] == ["a8"]:
        r = subprocess.run(["gh", "pr", "checks", a[1]], capture_output=True, text=True, encoding="utf-8")
        s["A8"] = {"r": "pass" if r.returncode == 0 else "fail", "note": (r.stdout or r.stderr).strip()[:300], "at": now()}
        save(s)
    for i in IDS:
        x = s.get(i)
        print(f"{i:3} {x['r'] if x else '—':12} {x['at'] if x else '':11} {x['note'][:60] if x else ''}")
    print("الحكم:", verdict(s))
    for t, ids in EARLY.items():
        ok = all(s.get(i, {}).get("r") == "pass" for i in ids)
        print(f"فحص {t}:", "نجح" if ok else "لم ينجح بعد", ids)


main()
