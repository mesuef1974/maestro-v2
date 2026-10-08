#!/usr/bin/env python3
"""بطاقاتٌ بلغت عتبة بوّابة المنطق (0+7) ولا أثرَ للبوّابة فيها — قراءةٌ فقط (0102، 2026-10-08).

    python logic_gate_lint.py [--since 2026-10-01] [--all-states]

العتبة (ميثاق 0301، قرار المالك 10-01): قرارٌ معماريّ أو هجرةٌ أو بندٌ يمسّ أكثرَ من شجرة. الدفترُ لا يحمل لها حقلاً بعد،
فالأداةُ تعدّ البطاقةَ مستوفيةً إن ذكرت ملاحظاتُها أو حقولُها «بوّابة المنطق»/Logic Gate/الأسئلة السبعة. وهي **حدٌّ أدنى**:
تكشف الغيابَ الكامل، ولا تحكم على جودة الإجابات (يحكم عليها صاحب الاختصاص).
تقرأ استمارات 0301 الرجعيّة المسجَّلة في handover_notes/retro_logic_gate_answers*.md فتعدّ البطاقةَ المذكورةَ فيها مستوفاةً.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import ledger

ROOT = Path(__file__).resolve().parent.parent
GATE = re.compile(r"بوّ?ابة المنطق|Logic Gate|الأسئلة السبعة|0\+7|7/7|Pre-mortem", re.IGNORECASE)
THRESH_TYPES = ("تأسيسٌ معماريّ",)
THRESH_FILES = re.compile(r"migrations|scheduler_cpsat")
ACTIVE = {"approved", "in_progress", "ready_for_review", "published"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-10-01")
    ap.add_argument("--all-states", action="store_true")
    a = ap.parse_args()
    answered = " ".join(p.read_text(encoding="utf-8", errors="replace") for p in (ROOT / "handover_notes").glob("retro_logic_gate_answers*.md"))
    cards, notes, state = {}, {}, {}
    for e in ledger.load_events():
        cid, k, d = e["id"], e["kind"], e.get("data", {})
        if k in ("created", "update"):
            cards.setdefault(cid, {}).update(d)
        elif k == "note":
            notes.setdefault(cid, []).append(d.get("text", ""))
        elif k == "state":
            state[cid] = d.get("state")
    missing = []
    for cid, c in cards.items():
        if cid[2:10] < a.since.replace("-", "") or (not a.all_states and state.get(cid) not in ACTIVE):
            continue
        is_thresh = c.get("type") in THRESH_TYPES or any(THRESH_FILES.search(f) for f in c.get("files", []))
        if not is_thresh:
            continue
        txt = " ".join(str(v) for v in c.values()) + " ".join(notes.get(cid, []))
        if not GATE.search(txt) and cid not in answered:
            missing.append((cid, state.get(cid), c.get("type"), str(c.get("problem", ""))[:60]))
    print(f"{len(missing)} بطاقة بلغت العتبة بلا أثرٍ لبوّابة المنطق (منذ {a.since})")
    for cid, st, ty, pr in sorted(missing):
        print(f"  {cid} {st} [{ty}] {pr}")


main()
