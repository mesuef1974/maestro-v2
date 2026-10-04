#!/usr/bin/env python3
"""تسويةٌ أسبوعيّةٌ بين تنبيهات code-scanning المغلقة في GitHub وبطاقات الدفتر المفتوحة التي تذكر رقمَ التنبيه — قراءةٌ فقط.

تُخرج قائمةَ بطاقاتٍ مفتوحةٍ لتنبيهٍ مغلق «للمراجعة»؛ ولا تعدّل الدفترَ ولا تغلق شيئاً (الإغلاقُ بقرار صاحب البطاقة بعد التحقّق من المصدر).

    python alert_reconcile.py --repo OWNER/REPO
    python alert_reconcile.py --alerts-json alerts.json     # بلا شبكة
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAESTRO = Path(os.environ.get("MAESTRO_HOME", "C:/Users/mesue/delivery_manager_work"))
sys.path.insert(0, str(MAESTRO / "tools"))

FINAL = {"closed", "merged", "published", "deferred"}
# «تنبيه #106» أو «alert #106» أو «#106» بعد كلمة تنبيه/فحص الشيفرة؛ نتجنّب أرقامَ طلبات الدمج (#725) بشرط وجود كلمة تنبيه قريبة
_REF = re.compile(r"(?:تنبيه(?:ُ|ات)?(?:\s+فحص\s+الشيفرة)?|alert|code[- ]?scanning)[^#\n]{0,40}((?:#\d+[\s,،/و]*)+)", re.IGNORECASE)
_NUM = re.compile(r"#(\d+)")


def alert_numbers(text: str) -> set[int]:
    """أرقامُ التنبيهات المذكورةُ في نصّ بطاقة (#106 و#110 بعد كلمة تنبيه)."""
    out: set[int] = set()
    for m in _REF.finditer(text or ""):
        out |= {int(n) for n in _NUM.findall(m.group(1))}
    return out


def item_text(item: dict) -> str:
    parts = [item.get(k, "") for k in ("problem", "impact", "accept")]
    parts += [n.get("text", "") for n in item.get("notes", [])]
    return "\n".join(p for p in parts if isinstance(p, str))


def fetch_closed_alerts(repo: str, runner=subprocess.run) -> list[dict]:
    """تنبيهاتُ code-scanning المغلقة عبر gh api (قابلٌ للحقن في الاختبارات بـrunner)."""
    proc = runner(["gh", "api", "--paginate", f"repos/{repo}/code-scanning/alerts?state=dismissed&per_page=100"],
                  capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    out = _load_pages(proc.stdout) if proc.returncode == 0 else None
    proc2 = runner(["gh", "api", "--paginate", f"repos/{repo}/code-scanning/alerts?state=fixed&per_page=100"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    fixed = _load_pages(proc2.stdout) if proc2.returncode == 0 else None
    if out is None and fixed is None:
        raise RuntimeError(f"تعذّر جلبُ التنبيهات: {proc.stderr.strip() or proc2.stderr.strip()}")
    return (out or []) + (fixed or [])


def _load_pages(text: str) -> list[dict]:
    """gh --paginate يلصق مصفوفاتٍ متتاليةً «][» أحياناً؛ نفصلها."""
    text = (text or "").strip()
    if not text:
        return []
    decoder, pos, rows = json.JSONDecoder(), 0, []
    while pos < len(text):
        obj, end = decoder.raw_decode(text, pos)
        rows += obj if isinstance(obj, list) else [obj]
        pos = end
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return rows


def reconcile(items: dict[str, dict], alerts: list[dict]) -> list[dict]:
    """بطاقاتٌ غيرُ منتهيةٍ تذكر تنبيهاً مغلقاً — للمراجعة فقط."""
    closed = {a["number"]: a for a in alerts if a.get("state") in ("dismissed", "fixed")}
    out = []
    for item in items.values():
        if item.get("state") in FINAL:
            continue
        for n in sorted(alert_numbers(item_text(item)) & set(closed)):
            a = closed[n]
            out.append({"card": item["id"], "card_state": item.get("state"), "alert": n, "alert_state": a["state"],
                        "rule": (a.get("rule") or {}).get("id", ""), "closed_at": a.get("fixed_at") or a.get("dismissed_at") or "",
                        "dismissed_reason": a.get("dismissed_reason") or "",
                        "action": "للمراجعة: تحقّق من المصدر ثمّ أغلق البطاقة أو أعِد فتحَ التنبيه"})
    return sorted(out, key=lambda r: (r["card"], r["alert"]))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--alerts-json", help="ملفُّ تنبيهاتٍ جاهز بدل gh api")
    args = ap.parse_args()
    import ledger
    if args.alerts_json:
        alerts = _load_pages(Path(args.alerts_json).read_text(encoding="utf-8"))
    elif args.repo:
        alerts = fetch_closed_alerts(args.repo)
    else:
        sys.exit("حدّد --repo OWNER/REPO أو --alerts-json")
    rows = reconcile(ledger.reduce_state(ledger.load_events()), alerts)
    print(json.dumps({"checked_alerts": len(alerts), "for_review": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
