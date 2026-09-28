#!/usr/bin/env python3
"""مراقبٌ لمرّةٍ واحدة (يُجدوَل كلَّ N دقيقة): ذاكرةٌ، عمرُ أقدم طلبٍ، تراكمُ WIP، خضرةُ main، وعملٌ غيرُ مدفوع. يُصدر تنبيهاتٍ بدرجاتٍ وإجراءاتٍ.

    python watch_once.py [--json] [--no-live]

--no-live يقيس الذاكرةَ محلّيّاً فقط (بلا gh ولا git). العتباتُ من projects/<project>/thresholds.json.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECTS = HERE.parent / "projects"
DOHA = timezone(timedelta(hours=3))


def free_memory_gb() -> float | None:
    if sys.platform != "win32":
        return None

    class MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMSTAT(); st.dwLength = ctypes.sizeof(MEMSTAT)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return round(st.ullAvailPhys / 1024**3, 2)


def memory_band(free_gb: float, th: dict) -> str:
    if free_gb >= th["green_min"]:
        return "green"
    if free_gb >= th["yellow_min"]:
        return "yellow"
    if free_gb >= th["red_min"]:
        return "red"
    return "critical"


def age_severity(hours: float, th: dict) -> str | None:
    if hours >= th["high"]:
        return "high"
    if hours >= th["warn"]:
        return "warn"
    return None


def wip_severity(count: int, th: dict) -> str | None:
    if count > th["high"]:
        return "warn"
    return None


def alert(code: str, severity: str, message: str, action: str = "") -> dict:
    return {"code": code, "severity": severity, "message": message, "action": action}


def gh(*args: str) -> list | dict | None:
    proc = subprocess.run(["gh", *args], capture_output=True, encoding="utf-8", errors="replace", check=False, cwd="D:/shschool_mvp")
    try:
        return json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else None
    except json.JSONDecodeError:
        return None


def collect(th: dict, live: bool = True, project: str = "schoolos") -> list[dict]:
    alerts: list[dict] = []
    free = free_memory_gb()
    if free is not None:
        band = memory_band(free, th["memory_free_gb"])
        if band != "green":
            sev = {"yellow": "warn", "red": "high", "critical": "critical"}[band]
            alerts.append(alert("memory", sev, f"الذاكرةُ المتاحة {free} غيغا ({band})", th["memory_free_gb"]["actions"][band]))
    if not live:
        return alerts
    prs = gh("pr", "list", "--state", "open", "--limit", "200", "--json", "number,createdAt,isDraft")
    if prs is None:
        alerts.append(alert("gh_unavailable", "warn", "تعذّرت قراءةُ الطلبات المفتوحة من gh", "تحقّق من gh auth والشبكة"))
    else:
        live_prs = [p for p in prs if not p["isDraft"]]
        now = datetime.now(timezone.utc)
        if live_prs:
            oldest_h = max((now - datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00"))).total_seconds() / 3600 for p in live_prs)
            sev = age_severity(oldest_h, th["flow"]["oldest_open_pr_age_h"])
            if sev:
                alerts.append(alert("oldest_pr_age", sev, f"أقدمُ طلبٍ مفتوحٍ عمره {oldest_h:.1f} س", "افتح نافذةَ مراجعةٍ أو اقترح رفعَ السعة"))
        sev = wip_severity(len(live_prs), th["flow"]["system_wip_target"])
        if sev:
            alerts.append(alert("system_wip", sev, f"{len(live_prs)} طلباً مفتوحاً (المستهدف ≤{th['flow']['system_wip_target']['high']})", "أوقف البدءَ الجديدَ عند المدخل"))
    runs = gh("run", "list", "--branch", "main", "--limit", "6", "--json", "conclusion,status,name")
    if runs is not None:
        failed = [r for r in runs if r.get("conclusion") == "failure"]
        if len(failed) >= th["flow"]["failed_main_runs_for_s2"]:
            alerts.append(alert("main_red", "high", f"{len(failed)} فحوصٍ فاشلة على main في آخر {len(runs)}", "أعلن S2 وأبلغ «النشر على الانتاج»"))
    alerts.extend(backup_alerts(th.get("claude_backup")))
    try:
        alerts.extend(orphan_alerts(project))
    except Exception as exc:  # noqa: BLE001 — المراقبُ لا يسقط بسبب فحصٍ فرعيّ
        alerts.append(alert("watch_error", "warn", f"فشل فحصُ الأشجار: {exc.__class__.__name__}", "شغّل session_load_v2 يدويّاً"))
    return alerts


def backup_age_severity(age_h: float | None, failed: bool, max_age_h: float) -> str | None:
    """نسخُ ~/.claude: فشلٌ مسجَّل أو غيابُ إيداعٍ أو إيداعٌ أقدمُ من الحدّ ⇒ high (تعطّل صامتاً 4.5 أشهر من قبل)."""
    if failed or age_h is None or age_h > max_age_h:
        return "high"
    return None


def backup_alerts(cfg: dict | None) -> list[dict]:
    if not cfg:
        return []
    repo = Path(cfg["repo"])
    proc = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ct", cfg["branch"]],
                          capture_output=True, encoding="utf-8", check=False)
    age_h = (datetime.now(timezone.utc).timestamp() - int(proc.stdout.strip())) / 3600 if proc.returncode == 0 and proc.stdout.strip() else None
    failed = (repo / "backups" / "BACKUP_FAILED.txt").is_file()
    sev = backup_age_severity(age_h, failed, cfg["max_age_h"])
    if not sev:
        return []
    why = "آخرُ نسخٍ فشل (backups/BACKUP_FAILED.txt)" if failed else ("لا إيداعَ في فرع النسخ" if age_h is None else f"آخرُ نسخٍ قبل {age_h:.0f} س")
    return [alert("claude_backup", sev, f"نسخُ ~/.claude الاحتياطيّ: {why}", "أبلغ المالك: backups/auto_backup.log ومهمّةُ Claude_DailyBackup")]


ORPHAN_SEVERITY = {"no_pr": "warn", "closed_unmerged": "warn", "work_after_merge": "warn", "merged_dirty": "info"}
ORPHAN_ACTION = {
    "no_pr": "اسأل المالكَ عن صاحبها قبل أيّ إزالة",
    "closed_unmerged": "طلبُها أُغلق بلا دمج: اسأل المالكَ أيُهمَل العملُ أم يُعاد فتحُه",
    "work_after_merge": "عملٌ جديدٌ فوق طلبٍ مدموج: اسأل صاحبها أيُدفع طلباً جديداً",
    "merged_dirty": "اندمج عملُها وبقيت ملفّاتٌ غيرُ مودَعة: تُراجَع قبل إزالة الشجرة",
}


def orphan_alerts(project: str = "schoolos", repo: Path = Path("D:/shschool_mvp")) -> list[dict]:
    """أشجارٌ بلا جلسةٍ مسمّاة فيها عملٌ معلَّقٌ فعلاً — يُحكم بحالة طلب الفرع (branch_status) لا بعدّ الإيداعات."""
    sys.path.insert(0, str(HERE))
    import branch_status as bs
    import session_load_v2 as sl

    warn: list[str] = []
    by_branch = bs.prs_by_branch(repo, warn)
    if by_branch is None:
        return [alert("gh_unavailable", "warn", "تعذّرت قراءةُ حالة الطلبات — فحصُ الأشجار اليتيمة معطَّل", "تحقّق من gh auth")]
    names = sl.load_json("session_names.json", project)
    ignored = set(sl.DEFAULT_IGNORED) | set(sl.load_json("ignored_trees.json", project).get("trees", []))
    contains = bs.git_contains(repo)
    merged = [p for rows in by_branch.values() for p in rows if p["state"] == "MERGED"]
    out = []
    for wt in sl.worktrees(repo, warn):
        name = Path(wt["worktree"]).name
        if name in ignored or name in names:
            continue
        ahead = len(sl.run("git", "rev-list", f"origin/main..{wt['HEAD']}", cwd=repo).split())
        dirty = len(sl.run("git", "--no-optional-locks", "-C", wt["worktree"], "status", "--porcelain").splitlines())
        own = by_branch.get(bs.branch_of(wt), [])
        result = bs.classify_tree(wt["HEAD"], bs.branch_of(wt), ahead, dirty, own, contains)
        if result["status"] == bs.NO_PR and ahead:  # قد يكون عملُها اندمج عبر طلب فرعٍ آخر
            result = bs.classify_tree(wt["HEAD"], bs.branch_of(wt), ahead, dirty, own, contains,
                                      elsewhere=bs.merged_elsewhere(repo, wt["HEAD"], merged, contains))
        if result["status"] in bs.PENDING:
            same, total = bs.overlap(repo, wt["HEAD"])
            left = f" · {total - same} من {total} ملفّاً ما زال مختلفاً عن main" if total else ""
            out.append(alert("orphan_tree", ORPHAN_SEVERITY[result["status"]], f"{name}: {bs.describe(result, ahead, dirty)}{left}", ORPHAN_ACTION[result["status"]]))
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true"); ap.add_argument("--no-live", action="store_true"); ap.add_argument("--project", default="schoolos")
    args = ap.parse_args()
    th = json.loads((PROJECTS / args.project / "thresholds.json").read_text(encoding="utf-8"))
    alerts = collect(th, live=not args.no_live, project=args.project)
    if args.json:
        print(json.dumps({"generated_doha": datetime.now(DOHA).isoformat(timespec="minutes"), "alerts": alerts}, ensure_ascii=False, indent=2))
        return
    print(f"مراقبٌ — الدوحة {datetime.now(DOHA):%Y-%m-%d %H:%M}")
    for a in alerts or [alert("ok", "info", "لا تنبيهات", "")]:
        print(f"[{a['severity']:8}] {a['code']}: {a['message']}" + (f" ← {a['action']}" if a["action"] else ""))


if __name__ == "__main__":
    main()
