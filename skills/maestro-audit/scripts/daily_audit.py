#!/usr/bin/env python3
"""قائمةُ التقييم اليوميّ لجلسة «0102 · التقييم والعصف: جودةُ المنظومة» في مخرجٍ واحد — قراءةٌ فقط، لا يكتب أيَّ ملفّ.

يجمع ما تطلبه طريقةُ العمل اليوميّة في ميثاق 0102 (tabs.json → session_policy.charters):
  1) السجلّ مقابل الجلسات الحيّة (validate_registry بقائمةٍ حيّة، لا باللقطة المحفوظة وحدها)
  2) الجلساتُ في تبويبها، والخاملةُ خارج النواة، ومواثيقُ بلا عضو
  3) المراقب watch_once (ذاكرة، أقدمُ طلب، WIP، خضرةُ main، النسخ، البدءُ المتأخّر، الأشجارُ اليتيمة)
  4) late_items من سجلّ العمل
  5) آخرُ إيداعٍ في مستودع المايسترو ونسخِ ~/.claude، واختباراتُ الحزمة
  6) أوقاتُ القرارات مقابل وقت إيداعها، واتّساقُ رقم إصدار الفلو

    python daily_audit.py --sessions-json <ملفُّ مخرج list_sessions> [--no-live] [--json]

الملفُّ: مصفوفةُ list_sessions كما هي (أو قائمةُ عناوين). list_sessions تُسقط الجلسةَ المستدعِية،
فيُضاف عنوانُها بـ--self-title (الافتراض «0301 · الحوكمة: حراسة القواعد» كما في الشريط — كانت 0103؛ وميثاقُ 0102 مدمَجٌ فيها منذ 2026-10-21).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DOHA = timezone(timedelta(hours=3))
NOW = datetime.now(DOHA)

# عتباتٌ اقترحتها المهارةُ (غيرُ موثَّقةٍ في قرار) — تُعدَّل بقرار
DECISION_AHEAD_TOLERANCE_MIN = 5   # وقتُ قرارٍ بعد إيداعه بأكثر من هذا = مستحيل ⇒ خطأُ تقدير
DECISION_LAG_REVIEW_MIN = 90       # قرارٌ أُودع بعد وقته المكتوب بأكثر من هذا ⇒ يُتحقَّق منه
IMMEDIATE_CODES = {"memory", "main_red", "claude_backup"}  # تنبيهاتٌ لا تنتظر التقرير (مع severity high/critical)


def run(*cmd: str, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(list(cmd), cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def doha(ts: float | datetime) -> str:
    dt = ts if isinstance(ts, datetime) else datetime.fromtimestamp(ts, DOHA)
    return dt.astimezone(DOHA).strftime("%m-%d %H:%M")


def load_live(path: Path | None, self_title: str, repo_prefix: str) -> tuple[list[dict] | None, list[str]]:
    """يعيد صفوفَ الجلسات الحيّة لمشروع المدرسة، ومعها ملاحظاتُ القراءة."""
    notes: list[str] = []
    if path is None:
        return None, ["لا قائمةَ حيّة (--sessions-json): فحصُ الجلسات مقابل اللقطة المحفوظة وحدها، وقد تكون قديمة"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    prefix = repo_prefix.replace("\\", "/").lower()
    for r in raw:
        if isinstance(r, str):
            rows.append({"title": r})
            continue
        if r.get("isArchived"):
            continue
        cwd = str(r.get("cwd", "")).replace("\\", "/").lower()
        if cwd and not cwd.startswith(prefix):
            notes.append(f"خارج المشروع (لا يُدار): «{r.get('title')}»")
            continue
        rows.append(r)
    if self_title and self_title not in {r["title"] for r in rows}:
        rows.append({"title": self_title, "isRunning": True, "_self": True})
        notes.append(f"أُضيفت الجلسةُ المستدعِية «{self_title}» (list_sessions تُسقطها)")
    return rows, notes


def registry_checks(root: Path, tabs: dict, routing: dict, live: list[dict] | None, idle_hours: float) -> list[dict]:
    sys.path.insert(0, str(root / "tools"))
    import validate_registry as vr

    out: list[dict] = []
    snapshot = json.loads((root / "projects/schoolos/sessions_snapshot.json").read_text(encoding="utf-8"))
    titles = [r["title"] for r in live] if live is not None else snapshot
    for p in vr.validate(tabs, routing, titles):
        out.append({"level": "report", "area": "السجلّ", "msg": p, "fix": "طابِق tabs.json والشريط ثمّ أعِد المدقّق"})
    if live is not None:
        added, gone = sorted(set(titles) - set(snapshot)), sorted(set(snapshot) - set(titles))
        if added or gone:
            out.append({"level": "report", "area": "اللقطة", "msg": f"sessions_snapshot.json قديمة: جديدٌ {added or '—'} · غائبٌ {gone or '—'}",
                        "fix": "حدّث اللقطةَ من list_sessions وأودِعها بمسارها الصريح"})
    members = {m: t["number"] for t in tabs["tabs"] for m in t.get("members", [])}
    for key in tabs.get("session_policy", {}).get("charters", {}):
        if key not in members:
            out.append({"level": "report", "area": "المواثيق", "msg": f"ميثاقٌ بعنوانٍ ليس عضواً في أيّ تبويب: «{key}»",
                        "fix": "صحّح مفتاحَ الميثاق ليطابق عنوانَ الجلسة حرفيّاً"})
    if live is None:
        return out
    core = set(tabs.get("session_policy", {}).get("core_sessions", []))
    for r in live:
        title = r["title"]
        if r.get("_self") or "group" not in r:
            continue
        group = r.get("group")
        if group is None:
            out.append({"level": "report", "area": "الشريط", "msg": f"«{title}» خارج أيّ تبويب", "fix": "تُنقل إلى تبويب رقمها (بموافقة التطبيق، للمايسترو)"})
        # التبويبُ المسجَّلُ أوّلاً (المجموعة 01 مرقَّمةٌ بالترتيب: 0201 و0301 فيها، أمر المالك 2026-10-21)، وإلّا أوّلُ خانتين
        elif title[:4].isdigit() and not group["name"].startswith(members.get(title, title[:2]) + " · "):
            out.append({"level": "report", "area": "الشريط", "msg": f"«{title}» في «{group['name']}» لا في تبويب {members.get(title, title[:2])}",
                        "fix": "بلّغ المايسترو بالنقل"})
        last = r.get("lastActivityAt")
        if title not in core and not r.get("isRunning") and last:
            idle_h = (NOW - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() / 3600
            if idle_h >= idle_hours:
                pr = f"، طلبُها #{r['prNumber']} {r.get('prState', '')}" if r.get("prNumber") else ""
                out.append({"level": "report", "area": "الخاملة", "msg": f"«{title}» خاملةٌ منذ {idle_h:.1f} س (آخرُ نشاط {doha(datetime.fromisoformat(last.replace('Z', '+00:00')))}{pr})",
                            "fix": "archive_check.py ثمّ اقتراحٌ للمايسترو؛ الأرشفةُ بأمر المالك وحده"})
    return out


def watch_checks(root: Path, live_watch: bool) -> list[dict]:
    sys.path.insert(0, str(root / "tools"))
    import watch_once as wo

    th = json.loads((root / "projects/schoolos/thresholds.json").read_text(encoding="utf-8"))
    alerts = wo.collect(th, live=live_watch)
    if not live_watch:  # النسخُ فحصٌ محلّيٌّ لا يحتاج gh — يُشغَّل ولو بلا اتّصال
        alerts += wo.backup_alerts(th.get("claude_backup"))
    out = []
    for a in alerts:
        if a["code"] == "late_start":  # يُعرض مفصَّلاً في قسم المتأخّر (ledger_checks) فلا يتكرّر
            continue
        immediate = a["severity"] in ("high", "critical") and a["code"] in IMMEDIATE_CODES
        out.append({"level": "immediate" if immediate else "report", "area": f"المراقب:{a['code']}",
                    "msg": f"[{a['severity']}] {a['message']}", "fix": a.get("action", "")})
    return out


def ledger_checks(root: Path) -> list[dict]:
    sys.path.insert(0, str(root / "tools"))
    import ledger

    items = ledger.reduce_state(ledger.load_events())
    late = sorted(ledger.late_items(items), key=ledger.order_key)
    # P0/P1 متأخّرٌ = high في watch_once.late_start_alerts ⇒ فوريّ؛ وما دونهما للتقرير
    out = [{"level": "immediate" if i.get("priority") in ("P0", "P1") else "report", "area": "المتأخّر",
            "msg": f"{i['id']} {i.get('priority')} بدؤه {i.get('start', '')[:16]} وحالتُه {i['state']}",
            "fix": "بلّغ المايسترو: يوجّهها أو يعيد جدولتَها بقرارٍ مسجَّل"} for i in late]
    approved = [i for i in items.values() if i.get("approvals")]
    if not approved:
        out.append({"level": "info", "area": "الاعتماد", "msg": "لا حدثَ اعتمادٍ في السجلّ بعد — «نسبةُ الاعتماد من أوّل جولة» غيرُ مقيسةٍ منه", "fix": ""})
    return out


def repo_checks(root: Path) -> list[dict]:
    out: list[dict] = []
    code, txt = run("git", "log", "-1", "--format=%ct%x09%h%x09%s", cwd=root)
    if code == 0 and txt.strip():
        ts, sha, subj = txt.strip().split("\t", 2)
        out.append({"level": "info", "area": "آخرُ إيداع", "msg": f"maestro-v2 {sha} {doha(float(ts))} الدوحة — {subj[:70]}", "fix": ""})
    _, ahead = run("git", "rev-list", "--count", "origin/main..HEAD", cwd=root)
    if ahead.strip().isdigit() and int(ahead) > 0:
        out.append({"level": "report", "area": "آخرُ إيداع", "msg": f"{ahead.strip()} إيداعاً غيرَ مرفوعٍ إلى origin/main (بلا fetch)", "fix": "الرفعُ بعد كلّ إيداعٍ مكتمل (D-36م)"})
    _, dirty = run("git", "status", "--porcelain", cwd=root)
    if dirty.strip():
        out.append({"level": "report", "area": "آخرُ إيداع", "msg": f"{len(dirty.splitlines())} مسارٌ غيرُ مودَع: {', '.join(l[3:] for l in dirty.splitlines()[:4])}",
                    "fix": "اعرف صاحبَه قبل أيّ إيداع — قد يكون عملَ جلسةٍ أخرى"})
    code, txt = run(sys.executable, "-m", "unittest", "test_package", "test_session_load_v2", cwd=root / "tools")
    ran = re.search(r"Ran (\d+) tests?", txt)
    ok = code == 0 and re.search(r"^OK", txt, re.M)
    out.append({"level": "info" if ok else "immediate", "area": "الاختبارات",
                "msg": f"{ran.group(1) if ran else '?'} اختباراً — {'ناجحة' if ok else 'فاشلة'}",
                "fix": "" if ok else "لا إيداعَ فوقها؛ أصلِح أو بلّغ المايسترو"})
    board = (root / "board_state.md").read_text(encoding="utf-8")
    m = re.search(r"آخرُ تحديث:\*\* (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", board)
    if m:
        age = (NOW - datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=DOHA)).total_seconds() / 3600
        out.append({"level": "report" if age > 12 else "info", "area": "اللوحة", "msg": f"board_state.md آخرُ تحديث {m.group(1)} (قبل {age:.1f} س)", "fix": ""})
    return out


DEC_RE = re.compile(r"^- (D-\d+م?) \| (\d{2})-(\d{2}) *[~≈]?(\d{1,2}):(\d{2})")


def decision_checks(root: Path, last_n: int) -> list[dict]:
    text = (root / "decisions.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    fixed: dict[str, tuple[int, int]] = {}
    for ln in lines:  # سطرُ «تصحيحُ أوقات» يحلّ محلّ الوقت المكتوب في القرار
        if ln.startswith("- تصحيحُ أوقات"):
            for did, hh, mm in re.findall(r"(D-\d+م?) (\d{1,2}):(\d{2})", ln):
                fixed[did] = (int(hh), int(mm))
    decs = [(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5))) for ln in lines if (m := DEC_RE.match(ln))]
    out: list[dict] = []
    for did, mo, day, hh, mm in decs[-last_n:]:
        hh, mm = fixed.get(did, (hh, mm))
        code, txt = run("git", "log", "--reverse", "--format=%ct", "-S", f"- {did} |", "--", "decisions.md", cwd=root)
        stamps = txt.split()
        if code != 0 or not stamps:
            out.append({"level": "report", "area": "القرارات", "msg": f"{did}: لم يُعثر على إيداعه", "fix": "تحقّق أنّه مودَع"})
            continue
        committed = datetime.fromtimestamp(int(stamps[0]), DOHA)
        written = datetime(committed.year, mo, day, hh, mm, tzinfo=DOHA)
        diff = (written - committed).total_seconds() / 60
        if diff > DECISION_AHEAD_TOLERANCE_MIN:
            out.append({"level": "report", "area": "القرارات", "msg": f"{did}: وقتُه المكتوب {hh:02}:{mm:02} بعد إيداعه {committed:%H:%M} بـ{diff:.0f} د — مستحيل",
                        "fix": "سطرُ «تصحيحُ أوقات» بوقت الإيداع؛ لا تعديلَ لنصّ القرار"})
        elif -diff > DECISION_LAG_REVIEW_MIN:
            out.append({"level": "report", "area": "القرارات", "msg": f"{did}: مكتوبٌ {hh:02}:{mm:02} وأُودع {committed:%H:%M} (بعده بـ{-diff:.0f} د)",
                        "fix": "تحقّق من الوقت الفعليّ من المحادثة أو السجلّ قبل أيّ تصحيح"})
    return out


def flow_checks(root: Path) -> list[dict]:
    out: list[dict] = []
    changelog = (root / "flow_changelog.md").read_text(encoding="utf-8")
    versions = re.findall(r"^\| (v\d+\.\d+) \|", changelog, re.M)
    latest = versions[-1] if versions else "?"
    found = {"flow_changelog.md": latest}
    probes = {
        "board_state.md": r"\*\*فلو:\*\* (v\d+\.\d+)",
        "handover.md": r"إصدارُ الفلو:\*\* (v\d+\.\d+)",
        "tools/review_window.py": r'flow_version: str = "(v\d+\.\d+)"',
    }
    for rel, pat in probes.items():
        m = re.search(pat, (root / rel).read_text(encoding="utf-8"))
        found[rel] = m.group(1) if m else "—"
    stale = {k: v for k, v in found.items() if v not in (latest, "—")}
    if stale:
        out.append({"level": "report", "area": "الفلو", "msg": f"آخرُ إصدار {latest}؛ ومختلفٌ في: " + "، ".join(f"{k}={v}" for k, v in stale.items()),
                    "fix": "حدّث الملفّ أو اجعل الأداةَ تقرأ الإصدارَ من flow_changelog.md"})
    top = max((int(n) for n in re.findall(r"D-(\d+)", changelog)), default=0)
    after = sorted({int(n) for n in re.findall(r"^- D-(\d+)", (root / "decisions.md").read_text(encoding="utf-8"), re.M)} - set(range(top + 1)))
    if after:
        out.append({"level": "report", "area": "الفلو", "msg": f"قراراتٌ بعد آخر ما في سجلّ الفلو (D-{top}): " + "، ".join(f"D-{n}" for n in after),
                    "fix": "قرِّر لكلٍّ: يغيّر الفلو ⇒ سطرٌ ورقمٌ جديد؛ لا يغيّره ⇒ لا شيء"})
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="C:/Users/mesue/delivery_manager_work")
    ap.add_argument("--sessions-json", type=Path)
    ap.add_argument("--self-title", default="0301 · الحوكمة: حراسة القواعد")  # كانت 0103 (ترقيمُ 01 بالترتيب، أمر المالك 2026-10-21)
    ap.add_argument("--repo-prefix", default="D:/shschool_mvp")
    ap.add_argument("--idle-hours", type=float, default=3.0)
    ap.add_argument("--decisions", type=int, default=12, help="عددُ آخر القرارات التي تُطابَق أوقاتُها")
    ap.add_argument("--no-live", action="store_true", help="المراقبُ بلا gh (الذاكرةُ والنسخُ والمتأخّرُ فقط)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    tabs = json.loads((root / "projects/schoolos/tabs.json").read_text(encoding="utf-8"))
    routing = json.loads((root / "projects/schoolos/routing.json").read_text(encoding="utf-8"))
    live, notes = load_live(args.sessions_json, args.self_title, args.repo_prefix)
    findings = (registry_checks(root, tabs, routing, live, args.idle_hours) + watch_checks(root, not args.no_live)
                + ledger_checks(root) + repo_checks(root) + decision_checks(root, args.decisions) + flow_checks(root))
    if args.json:
        print(json.dumps({"generated_doha": NOW.isoformat(timespec="minutes"), "notes": notes, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        print(f"التقييمُ اليوميّ — الدوحة {NOW:%Y-%m-%d %H:%M} — الجلساتُ الحيّة: {'—' if live is None else len(live)}")
        for n in notes:
            print(f"  · {n}")
        for level, head in (("immediate", "فوريّ (للمايسترو الآن)"), ("report", "للتقرير"), ("info", "للعلم")):
            rows = [f for f in findings if f["level"] == level]
            print(f"\n## {head}: {len(rows)}")
            for f in rows:
                print(f"- [{f['area']}] {f['msg']}" + (f" ← {f['fix']}" if f["fix"] else ""))
    return 1 if any(f["level"] == "immediate" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
