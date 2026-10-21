#!/usr/bin/env python3
"""تسجيلُ زمن pushed/merged من GitHub لا من الإدخال (W-20261020-014) — بلا تعديل ledger.py.

    python ledger_at_github.py show <state> --head <sha8> [--branch <فرع>]      # يطبع الزمن فقط
    python ledger_at_github.py record <البطاقة> <state> --head <sha8> --by <رقم> [--branch <فرع>]

`record` يضيف حدثَ `update` جديداً (append-only) فيه at وat_source وstate؛ لا يمسّ حالةً ولا اعتماداً،
ويُقرأ الزمنُ المصحَّح بـ`corrected_times`. pushed = أوّلُ دفعٍ بلغ بالفرع الرأسَ؛ merged = mergedAt للطلب المدموج.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

import ledger

SLUG = "sh-school/shschool_mvp"


def _gh(args: list[str]):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")  # noqa: S603,S607
    if p.returncode:
        raise ledger.LedgerError("فشل gh: " + (p.stderr or "").strip()[:160])
    return json.loads(p.stdout or "[]")


def github_time(state: str, head: str, branch: str | None = None, fetch=None) -> str:
    if state not in ("pushed", "merged"):
        raise ledger.LedgerError("pushed وmerged فقط")
    get = fetch or _gh
    if state == "merged":
        prs = get(["pr", "list", "--repo", SLUG, "--state", "merged", "--search", head,
                   "--json", "headRefOid,mergedAt", "--limit", "20"])
        hits = [x for x in prs if x["headRefOid"].startswith(head) and x.get("mergedAt")]
        if not hits:
            raise ledger.LedgerError(f"لا طلبَ مدموجاً برأس {head}")
        raw = hits[0]["mergedAt"]
    else:
        if not branch:
            raise ledger.LedgerError("pushed يلزمه --branch")
        acts = get(["api", f"repos/{SLUG}/activity?ref=refs/heads/{branch}&activity_type=push&per_page=100"])
        times = sorted(a["timestamp"] for a in acts if str(a.get("after", "")).startswith(head))
        if not times:
            raise ledger.LedgerError(f"لا دفعَ مسجَّلاً للفرع {branch} برأس {head}")
        raw = times[0]
    return ledger.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(ledger.DOHA).isoformat(timespec="seconds")


def record(card: str, state: str, head: str, by: str, branch: str | None = None, fetch=None, path=None) -> str:
    items = ledger.reduce_state(ledger.load_events(path))
    if card not in items:
        raise ledger.LedgerError(f"بطاقةٌ غيرُ موجودة: {card}")
    at = github_time(state, head, branch or items[card].get("branch"), fetch)
    ledger.append_event("update", card, {"at_github": {"state": state, "at": at, "head": head, "by": by}}, path)
    return at


def corrected_times(events: list[dict]) -> dict[str, dict[str, str]]:
    """{بطاقة: {state: at}} من أحداث at_github (الأخيرُ يغلب)."""
    out: dict[str, dict[str, str]] = {}
    for e in events:
        g = e["data"].get("at_github") if e["kind"] == "update" else None
        if g:
            out.setdefault(e["id"], {})[g["state"]] = g["at"]
    return out


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap =argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("state")
    s.add_argument("--head", required=True)
    s.add_argument("--branch")
    r = sub.add_parser("record")
    r.add_argument("card")
    r.add_argument("state")
    r.add_argument("--head", required=True)
    r.add_argument("--by", required=True)
    r.add_argument("--branch")
    a = ap.parse_args(argv)
    try:
        print(github_time(a.state, a.head, a.branch) if a.cmd == "show" else record(a.card, a.state, a.head, a.by, a.branch))
    except ledger.LedgerError as e:
        print(f"✘ {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
