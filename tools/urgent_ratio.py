#!/usr/bin/env python3
"""نسبة «العاجل» وتبريرُه — قراءةٌ فقط، لا تحجب شيئاً ولا ترفض وسماً (W-20261014-016).

نسبتان: (١) بطاقاتُ الدفتر urgent إلى كلّ ما بلغ published؛ (٢) الطلباتُ المدموجةُ الموسومةُ «نشر-عاجل» إلى المدموجة (gh) في آخر N.
ولكلّ وسمِ بطاقةٍ سببُه ومصدرُه (أمرُ المالك بتاريخه أو قرارٌ/حادثةٌ في الملاحظات) أو «بلا سبب». أمرُ المالك بالعاجل يُنفَّذ كما هو.

    python urgent_ratio.py [--last 100] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

LABEL = "نشر-عاجل"
REASON_RE = re.compile(r"أمر المالك|owner_order|حادثة|D-\d+م|عاجل بسبب|بسبب")


def card_reason(item: dict) -> tuple[str, str]:
    """(المصدر، السبب) أو ('', '') إن لم يوجد."""
    if item.get("owner_order"):
        return "أمر المالك", str(item["owner_order"])[:80]
    for n in item.get("notes", []):
        if REASON_RE.search(n.get("text", "")):
            return "ملاحظة", n["text"][:80]
    if item.get("origin") == "owner-order":
        return "أمر المالك", "origin=owner-order"
    return "", ""


def card_ratio(events: list[dict]) -> dict:
    items = ledger.reduce_state(events)
    base = [i for i in items.values() if i["state"] == "published"]
    urgent = [i for i in items.values() if i.get("urgent")]
    rows = []
    for it in sorted(urgent, key=lambda i: i["id"]):
        src, why = card_reason(it)
        rows.append({"id": it["id"], "state": it["state"], "source": src or "—", "reason": why or "بلا سبب"})
    return {"urgent": len(urgent), "published": len(base), "all_cards": len(items),
            "ratio_of_all": round(len(urgent) / len(items), 4) if items else 0.0,
            "without_reason": sum(1 for r in rows if r["reason"] == "بلا سبب"), "rows": rows}


REPO = "sh-school/shschool_mvp"


def gh_merged(last: int, repo: str = REPO) -> list[dict] | None:
    """آخر N طلبٍ مدموج بتسمياته؛ None إن غاب gh أو فشل (لا يكسر المخرج)."""
    try:
        proc = subprocess.run(["gh", "pr", "list", "-R", repo, "--state", "merged", "--limit", str(last), "--json", "number,labels"],
                              capture_output=True, encoding="utf-8", errors="replace", check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def pr_ratio(prs: list[dict] | None) -> dict:
    if prs is None:
        return {"available": False, "note": "gh غير متاح — نسبة الطلبات غير مقيسة"}
    urgent = [p["number"] for p in prs if LABEL in [lb.get("name") for lb in p.get("labels", [])]]
    return {"available": True, "merged": len(prs), "urgent": len(urgent),
            "ratio": round(len(urgent) / len(prs), 4) if prs else 0.0, "urgent_numbers": urgent}


def render(rep: dict) -> str:
    c, p = rep["cards"], rep["prs"]
    out = [f"بطاقات: عاجل {c['urgent']} من {c['all_cards']} ({c['ratio_of_all']:.1%}) · منشورة {c['published']} · بلا سبب {c['without_reason']}"]
    out.append(f"طلبات: عاجل {p['urgent']} من {p['merged']} ({p['ratio']:.0%})" if p["available"] else p["note"])
    out += [f"{r['id']} [{r['state']}] {r['source']} :: {r['reason']}" for r in c["rows"]]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=100)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = {"cards": card_ratio(ledger.load_events()), "prs": pr_ratio(gh_merged(a.last))}
    print(json.dumps(rep, ensure_ascii=False, indent=1) if a.json else render(rep))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
