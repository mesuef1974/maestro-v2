#!/usr/bin/env python3
"""الراكدُ في الدفتر — قراءةٌ فقط: بطاقاتٌ routed/captured مضى على آخر حدثِ حالتها أكثر من 7 أيام، ومصيرٌ مقترحٌ لكلٍّ بدليلٍ منه.

لا تنقل بطاقةً ولا تغلقها ولا ترسل لأحد: المصيرُ يقرره صاحبُ البطاقة أو 0101 (D-421م). W-20261014-015.

    python ledger_stale.py [--days 7] [--recent-days 3] [--now ISO] [--html out.html] [--json]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

STALE_STATES = ("routed", "captured")
RED_LINE = re.compile(r"D-381|الجدول المعتمد الحيّ", re.I)
DEFERRED = re.compile(r"D-\d+م", re.I)
DEFER_WORDS = re.compile(r"أُجّل|مؤجَّل|تأجيل|مجمَّد|مجمد")


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def last_state_time(item: dict) -> str:
    """آخرُ حدثِ حالة؛ والمُلتقطةُ التي لم تتحرك فعمرُها من الإنشاء."""
    return item.get("state_ts") or item["created"]


def recent_note(item: dict, now: datetime, recent: timedelta) -> bool:
    return any(now - _ts(n["ts"]) <= recent for n in item.get("notes", []))


def _norm(problem: str) -> str:
    return re.sub(r"\W+", "", problem or "")[:60]


def propose(item: dict, duplicates: dict[str, list[str]]) -> tuple[str, str]:
    """(المصير المقترح، الدليل) — اقتراحٌ لا تنفيذ."""
    text = " ".join([item.get("problem", "")] + [n.get("text", "") for n in item.get("notes", [])])
    if RED_LINE.search(text):
        return "استثناء — خطٌّ أحمر", "تذكر D-381م أو الجدول المعتمد الحيّ؛ لا يُمسّ"
    key = _norm(item.get("problem", ""))
    twins = [i for i in duplicates.get(key, []) if i != item["id"]]
    if key and twins:
        return "إغلاق مكرَّر (يقرره 0101)", "نصُّ المشكلة مطابقٌ لـ" + "،".join(twins[:3])
    if DEFER_WORDS.search(text) and DEFERRED.search(text):
        return "مؤجَّل بقرار", "ملاحظةٌ تذكر تأجيلاً وقراراً: " + DEFERRED.findall(text)[0]
    if DEFER_WORDS.search(text):
        return "مؤجَّل بلا قرارٍ مسجَّل — يُسجَّل أو يُوجَّه", "ذُكر التأجيلُ دون رقم قرار"
    if item.get("held_by"):
        return "متابعة المنفّذ", f"محجوزةٌ عند {item['held_by']} ولا حركةَ حالة"
    if item["state"] == "captured":
        return "توجيه أو إغلاق", "ملتقطةٌ بلا توجيه ولا حاملٍ"
    return "إعادة توجيه", "موجَّهةٌ بلا حاملٍ حالي"


def collect(events: list[dict], now: datetime, days: int = 7, recent_days: int = 3) -> dict:
    items = ledger.reduce_state(events)
    dup: dict[str, list[str]] = {}
    for it in items.values():
        if it["state"] in STALE_STATES:
            dup.setdefault(_norm(it.get("problem", "")), []).append(it["id"])
    stale, active = [], []
    for it in items.values():
        if it["state"] not in STALE_STATES:
            continue
        age = now - _ts(last_state_time(it))
        if age <= timedelta(days=days):
            continue
        fate, proof = propose(it, dup)
        row = {"id": it["id"], "state": it["state"], "age_days": round(age.total_seconds() / 86400, 1),
               "held_by": it.get("held_by") or "—", "problem": it.get("problem", "")[:90], "fate": fate, "proof": proof}
        (active if recent_note(it, now, timedelta(days=recent_days)) else stale).append(row)
    stale.sort(key=lambda r: -r["age_days"])
    active.sort(key=lambda r: -r["age_days"])
    totals = Counter(i["state"] for i in items.values() if i["state"] in STALE_STATES)
    return {"totals": dict(totals), "stale": stale, "active": active,
            "by_holder": dict(Counter(r["held_by"] for r in stale))}


def render_text(rep: dict, days: int) -> str:
    out = [f"الراكد أقدم من {days} أيام — routed {rep['totals'].get('routed', 0)} · captured {rep['totals'].get('captured', 0)}",
           f"راكدة بلا نشاط: {len(rep['stale'])} · عليها ملاحظة حديثة (عملٌ جارٍ): {len(rep['active'])}", ""]
    for r in rep["stale"]:
        out.append(f"{r['id']} [{r['state']}] {r['age_days']} يوم · {r['held_by']} — {r['fate']} ({r['proof']}) :: {r['problem']}")
    if rep["active"]:
        out += ["", "عملٌ جارٍ (مستثنى):"] + [f"{r['id']} {r['age_days']} يوم · {r['held_by']}" for r in rep["active"]]
    return "\n".join(out)


def render_html(rep: dict, days: int) -> str:
    def rows(lst):
        return "".join("<tr>" + "".join(f"<td>{html.escape(str(r[k]))}</td>" for k in
                       ("id", "state", "age_days", "held_by", "fate", "proof", "problem")) + "</tr>" for r in lst)
    head = "<tr><th>البطاقة</th><th>الحالة</th><th>العمر بالأيام</th><th>الحاملة</th><th>المصير المقترح</th><th>الدليل</th><th>المشكلة</th></tr>"
    return (f"<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>راكد الدفتر</title>"
            f"<body><h1>الراكد في الدفتر (أقدم من {days} أيام)</h1>"
            f"<p>عمر البطاقة = الزمن منذ آخر حدثِ حالة (أو الإنشاء إن لم تتحرك). المصير مقترحٌ فقط؛ يقرره صاحب البطاقة أو 0101.</p>"
            f"<table border='1' cellpadding='4'>{head}{rows(rep['stale'])}</table>"
            f"<h2>عملٌ جارٍ (ملاحظة حديثة) — مستثنى</h2><table border='1' cellpadding='4'>{head}{rows(rep['active'])}</table></body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--recent-days", type=int, default=3)
    ap.add_argument("--now")
    ap.add_argument("--html")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    now = _ts(a.now) if a.now else datetime.now(ledger.DOHA)
    rep = collect(ledger.load_events(), now, a.days, a.recent_days)
    if a.html:
        Path(a.html).write_text(render_html(rep, a.days), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1) if a.json else render_text(rep, a.days))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
