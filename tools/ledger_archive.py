#!/usr/bin/env python3
"""أرشفةُ الدفتر (W-20261027-015، توصية 10 من سواط 10-27): البطاقاتُ المنتهية القديمة تنتقل بكلّ أحداثها من events.jsonl
إلى ملفٍّ شهريّ `ledger/archive/events-YYYY-MM.jsonl` مع فهرس `ledger/archive/index.json` (بطاقة ← ملف)، فيُقرأ ما هو حيّ وحده في كلّ أمر.

القاعدة: لا تُؤرشف إلّا بطاقةٌ حالتُها published أو closed وآخرُ حدثٍ لها أقدمُ من `--days` (30). تُنقل بأحداثها كلّها معاً فلا تنقسم بطاقةٌ
بين الملفّين ويبقى `reduce_state` على الحيّ صحيحاً. عرضٌ فقط بلا `--apply`؛ والتطبيقُ تحت قفل الدفتر ونسخةٍ احتياطيّةٍ يوميّة
وإحلالٍ ذرّيٍّ للملفّ، وإعادتُه لا تفعل شيئاً (idempotent). القراءةُ من الأرشيف: `events_of(card)`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

ARCHIVABLE = ("published", "closed")
DEFAULT_DAYS = 30


def archive_dir(path=None) -> Path:
    return ledger.ledger_path(path).parent / "archive"


def _ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def plan(events: list[dict], now: datetime, days: int = DEFAULT_DAYS) -> dict[str, str]:
    """بطاقة ← شهرُ ملفّها `YYYY-MM` (شهرُ آخر حدثٍ لها) لما يُؤرشف."""
    states = ledger.reduce_state(events)
    last: dict[str, datetime] = {}
    for ev in events:
        t = _ts(ev.get("ts", ""))
        if t is not None and (ev["id"] not in last or t > last[ev["id"]]):
            last[ev["id"]] = t
    cutoff = now - timedelta(days=days)
    return {cid: last[cid].strftime("%Y-%m") for cid, st in sorted(states.items())
            if st.get("state") in ARCHIVABLE and cid in last and last[cid] < cutoff}


def _read_index(path=None) -> dict[str, str]:
    try:
        return json.loads((archive_dir(path) / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _atomic(dest: Path, text: str) -> None:
    tmp = dest.with_name(dest.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dest)


def apply(path=None, now: datetime | None = None, days: int = DEFAULT_DAYS) -> dict:
    """ينفّذ الأرشفةَ؛ يعيد {cards, events, files}. الأرشيفُ يُكتب قبل الإحلال: انقطاعٌ بينهما يترك تكراراً لا فقداناً."""
    p = ledger.ledger_path(path)
    now = now or datetime.now(ledger.DOHA)
    empty = {"cards": 0, "events": 0, "files": []}
    if not p.is_file():
        return empty
    with ledger._file_lock(p):
        events = ledger.load_events(p)
        moving = plan(events, now, days)
        if not moving:
            return empty
        ledger.daily_backup(p)
        adir = archive_dir(p)
        adir.mkdir(parents=True, exist_ok=True)
        index = _read_index(p)
        by_file: dict[str, list[dict]] = defaultdict(list)
        keep: list[dict] = []
        for ev in events:
            month = moving.get(ev["id"])
            if month:
                by_file[f"events-{month}.jsonl"].append(ev)
            else:
                keep.append(ev)
        for name, evs in by_file.items():
            with (adir / name).open("a", encoding="utf-8") as f:
                for ev in evs:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        for cid, month in moving.items():
            index[cid] = f"events-{month}.jsonl"
        _atomic(adir / "index.json", json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True))
        _atomic(p, "".join(json.dumps(ev, ensure_ascii=False) + "\n" for ev in keep))
        return {"cards": len(moving), "events": sum(len(v) for v in by_file.values()), "files": sorted(by_file)}


def events_of(card: str, path=None) -> list[dict]:
    """أحداثُ بطاقةٍ مؤرشفة (فارغةٌ إن لم تُؤرشف)."""
    name = _read_index(path).get(card)
    f = archive_dir(path) / name if name else None
    out = []
    for line in f.read_text(encoding="utf-8").splitlines() if f and f.is_file() else []:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("id") == card:
            out.append(ev)
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--apply", action="store_true", help="بلا هذا عرضٌ فقط")
    a = ap.parse_args(argv)
    events = ledger.load_events()
    moving = plan(events, datetime.now(ledger.DOHA), a.days)
    n = sum(1 for ev in events if ev["id"] in moving)
    print(f"الدفتر: {len(events)} حدثاً · تُؤرشف {len(moving)} بطاقةً ({n} حدثاً) أقدمُ من {a.days} يوماً؛ يبقى {len(events) - n}")
    if not a.apply:
        print("(عرض) — لا شيءَ كُتب؛ --apply للتنفيذ")
        return 0
    res = apply(days=a.days)
    print(f"أُرشفت {res['cards']} بطاقةً و{res['events']} حدثاً إلى {', '.join(res['files']) or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
