#!/usr/bin/env python3
"""مراقبٌ لمرّةٍ واحدة (يُجدوَل كلَّ N دقيقة): ذاكرةٌ وأثقلُ مستهلكيها، عمرُ أقدم طلبٍ (بلا المؤجَّل بقرار)، تراكمُ WIP، خضرةُ main،
صحّةُ الإنتاج، تنبيهاتُ أمن GitHub، وعملٌ غيرُ مدفوع. يُصدر تنبيهاتٍ بدرجاتٍ وإجراءاتٍ.

    python watch_once.py [--json] [--no-live]

--no-live يقيس الذاكرةَ محلّيّاً فقط (بلا gh ولا git). العتباتُ من projects/<project>/thresholds.json.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import io
import json
import subprocess
import sys
import urllib.error
import urllib.request
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


def top_processes(limit: int = 3) -> list[tuple[str, int]]:
    """أكبرُ مستهلكي الذاكرة مجمَّعين باسم الصورة (ميغابايت) — من tasklist بلا PowerShell، فهو خفيفٌ حين تضيق الذاكرة."""
    if sys.platform != "win32":
        return []
    proc = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, encoding="utf-8", errors="replace", check=False)
    return aggregate_tasklist(proc.stdout, limit) if proc.returncode == 0 else []


def aggregate_tasklist(csv_text: str, limit: int = 3) -> list[tuple[str, int]]:
    """يجمع أسطرَ tasklist (الاسم، PID، الجلسة، رقمُها، «123,456 K») باسم الصورة؛ وما لا يُحلَّل يُتجاوز."""
    totals: dict[str, int] = {}
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < 5:
            continue
        digits = "".join(ch for ch in row[4] if ch.isdigit())
        if digits:
            totals[row[0]] = totals.get(row[0], 0) + int(digits)
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [(name, kb // 1024) for name, kb in ranked]


def memory_alert(free: float, th: dict, top: list[tuple[str, int]] | None = None) -> dict | None:
    """تنبيهُ الذاكرة، ومعه أكبرُ المستهلكين حين يكون غيرَ أخضر (كانت 0203 تجمعه يدويّاً بـGet-Process)."""
    band = memory_band(free, th)
    if band == "green":
        return None
    sev = {"yellow": "warn", "red": "high", "critical": "critical"}[band]
    heavy = f" · الأثقل: {'، '.join(f'{n} {mb} م.ب' for n, mb in top)}" if top else ""
    return alert("memory", sev, f"الذاكرةُ المتاحة {free} غيغا ({band}){heavy}", th["actions"][band])


def health_alerts(cfg: dict | None, fetch=None) -> list[dict]:
    """صحّةُ الإنتاج من `/health/`: ردٌّ غيرُ 200 أو تعذّرُ الاتّصال ⇒ high (كانت 0203 تفحصها يدويّاً بـcurl)."""
    if not cfg or not cfg.get("url"):
        return []
    status, error = (fetch or http_status)(cfg["url"], cfg.get("timeout_s", 10))
    if status == 200:
        return []
    why = f"الردّ {status}" if status else f"تعذّر الاتّصال ({error})"
    return [alert("prod_health", "high", f"صحّةُ الإنتاج: {why}", "أبلغ «0601 · النشر على الإنتاج والدمج»، وS2 إن تكرّر")]


def http_status(url: str, timeout: float) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "schoolos-watch"}), timeout=timeout) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, exc.__class__.__name__


SEC_KINDS = ("dependabot", "code-scanning", "secret-scanning")


def security_severity(kind: str, item: dict) -> str:
    """درجةُ تنبيه الأمن كما يعلنها GitHub؛ والسرُّ المكشوفُ حرجٌ دائماً."""
    if kind == "secret-scanning":
        return "critical"
    if kind == "dependabot":
        return (item.get("security_advisory") or {}).get("severity") or "unknown"
    rule = item.get("rule") or {}
    return rule.get("security_severity_level") or rule.get("severity") or "unknown"


def security_alerts(repo: str | None, fetch=None) -> list[dict]:
    """تنبيهاتُ أمن GitHub المفتوحة: حرجٌ أو عالٍ ⇒ high، وغيرُهما ⇒ info. تعذّرُ نوعٍ يُذكر ولا يُسقط غيرَه."""
    if not repo:
        return []
    fetch = fetch or (lambda kind: gh("api", f"repos/{repo}/{kind}/alerts?state=open&per_page=100"))
    counts: dict[str, int] = {}
    missing = []
    for kind in SEC_KINDS:
        items = fetch(kind)
        if not isinstance(items, list):
            missing.append(kind)
            continue
        for item in items:
            sev = security_severity(kind, item)
            counts[sev] = counts.get(sev, 0) + 1
    out = []
    if counts:
        loud = counts.get("critical", 0) + counts.get("high", 0)
        detail = "، ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        out.append(alert("security_alerts", "high" if loud else "info", f"تنبيهاتُ أمن GitHub المفتوحة: {detail}",
                         "أبلغ مسار الأمن" if loud else ""))
    if missing:
        out.append(alert("security_unavailable", "warn", f"تعذّرت قراءةُ: {'، '.join(missing)}", "تحقّق من صلاحيّة gh (security_events)"))
    return out


def open_pr_age_hours(prs: list[dict], deferred: set[int], now: datetime) -> float | None:
    """عمرُ أقدم طلبٍ حيّ — بلا المسوّدات ولا المؤجَّل بقرار (W-013: #631 كان يُطلق إنذاراً كاذباً دائماً)."""
    live = [p for p in prs if not p["isDraft"] and p["number"] not in deferred]
    if not live:
        return None
    return max((now - datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00"))).total_seconds() / 3600 for p in live)


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
        top = top_processes() if memory_band(free, th["memory_free_gb"]) != "green" else None
        mem = memory_alert(free, th["memory_free_gb"], top)
        if mem:
            alerts.append(mem)
    if not live:
        return alerts
    prs = gh("pr", "list", "--state", "open", "--limit", "200", "--json", "number,createdAt,isDraft")
    if prs is None:
        alerts.append(alert("gh_unavailable", "warn", "تعذّرت قراءةُ الطلبات المفتوحة من gh", "تحقّق من gh auth والشبكة"))
    else:
        live_prs = [p for p in prs if not p["isDraft"]]
        deferred = {int(n) for n in th["flow"].get("deferred_prs", {})}
        oldest_h = open_pr_age_hours(prs, deferred, datetime.now(timezone.utc))
        if oldest_h is not None:
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
    alerts.extend(health_alerts(th.get("production_health")))
    alerts.extend(security_alerts(th.get("security_repo")))
    alerts.extend(late_start_alerts())
    try:
        alerts.extend(orphan_alerts(project))
    except Exception as exc:  # noqa: BLE001 — المراقبُ لا يسقط بسبب فحصٍ فرعيّ
        alerts.append(alert("watch_error", "warn", f"فشل فحصُ الأشجار: {exc.__class__.__name__}", "شغّل session_load_v2 يدويّاً"))
    return alerts


def late_start_alerts() -> list[dict]:
    """مهامُّ السجلّ التي حان زمنُ بدئها ولم تبدأ — «لا شيءَ بدون زمن» (قرارُ المالك 09-28)."""
    sys.path.insert(0, str(HERE))
    import ledger
    late = ledger.late_items(ledger.reduce_state(ledger.load_events()))
    if not late:
        return []
    worst = min(late, key=ledger.order_key)
    return [alert("late_start", "high" if any(i.get("priority") in ("P0", "P1") for i in late) else "warn",
                  f"{len(late)} مهمّةً حان بدؤها ولم تبدأ؛ أعلاها {worst['id']} ({worst.get('priority')}، بدء {worst.get('start','')[:16]})",
                  "وجّهها الآن أو أعِد جدولتها بقرارٍ مسجَّل")]


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
