#!/usr/bin/env python3
"""سجلُّ الردود المنتظَرة وإعادةُ السؤال تلقائيّاً (أمرُ المالك 2026-10-03: متابعةُ الردّ تكون منّي، وإن لم يرد أسأل مرّةً أخرى).

    python pending_replies.py add --to 0101 --about "قرارُ pr_red (أ)/(ب)"
    python pending_replies.py list
    python pending_replies.py overdue [--minutes 30]     ما تأخّر ردُّه → أعيد السؤالَ فوراً بلا أمرٍ
    python pending_replies.py done <رقم> [--note "…"]
    python pending_replies.py asked <رقم>               سجّلتُ إعادةَ سؤال (يُحسب العدّاد)

الملفُّ `ledger/pending_replies.jsonl` يُلحَق فقط. القاعدةُ عندي: في **كلّ دورة** (رسالةُ المالك أو جلسةٍ) أشغّل `overdue` وأعيد السؤالَ لكلّ ما تأخّر، وأذكر في ختم ردّي «أنتظر: …» من هذا السجلّ لا من الذاكرة.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "ledger" / "pending_replies.jsonl"
DOHA = timezone(timedelta(hours=3))


def _rows(path: Path = FILE) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []


def _append(row: dict, path: Path = FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _now() -> datetime:
    return datetime.now(DOHA)


def add(to: str, about: str, path: Path = FILE, now: datetime | None = None, from_: str = "") -> int:
    """from_ (اختياري): الجلسةُ المنتظِرة، فتظهر في حقل waiting من حالتها (W-20261025-001)."""
    n = sum(1 for r in _rows(path) if r["kind"] == "add") + 1
    row = {"kind": "add", "n": n, "ts": (now or _now()).isoformat(timespec="minutes"), "to": to, "about": about.strip()}
    if from_:
        row["from"] = from_
    _append(row, path)
    return n


def open_items(path: Path = FILE) -> list[dict]:
    rows = _rows(path)
    closed = {r["n"] for r in rows if r["kind"] == "done"}
    asked: dict[int, list[str]] = {}
    for r in rows:
        if r["kind"] == "asked":
            asked.setdefault(r["n"], []).append(r["ts"])
    out = []
    for r in rows:
        if r["kind"] == "add" and r["n"] not in closed:
            last = asked.get(r["n"], [r["ts"]])[-1]
            out.append({**r, "last": last, "asks": len(asked.get(r["n"], []))})
    return out


def overdue(minutes: float = 30.0, path: Path = FILE, now: datetime | None = None) -> list[dict]:
    now = now or _now()
    return [r for r in open_items(path) if (now - datetime.fromisoformat(r["last"])).total_seconds() / 60 >= minutes]


def done(n: int, note: str = "", path: Path = FILE) -> None:
    if not any(r["kind"] == "add" and r["n"] == n for r in _rows(path)):
        raise ValueError(f"لا بندَ برقم {n}")
    _append({"kind": "done", "n": n, "ts": _now().isoformat(timespec="minutes"), "note": note.strip()}, path)


def asked(n: int, path: Path = FILE) -> None:
    if not any(r["kind"] == "add" and r["n"] == n for r in _rows(path)):
        raise ValueError(f"لا بندَ برقم {n}")
    _append({"kind": "asked", "n": n, "ts": _now().isoformat(timespec="minutes")}, path)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--to", required=True); a.add_argument("--about", required=True); a.add_argument("--from", dest="from_", default="", help="الجلسةُ المنتظِرة (تُدوَّن في waiting)")
    sub.add_parser("list")
    o = sub.add_parser("overdue"); o.add_argument("--minutes", type=float, default=30.0)
    d = sub.add_parser("done"); d.add_argument("n", type=int); d.add_argument("--note", default="")
    k = sub.add_parser("asked"); k.add_argument("n", type=int)
    x = ap.parse_args()
    if x.cmd == "add":
        print(f"سُجّل #{add(x.to, x.about, from_=x.from_)}")
    elif x.cmd in ("list", "overdue"):
        items = open_items() if x.cmd == "list" else overdue(x.minutes)
        for r in items:
            print(f"#{r['n']} إلى {r['to']} منذ {r['ts'][5:16]} (آخرُ سؤال {r['last'][5:16]}، أُعيد {r['asks']} مرّة): {r['about'][:90]}")
        if not items:
            print("لا ردودَ منتظَرة" if x.cmd == "list" else "لا ما تأخّر")
    elif x.cmd == "done":
        done(x.n, x.note); print("ok")
    else:
        asked(x.n); print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
