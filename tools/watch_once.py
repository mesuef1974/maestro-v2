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


COMMIT_DEFAULT = {"warn": 85.0, "high": 90.0, "critical": 95.0}  # نسبةُ الالتزام % (توصيةُ 0101 10-03: الخطرُ الحقيقيّ الالتزامُ لا الرام)


def commit_percent() -> float | None:
    """نسبةُ الالتزام (Commit charge) من الحدّ — عند ~95–100% تفشل التخصيصاتُ؛ والتقليصُ لا يخفضها."""
    if sys.platform != "win32":
        return None

    class MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MEMSTAT(); st.dwLength = ctypes.sizeof(MEMSTAT)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
    return round(100 * (1 - st.ullAvailPageFile / st.ullTotalPageFile), 1)


def commit_alert(pct: float | None, th: dict | None = None) -> dict | None:
    if pct is None:
        return None
    th = {**COMMIT_DEFAULT, **(th or {})}
    if pct >= th["critical"]:
        sev = "critical"
    elif pct >= th["high"]:
        sev = "high"
    elif pct >= th["warn"]:
        sev = "warn"
    else:
        return None
    return alert("commit", sev, f"الالتزامُ {pct}% من الحدّ (تفشل التخصيصاتُ قرابةَ 95–100%)",
                 "اخفض الجلساتِ الحيّة (قائمةُ 0102) أو أحِل إلى device_memory_guard.ps1 DryRun؛ لا تقليصَ WorkingSet فهو لا يخفض الالتزام")


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
    proc = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, encoding="utf-8", errors="replace", check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
    return [alert("prod_health", "high", f"صحّةُ الإنتاج: {why}", "أبلغ «0601 · الإصدار: الدمجُ والنشر»، وS2 إن تكرّر")]


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
    proc = subprocess.run(["gh", *args], capture_output=True, encoding="utf-8", errors="replace", check=False, cwd="D:/shschool_mvp", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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
    ca = commit_alert(commit_percent(), th.get("commit_pct"))
    if ca:
        alerts.append(ca)
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
    alerts.extend(pr_watch_alerts())
    try:
        alerts.extend(approved_stall_alerts())
        alerts.extend(p0_captured_alerts())
        alerts.extend(roadmap_late_alerts())
        alerts.extend(pr_red_alerts())
        alerts.extend(deposit_alerts(project))
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


ROADMAP_LATE_HOURS = 24.0
SERIES = HERE.parent / "ledger" / "watch_series.jsonl"


def roadmap_late_alerts(now: datetime | None = None, entries: list[dict] | None = None, served: str | None = None) -> list[dict]:
    """طلبٌ مدموجٌ بلا سطر خارطةٍ خلال يوم (W-20261023-014): هدفُ ميثاق 0701 «كلُّ مدموجٍ منشورٍ مسجَّلٌ خلال يوم» مخالفةٌ تُرصد لا تُنسى."""
    sys.path.insert(0, str(HERE))
    import roadmap_queue as rq

    if entries is None:
        entries = rq.read()
    if served is None:
        proposals = HERE.parent / "handover_notes" / "roadmap_proposals.md"
        served = proposals.read_text(encoding="utf-8") if proposals.exists() else ""
    stale = rq.late(entries, served, now, ROADMAP_LATE_HOURS)
    if not stale:
        return []
    oldest = min(stale, key=lambda e: e.get("merged_at") or e.get("queued_at") or "")
    return [alert("roadmap_late", "warn", f"{len(stale)} طلباً مدموجاً بلا سطر خارطةٍ منذ أكثر من {int(ROADMAP_LATE_HOURS)} ساعة؛ أقدمُها #{oldest.get('pr')} ({oldest.get('card') or '—'})",
                  "0701: python tools/roadmap_line.py --write ثمّ أغلق البند؛ المخالفةُ تُسجَّل")]


def append_series(alerts: list[dict], now: datetime | None = None, path: Path | None = None) -> bool:
    """سلسلةُ نتائج المراقب بتاريخها (سطرٌ لكلّ تشغيل): الاتجاهُ يُبنى من الملفّ لا من نقلٍ نصّيّ. فشلُ الكتابة لا يُسقط المراقب."""
    now = now or datetime.now(DOHA)
    row = {"ts": now.isoformat(timespec="seconds"), "count": len(alerts), "alerts": [{"code": a["code"], "severity": a["severity"]} for a in alerts]}
    try:
        p = path or SERIES
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + chr(10))
        return True
    except OSError:
        return False


def pr_watch_alerts(now: datetime | None = None, age_min: float | None = -1.0) -> list[dict]:
    """مراقبُ الطلبات توقّف (مهلةُ Monitor 30 د أو موتُ الجلسة) — والصمتُ يُقرأ نجاحاً. لا تنبيهَ قبل أوّل نبضة ولا ليلاً (23:00 حتى 07:00)."""
    sys.path.insert(0, str(HERE))
    import pr_watch
    now = now or datetime.now(timezone.utc)
    if age_min == -1.0:  # القيمةُ الحيّة؛ غيرُها للاختبار
        age_min = pr_watch.heartbeat_age(now)
    if age_min is None or not 7 <= now.astimezone(DOHA).hour < 23 or age_min <= pr_watch.HEARTBEAT_STALE_MIN:
        return []
    return [alert("pr_watch_dead", "warn", f"مراقبُ الطلبات متوقّفٌ منذ {int(age_min)} د",
                  "0601: أعِد تسليحَه بأداة Monitor: python C:/Users/mesue/delivery_manager_work/tools/pr_watch.py --loop")]


