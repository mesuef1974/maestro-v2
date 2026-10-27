#!/usr/bin/env python3
"""المهامّ الدوريّة: جدولٌ واحد يقرؤه الكنّاسُ فيرسل لصاحب كلّ مهمّةٍ في موعدها رسالةً واحدةً إلى صندوقه (W-20261026-011).

    python periodic_tasks.py list                # الجدولُ وما استحقّ الآن (بلا إرسال)
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
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def schedule_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "projects" / "schoolos" / "periodic_tasks.json"


def state_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "ledger" / "periodic_state.json"


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


def render(owner: str, tasks: list[dict]) -> str:
    lines = [f"[مهامّ دوريّة مستحقّة لـ{owner}] نفِّذها اليوم وسجّل نتيجتها:"]
    for i, t in enumerate(tasks, 1):
        lines.append(f"{i}) {t['what']}" + (f" — `{t['cmd']}`" if t.get("cmd") else ""))
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
            p = state_path(root)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")  # بعد كلّ صاحب: انقطاعٌ لا يكرّر ما أُرسل
        sent[owner] = [t["id"] for t in ts]
    return sent


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
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
