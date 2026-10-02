#!/usr/bin/env python3
"""ملخّصُ إيداعات الجلسات آليّاً — لا يُسأل المالكُ ولا تُسأل الجلساتُ «هل أُبلغ المايسترو بالإيداع؟».

    python deposits_feed.py [--write] [--json] [--no-fetch] [--stale-hours 3]

يقرأ كلَّ شجرةِ عملٍ (git worktree) فيستخرج إيداعاتِها التي لم تبلغ origin/main، ويسندها إلى جلستها المسمّاة، ويربطها بطلب الدمج
المفتوح إن وُجد، ويقارنها بلقطةٍ سابقة (ledger/deposits_state.json) فيُبرز «الجديد منذ آخر تشغيل». الإيداعُ المحلّيُّ بلا طلبٍ يتجاوز
العتبةَ يُعلَّم «غيرُ مُسلَّم للمعاينة». --write يكتب deposits_auto.md (لا يُحرَّر يدويّاً).

قراءةٌ فقط للمستودع؛ يكتب لقطتَه وملفَّه في مجلّد المايسترو وحدَه.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import session_load_v2 as sl

ROOT = Path(__file__).resolve().parent.parent
DOHA = timezone(timedelta(hours=3))
STATE = ROOT / "ledger" / "deposits_state.json"
OUT = ROOT / "deposits_auto.md"


def commits_ahead(path: str, head: str, repo: Path, warn: list[str]) -> list[dict]:
    raw = sl.run("git", "log", "--format=%h|%ct|%s", "-n", "15", f"origin/main..{head}", cwd=repo, warn=warn)
    out = []
    for line in raw.splitlines():
        sha, ts, subject = (line.split("|", 2) + ["", ""])[:3]
        if sha and ts.isdigit():
            out.append({"sha": sha, "ts": int(ts), "subject": subject})
    return out


def collect(repo: Path, project: str, fetch: bool, stale_hours: float, now: float | None = None) -> dict:
    import branch_status as bs

    warn: list[str] = []
    now = now or time.time()
    names = sl.load_json("session_names.json", project)
    ignored = set(sl.DEFAULT_IGNORED) | set(sl.load_json("ignored_trees.json", project).get("trees", []))
    if fetch:
        sl.run("git", "fetch", "-q", "origin", "main", cwd=repo, warn=warn)
    by_branch = bs.prs_by_branch(repo, warn)
    if by_branch is None:
        warn.append("تعذّرت قراءةُ طلبات GitHub — حالاتُ الإيداعات غيرُ موثوقة")
        by_branch = {}
    contains = bs.git_contains(repo)
    merged = [p for rows in by_branch.values() for p in rows if p["state"] == "MERGED"]
    prev = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"seen": {}}
    seen_before = set(prev.get("seen", {}))
    rows = []
    for wt in sl.worktrees(repo, warn):
        tree = Path(wt["worktree"]).name
        if tree in ignored:
            continue
        ahead = len(sl.run("git", "rev-list", f"origin/main..{wt['HEAD']}", cwd=repo, warn=warn).split())
        dirty = len(sl.run("git", "--no-optional-locks", "-C", wt["worktree"], "status", "--porcelain").splitlines())
        own = by_branch.get(bs.branch_of(wt), [])
        result = bs.classify_tree(wt["HEAD"], bs.branch_of(wt), ahead, dirty, own, contains)
        if result["status"] == bs.NO_PR and ahead:  # قد يكون عملُها اندمج عبر طلب فرعٍ آخر
            result = bs.classify_tree(wt["HEAD"], bs.branch_of(wt), ahead, dirty, own, contains,
                                      elsewhere=bs.merged_elsewhere(repo, wt["HEAD"], merged, contains))
        status = result["status"]
        if status not in bs.PENDING and status != bs.OPEN_PR:
            continue  # اندمج عملُها أو لا إيداعَ — لا شيءَ يُبلَّغ
        cs = commits_ahead(wt["worktree"], wt["HEAD"], repo, warn)
        age_h = (now - min(c["ts"] for c in cs)) / 3600 if cs else 0.0
        open_prs = sorted(p["number"] for p in own if p["state"] == "OPEN")
        rows.append({
            "session": names.get(tree, tree), "named": tree in names, "tree": tree, "head": wt["HEAD"][:8],
            "pr": open_prs[0] if open_prs else None, "status": status, "label": bs.LABEL_AR.get(status, status),
            "commits": ahead, "dirty": dirty, "latest": cs[0]["subject"][:90] if cs else "—", "age_h": round(age_h, 1),
            "new": [c["sha"] for c in cs if c["sha"] not in seen_before],
            "stale_no_pr": status in bs.PENDING and age_h >= stale_hours,
        })
    rows.sort(key=lambda r: (not r["stale_no_pr"], -r["age_h"]))
    return {"generated_doha": datetime.fromtimestamp(now, DOHA).isoformat(timespec="minutes"), "rows": rows, "warnings": warn,
            "all_shas": {c: now for r in rows for c in r["new"]}, "prev_seen": prev.get("seen", {})}


def save_state(data: dict) -> None:
    seen = dict(data["prev_seen"])
    seen.update(data["all_shas"])
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"seen": seen}, ensure_ascii=False), encoding="utf-8")


def render(data: dict) -> str:
    rows = data["rows"]
    out = [f"## الإيداعات [آلي — الدوحة {data['generated_doha']}]", "",
           "| الجلسة | إيداعات | طلب الدمج | عمرُ أقدمها (س) | آخرُها | جديد؟ |", "|---|---|---|---|---|---|"]
    for r in rows:
        pr = f"#{r['pr']}" if r["pr"] else (f"⚠ {r.get('label', 'بلا طلب')} — غيرُ مُسلَّم للمعاينة" if r["stale_no_pr"] else r.get("label", "محلّيّ (بلا طلب)"))
        out.append(f"| {r['session'][:34]} | {r['commits']} | {pr} | {r['age_h']} | {r['latest']} | {'نعم (' + str(len(r['new'])) + ')' if r['new'] else '—'} |")
    if not rows:
        out.append("| — | لا إيداعَ معلَّق | | | | |")
    stale = [r["session"] for r in rows if r["stale_no_pr"]]
    out += ["", f"- إيداعاتٌ بلا طلبٍ تجاوزت العتبة: {stale or 'لا شيء'}"]
    for w in data["warnings"]:
        out.append(f"- ⚠ {w}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--repo", default="D:/shschool_mvp")
    ap.add_argument("--project", default="schoolos")
    ap.add_argument("--stale-hours", type=float, default=3.0)
    a = ap.parse_args()
    data = collect(Path(a.repo), a.project, not a.no_fetch, a.stale_hours)
    text = render(data)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.json:
        print(json.dumps({k: v for k, v in data.items() if k not in ("all_shas", "prev_seen")}, ensure_ascii=False))
    else:
        print(text)
    if a.write:
        OUT.write_text("# إيداعاتُ الجلسات (آلي — لا يُحرَّر يدويّاً)\n\n" + text, encoding="utf-8")
        save_state(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
