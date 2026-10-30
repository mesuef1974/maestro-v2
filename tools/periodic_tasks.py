#!/usr/bin/env python3
"""المهامّ الدوريّة: جدولٌ واحد يقرؤه الكنّاسُ فيرسل لصاحب كلّ مهمّةٍ في موعدها رسالةً واحدةً إلى صندوقه (W-20261026-011).

    python periodic_tasks.py list                # الجدولُ وما استحقّ الآن (بلا إرسال)
    python periodic_tasks.py done <معرّف> --by <رقم>   # تسجيلُ النتيجة: يوقف إعادةَ الرسالة (كلّ 6 ساعات، حتى مرّتين)
    python periodic_tasks.py run [--dry-run]     # يرسل المستحقَّ مرّةً واحدةً في اليوم ويحفظ ledger/periodic_state.json

الجدولُ: projects/schoolos/periodic_tasks.json. الإرسالُ إلى ledger/inbox/<صاحب>.jsonl بلا كلفة نموذج، والجرسُ (inbox.py) يوقظ الخاملة.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
DOHA = timezone(timedelta(hours=3))
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # يطابق datetime.weekday()
SENDER = "0000"  # مرسِلُ الجدول: ليس جلسة
RESEND_AFTER_H = 6  # W-20261028-014: مهمّةٌ لم تُسجَّل نتيجتُها خلال هذه المدّة تُعاد رسالتُها
MAX_RESENDS = 2  # سقفُ الإعادة في اليوم الواحد: لا إغراقَ لصندوقٍ غائبٍ صاحبُه
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def schedule_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "projects" / "schoolos" / "periodic_tasks.json"


def state_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "ledger" / "periodic_state.json"


def log_path(root: Path | None = None) -> Path:
    """سجلُّ الدفتر للمهامّ الدوريّة: يُلحَق فقط {"k":"sent"|"done","id","ts"} (W-20261028-014)."""
    return (root or ROOT) / "ledger" / "periodic_log.jsonl"


def _log(row: dict, root: Path | None = None) -> None:
    p = log_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_log(root: Path | None = None) -> list[dict]:
    out = []
    try:
        lines = log_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("k") in ("sent", "done") and d.get("id") and d.get("ts"):
            out.append(d)
    return out


def mark_done(task_id: str, by: str, now: datetime | None = None, root: Path | None = None) -> None:
    """تسجيلُ نتيجة المهمّة: يوقف إعادةَ رسالتها اليوم."""
    if task_id not in {t["id"] for t in load_tasks(root)}:
        raise ValueError(f"مهمّةٌ دوريّةٌ غيرُ معروفة: {task_id}")
    _log({"k": "done", "id": task_id, "by": by, "ts": (now or datetime.now(DOHA)).astimezone(DOHA).isoformat()}, root)


def overdue(tasks: list[dict], now: datetime, log: list[dict]) -> list[dict]:
    """مهامُّ أُرسلت اليومَ ولم تُسجَّل نتيجتُها منذ آخر إرسالٍ وانقضت RESEND_AFTER_H ولم تبلغ سقفَ الإعادة."""
    now = now.astimezone(DOHA)
    today = now.date().isoformat()
    out = []
    for t in tasks:
        rows = [r for r in log if r["id"] == t["id"] and r["ts"][:10] == today]
        sent = [r for r in rows if r["k"] == "sent"]
        if not sent or any(r["k"] == "done" for r in rows):
            continue
        last = datetime.fromisoformat(sent[-1]["ts"])
        if len(sent) <= MAX_RESENDS and now - last >= timedelta(hours=RESEND_AFTER_H):
            out.append(t)
    return out


def validate(tasks: list[dict]) -> list[str]:
    out, seen = [], set()
    for t in tasks:
        tid = t.get("id", "؟")
        if tid in seen:
            out.append(f"{tid}: معرّفٌ مكرَّر")
        seen.add(tid)
        if not re.fullmatch(r"\d{4}", str(t.get("owner", ""))):
            out.append(f"{tid}: owner رقمُ جلسةٍ من أربع خانات")
        if not t.get("days") or any(d not in DAYS for d in t["days"]):
            out.append(f"{tid}: days من {','.join(DAYS)}")
        if not TIME_RE.match(str(t.get("time", ""))):
            out.append(f"{tid}: time بصيغة HH:MM")
        if not str(t.get("what", "")).strip():
            out.append(f"{tid}: what فارغ")
    return out


def load_tasks(root: Path | None = None) -> list[dict]:
    tasks = json.loads(schedule_path(root).read_text(encoding="utf-8"))["tasks"]
    problems = validate(tasks)
    if problems:
        raise ValueError("جدولُ المهامّ الدوريّة معيب: " + "؛ ".join(problems[:5]))
    return tasks


def load_state(root: Path | None = None) -> dict[str, str]:
    try:
        d = json.loads(state_path(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def due(tasks: list[dict], now: datetime, state: dict[str, str]) -> list[dict]:
    """المهامُّ المستحقّة: يومُها اليوم وبلغ وقتُها ولم تُرسَل اليوم (تأخّرُ الكنّاس لا يضيّعها في اليوم نفسه ولا يكرّرها)."""
    now = now.astimezone(DOHA)
    today = now.date().isoformat()
    out = []
    for t in tasks:
        if DAYS[now.weekday()] not in t["days"] or now.strftime("%H:%M") < t["time"]:
            continue
        if state.get(t["id"]) == today:
            continue
        out.append(t)
    return out


def render(owner: str, tasks: list[dict], resend: bool = False) -> str:
    head = "[إعادة: لم تُسجَّل نتيجتها] " if resend else ""
    lines = [f"{head}[مهامّ دوريّة مستحقّة لـ{owner}] نفِّذها اليوم وسجّل نتيجتها:"]
    for i, t in enumerate(tasks, 1):
        lines.append(f"{i}) {t['what']}" + (f" — `{t['cmd']}`" if t.get("cmd") else ""))
    lines.append(f"عند الإنجاز: python tools/periodic_tasks.py done <المعرّف> --by {owner} (المعرّفات: " + "، ".join(t["id"] for t in tasks) + ")")
    return "\n".join(lines)


def run_due(now: datetime | None = None, root: Path | None = None, send=None, dry_run: bool = False) -> dict[str, list[str]]:
    """يرسل لكلّ صاحبٍ رسالةً واحدةً بمهامّه المستحقّة ويسجّل اليوم لكلّ مهمّةٍ بعد نجاح الإرسال. يعيد {صاحب: [معرّفات]}."""
    now = (now or datetime.now(DOHA)).astimezone(DOHA)
    tasks = load_tasks(root)
    state = load_state(root)
    by_owner: dict[str, list[dict]] = {}
    for t in due(tasks, now, state):
        by_owner.setdefault(t["owner"], []).append(t)
    if send is None:
        import inbox

        def send(owner: str, text: str) -> None:
            inbox.send(owner, SENDER, text, root)

    sent: dict[str, list[str]] = {}
    for owner, ts in sorted(by_owner.items()):
        if not dry_run:
            send(owner, render(owner, ts))
            for t in ts:
                state[t["id"]] = now.date().isoformat()
                _log({"k": "sent", "id": t["id"], "owner": owner, "ts": now.isoformat()}, root)
            p = state_path(root)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # بعد كلّ صاحب: انقطاعٌ لا يكرّر ما أُرسل
        sent[owner] = [t["id"] for t in ts]
    redo: dict[str, list[dict]] = {}
    for t in overdue(tasks, now, read_log(root)):
        redo.setdefault(t["owner"], []).append(t)
    for owner, ts in sorted(redo.items()):
        if not dry_run:
            send(owner, render(owner, ts, resend=True))
            for t in ts:
                _log({"k": "sent", "id": t["id"], "owner": owner, "ts": now.isoformat(), "resend": True}, root)
        sent.setdefault(owner, []).extend(t["id"] for t in ts)
    return sent


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("done", help="يسجّل نتيجة مهمّةٍ فيتوقّف إعادتُها اليوم")
    d.add_argument("id")
    d.add_argument("--by", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "done":
        mark_done(a.id, a.by)
        print(f"سُجّلت نتيجة {a.id} من {a.by}")
        return 0
    if a.cmd == "list":
        state = load_state()
        tasks = load_tasks()
        pending = {t["id"] for t in due(tasks, datetime.now(DOHA), state)}
        for t in tasks:
            print(f"{t['id']:<22} {t['owner']} {','.join(t['days']):<24} {t['time']} آخر إرسال: {state.get(t['id'], '—')}" + ("  ← مستحقّة" if t["id"] in pending else ""))
        return 0
    sent = run_due(dry_run=a.dry_run)
    print("\n".join(f"{o}: {', '.join(ids)}" for o, ids in sent.items()) if sent else "لا مستحقّ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
