#!/usr/bin/env python3
"""لقطةُ حِمل الجلسات v2 — مقترَحٌ يُصلح عيوبَ session_load.py (لم يُطبَّق على الأصل).

قراءةٌ فقط على الأشجار؛ الكتابةُ الوحيدة `git fetch` لمرجع origin/main (يُعطَّل بـ --no-fetch).

ما تغيّر عن الأصل:
  1) نسبةُ الطلب إلى جلسته: رأسُ الطلب أسلافُ رأس الشجرة **أو** موجودٌ في reflog الشجرة (فمن عنده ستّةُ طلباتٍ
     مستقلّةٍ يظهر بستّة لا بواحد)؛ وملفُّ pr_owner_overrides.json يحسم الاستثناءات.
  2) «اليوم/أمس» بتوقيت الدوحة (UTC+3) لا UTC.
  3) «مثقلة» = ≥ حدِّ الطلبات المفتوحة **أو** ≥ حدِّ السياق (كما في نموذج التشغيل)، ومعها «فوق WIP» (> حدّ العمل الجاري).
  4) أسماءُ الجلسات من session_names.json لا من قاموسٍ في الشيفرة؛ وما لم يُطابَق يُبلَّغ عنه.
  5) فشلُ gh أو git لا يمرّ صامتاً ولا يُسقط الأداة: تحذيرٌ على stderr وحقلٌ في المخرجات.
  6) استدعاءٌ واحدٌ لكلّ شجرةٍ بدل استدعاءٍ لكلّ زوجِ (طلب × شجرة).

    python session_load_v2.py [--json] [--no-fetch] [--repo D:/shschool_mvp] [--wip-limit 3] [--heavy-mb 40]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DOHA = timezone(timedelta(hours=3))
HERE = Path(__file__).resolve().parent
PROJECTS = HERE.parent / "projects"
TRANSCRIPTS = Path("C:/Users/mesue/.claude/projects")
REFLOG_DEPTH = 400
DEFAULT_IGNORED = ("main-preview", "integration-preview")
TS_RE = re.compile(rb'"timestamp":"(\d{4}-\d\d-\d\dT\d\d)')


# ---------- دوالُّ الحساب (نقيّة، مختبَرة) ----------


def doha_day(hour_prefix: str, _cache: dict[str, date] = {}) -> date:  # noqa: B006 — ذاكرةٌ مقصودة
    """'YYYY-MM-DDTHH' (UTC) ← يومُ الدوحة (UTC+3)."""
    got = _cache.get(hour_prefix)
    if got is None:
        utc = datetime.strptime(hour_prefix, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
        got = _cache[hour_prefix] = utc.astimezone(DOHA).date()
    return got


def count_events(prefixes, today: date) -> tuple[int, int]:
    """يعدّ الأحداثَ (نُسخةَ الساعة UTC لكلّ سطر) ليومِ الدوحة اليوم وأمس."""
    yesterday = today - timedelta(days=1)
    n_today = n_yest = 0
    for prefix in prefixes:
        day = doha_day(prefix)
        if day == today:
            n_today += 1
        elif day == yesterday:
            n_yest += 1
    return n_today, n_yest


def attribute_prs(prs: list[dict], trees: list[dict], overrides: dict[str, str]) -> dict[int, str | None]:
    """يُنسب كلُّ طلبٍ إلى شجرةٍ واحدة (أو None).

    الأولويّة: الاستثناءُ اليدويّ ← الأقربُ في reflog الشجرة (الأحدثُ زيارةً) ← أسلافُ رأس الشجرة (ahead).
    كلُّ شجرةٍ في trees: {"name": ..., "ahead": set[str], "reflog": list[str]}.
    """
    out: dict[int, str | None] = {}
    for pr in prs:
        num, sha = pr["number"], pr["headRefOid"]
        if str(num) in overrides:
            out[num] = overrides[str(num)]
            continue
        best: tuple[int, int, str] | None = None
        for tree in trees:
            if sha in tree["reflog"]:
                cand = (0, tree["reflog"].index(sha), tree["name"])
            elif sha in tree["ahead"]:
                cand = (1, 0, tree["name"])
            else:
                continue
            if best is None or cand < best:
                best = cand
        out[num] = best[2] if best else None
    return out


def classify(row: dict, wip_limit: int, heavy_mb: int) -> dict:
    """يضيف حقولَ التصنيف: over_wip / heavy / overloaded / assignable (تعريفُ operating_model §2)."""
    over_wip = row["open_prs"] > wip_limit
    heavy = row["context_mb"] >= heavy_mb
    # «مثقلة» = ≥ 4 طلباتٍ مفتوحة أو سياقٌ ≥ الحدّ؛ 4 = wip_limit + 1 (الحدُّ 3 كما في الملفّ المرجعيّ)
    overloaded = row["open_prs"] >= wip_limit + 1 or heavy
    return {**row, "over_wip": over_wip, "heavy": heavy, "overloaded": overloaded, "assignable": not overloaded}


# ---------- الاستدعاءات الخارجيّة (تُبلِّغ فشلَها) ----------


def run(*args: str, cwd: Path | str | None = None, warn: list[str] | None = None) -> str:
    proc = subprocess.run(list(args), cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0 and warn is not None:
        warn.append(f"{' '.join(args[:3])}… رجع {proc.returncode}: {proc.stderr.strip()[:160]}")
    return proc.stdout.strip()


def worktrees(repo: Path, warn: list[str]) -> list[dict]:
    found, cur = [], {}
    for line in run("git", "worktree", "list", "--porcelain", cwd=repo, warn=warn).splitlines() + [""]:
        if not line:
            path = cur.get("worktree", "").replace("\\", "/")
            if path and "/.claude/worktrees/" in path and "HEAD" in cur and Path(path).is_dir():
                found.append(cur)
            cur = {}
        elif " " in line:
            key, value = line.split(" ", 1)
            cur[key] = value
    return found


def open_prs(repo: Path, warn: list[str]) -> list[dict] | None:
    raw = run(
        "gh", "pr", "list", "--state", "open", "--limit", "200",
        "--json", "number,headRefOid,isDraft,title,author", cwd=repo, warn=warn,
    )
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        warn.append("gh pr list لم يُرجع JSON صالحاً — عدّاداتُ الطلبات غيرُ موثوقة")
        return None


def transcript_stats(name: str, today: date) -> tuple[int, int, int]:
    folder = TRANSCRIPTS / f"D--shschool-mvp--claude-worktrees-{name}"
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    if not files:
        return 0, 0, 0
    newest = files[-1]
    with newest.open("rb") as fh:
        prefixes = (m.group(1).decode() for line in fh if (m := TS_RE.search(line)))
        n_today, n_yest = count_events(prefixes, today)
    return newest.stat().st_size // 1048576, n_today, n_yest


def load_json(name: str, project: str = "schoolos") -> dict:
    path = PROJECTS / project / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


# ---------- الأصل ----------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--repo", default="D:/shschool_mvp")
    ap.add_argument("--wip-limit", type=int, default=3)
    ap.add_argument("--heavy-mb", type=int, default=40)
    ap.add_argument("--project", default="schoolos", help="مجلّدُ ملفّ المشروع تحت projects/")
    args = ap.parse_args()

    repo, warn = Path(args.repo), []
    names, overrides = load_json("session_names.json", args.project), load_json("pr_owner_overrides.json", args.project)
    ignored = set(DEFAULT_IGNORED) | set(load_json("ignored_trees.json", args.project).get("trees", []))
    today = datetime.now(DOHA).date()
    if not args.no_fetch:
        run("git", "fetch", "-q", "origin", "main", cwd=repo, warn=warn)
    prs = open_prs(repo, warn)

    trees = []
    for wt in worktrees(repo, warn):
        name = Path(wt["worktree"]).name
        if name in ignored:  # أشجارُ البنية (المعاينة والتكامل) تضمّ رؤوسَ الجميع فتسرق نسبةَ الطلبات
            continue
        ahead = set(run("git", "rev-list", f"origin/main..{wt['HEAD']}", cwd=repo, warn=warn).split())
        reflog = run("git", "-C", wt["worktree"], "reflog", "--format=%H", "-n", str(REFLOG_DEPTH)).split()
        dirty = len(run("git", "--no-optional-locks", "-C", wt["worktree"], "status", "--porcelain").splitlines())
        trees.append({"name": name, "ahead": ahead, "reflog": reflog, "dirty": dirty, "head": wt["HEAD"]})

    owner = attribute_prs(prs or [], trees, overrides)
    by_tree: dict[str, list[dict]] = {t["name"]: [] for t in trees}
    unowned = []
    for pr in prs or []:
        (by_tree[owner[pr["number"]]] if owner[pr["number"]] else unowned).append(pr)

    rows = []
    for tree in trees:
        mine = by_tree[tree["name"]]
        size_mb, ev_today, ev_yest = transcript_stats(tree["name"], today)
        rows.append(
            classify(
                {
                    "session": names.get(tree["name"], tree["name"]),
                    "named": tree["name"] in names,
                    "tree": tree["name"],
                    "open_prs": len(mine),
                    "draft_prs": sum(1 for p in mine if p["isDraft"]),
                    "pr_numbers": sorted(p["number"] for p in mine),
                    "unmerged_commits": len(tree["ahead"]),
                    "dirty_files": tree["dirty"],
                    "context_mb": size_mb,
                    "events_today": ev_today,
                    "events_yesterday": ev_yest,
                },
                args.wip_limit,
                args.heavy_mb,
            )
        )
    for r in rows:  # شجرةٌ بلا جلسةٍ مسمّاة (يتيمة أو هذه الجلسة) لا تُعرض صالحةً للإسناد
        r["assignable"] = r["assignable"] and r["named"]
    rows.sort(key=lambda r: (-r["open_prs"], -r["events_today"]))

    result = {
        "generated_doha": datetime.now(DOHA).isoformat(timespec="minutes"),
        "wip_limit": args.wip_limit,
        "heavy_mb": args.heavy_mb,
        "open_prs_total": None if prs is None else len(prs),
        "unowned_prs": [p["number"] for p in unowned],
        "unnamed_trees": [r["tree"] for r in rows if not r["named"]],
        "warnings": warn,
        "sessions": rows,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"لقطةُ حِمل الجلسات — الدوحة {result['generated_doha']} | WIP≤{args.wip_limit} | ثقيل≥{args.heavy_mb}MB")
    print(f"{'الجلسة':<34} {'PR':>3} {'إيداعات':>7} {'معدَّل':>6} {'MB':>4} {'اليوم':>6} {'أمس':>6}  الحالة")
    for r in rows:
        flags = " ".join(f for f, on in (("فوق-WIP", r["over_wip"]), ("ثقيل", r["heavy"]), ("مثقلة", r["overloaded"])) if on)
        prs_txt = ("  #" + ",#".join(map(str, r["pr_numbers"]))) if r["pr_numbers"] else ""
        print(
            f"{r['session'][:34]:<34} {r['open_prs']:>3} {r['unmerged_commits']:>7} {r['dirty_files']:>6} "
            f"{r['context_mb']:>4} {r['events_today']:>6} {r['events_yesterday']:>6}  {flags}{prs_txt}"
        )
    ok = [r["session"] for r in rows if r["assignable"]]
    print(f"\nلا إسنادَ جديداً: {[r['session'] for r in rows if r['overloaded']] or 'لا أحد'}")
    print(f"صالحةٌ للإسناد ({len(ok)}): {', '.join(ok) or '—'}")
    if unowned:
        print(f"طلباتٌ بلا صاحب (آليّةٌ أو غيرُ منسوبة): {[p['number'] for p in unowned]}")
    if result["unnamed_trees"]:
        print(f"أشجارٌ بلا اسمٍ في session_names.json: {result['unnamed_trees']}")
    for w in warn:
        print(f"تحذير: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
