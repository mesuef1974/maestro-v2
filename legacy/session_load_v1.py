#!/usr/bin/env python3
"""لقطةُ حِمل الجلسات — أداةُ «مدير تطوير البرمجيات» (قراءةٌ فقط، بلا كتابة في أيّ شجرة).

لكلّ شجرةِ جلسةٍ: طلباتُ الدمج المفتوحةُ التي رأسُها في فرعها، وإيداعاتُها التي لم تُدمج، وملفّاتُها غيرُ المودَعة،
وحجمُ سياقها (نصُّ المحادثة بالميغا) وأحداثُ اليوم والأمس — مؤشّراتٌ حتميّةٌ رخيصة بدل التخمين.

    python session_load.py            # جدولٌ نصّيّ
    python session_load.py --json     # للأدوات

الاسمُ المقروء يؤخذ من WORKTREE_SESSION أدناه؛ فما لم يُطابَق يظهر باسم مجلّد الشجرة (طابِقه بـListAgents).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path("D:/shschool_mvp")
TRANSCRIPTS = Path("C:/Users/mesue/.claude/projects")
HEAVY_MB = 40  # سياقٌ ثقيل: الجلسةُ بطيئةٌ وغاليةٌ في كلّ إيقاظ

WORKTREE_SESSION = {
    "amazing-proskuriakova-202fdd": "النشر على الانتاج",
    "distracted-ardinghelli-fb239e": "أمين خارطة التجويد",
    "student-count-mismatch-5aab99": "منصّة · فحص الإدارة",
    "epic-tesla-9f1df1": "مستشار ومصدر الحقيقة للمنصّة",
    "gracious-banach-f725f1": "مسار الأمن والامتثال",
    "nervous-elbakyan-90f3f2": "بصريّ · تخطيط لوحة المدير",
    "heuristic-montalcini-ebb0b0": "مسار الجوال وتجربة المستخدم",
    "modest-cannon-c6e046": "أمين المستودع · الجيت والشجرات",
    "fixes-02-3c5472": "بصريّ · محور الجوال",
    "priceless-snyder-945a8f": "مسار الديون التقنيّة",
    "clever-borg-26f305": "مسار سطح المكتب واللابتوب",
    "agitated-williamson-59ca12": "الحوكمة · اختصاصات الجلسات",
    "exciting-noether-1e7f28": "جدول · التشغيل",
    "ecstatic-euclid-60b658": "مسار التشغيل والموثوقيّة",
    "hopeful-solomon-0950f3": "مسار الواجهة والهويّة",
    "ecstatic-allen-55abd7": "مسار Backend والبيانات",
    "magical-montalcini-c69014": "مسار الجودة والاختبارات والوثائق",
    "funny-cray-7eb097": "مسار وظائف المنتج",
    "awesome-varahamihira-65388c": "أمين البلاغات",
    "busy-dubinsky-8e96e8": "جدول · المولّد وإقلاع الأحد",
}


def run(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(
        list(args), cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False
    )
    return out.stdout.strip()


def worktrees() -> list[dict]:
    found, cur = [], {}
    for line in run("git", "worktree", "list", "--porcelain", cwd=REPO).splitlines() + [""]:
        if not line:
            if cur.get("worktree") and "/.claude/worktrees/" in cur["worktree"].replace("\\", "/"):
                found.append(cur)
            cur = {}
        elif " " in line:
            key, value = line.split(" ", 1)
            cur[key] = value
    return found


def open_prs() -> list[dict]:
    raw = run(
        "gh", "pr", "list", "--state", "open", "--limit", "100",
        "--json", "number,headRefOid,isDraft,title", cwd=REPO,
    )
    return json.loads(raw) if raw else []


def transcript_stats(name: str) -> tuple[int, int, int]:
    folder = TRANSCRIPTS / f"D--shschool-mvp--claude-worktrees-{name}"
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    if not files:
        return 0, 0, 0
    newest = files[-1]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    n_today = n_yest = 0
    with newest.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if f'"timestamp":"{today}' in line:
                n_today += 1
            elif f'"timestamp":"{yesterday}' in line:
                n_yest += 1
    return newest.stat().st_size // 1048576, n_today, n_yest


def is_ancestor(commit: str, head: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, head], cwd=REPO, capture_output=True, check=False
    ).returncode == 0


def main() -> None:
    run("git", "fetch", "-q", "origin", "main", cwd=REPO)
    prs = open_prs()
    rows = []
    for wt in worktrees():
        name = Path(wt["worktree"]).name
        if name == "main-preview" or "HEAD" not in wt:
            continue
        head = wt["HEAD"]
        ahead = int(run("git", "rev-list", "--count", f"origin/main..{head}", cwd=REPO) or 0)
        dirty = len(
            run("git", "--no-optional-locks", "-C", wt["worktree"], "status", "--porcelain").splitlines()
        )
        mine = [p for p in prs if is_ancestor(p["headRefOid"], head)]
        size_mb, today, yesterday = transcript_stats(name)
        rows.append(
            {
                "session": WORKTREE_SESSION.get(name, name),
                "tree": name,
                "open_prs": len(mine),
                "draft_prs": sum(1 for p in mine if p["isDraft"]),
                "unmerged_commits": ahead,
                "dirty_files": dirty,
                "context_mb": size_mb,
                "events_today": today,
                "events_yesterday": yesterday,
                "heavy": size_mb >= HEAVY_MB,
            }
        )
    rows.sort(key=lambda r: (-r["open_prs"], -r["events_today"]))
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    print(f"{'الجلسة':<34} {'PR':>3} {'إيداعات':>7} {'معدَّل':>6} {'سياق MB':>7} {'اليوم':>6} {'أمس':>6}")
    for r in rows:
        flag = " ثقيل" if r["heavy"] else ""
        print(
            f"{r['session'][:34]:<34} {r['open_prs']:>3} {r['unmerged_commits']:>7} {r['dirty_files']:>6} "
            f"{r['context_mb']:>7} {r['events_today']:>6} {r['events_yesterday']:>6}{flag}"
        )


if __name__ == "__main__":
    main()
