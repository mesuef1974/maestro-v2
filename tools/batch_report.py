#!/usr/bin/env python3
"""تقريرُ الدفعة المولَّد HTML وJSON من الدفتر وgh (W-20261016-028) — لا رقمَ يدويّ ولا نقلَ من رسالة.

    python batch_report.py [--days 7] [--out handover_notes/batch_report]   # يكتب .json و.html بالأرقام نفسها

الأرقام: بطاقاتٌ برؤوسها واعتماداتها وطلباتها، ومؤشراتٌ أربعة: وسيط «جاهز←اعتماد» والمئين 90 (من ready_approve_baseline)،
عددُ إعادات الاعتماد (من reapproval_causes)، وطابورُ المالك (بطاقاتٌ جاهزةٌ لم تُعتمد). لا حسابَ مكرَّراً.
المطابقةُ بين الطلب والبطاقة **بالرمز الصريح** W-YYYYMMDD-NNN في عنوان الطلب أو وصفه أو اسم فرعه فقط — لا بالرأس ولا بالقرب
(منعاً لخطأ #913 و#940). طلبٌ بلا رمزٍ لا يُنسب لبطاقة. وما لا يُقاس يظهر «غير مقيس».
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import ledger
import publish_sync as ps
import ready_approve_baseline as rab
import reapproval_causes as rc

CODE_RE = re.compile(r"\bW-\d{8}-\d{3}\b")
UNMEASURED = "غير مقيس"
ROOT = Path(__file__).resolve().parent.parent

DEFINITIONS = {
    "ready_to_approve_median_h": "وسيطُ الساعات من «جاهزٌ للمعاينة» إلى اعتماد المالك — نصفُ البطاقات اعتُمدت أسرع منه.",
    "ready_to_approve_p90_h": "المئين 90 لزمن الانتظار نفسِه — تسعٌ من كلّ عشر بطاقاتٍ اعتُمدت خلال هذا الزمن أو أقلّ.",
    "reapprovals": "عددُ البطاقات التي اعتُمد رأسُها ثمّ اعتُمد رأسٌ مختلفٌ لها (إيداعٌ بعد الاعتماد).",
    "owner_queue": "بطاقاتٌ بحالة «جاهزٌ للمعاينة» تنتظر اعتمادَ المالك الآن.",
}


def explicit_code(pr: dict) -> str | None:
    """رمزُ البطاقة الصريحُ الوحيد في الطلب؛ لا رمزَ أو أكثرُ من رمزٍ مختلف = لا نسب."""
    text = " ".join(str(pr.get(k) or "") for k in ("title", "body", "headRefName"))
    codes = set(CODE_RE.findall(text))
    return codes.pop() if len(codes) == 1 else None


def match_prs(prs: list[dict]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for pr in prs:
        code = explicit_code(pr)
        if code:
            out.setdefault(code, []).append(pr["number"])
    return out


def indicators(events: list[dict], states: dict[str, dict], days: int, now: datetime, reapprovals: int | None) -> dict:
    res = rab.report(events, [days], now)
    win = res["windows"][str(days)]
    return {
        "window_days": days,
        "ready_to_approve_median_h": win.get("median", UNMEASURED),
        "ready_to_approve_p90_h": win.get("p90", UNMEASURED),
        "ready_to_approve_n": win.get("n", 0),
        "coverage": res["coverage"],
        "reapprovals": reapprovals if reapprovals is not None else UNMEASURED,
        "owner_queue": sum(1 for s in states.values() if s.get("state") == "ready_for_review"),
    }


def build(events: list[dict], prs: list[dict] | None, days: int = 7, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    states = ledger.reduce_state(events)
    by_card = match_prs(prs) if prs is not None else None
    cards = []
    for cid, st in sorted(states.items()):
        if st.get("state") in {"captured", "verified", "deferred", "closed"}:
            continue
        cards.append({
            "id": cid,
            "state": st.get("state"),
            "head": (st.get("head") or "")[:8] or UNMEASURED,
            "approved_head": (st.get("approved_head") or "")[:8] or UNMEASURED,
            "approvals": len(st.get("approvals") or []),
            "prs": (by_card.get(cid, []) if by_card is not None else UNMEASURED),
        })
    reapprovals = len({c for c, _o, _n in rc.pairs(events)})
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "prs_source": "gh" if prs is not None else UNMEASURED,
        "cards": cards,
        "indicators": indicators(events, states, days, now, reapprovals),
        "definitions": DEFINITIONS,
    }


def render_html(rep: dict) -> str:
    e = html.escape
    ind = rep["indicators"]
    def prs_text(prs) -> str:
        return "، ".join(f"#{n}" for n in prs) if isinstance(prs, list) else str(prs)

    rows = "".join(
        f"<tr><td>{e(c['id'])}</td><td>{e(str(c['state']))}</td><td>{e(c['head'])}</td><td>{e(c['approved_head'])}</td>"
        f"<td>{c['approvals']}</td><td>{e(prs_text(c['prs']))}</td></tr>"
        for c in rep["cards"]
    )
    cards_ind = "".join(
        f"<div class='k'><b>{e(str(ind[k]))}</b><span>{e(DEFINITIONS[k])}</span></div>"
        for k in ("ready_to_approve_median_h", "ready_to_approve_p90_h", "reapprovals", "owner_queue")
    )
    cov = ind["coverage"]
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>تقرير الدفعة</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:Tahoma,sans-serif;margin:1rem;padding-inline:1rem;line-height:1.7}}
.k{{display:grid;gap:.2rem;border:1px solid #8884;border-radius:8px;padding:.6rem;margin-block:.5rem}}
.k b{{font-size:1.4rem}} table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #8884;padding:.3rem;text-align:start}}
</style></head><body>
<h1>تقرير الدفعة</h1>
<p>وُلِّد آلياً من الدفتر وgh في {e(rep['generated_at'])} (نافذة {ind['window_days']} أيام). مصدرُ الطلبات: {e(rep['prs_source'])}.</p>
<h2>المؤشرات</h2>{cards_ind}
<p>تغطية «جاهز←اعتماد»: {cov['with_ready']} من {cov['approved']} معتمَدة؛ لا يُعمَّم.</p>
<h2>البطاقات</h2>
<table><thead><tr><th>البطاقة</th><th>الحالة</th><th>الرأس</th><th>رأس الاعتماد</th><th>الاعتمادات</th><th>الطلبات (برمزٍ صريح)</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>
"""


def fetch_prs(limit: int) -> list[dict] | None:
    try:
        return json.loads(
            ps._gh(["pr", "list", "--repo", ps.SLUG, "--state", "all", "--limit", str(limit),
                    "--json", "number,title,body,headRefName"])
        )
    except Exception:  # gh غائب: الطلبات «غير مقيس»
        return None


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--out", default=str(ROOT / "handover_notes" / "batch_report"))
    a = ap.parse_args(argv)
    rep = build(ledger.load_events(), fetch_prs(a.limit), a.days)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".html").write_text(render_html(rep), encoding="utf-8")
    print(f"كُتب {out.with_suffix('.json')} و{out.with_suffix('.html')} — {len(rep['cards'])} بطاقة، الطلبات: {rep['prs_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