def backup_age_severity(age_h: float | None, failed: bool, max_age_h: float) -> str | None:
    """نسخُ ~/.claude: فشلٌ مسجَّل أو غيابُ إيداعٍ أو إيداعٌ أقدمُ من الحدّ ⇒ high (تعطّل صامتاً 4.5 أشهر من قبل)."""
    if failed or age_h is None or age_h > max_age_h:
        return "high"
    return None


def backup_failure_is_current(failed_mtime: float | None, last_commit_ts: float | None) -> bool:
    """علامةُ الفشل تُنذر فقط إن كانت **أحدثَ** من آخر نسخةٍ ناجحة (W-20260929-008).

    السكربتُ لا يحذف `BACKUP_FAILED.txt` بعد نجاحٍ لاحق، فكان الإنذارُ الكاذبُ يبقى. فإن لم يُعرف وقتُ آخر نسخةٍ
    نجحت (لا إيداع) فالعلامةُ سارية؛ وإن لم تُوجد العلامةُ فلا فشل.
    """
    if failed_mtime is None:
        return False
    return last_commit_ts is None or failed_mtime > last_commit_ts


def backup_alerts(cfg: dict | None) -> list[dict]:
    if not cfg:
        return []
    repo = Path(cfg["repo"])
    proc = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ct", cfg["branch"]],
                          capture_output=True, encoding="utf-8", check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    commit_ts = int(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else None
    age_h = (datetime.now(timezone.utc).timestamp() - commit_ts) / 3600 if commit_ts is not None else None
    marker = repo / "backups" / "BACKUP_FAILED.txt"
    failed = backup_failure_is_current(marker.stat().st_mtime if marker.is_file() else None, commit_ts)
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


def deposit_alerts(project: str = "schoolos", repo: Path = Path("D:/shschool_mvp")) -> list[dict]:
    """إيداعاتُ الجلسات المسمّاة التي لم تُسلَّم للمعاينة (بلا طلبٍ) فوق العتبة — يبلغ المايسترو آليّاً لا بسؤال الجلسات (أمر المالك 2026-10-02)."""
    sys.path.insert(0, str(HERE))
    import deposits_feed as df

    data = df.collect(repo, project, False, 3.0)
    return [
        alert("unreported_deposit", "info", f"{r['session']}: {r['commits']} إيداعاً ({r['label']}) منذ {r['age_h']} س — {r['latest'][:60]}", "وجّه الجلسةَ لتسليم «جاهزٌ للمعاينة» أو افتح طلباً")
        for r in data["rows"] if r["stale_no_pr"] and r["named"]
    ]


def pr_red_alerts(with_log: bool = True) -> list[dict]:
    """أحمرٌ حقيقيٌّ في الطلبات المفتوحة بتفاصيله (الفحصُ الفاشل وسببُه والبطاقةُ والجلسةُ المنفِّذة) — للمايسترو فوراً (طلبُ المالك 10-02)."""
    sys.path.insert(0, str(HERE))
    import pr_red

    out = []
    for pr in pr_red.open_prs():
        rep = pr_red.report_for(pr, with_log=with_log)
        if rep:
            out.append(alert("pr_red", "high", pr_red.render(rep),
                             f"أبلغ المنفِّذة ({rep['session'] or 'غيرَ مُسنَدة'}) بالفحص الفاشل وسببه؛ لا تُدخل الطلبَ الطابور وهو أحمر"))
    return out


P0_STALL_MINUTES = 60.0  # مبدئيّ (قرار 0101، يُضبط بالقياس)


def p0_captured_alerts(minutes: float = P0_STALL_MINUTES, now: datetime | None = None) -> list[dict]:
    """بطاقةُ P0 ما زالت captured/routed ولم تتحرّك خلال N دقيقة — قبل أن تصير late فيُنبَّه المايسترو (لا المالكُ) فوراً.

    «لم تتحرّك» = منذ آخر تغيّرِ حالةٍ (state_ts) وإلّا منذ إنشائها (D-66م: لا مُطلِقَ زمنيّاً عند 0201/0203).
    """
    sys.path.insert(0, str(HERE))
    import ledger as lg

    now = now or datetime.now(DOHA)
    out = []
    for item in lg.reduce_state(lg.load_events(None)).values():
        if item.get("priority") != "P0" or item.get("state") not in ("captured", "routed"):
            continue
        start = item.get("start")
        if start:  # مجدولةٌ لبدءٍ مستقبليّ بقرارٍ مسجَّل: انتظارُها ليس ركوداً (قرار المالك 2026-10-04، تقييم الفلو)
            try:
                start_dt = datetime.fromisoformat(start)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=DOHA)
                if start_dt > now:
                    continue
            except ValueError:
                pass
        since = datetime.fromisoformat(item.get("state_ts") or item["created"])
        age_min = (now - since).total_seconds() / 60
        if age_min >= minutes:
            out.append(alert("p0_captured", "high",
                             f"{item['id']} P0 ({item['state']}) لم تتحرّك منذ {age_min:.0f} د — {str(item.get('problem', ''))[:60]}",
                             "للمايسترو: أسندها الآن أو أبلغ 0201؛ P0 لا تنتظر فحصاً يدويّاً"))
    return out


