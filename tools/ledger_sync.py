#!/usr/bin/env python3
"""مزامنةُ الدفتر بعد الدمج والنشر في مشغّلٍ واحد (W-20261019-018) — عرضٌ افتراضيّاً و`--apply` للنقل.

يجمع publish_sync وpublish_auto وmerged_cards_sync: لكلّ بطاقةٍ approved/pushed/merged ولها رأسٌ يقابل طلباً مدموجاً (بالرأس نفسه)
في أحد المستودعات الموسومة أدناه، تُنقل بالتسلسل المسموح pushed ثمّ merged ثمّ published بلا قفز:
  - shschool_mvp: published فقط إن صار دمجُ الطلب داخل الإنتاج (/health/ وgh compare)، وإلا merged.
  - maestro-v2: لا إنتاج منفصل (الفرعُ الرئيسيّ هو المنتَج) فالطلبُ المدموج = published.
بطاقةٌ pushed بلا أيّ طلبٍ (مفتوحٍ أو مدموجٍ) بعد مهلةٍ **تُبلَّغ ولا تُحوَّل** (لا حالةَ بلا طلبٍ مدموج).
لا يدمج ولا يرسل ولا يفرض حالةً: غيابُ gh أو /health/ = غير مقيس ولا نقل. الإبلاغُ نصّاً مجمَّعاً لأداة الجلسات.

    python ledger_sync.py                 # عرض
    python ledger_sync.py --apply         # ينقل ويطبع الإبلاغ
    python ledger_sync.py --loop --interval 600 --apply   # للمراقبة بأداة Monitor
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import ledger
import publish_sync as ps

# (slug, بحثٌ عن الإنتاج): الإنتاجُ المنفصل لـshschool_mvp وحدَه
REPOS = (("sh-school/shschool_mvp", True), ("mesuef1974/maestro-v2", False))
ORPHAN_AFTER = timedelta(hours=2)
ROOT_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent  # مجلّد الجذر الحيّ الذي تعمل منه الجلسات
CHAIN = ps.CHAIN
ORDER = ("approved", *CHAIN)


def fetch_prs(slug: str, state: str, limit: int, gh=ps._gh) -> dict[str, dict]:
    """رأس الطلب (8 أحرف) → {number, merge, at} لطلبات المستودع بالحالة المعطاة (merged|open)."""
    rows = json.loads(
        gh(
            [
                "pr",
                "list",
                "--repo",
                slug,
                "--state",
                state,
                "--limit",
                str(limit),
                "--json",
                "number,headRefOid,mergeCommit,mergedAt",
            ]
        )
    )
    return {
        r["headRefOid"][:8]: {
            "number": r["number"],
            "merge": (r.get("mergeCommit") or {}).get("oid", ""),
            "at": r.get("mergedAt") or "",
        }
        for r in rows
    }


def root_live(merge_oid: str, root: str | None = None, run=None) -> bool:
    """(W-20261027-003) دمجُ طلبٍ في maestro-v2 «حيٌّ» فقط إن كان سلفاً لرأس الجذر الذي تعمل منه الجلسات؛ commit مجهولٌ محلّياً = غير حيّ."""
    if not merge_oid:
        return False
    cmd = ["git", "merge-base", "--is-ancestor", merge_oid, "HEAD"]
    if run is not None:
        return run(cmd, root or str(ROOT_DIR)) == 0
    try:
        return subprocess.run(cmd, cwd=root or str(ROOT_DIR), capture_output=True, timeout=30, check=False).returncode == 0  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return False


def target_for(
    slug_prod: bool, pr: dict, prod: str | None, check=ps.in_production, live=None
) -> str | None:
    """الحالةُ الهدف: published إن دمجُه داخل الإنتاج (shschool) أو حيٌّ في الجذر (maestro-v2، `live`)؛ merged إن دُمج ولم يصل؛ وإلا None."""
    if not pr:
        return None
    if not slug_prod:
        return "published" if live and live(pr["merge"]) else "merged"
    return "published" if prod and check(pr["merge"], prod) else "merged"


def plan(
    states: dict,
    merged: dict[str, dict[str, dict]],
    prod: str | None,
    check=ps.in_production,
    live=None,
) -> list[dict]:
    """صفوفُ النقل: {id, state, target, head, pr, slug, merge} لما حالتُه أدنى من هدفه، بلا قفز (النقلُ بالسلسلة)."""
    rows = []
    for cid, st in sorted(states.items()):
        if st.get("state") not in ps.PENDING:
            continue
        head = ps.card_head(st)
        if not head:
            continue
        for slug, has_prod in REPOS:
            pr = merged.get(slug, {}).get(head)
            target = target_for(has_prod, pr, prod, check, live)
            if target and ORDER.index(st["state"]) < ORDER.index(target):
                rows.append(
                    {
                        "id": cid,
                        "state": st["state"],
                        "target": target,
                        "head": head,
                        "pr": pr["number"],
                        "slug": slug,
                        "merge": pr["merge"][:9],
                        "at": pr.get("at", ""),
                    }
                )
                break
    return rows


def steps(row: dict) -> list[str]:
    """خطواتُ السلسلة من حالة البطاقة إلى هدفها شاملةً الهدف."""
    start = CHAIN.index(row["state"]) + 1 if row["state"] in CHAIN else 0
    end = CHAIN.index(row["target"]) + 1
    return list(CHAIN[start:end])


def orphans(
    states: dict,
    events: list[dict],
    open_prs: dict[str, dict[str, dict]],
    merged: dict[str, dict[str, dict]],
    now: datetime,
) -> list[dict]:
    """بطاقاتُ pushed بلا طلبٍ مفتوحٍ أو مدموجٍ بعد المهلة: تُبلَّغ ولا تُحوَّل."""
    last_ts: dict[str, str] = {}
    for ev in events:
        if ev["kind"] == "state" and ev["data"].get("state") == "pushed":
            last_ts[ev["id"]] = ev["ts"]
    out = []
    for cid, st in sorted(states.items()):
        if st.get("state") != "pushed":
            continue
        head = ps.card_head(st)
        if any(head in (open_prs.get(s, {}) | merged.get(s, {})) for s, _ in REPOS):
            continue
        try:
            age = now - datetime.fromisoformat(last_ts[cid])
        except (KeyError, ValueError):
            continue
        if age >= ORPHAN_AFTER:
            out.append(
                {
                    "id": cid,
                    "head": head,
                    "hours": int(age.total_seconds() // 3600),
                    "held_by": st.get("held_by") or "",
                }
            )
    return out


def queue_rows(states: dict, merged: dict[str, dict[str, dict]]) -> list[dict]:
    """سطورُ طابور الخارطة (W-20261023-014): لكلّ بطاقةٍ رأسُها (approved…published) يقابل طلباً مدموجاً؛ الحقيقةُ الدفترُ وgh لا رسالةٌ.
    تُلحَق بلا تكرار (roadmap_queue.enqueue) فيعاد الحسابُ كلَّ دورةٍ ويلتقط ما سقط سابقاً."""
    rows = []
    for cid, st in sorted(states.items()):
        if st.get("state") not in ORDER:
            continue
        head = ps.card_head(st)
        if not head:
            continue
        for slug, _ in REPOS:
            pr = merged.get(slug, {}).get(head)
            if pr:
                rows.append({"pr": pr["number"], "repo": slug, "card": cid, "commit": pr["merge"][:8], "merged_at": pr.get("at", "")})
                break
    return rows


def enqueue_roadmap(rows: list[dict], enqueue=None) -> list[str]:
    import roadmap_queue as rq

    add = enqueue or rq.enqueue
    return [f"{r['card']} #{r['pr']} ({r['repo'].split('/')[1]})" for r in rows if add(r)]


def apply_rows(rows: list[dict], prod: str | None, move=None) -> list[str]:
    """ينقل كلَّ صفٍّ بالتسلسل؛ فشلُ بطاقةٍ يُسجَّل ولا يوقف الباقي. لا `by` (لا ينتحل 0601)."""
    move = move or ledger.move
    done = []
    for r in rows:
        why = (
            f"آلياً (ledger_sync) — #{r['pr']} مدموج {r['merge']} في {r['slug']}"
            + (f" وقتَ دمجِه الفعليّ في GitHub {r['at']}" if r.get("at") else "")
            + (
                f" ومنشور {prod[:7]}"
                if r["target"] == "published"
                and prod
                and r["slug"].endswith("shschool_mvp")
                else ""
            )
        )
        try:
            for step in steps(r):
                kw = {"waive_remote_check": why} if step == "pushed" else {}
                move(r["id"], step, note=why if step == r["target"] else None, **kw)
            done.append(f"{r['id']} ← {r['target']} (#{r['pr']})")
        except ledger.LedgerError as exc:
            done.append(f"{r['id']} ✘ {exc}")
    return done


def report(rows: list[dict], orph: list[dict]) -> list[str]:
    lines = []
    if rows:
        lines.append(
            "نُقلت/تُنقل: "
            + "، ".join(f"{r['id']} ← {r['target']} (#{r['pr']})" for r in rows)
        )
    if orph:
        lines.append(
            "pushed بلا طلب (لم تُحوَّل، افتحوا الطلب أو أعيدوا البطاقة): "
            + "، ".join(
                f"{o['id']} ({o['hours']}س"
                + (f"، {o['held_by']}" if o["held_by"] else "")
                + ")"
                for o in orph
            )
        )
    return lines


def cycle(apply: bool, limit: int, commit: str | None = None) -> int:
    try:
        prod = commit
        if not prod:
            try:
                prod = ps.fetch_health()
            except ps.SyncError as exc:
                print(
                    f"# غير مقيس (الإنتاج): {exc} — تُنقل بطاقاتُ المستودعات بلا إنتاجٍ وحدَها إلى merged/published",
                    file=sys.stderr,
                )
        merged = {s: fetch_prs(s, "merged", limit) for s, _ in REPOS}
        open_prs = {s: fetch_prs(s, "open", limit) for s, _ in REPOS}
        events = ledger.load_events()
        states = ledger.reduce_state(events)
    except ps.SyncError as exc:
        print(f"✘ غير مقيس: {exc} — لا نقل", file=sys.stderr)
        return 2
    rows = plan(states, merged, prod, live=root_live)
    orph = orphans(
        states, events, open_prs, merged, datetime.now(timezone(timedelta(hours=3)))
    )
    print(
        f"الإنتاج {(prod or '—')[:7]} — {len(rows)} بطاقة للنقل، {len(orph)} pushed بلا طلب"
    )
    for r in rows:
        print(
            f"  {r['id']} ({r['state']}→{r['target']}) #{r['pr']} {r['slug'].split('/')[1]} رأس {r['head']}"
        )
    if apply:
        for line in apply_rows(rows, prod):
            print("  " + line)
        queued = enqueue_roadmap(queue_rows(ledger.reduce_state(ledger.load_events()), merged))
        if queued:
            print(f"  طابورُ الخارطة: أُلحق {len(queued)}: " + "؛ ".join(queued[:8]))
    elif rows:
        print("عرض فقط — أضف --apply للنقل")
    for line in report(rows, orph):
        print("إبلاغ: " + line)
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--commit", help="بدل قراءة /health/")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=600)
    a = ap.parse_args(argv)
    while True:
        rc = cycle(a.apply, a.limit, a.commit)
        if not a.loop:
            return rc
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
