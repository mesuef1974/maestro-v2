#!/usr/bin/env python3
"""قائمةُ المالك: «ما ينتظرك» بثلاثة بنودٍ على الأكثر (قرارُ المالك 2026-10-05: خفضُ التشتّت).

    python owner_queue.py                       القائمة (≤ 3 بنود مرتّبةً بالأولويّة ثمّ العمر + «والمزيد: n»)
    python owner_queue.py --json
    python owner_queue.py decision-add --id D-1 --question "…" --options "أ" "ب" [--priority P1]
    python owner_queue.py decision-close D-1 --answer "…"

المصادر: بطاقاتُ ready_for_review (معاينة) + قراراتٌ معلَّقة من `ledger/owner_decisions.jsonl` (يُلحَق فقط،
يُنشأ عند أوّل استعمال ولا يُودَع تلقائياً). وبطاقاتُ approved تُعرض في قسمٍ منفصلٍ بلا عدّ: تنتظر دفعاً لا مالكاً.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import ledger

FILE = Path(__file__).resolve().parent.parent / "ledger" / "owner_decisions.jsonl"
LIMIT = 3


def _rows(path: Path = FILE) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []


def _append(row: dict, path: Path = FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def decision_add(did: str, question: str, options: list[str], priority: str = "P1", path: Path = FILE, now: datetime | None = None) -> None:
    if any(r["kind"] == "add" and r["id"] == did for r in _rows(path)):
        raise ledger.LedgerError(f"قرارٌ موجودٌ بهذا الرمز: {did}")
    if priority not in ledger.PRIORITIES:
        raise ledger.LedgerError(f"أولويّةٌ غيرُ صالحة: {priority}")
    _append({"kind": "add", "id": did, "question": question.strip(), "options": options, "priority": priority,
             "added": (now or datetime.now(ledger.DOHA)).isoformat(timespec="minutes")}, path)


def decision_close(did: str, answer: str, path: Path = FILE, now: datetime | None = None) -> None:
    rows = _rows(path)
    if not any(r["kind"] == "add" and r["id"] == did for r in rows):
        raise ledger.LedgerError(f"قرارٌ غيرُ موجود: {did}")
    if any(r["kind"] == "close" and r["id"] == did for r in rows):
        raise ledger.LedgerError(f"القرارُ مغلقٌ أصلاً: {did}")
    _append({"kind": "close", "id": did, "answer": answer.strip(), "closed": (now or datetime.now(ledger.DOHA)).isoformat(timespec="minutes")}, path)


def open_decisions(path: Path = FILE) -> list[dict]:
    rows = _rows(path)
    closed = {r["id"] for r in rows if r["kind"] == "close"}
    return [r for r in rows if r["kind"] == "add" and r["id"] not in closed]


def age_text(since: str, now: datetime) -> str:
    try:
        secs = (now - datetime.fromisoformat(since)).total_seconds()
    except (ValueError, TypeError):
        return "—"
    hours = int(secs // 3600)
    return f"{hours // 24} يوم" if hours >= 48 else f"{max(hours, 0)} ساعة"


def _rank(priority: str) -> int:
    return ledger.PRIORITIES.index(priority) if priority in ledger.PRIORITIES else len(ledger.PRIORITIES)


def build(items: dict, decisions: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(ledger.DOHA)
    rows = []
    for it in items.values():
        if it.get("state") == "ready_for_review":
            since = it.get("state_ts", it.get("created", ""))
            rows.append({"type": "معاينة", "id": it["id"], "ask": f"عاين واعتمد أو أرسل ملاحظات — {it.get('problem', '')[:60]}",
                         "priority": it.get("priority", "P3"), "since": since})
    for d in decisions:
        rows.append({"type": "قرار", "id": d["id"], "ask": f"{d['question']} [{' / '.join(d.get('options') or [])}]",
                     "priority": d.get("priority", "P1"), "since": d["added"]})
    rows.sort(key=lambda r: (_rank(r["priority"]), r["since"]))
    for r in rows:
        r["age"] = age_text(r["since"], now)
    waiting_push = sorted(({"id": i["id"], "since": i.get("state_ts", ""), "age": age_text(i.get("state_ts", ""), now),
                            "problem": i.get("problem", "")[:60]} for i in items.values() if i.get("state") == "approved"),
                          key=lambda r: r["since"])
    return {"shown": rows[:LIMIT], "more": max(len(rows) - LIMIT, 0), "total": len(rows), "awaiting_push": waiting_push}


def render(q: dict) -> str:
    lines = ["ما ينتظر المالك:"]
    if not q["shown"]:
        lines.append("  لا شيء.")
    for r in q["shown"]:
        lines.append(f"  [{r['type']}] {r['id']} ({r['priority']}) — {r['ask']} — منذ {r['age']}")
    if q["more"]:
        lines.append(f"والمزيد: {q['more']}")
    if q["awaiting_push"]:
        lines.append("معتمدٌ ينتظر الدفعَ (لا يلزم المالك):")
        lines += [f"  {r['id']} — {r['problem']} — منذ {r['age']}" for r in q["awaiting_push"]]
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    da = sub.add_parser("decision-add")
    da.add_argument("--id", required=True)
    da.add_argument("--question", required=True)
    da.add_argument("--options", nargs="+", required=True)
    da.add_argument("--priority", default="P1")
    dc = sub.add_parser("decision-close")
    dc.add_argument("id")
    dc.add_argument("--answer", required=True)
    args = ap.parse_args()
    try:
        if args.cmd == "decision-add":
            decision_add(args.id, args.question, args.options, args.priority)
            print("ok")
        elif args.cmd == "decision-close":
            decision_close(args.id, args.answer)
            print("ok")
        else:
            q = build(ledger.reduce_state(ledger.load_events()), open_decisions())
            print(json.dumps(q, ensure_ascii=False, indent=2) if args.json else render(q))
    except ledger.LedgerError as exc:
        sys.exit(f"رُفض: {exc}")


if __name__ == "__main__":
    main()
