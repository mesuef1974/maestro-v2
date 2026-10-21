#!/usr/bin/env python3
"""سجلُّ العصف بنتيجته — سطرٌ واحدٌ لكلّ عصفٍ (قرار 0101، D-157م): بلا وثيقةٍ إضافيّة.

    python brainstorm_log.py add --question "…" --chosen "…" --expected "…" --metric "…" --recheck 2026-10-09 \\
        --baseline 1.35 --target 1.0 --unit س --source "gh pr list … (أمرُ القياس نفسُه)" [--by 0301]
    python brainstorm_log.py quantify <رقم> --baseline 1.35 --target 1.0 --unit س --source "…"   يُلحق أساساً وهدفاً بعصفٍ سُجّل بلا رقم
    python brainstorm_log.py due            ما حان موعدُ إعادة قياسه (تقرؤه 0701 لا كاتبةُ العصف 0301 — أمرُ المالك 2026-10-21 «القراءة لـ0701»)
    python brainstorm_log.py result <رقم> --actual 0.9 [--confounders "…"] [--note "…"]   0701 تقيس بأمر المصدر نفسِه فيُحسب الأثرُ آلياً
    python brainstorm_log.py result <رقم> --achieved yes|no|partial --note "…"            لعصفٍ بلا رقمٍ قياسيّ (حكمٌ نوعيّ)

الأثرُ = (الفعليّ − الأساس) ÷ (الهدف − الأساس): ≥1 تحقّق، (0..1) جزئيّ، ≤0 لم يتحقّق (يصحّ للاتّجاهين: خفضٍ أو رفع).
الأثرُ **ارتباطٌ لا سببيّة**: تُسجَّل «المُشوِّشات» (تغييراتٌ أخرى في الفترة نفسِها) فيُقرأ الأثرُ بحذرٍ.

الملفّ `ledger/brainstorms.jsonl` يُلحَق فقط. مؤشّرُ 0701 (قارئةُ الأثر): نسبةُ العصف الذي حقّق أثرَه المتوقَّع = achieved=yes ÷ ما أُعيد قياسُه.
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


def _brainstorms(path: Path = FILE) -> list[dict]:
    """العصفُ بعد دمج أحداث quantify (إضافةُ أساسٍ وهدفٍ لاحقاً دون تعديل ما كُتب)."""
    rows = _rows(path)
    q = {r["n"]: r for r in rows if r["kind"] == "quantify"}
    out = []
    for r in rows:
        if r["kind"] == "brainstorm":
            out.append({**r, **{k: v for k, v in q.get(r["n"], {}).items() if k in ("baseline", "target", "unit", "source")}})
    return out


def quantify(n: int, baseline: float, target: float, unit: str, source: str, path: Path = FILE) -> None:
    """يُلحق أساساً وهدفاً وأمرَ قياسٍ بعصفٍ سُجّل بلا رقم (لا تعديلَ لسطرٍ كُتب)."""
    if not any(r["n"] == n for r in _brainstorms(path)):
        raise ValueError(f"لا عصفَ برقم {n}")
    if baseline == target or not source.strip():
        raise ValueError("أساسٌ ≠ هدفٍ وأمرُ قياسٍ مصدر")
    _append({"kind": "quantify", "n": n, "ts": datetime.now(DOHA).isoformat(timespec="minutes"), "baseline": baseline, "target": target,
             "unit": unit, "source": source.strip()}, path)


def _append(row: dict, path: Path = FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def add(question: str, chosen: str, expected: str, metric: str, recheck: str, by: str = "0301", path: Path = FILE,
        baseline: float | None = None, target: float | None = None, unit: str = "", source: str = "") -> int:
    date.fromisoformat(recheck)  # يرفض تاريخاً غيرَ صالح
    if (baseline is None) != (target is None):
        raise ValueError("الأساسُ والهدفُ معاً أو لا شيء")
    if baseline is not None and (baseline == target or not source.strip()):
        raise ValueError("عصفٌ بأثرٍ قياسيّ يلزمه أساسٌ ≠ هدفٍ وأمرُ قياسٍ مصدرٌ (--source) تعيده 0701")
    n = sum(1 for r in _rows(path) if r["kind"] == "brainstorm") + 1
    row = {"kind": "brainstorm", "n": n, "ts": datetime.now(DOHA).isoformat(timespec="minutes"), "by": by, "question": question.strip(),
           "chosen": chosen.strip(), "expected": expected.strip(), "metric": metric.strip(), "recheck": recheck}
    if baseline is not None:
        row.update({"baseline": baseline, "target": target, "unit": unit, "source": source.strip()})
    _append(row, path)
    return n


def due(today: date | None = None, path: Path = FILE) -> list[dict]:
    today = today or date.today()
    done = {r["n"] for r in _rows(path) if r["kind"] == "result"}
    return [r for r in _brainstorms(path) if r["n"] not in done and date.fromisoformat(r["recheck"]) <= today]


def effect(baseline: float, target: float, actual: float) -> float:
    """نسبةُ ما تحقّق من المسافة بين الأساس والهدف؛ تصحّ لخفضٍ (الهدفُ أقلّ) أو رفعٍ (الهدفُ أكبر)."""
    return round((actual - baseline) / (target - baseline), 2)


def result(n: int, achieved: str | None = None, note: str = "", path: Path = FILE, actual: float | None = None, confounders: str = "") -> None:
    row = next((r for r in _brainstorms(path) if r["n"] == n), None)
    if row is None:
        raise ValueError(f"لا عصفَ برقم {n}")
    out = {"kind": "result", "n": n, "ts": datetime.now(DOHA).isoformat(timespec="minutes"), "note": note.strip(), "confounders": confounders.strip()}
    if actual is not None:
        if "baseline" not in row:
            raise ValueError("هذا العصفُ بلا أساسٍ وهدف — استعمل --achieved")
        e = effect(row["baseline"], row["target"], actual)
        out.update({"actual": actual, "effect": e, "achieved": "yes" if e >= 1 else ("partial" if e > 0 else "no")})
    else:
        if achieved not in ("yes", "no", "partial"):
            raise ValueError("achieved: yes|no|partial (أو --actual برقمٍ)")
        out["achieved"] = achieved
    _append(out, path)


def success_rate(path: Path = FILE) -> dict:
    res = [r for r in _rows(path) if r["kind"] == "result"]
    yes = sum(1 for r in res if r["achieved"] == "yes")
    eff = [r["effect"] for r in res if "effect" in r]
    return {"measured": len(res), "achieved": yes, "rate": round(yes / len(res), 2) if res else None,
            "quantified": len(eff), "mean_effect": round(sum(eff) / len(eff), 2) if eff else None}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    for k in ("question", "chosen", "expected", "metric", "recheck"):
        a.add_argument(f"--{k}", required=True)
    a.add_argument("--baseline", type=float); a.add_argument("--target", type=float)
    a.add_argument("--unit", default=""); a.add_argument("--source", default="")
    a.add_argument("--by", default="0301")  # كاتبةُ العصف: الحوكمة (ميثاقُ 0102 مدمَجٌ فيها)
    sub.add_parser("due")
    qz = sub.add_parser("quantify")
    qz.add_argument("n", type=int); qz.add_argument("--baseline", type=float, required=True); qz.add_argument("--target", type=float, required=True)
    qz.add_argument("--unit", default=""); qz.add_argument("--source", required=True)
    r = sub.add_parser("result")
    r.add_argument("n", type=int)
    r.add_argument("--achieved")
    r.add_argument("--actual", type=float)
    r.add_argument("--confounders", default="")
    r.add_argument("--note", default="")
    x = ap.parse_args()
    if x.cmd == "add":
        print(f"سُجّل عصفٌ رقم {add(x.question, x.chosen, x.expected, x.metric, x.recheck, x.by, baseline=x.baseline, target=x.target, unit=x.unit, source=x.source)}")
    elif x.cmd == "due":
        d = due()
        print("\n".join(f"#{r['n']} (موعدُه {r['recheck']}): {r['question'][:70]} ← المقياس: {r['metric'][:60]}" + (f" | أساسٌ {r['baseline']}→هدفٌ {r['target']} {r.get('unit', '')} | قِس بـ: {r['source'][:80]}" if 'baseline' in r else "") for r in d) or "لا إعادةَ قياسٍ مستحقّة")
        print("نجاحُ العصف حتى الآن:", success_rate())
    elif x.cmd == "quantify":
        quantify(x.n, x.baseline, x.target, x.unit, x.source)
        print("ok")
    else:
        result(x.n, x.achieved, x.note, actual=x.actual, confounders=x.confounders)
        print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
