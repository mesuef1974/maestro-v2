#!/usr/bin/env python3
"""سجلُّ العصف بنتيجته — سطرٌ واحدٌ لكلّ عصفٍ (قرار 0101، D-157م): بلا وثيقةٍ إضافيّة.

    python brainstorm_log.py add --question "…" --chosen "…" --expected "…" --metric "…" --recheck 2026-10-09 [--by 0104]
    python brainstorm_log.py due            ما حان موعدُ إعادة قياسه (يقرؤه 0102 لا 0104)
    python brainstorm_log.py result <رقم> --achieved yes|no|partial --note "…"   0102 تسجّل نتيجةَ إعادة القياس

الملفّ `ledger/brainstorms.jsonl` يُلحَق فقط. مؤشّرُ 0104: نسبةُ العصف الذي حقّق أثرَه المتوقَّع = achieved=yes ÷ ما أُعيد قياسُه.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "ledger" / "brainstorms.jsonl"
DOHA = timezone(timedelta(hours=3))


def _rows(path: Path = FILE) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _append(row: dict, path: Path = FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def add(question: str, chosen: str, expected: str, metric: str, recheck: str, by: str = "0104", path: Path = FILE) -> int:
    date.fromisoformat(recheck)  # يرفض تاريخاً غيرَ صالح
    n = sum(1 for r in _rows(path) if r["kind"] == "brainstorm") + 1
    _append({"kind": "brainstorm", "n": n, "ts": datetime.now(DOHA).isoformat(timespec="minutes"), "by": by, "question": question.strip(),
             "chosen": chosen.strip(), "expected": expected.strip(), "metric": metric.strip(), "recheck": recheck}, path)
    return n


def due(today: date | None = None, path: Path = FILE) -> list[dict]:
    today = today or date.today()
    rows = _rows(path)
    done = {r["n"] for r in rows if r["kind"] == "result"}
    return [r for r in rows if r["kind"] == "brainstorm" and r["n"] not in done and date.fromisoformat(r["recheck"]) <= today]


def result(n: int, achieved: str, note: str, path: Path = FILE) -> None:
    if achieved not in ("yes", "no", "partial"):
        raise ValueError("achieved: yes|no|partial")
    if not any(r["kind"] == "brainstorm" and r["n"] == n for r in _rows(path)):
        raise ValueError(f"لا عصفَ برقم {n}")
    _append({"kind": "result", "n": n, "ts": datetime.now(DOHA).isoformat(timespec="minutes"), "achieved": achieved, "note": note.strip()}, path)


def success_rate(path: Path = FILE) -> dict:
    res = [r for r in _rows(path) if r["kind"] == "result"]
    yes = sum(1 for r in res if r["achieved"] == "yes")
    return {"measured": len(res), "achieved": yes, "rate": round(yes / len(res), 2) if res else None}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    for k in ("question", "chosen", "expected", "metric", "recheck"):
        a.add_argument(f"--{k}", required=True)
    a.add_argument("--by", default="0104")
    sub.add_parser("due")
    r = sub.add_parser("result")
    r.add_argument("n", type=int)
    r.add_argument("--achieved", required=True)
    r.add_argument("--note", default="")
    x = ap.parse_args()
    if x.cmd == "add":
        print(f"سُجّل عصفٌ رقم {add(x.question, x.chosen, x.expected, x.metric, x.recheck, x.by)}")
    elif x.cmd == "due":
        d = due()
        print("\n".join(f"#{r['n']} (موعدُه {r['recheck']}): {r['question'][:70]} ← المقياس: {r['metric'][:60]}" for r in d) or "لا إعادةَ قياسٍ مستحقّة")
        print("نجاحُ العصف حتى الآن:", success_rate())
    else:
        result(x.n, x.achieved, x.note)
        print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
