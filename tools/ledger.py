#!/usr/bin/env python3
"""سجلُّ العمل (ledger) — مصدرُ الحقيقة الآليّ لبطاقات العمل. أحداثٌ تُلحَق فقط (JSONL)، والحالةُ تُشتقّ منها.

اللوحةُ عرضٌ مُولَّد؛ لا يُحرَّر يدويّاً. حمايةُ PDPPL في الكود: لا نصَّ خامّاً طويلاً ولا أرقامَ هويّةٍ ولا بريداً في أيّ حقل.

    python ledger.py add --source owner --type ui --problem "..." --impact "..." --accept "..." [--files a b] [--urgent]
    python ledger.py move W-20260926-001 in_progress
    python ledger.py list [--state ready_for_review]
    python ledger.py show W-20260926-001
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOHA = timezone(timedelta(hours=3))
FIELD_MAX = 240
STATES = [
    "captured", "verified", "routed", "in_progress", "ready_for_review", "notes",
    "approved", "pushed", "merged", "published", "closed", "deferred",
]
SOURCES = ("owner", "intake", "roadmap", "kpi_guard", "alert", "advisor", "repo_keeper", "discovery")
TEXT_FIELDS = ("problem", "impact", "accept", "note")
_PII = re.compile(r"\b\d{9,}\b|[\w.+-]+@[\w-]+\.[\w.]+")


class LedgerError(ValueError):
    pass


def ledger_path(path: str | os.PathLike | None = None) -> Path:
    return Path(path or os.environ.get("LEDGER_PATH") or ROOT / "ledger" / "events.jsonl")


def now_doha() -> str:
    return datetime.now(DOHA).isoformat(timespec="seconds")


def check_text(name: str, value: str) -> str:
    if len(value) > FIELD_MAX:
        raise LedgerError(f"الحقل {name} أطول من {FIELD_MAX} حرفاً — لخّص ولا تلصق نصَّ رسالةٍ خامّاً")
    if _PII.search(value):
        raise LedgerError(f"الحقل {name} يبدو فيه رقمُ هويّةٍ أو بريد — تُمنع البياناتُ الشخصيّة في السجلّ")
    return value.strip()


def load_events(path=None) -> list[dict]:
    p = ledger_path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_event(kind: str, item_id: str, data: dict | None = None, path=None) -> dict:
    p = ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": now_doha(), "id": item_id, "kind": kind, "data": data or {}}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def reduce_state(events: list[dict]) -> dict[str, dict]:
    items: dict[str, dict] = {}
    for ev in events:
        data, item_id = ev["data"], ev["id"]
        if ev["kind"] == "created":
            items[item_id] = {"id": item_id, "created": ev["ts"], "state": "captured", "approvals": [], "notes": [], **data}
            continue
        item = items.get(item_id)
        if item is None:
            continue
        if ev["kind"] == "state":
            item["state"] = data["state"]
            item["state_ts"] = ev["ts"]
        elif ev["kind"] == "update":
            item.update(data)
        elif ev["kind"] == "approval":
            item["approvals"].append({"ts": ev["ts"], **data})
        elif ev["kind"] == "note":
            item["notes"].append({"ts": ev["ts"], **data})
    return items


def new_id(events: list[dict], today: str | None = None) -> str:
    day = today or datetime.now(DOHA).strftime("%Y%m%d")
    n = sum(1 for e in events if e["kind"] == "created" and e["id"].startswith(f"W-{day}-")) + 1
    return f"W-{day}-{n:03d}"


def add_item(source: str, problem_type: str, problem: str, impact: str, accept: str,
             files: list[str] | None = None, urgent: bool = False, path=None, scores: dict | None = None) -> str:
    if source not in SOURCES:
        raise LedgerError(f"مصدرٌ غيرُ معروف: {source} (المسموح: {', '.join(SOURCES)})")
    data = {
        "source": source, "type": problem_type,
        "problem": check_text("problem", problem), "impact": check_text("impact", impact),
        "accept": check_text("accept", accept), "files": [f[:200] for f in (files or [])][:20],
        "urgent": bool(urgent), "scores": scores or {},
    }
    events = load_events(path)
    item_id = new_id(events)
    append_event("created", item_id, data, path)
    return item_id


def move(item_id: str, state: str, path=None, note: str | None = None) -> None:
    if state not in STATES:
        raise LedgerError(f"حالةٌ غيرُ معروفة: {state}")
    if item_id not in reduce_state(load_events(path)):
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    append_event("state", item_id, {"state": state}, path)
    if note:
        append_event("note", item_id, {"text": check_text("note", note)}, path)


def wsjf(item: dict) -> float:
    """(قيمة + إلحاحُ وقت + خفضُ مخاطرة) ÷ الحجم؛ كلٌّ من 1 إلى 5؛ الاستعجالُ يرفع الإلحاح إلى 5."""
    s = item.get("scores") or {}
    value, urgency, risk, size = (max(1, min(5, int(s.get(k, 3)))) for k in ("value", "urgency", "risk", "size"))
    if item.get("urgent"):
        urgency = 5
    return round((value + urgency + risk) / size, 2)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--source", required=True); a.add_argument("--type", required=True)
    a.add_argument("--problem", required=True); a.add_argument("--impact", required=True); a.add_argument("--accept", required=True)
    a.add_argument("--files", nargs="*", default=[]); a.add_argument("--urgent", action="store_true")
    m = sub.add_parser("move"); m.add_argument("id"); m.add_argument("state"); m.add_argument("--note")
    ls = sub.add_parser("list"); ls.add_argument("--state")
    sh = sub.add_parser("show"); sh.add_argument("id")
    args = ap.parse_args()
    try:
        if args.cmd == "add":
            print(add_item(args.source, args.type, args.problem, args.impact, args.accept, args.files, args.urgent))
        elif args.cmd == "move":
            move(args.id, args.state, note=args.note); print("ok")
        else:
            items = reduce_state(load_events())
            if args.cmd == "show":
                print(json.dumps(items.get(args.id), ensure_ascii=False, indent=2))
            else:
                for it in sorted(items.values(), key=lambda i: -wsjf(i)):
                    if not args.state or it["state"] == args.state:
                        print(f"{it['id']}  {it['state']:16} wsjf={wsjf(it):<5} {it['type']:16} {it['problem'][:60]}")
    except LedgerError as exc:
        sys.exit(f"رُفض: {exc}")


if __name__ == "__main__":
    main()
