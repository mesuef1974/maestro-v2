#!/usr/bin/env python3
"""فاحصُ أهليّة الأرشفة — الفحوصُ الخمسة + الدوام + الأشجار المشتركة؛ يُخرج سطرَ «سبب» جاهزاً لنافذة موافقة التطبيق. قراءةٌ فقط.

الأرشفةُ في التطبيق تُزيل الشجرةَ افتراضيّاً وتُؤرشف الجلساتِ التي تشاركها؛ فلا يصحّ طلبُ الموافقة بلا هذا الفحص.

    python archive_check.py <اسم-مجلّد-الشجرة> --title "عنوان الجلسة" [--running] [--shared 0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import branch_status as bs  # noqa: E402
import session_load_v2 as sl  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def parse_cherry(output: str) -> tuple[int, int]:
    """git cherry: '+' = إيداعٌ لم يُدمج بمحتواه، '-' = مكافئُه موجودٌ في main."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    return sum(ln.startswith("+") for ln in lines), sum(ln.startswith("-") for ln in lines)


def permanent_titles(tabs: dict) -> dict[str, str]:
    """عنوانٌ ← سببُ المنع: جلساتُ النواة الثابتة وحدها (D-43م)؛ والباقي يُؤرشف حين ينتهي عملُه."""
    return {title: "جلسةٌ ثابتةٌ من النواة" for title in tabs.get("session_policy", {}).get("core_sessions", [])}


def evaluate(facts: dict, blocked_titles: dict[str, str]) -> dict:
    blockers = []
    held = blocked_titles.get(facts["title"]) or next((r for t, r in blocked_titles.items() if t[:4] == facts["title"][:4] and facts["title"][:4].isdigit()), None)
    if held:  # الحمايةُ بالرقم لا بنصّ العنوان: العنوانُ الحيُّ يتغيّر («خفيفة» مقابل «المايسترو») ولا تسقط الحمايةُ بذلك
        blockers.append(held)
    if facts["open_prs"]:
        blockers.append(f"{len(facts['open_prs'])} طلبات مفتوحة: " + ", ".join("#" + str(n) for n in facts["open_prs"]))
    status = facts.get("branch_status")
    if status in (bs.WORK_AFTER_MERGE, bs.CLOSED_UNMERGED, bs.NO_PR):
        refs = (" " + ", ".join("#" + str(n) for n in facts.get("branch_prs", []))) if facts.get("branch_prs") else ""
        blockers.append(f"{bs.LABEL_AR[status]}{refs} ({facts['cherry_plus']} إيداعاً خارج main)")
    elif status is None and facts["cherry_plus"]:  # gh غيرُ متاح: الأحوطُ الحكمُ بـcherry
        blockers.append(f"{facts['cherry_plus']} إيداعاً لم يُدمج بمحتواه (git cherry؛ حالةُ الطلب غيرُ معروفة)")
    if facts["dirty_files"]:
        blockers.append(f"{facts['dirty_files']} ملفّاً غيرَ مودَع")
    if facts["running"]:
        blockers.append("تعمل الآن")
    if not facts["handover_saved"]:
        blockers.append("لا مذكّرةَ تسليمٍ محفوظة")
    if facts["shared_with"]:
        blockers.append(f"الشجرةُ مشتركةٌ مع {facts['shared_with']} جلسةً أخرى (تُؤرشَف معها)")
    if blockers:
        reason = "لا تُؤرشَف: " + " · ".join(blockers)
    else:
        done = bs.LABEL_AR.get(status, "لا عملَ خارج main") + ((" " + ", ".join("#" + str(n) for n in facts.get("branch_prs", []))) if facts.get("branch_prs") else "")
        reason = (f"أرشفةُ «{facts['title']}»: لا طلبَ مفتوح · {done} · 0 ملفّ غيرُ مودَع · غيرُ دائمة · "
                  "لا تعمل الآن · مذكّرةُ تسليمٍ محفوظة · العودةُ بـunarchive_session")
    return {"eligible": not blockers, "blockers": blockers, "reason": reason[:400], "facts": facts}


def gather(tree: str, title: str, running: bool, shared: int, repo: Path = Path("D:/shschool_mvp")) -> dict:
    warn: list[str] = []
    wt = next((w for w in sl.worktrees(repo, warn) if Path(w["worktree"]).name == tree), None)
    if wt is None:
        sys.exit(f"لا شجرةَ باسم {tree}")
    head, path = wt["HEAD"], wt["worktree"]
    ahead = set(sl.run("git", "rev-list", f"origin/main..{head}", cwd=repo, warn=warn).split())
    reflog = set(sl.run("git", "-C", path, "reflog", "--format=%H", "-n", str(sl.REFLOG_DEPTH)).split())
    prs = sl.open_prs(repo, warn) or []
    mine = sorted(p["number"] for p in prs if p["headRefOid"] in ahead or p["headRefOid"] in reflog)
    plus, _ = parse_cherry(sl.run("git", "-C", path, "cherry", "origin/main", "HEAD"))
    dirty = len(sl.run("git", "--no-optional-locks", "-C", path, "status", "--porcelain").splitlines())
    by_branch = bs.prs_by_branch(repo, warn)
    if by_branch is None:
        judged = {"status": None, "prs": []}
    else:
        contains, own = bs.git_contains(repo), by_branch.get(bs.branch_of(wt), [])
        judged = bs.classify_tree(head, bs.branch_of(wt), len(ahead), dirty, own, contains)
        if judged["status"] == bs.NO_PR and ahead:
            merged = [p for rows in by_branch.values() for p in rows if p["state"] == "MERGED"]
            judged = bs.classify_tree(head, bs.branch_of(wt), len(ahead), dirty, own, contains,
                                      elsewhere=bs.merged_elsewhere(repo, head, merged, contains))
    return {
        "title": title, "tree": tree, "open_prs": mine, "cherry_plus": plus, "dirty_files": dirty, "running": running,
        "branch_status": judged["status"], "branch_prs": judged["prs"],
        "handover_saved": (ROOT / "handover_notes" / f"{tree}.md").is_file(), "shared_with": shared, "warnings": warn,
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree"); ap.add_argument("--title", required=True)
    ap.add_argument("--running", action="store_true"); ap.add_argument("--shared", type=int, default=0)
    ap.add_argument("--project", default="schoolos")
    args = ap.parse_args()
    tabs = json.loads((ROOT / "projects" / args.project / "tabs.json").read_text(encoding="utf-8"))
    print(json.dumps(evaluate(gather(args.tree, args.title, args.running, args.shared), permanent_titles(tabs)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
