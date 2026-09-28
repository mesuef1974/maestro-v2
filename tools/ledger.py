#!/usr/bin/env python3
"""سجلُّ العمل (ledger) — مصدرُ الحقيقة الآليّ لبطاقات العمل. أحداثٌ تُلحَق فقط (JSONL)، والحالةُ تُشتقّ منها.

اللوحةُ عرضٌ مُولَّد؛ لا يُحرَّر يدويّاً. حمايةُ PDPPL في الكود: لا نصَّ خامّاً طويلاً ولا أرقامَ هويّةٍ ولا بريداً في أيّ حقل.

    python ledger.py add --source owner --type ui --problem "..." --impact "..." --accept "..." --start 2026-09-29T08:00 --priority P1 [--files a b] [--urgent]
    (زمنُ البدء والأولويّة إلزاميّان — قرارُ المالك 2026-09-28)
    python ledger.py move W-20260926-001 in_progress
    python ledger.py list [--state ready_for_review]
    python ledger.py show W-20260926-001
    python ledger.py tag W-20260926-001 --branch claude/<فرع> [--raise-to high --reason "..."] [--apply]   # وسمُ الخطورة والمجال؛ عرضٌ فقط بلا --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
PRIORITIES = ("P0", "P1", "P2", "P3")  # P0 استعجال · P1 هذا الأسبوع · P2 هذا الشهر · P3 لاحقاً مؤرَّخ
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


def parse_start(value: str) -> str:
    """زمنُ البدء الفعليّ إلزاميّ (قرارُ المالك 2026-09-28: «لا شيءَ بدون زمن»). يُقبل ISO بتوقيت الدوحة أو بمنطقةٍ صريحة."""
    if not value:
        raise LedgerError("زمنُ البدء إلزاميّ — لا مهمّةَ بلا زمن (مثال: 2026-09-29T08:00)")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"زمنُ بدءٍ غيرُ صالح: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DOHA)
    return dt.astimezone(DOHA).isoformat(timespec="minutes")


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
             files: list[str] | None = None, urgent: bool = False, path=None, scores: dict | None = None,
             start: str = "", priority: str = "") -> str:
    if source not in SOURCES:
        raise LedgerError(f"مصدرٌ غيرُ معروف: {source} (المسموح: {', '.join(SOURCES)})")
    if priority not in PRIORITIES:
        raise LedgerError(f"الأولويّة إلزاميّة، واحدةٌ من {', '.join(PRIORITIES)}")
    if urgent and priority != "P0":
        raise LedgerError("الاستعجالُ أولويّتُه P0")
    data = {
        "source": source, "type": problem_type, "priority": priority, "start": parse_start(start),
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


def order_key(item: dict) -> tuple:
    """الأولويّةُ أوّلاً، ثمّ زمنُ البدء الأقرب، ثمّ WSJF الأعلى."""
    pr = item.get("priority", "P3")
    return (PRIORITIES.index(pr) if pr in PRIORITIES else len(PRIORITIES), item.get("start", "9999"), -wsjf(item))


def late_items(items: dict, now: datetime | None = None) -> list[dict]:
    """مهامُّ حان زمنُ بدئها ولم تبدأ (ما زالت captured/verified/routed)."""
    now = now or datetime.now(DOHA)
    waiting = ("captured", "verified", "routed")
    return [i for i in items.values() if i.get("state") in waiting and i.get("start") and datetime.fromisoformat(i["start"]) <= now]


def _git_read(cmd: list[str]) -> str:
    """أمرٌ قرائيٌّ على غيت أو gh؛ يفشل بصوتٍ عالٍ لا صامتاً."""
    repo = os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", check=False, cwd=repo)
    if proc.returncode != 0:
        raise LedgerError(f"فشل: {' '.join(cmd[:4])} — {proc.stderr.strip()[:200]}")
    return proc.stdout


def tag_item(card: str, paths: list[str], head: str = "", pr: int | None = None, raise_to: str = "",
             reason: str = "", apply: bool = False, path=None) -> dict:
    """يصنّف مساراتِ العمل ويكتب خطورةَ البطاقة ومجالَها حدثَ update (يُلحَق فقط). بلا apply عرضٌ فقط. لا خفضَ للخطورة أبداً."""
    from risk_tier import TIER_ORDER, classify_paths

    if card not in reduce_state(load_events(path)):
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {card}")
    if not paths:
        raise LedgerError("لا مساراتٍ متغيّرة — تحقّق من اسم الفرع أو أنّ العملَ أُودِع")
    info = classify_paths(paths)
    tier = info["tier"]
    if raise_to:
        if not reason:
            raise LedgerError("--raise-to يلزمه --reason")
        if TIER_ORDER.index(raise_to) < TIER_ORDER.index(tier):
            raise LedgerError(f"لا خفضَ للخطورة ({tier} ← {raise_to}): الأداةُ حدٌّ أدنى لا أعلى")
        tier = raise_to
    data = {"tier": tier, "category": info["category"], "area": info["area"], "flags": info["flags"], "files_changed": len(paths)}
    if head:
        data["head"] = head  # الإيداعُ المصنَّف: يُقارَن لاحقاً برأس الطلب قبل الدمج
    if pr:
        data["pr"] = pr
    if raise_to:
        data["tier_reason"] = check_text("note", reason)
    if apply:
        append_event("update", card, data, path)
    return {"card": card, "update": data, "categories": info["categories"], "applied": apply}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--source", required=True); a.add_argument("--type", required=True)
    a.add_argument("--problem", required=True); a.add_argument("--impact", required=True); a.add_argument("--accept", required=True)
    a.add_argument("--files", nargs="*", default=[]); a.add_argument("--urgent", action="store_true")
    a.add_argument("--start", required=True, help="زمنُ البدء الفعليّ ISO بتوقيت الدوحة"); a.add_argument("--priority", required=True, choices=PRIORITIES)
    m = sub.add_parser("move"); m.add_argument("id"); m.add_argument("state"); m.add_argument("--note")
    ls = sub.add_parser("list"); ls.add_argument("--state")
    sh = sub.add_parser("show"); sh.add_argument("id")
    tg = sub.add_parser("tag", help="يكتب خطورةَ البطاقة ومجالها من مسارات عملها")
    tg.add_argument("id")
    src = tg.add_mutually_exclusive_group(required=True)
    src.add_argument("--branch"); src.add_argument("--pr", type=int); src.add_argument("--paths", nargs="+")
    tg.add_argument("--raise-to", default=""); tg.add_argument("--reason", default=""); tg.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        if args.cmd == "add":
            print(add_item(args.source, args.type, args.problem, args.impact, args.accept, args.files, args.urgent,
                           start=args.start, priority=args.priority))
        elif args.cmd == "move":
            move(args.id, args.state, note=args.note); print("ok")
        elif args.cmd == "tag":
            head, pr = "", None
            if args.branch:
                paths = _git_read(["git", "diff", "--name-only", f"origin/main...{args.branch}"]).split()
                head = _git_read(["git", "rev-parse", "--short=8", args.branch]).strip()
            elif args.pr:
                data = json.loads(_git_read(["gh", "pr", "view", str(args.pr), "--json", "files,headRefOid"]))
                paths, head, pr = [f["path"] for f in data.get("files", [])], data.get("headRefOid", "")[:8], args.pr
            else:
                paths = args.paths
            out = tag_item(args.id, paths, head, pr, args.raise_to, args.reason, args.apply)
            print(json.dumps(out, ensure_ascii=False, indent=2))
            print("أُلحق حدثُ update" if args.apply else "عرضٌ فقط — أضِف --apply للكتابة")
        else:
            items = reduce_state(load_events())
            if args.cmd == "show":
                print(json.dumps(items.get(args.id), ensure_ascii=False, indent=2))
            else:
                for it in sorted(items.values(), key=order_key):
                    if not args.state or it["state"] == args.state:
                        print(f"{it['id']}  {it.get('priority','—')}  بدء={it.get('start','—')[:16]}  {it['state']:16} {it['type']:16} {it['problem'][:50]}")
    except LedgerError as exc:
        sys.exit(f"رُفض: {exc}")


if __name__ == "__main__":
    main()
