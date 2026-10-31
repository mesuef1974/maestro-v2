#!/usr/bin/env python3
"""المهامّ الدوريّة: جدولٌ واحد يقرؤه الكنّاسُ فيرسل لصاحب كلّ مهمّةٍ في موعدها رسالةً واحدةً إلى صندوقه (W-20261026-011).

    python periodic_tasks.py list                # الجدولُ وما استحقّ الآن (بلا إرسال)
    python periodic_tasks.py run [--dry-run]     # يرسل المستحقَّ مرّةً واحدةً في اليوم ويحفظ ledger/periodic_state.json
    python periodic_tasks.py done <المعرّف>      # يسجّل إنجازَ مهمّةٍ اليوم فتتوقّف إعادةُ رسالتها

كلُّ إرسالٍ (وإعادةٍ وإنجاز) يُلحَق بموعده في ledger/periodic_log.jsonl (W-20261028-014). مهمّةٌ أُرسلت اليوم ولم يُسجَّل إنجازُها
خلال RESEND_AFTER_H ساعات تُعاد رسالتُها، بسقف MAX_RESENDS مرّتين في اليوم، ولا تعبر الأيّام (غدًا تستحقّ من جديد بموعدها).

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
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
RESEND_AFTER_H = 6  # ساعاتٌ منذ آخر إرسالٍ بلا إنجازٍ مسجَّل
MAX_RESENDS = 2  # إعاداتٌ في اليوم (غير الإرسال الأوّل)


def schedule_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "projects" / "schoolos" / "periodic_tasks.json"


def state_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "ledger" / "periodic_state.json"


def log_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "ledger" / "periodic_log.jsonl"


def log_event(kind: str, task: str, owner: str, now: datetime, root: Path | None = None) -> None:
    """يُلحِق حدثاً (sent|resent|done) بموعده في سجلّ المهامّ الدوريّة؛ إلحاقٌ فقط."""
    p = log_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": now.astimezone(DOHA).isoformat(timespec="seconds"), "kind": kind, "task": task, "owner": owner}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_log(root: Path | None = None) -> list[dict]:
    try:
        lines = log_path(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("task") and row.get("ts"):
            out.append(row)
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


def overdue(tasks: list[dict], now: datetime, log: list[dict]) -> list[dict]:
    """مهامُّ أُرسلت اليوم ومرّت RESEND_AFTER_H ساعات على آخر إرسالٍ لها بلا «done» اليوم، ولم تبلغ سقفَ الإعادات.
    لا تعبر الأيّام: الإرسالُ والفحصُ في يومٍ واحدٍ بتوقيت الدوحة."""
    now = now.astimezone(DOHA)
    today = now.date().isoformat()
    by_task: dict[str, list[dict]] = {}
    for row in log:
        try:
            ts = datetime.fromisoformat(row["ts"]).astimezone(DOHA)
        except ValueError:
            continue
        if ts.date().isoformat() == today:
            by_task.setdefault(row["task"], []).append({**row, "_ts": ts})
    out = []
    for t in tasks:
        rows = by_task.get(t["id"], [])
        kinds = [r.get("kind") for r in rows]
        if not rows or "done" in kinds or kinds.count("resent") >= MAX_RESENDS:
            continue
        last = max(r["_ts"] for r in rows if r.get("kind") in ("sent", "resent"))
        if now - last >= timedelta(hours=RESEND_AFTER_H):
            out.append(t)
    return out


def render(owner: str, tasks: list[dict], resent: frozenset[str] = frozenset()) -> str:
    lines = [f"[مهامّ دوريّة مستحقّة لـ{owner}] نفِّذها اليوم وسجّل نتيجتها:"]
    for i, t in enumerate(tasks, 1):
        mark = "[إعادة: لم يُسجَّل إنجازُها] " if t["id"] in resent else ""
        lines.append(f"{i}) {mark}{t['what']}" + (f" — `{t['cmd']}`" if t.get("cmd") else ""))
    lines.append("بعد التنفيذ سجّل الإنجاز لتتوقّف الإعادة: " + "؛ ".join(f"`python tools/periodic_tasks.py done {t['id']}`" for t in tasks))
    return "\n".join(lines)


def run_due(now: datetime | None = None, root: Path | None = None, send=None, dry_run: bool = False) -> dict[str, list[str]]:
    """يرسل لكلّ صاحبٍ رسالةً واحدةً بمهامّه المستحقّة (والمُعادة) ويسجّل اليوم لكلّ مهمّةٍ بعد نجاح الإرسال. يعيد {صاحب: [معرّفات]}."""
    now = (now or datetime.now(DOHA)).astimezone(DOHA)
    tasks = load_tasks(root)
    state = load_state(root)
    by_owner: dict[str, list[dict]] = {}
    resent: set[str] = set()
    for t in overdue(tasks, now, load_log(root)):
        resent.add(t["id"])
        by_owner.setdefault(t["owner"], []).append(t)
    for t in due(tasks, now, state):
        by_owner.setdefault(t["owner"], []).append(t)
    if send is None:
        import inbox

        def send(owner: str, text: str) -> None:
            inbox.send(owner, SENDER, text, root)

    sent: dict[str, list[str]] = {}
    for owner, ts in sorted(by_owner.items()):
        if not dry_run:
            send(owner, render(owner, ts, frozenset(resent)))
            for t in ts:
                state[t["id"]] = now.date().isoformat()
                log_event("resent" if t["id"] in resent else "sent", t["id"], owner, now, root)
            p = state_path(root)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # بعد كلّ صاحب: انقطاعٌ لا يكرّر ما أُرسل
        sent[owner] = [t["id"] for t in ts]
    return sent


def mark_done(task_id: str, now: datetime | None = None, root: Path | None = None) -> str:
    """يسجّل إنجازَ مهمّةٍ اليوم؛ معرّفٌ مجهولٌ يرفعه ValueError. يعيد صاحبَ المهمّة."""
    now = (now or datetime.now(DOHA)).astimezone(DOHA)
    task = next((t for t in load_tasks(root) if t["id"] == task_id), None)
    if task is None:
        raise ValueError(f"معرّفٌ مجهول: {task_id}")
    log_event("done", task_id, task["owner"], now, root)
    return task["owner"]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("done")
    d.add_argument("task_id")
    a = ap.parse_args(argv)
    if a.cmd == "done":
        try:
            owner = mark_done(a.task_id)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"سُجّل إنجازُ {a.task_id} ({owner}) اليوم")
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