def pr_states_for_card(card: str, repo: str = "D:/shschool_mvp") -> list[dict] | None:
    """طلباتُ الدمج التي تذكر البطاقةَ (عنواناً أو وصفاً) بحالتها الفعليّة من GitHub؛ None إن تعذّرت القراءة."""
    p = subprocess.run(["gh", "pr", "list", "--state", "all", "--search", card, "--json", "number,state,title"],
                       cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except ValueError:
        return None


def approved_stall_alerts(minutes: float = 45.0, now: datetime | None = None, pr_lookup=pr_states_for_card) -> list[dict]:
    """بطاقاتٌ اعتُمدت ولم تُدفع بعد فوق العتبة — تُقاطَع بحالة الطلب الفعليّة (10-02: ثلاثُ بطاقاتٍ «معتمَدة» كانت مدموجةً فتأخّر الدفتر لا الدفع).

    مدموجٌ فعلاً ← تنبيهُ تأخّر تسجيل الدفتر (ledger_lag)؛ طلبٌ مفتوحٌ ← معلومةٌ لا تأخّر دفع؛ لا طلبَ ← approved_not_pushed.
    """
    sys.path.insert(0, str(HERE))
    import ledger as lg

    now = now or datetime.now(DOHA)
    out = []
    for item in lg.reduce_state(lg.load_events(None)).values():
        if item.get("state") != "approved" or not item.get("state_ts"):
            continue
        age_min = (now - datetime.fromisoformat(item["state_ts"])).total_seconds() / 60
        if age_min < minutes:
            continue
        prs = pr_lookup(item["id"]) or []
        merged = [x for x in prs if x.get("state") == "MERGED"]
        opened = [x for x in prs if x.get("state") == "OPEN"]
        brief = str(item.get("problem", ""))[:60]
        if merged:
            out.append(alert("ledger_lag", "warn", f"{item['id']} «approved» في الدفتر منذ {age_min / 60:.1f} س لكنّ #{merged[0]['number']} مدموجٌ فعلاً",
                             "سجّل merged/published في الدفتر (0601 أو 0101) — الدفتر متأخّرٌ لا الدفع"))
        elif opened:
            out.append(alert("approved_pr_open", "info", f"{item['id']} معتمَدةٌ منذ {age_min / 60:.1f} س وطلبُها #{opened[0]['number']} مفتوح — {brief}",
                             "لا تأخّرَ دفع؛ انتظارُ الدمج/البوّابات"))
        else:
            out.append(alert("approved_not_pushed", "warn" if age_min >= 180 else "info",
                             f"{item['id']} معتمَدةٌ منذ {age_min / 60:.1f} س ولا طلبَ دمجٍ لها — {brief}",
                             "ذكّر الجلسةَ المنفِّذة بالدفع (بعد الاعتماد الدفعُ من الفلو) أو تحقّق من أنّها حيّة"))
    return out


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
    content = bs.git_content_merged(repo)
    merged = [p for rows in by_branch.values() for p in rows if p["state"] == "MERGED"]
    out = []
    for wt in sl.worktrees(repo, warn):
        name = Path(wt["worktree"]).name
        if name in ignored or name in names:
            continue
        ahead = len(sl.run("git", "rev-list", f"origin/main..{wt['HEAD']}", cwd=repo).split())
        dirty = len(sl.run("git", "--no-optional-locks", "-C", wt["worktree"], "status", "--porcelain").splitlines())
        own = by_branch.get(bs.branch_of(wt), [])
        result = bs.classify_tree(wt["HEAD"], bs.branch_of(wt), ahead, dirty, own, contains, content_merged=content)
        if result["status"] == bs.NO_PR and ahead:  # قد يكون عملُها اندمج عبر طلب فرعٍ آخر
            result = bs.classify_tree(wt["HEAD"], bs.branch_of(wt), ahead, dirty, own, contains,
                                      elsewhere=bs.merged_elsewhere(repo, wt["HEAD"], merged, contains, content),
                                      content_merged=content)
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
    append_series(alerts)
    if args.json:
        print(json.dumps({"generated_doha": datetime.now(DOHA).isoformat(timespec="minutes"), "alerts": alerts}, ensure_ascii=False, indent=2))
        return
    print(f"مراقبٌ — الدوحة {datetime.now(DOHA):%Y-%m-%d %H:%M}")
    for a in alerts or [alert("ok", "info", "لا تنبيهات", "")]:
        print(f"[{a['severity']:8}] {a['code']}: {a['message']}" + (f" ← {a['action']}" if a["action"] else ""))


if __name__ == "__main__":
    main()
