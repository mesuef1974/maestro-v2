#!/usr/bin/env python3
"""طابورُ مزامنة الخارطة: سطرٌ لكلّ طلبٍ اندمج (ledger/roadmap_queue.jsonl) تقرؤه 0701 فتغلق البندَ أو تحدّث تقدّمه.

    python roadmap_queue.py list

يُلحقه post_merge_checklist.py --enqueue عند كلّ اندماج. السطر: {"pr", "card", "commit", "merged_at", "queued_at"}.
قراءةٌ وإلحاقٌ فقط؛ لا يحذف ولا يعدّل.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "ledger" / "roadmap_queue.jsonl"


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def read(path: Path | None = None) -> list[dict]:
    p = path or QUEUE
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # سطرٌ تالف لا يُسقط القراءة
    return out


def enqueue(entry: dict, path: Path | None = None, now: datetime | None = None) -> bool:
    """يُلحق السطر إن لم يكن الطلبُ فيه من قبل؛ يُرجع True إن أُلحق."""
    p = path or QUEUE
    if any(str(e.get("pr")) == str(entry.get("pr")) for e in read(p)):
        return False
    row = {**entry, "queued_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")}
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True


def oldest_age_hours(entries: list[dict], now: datetime | None = None) -> float | None:
    now = now or datetime.now(timezone.utc)
    ages = [(now - d).total_seconds() / 3600 for e in entries if (d := _parse(e.get("merged_at") or e.get("queued_at")))]
    return max(ages) if ages else None


def render(entries: list[dict], now: datetime | None = None) -> str:
    if not entries:
        return "طابورُ الخارطة فارغ"
    lines = [f"طابورُ الخارطة: {len(entries)} طلباً بانتظار المزامنة"]
    for e in entries:
        lines.append(f"  #{e.get('pr')}  البطاقة {e.get('card') or '—'}  commit {e.get('commit') or '—'}  اندمج {e.get('merged_at') or '—'}")
    age = oldest_age_hours(entries, now)
    if age is not None:
        lines.append(f"عمرُ الأقدم: {age:.1f} ساعة")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["list"])
    ap.parse_args(argv)
    print(render(read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
