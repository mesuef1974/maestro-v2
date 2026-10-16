#!/usr/bin/env python3
"""متابعةُ الفلو المكوَّدة (W-20261016-019) — جدولُ تعليقاتٍ بالشدّة من سبع حالات، قراءةً فقط.

    python tools/flow_watch.py [--html ملف.html] [--no-live] [--now ISO]
                               [--approved-min 30] [--pushed-min 120] [--pr-min 60] [--routed-hours 24]
                               [--preview-min 60] [--ready-min 60] [--silent-min 30]

الحالاتُ السبع (الأسماءُ أسماءُ الدفتر لا نصوصٌ حرّة):
  1 approved لم يُدفع                 2 pushed لم يُدمج                 3 طلبٌ أحمر أو معلَّق
  4 routed بلا بدءٍ أو بمواصفةٍ ليست full   5 تثبيتُ 8500 منتهٍ أو طابورٌ   6 ready_for_review بلا حزمة أدلّة
  7 جلسةٌ صامتة بعد إحالة

قراءةٌ فقط: لا يكتب في الدفتر ولا يرسل رسائل ولا يمسّ git ولا يغيّر حالةَ المعاينة؛ والملفُّ الوحيدُ الذي قد يكتبه هو `--html` الذي
يطلبه المستدعي. أداةٌ غائبة (gh أو preview) تُطبع «غير مقيس» ولا تُعدّ سليمةً. رمزُ الخروج 0 دائماً ما لم تفشل قراءةُ الدفتر (1).

افتراضان معلَنان (من البطاقات الجارية لا من الذاكرة):
  • «حزمةُ الأدلّة» = ملاحظةٌ في البطاقة بعد دخولها ready_for_review تبدأ بـ«(0502)» وفيها «أدلّ» أو «لقط» أو «pack.md» أو «evidence/».
  • «الجلسةُ الصامتة» = إحالةٌ (routed بمُحالٍ إليه، أو ready_for_review إلى 0501) لم يعقبها حدثٌ من المُحالة إليها
    (state بـ`by` تلك الجلسة أو ملاحظةٌ تبدأ بـ«(رقمها)») خلال العتبة.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402
import pr_watch  # noqa: E402  (الطلباتُ تُقرأ بدوالّه لا بنسخها)

UNMEASURED = "غير مقيس"
CARD_RE = re.compile(r"W-\d{8}-\d{3}")
QUEUE_LINE = re.compile(r"^\s*\d+\.\s+(\S+)\s+—.*\(منذ (\d+) دقيقة\)")
PIN_EXPIRED = re.compile(r"منتهٍ|منتهي|انتهت|انقضت")
EVIDENCE_NOTE = re.compile(r"أدلّ|أدل|لقط|pack\.md|evidence/")
PREVIEW_CANDIDATES = (
    Path("D:/shschool_mvp/scripts/preview.sh"),
    *sorted(Path("D:/shschool_mvp/.claude/worktrees").glob("*/scripts/preview.sh")),
)
# bash من PATH على ويندوز قد يكون WSL (مسارٌ مختلف) فلا يجد السكربت؛ فيُستعمل bash المرفق بـGit صراحةً.
GIT_BASH = next((p for p in (Path("C:/Program Files/Git/bin/bash.exe"), Path("C:/Program Files/Git/usr/bin/bash.exe")) if p.is_file()), Path("bash"))
SEVERITY_ORDER = {"red": 0, "yellow": 1, "unmeasured": 2}
SEVERITY_AR = {"red": "أحمر", "yellow": "أصفر", "unmeasured": UNMEASURED}


@dataclass(frozen=True)
class Thresholds:
    approved_min: int = 30
    pushed_min: int = 120
    pr_min: int = 60
    routed_hours: int = 24
    preview_min: int = 60
    ready_min: int = 60
    silent_min: int = 30


@dataclass(frozen=True)
class Row:
    severity: str  # red | yellow | unmeasured
    case: int
    subject: str
    age_min: int | None
    owner: str
    action: str
    ref: str


def _age_min(iso: str, now: datetime) -> int:
    return int((now - datetime.fromisoformat(iso)).total_seconds() // 60)


def _severity(age: int, limit: int) -> str:
    return "red" if age >= 2 * limit else "yellow"


def _holder(item: dict) -> str:
    return item.get("held_by") or "—"


def _find_pr(cid: str, prs: list[dict]) -> dict | None:
    hits = [p for p in prs if cid in f"{p.get('title', '')}\n{p.get('body') or ''}"]
    return max(hits, key=lambda p: p["number"]) if hits else None


def approved_not_pushed(items: dict, now: datetime, th: Thresholds) -> list[Row]:
    rows = []
    for it in items.values():
        if it["state"] != "approved":
            continue
        age = _age_min(it["state_ts"], now)
        if age > th.approved_min:
            rows.append(Row(_severity(age, th.approved_min), 1, "معتمدٌ لم يُدفع", age, _holder(it), "ادفعي الآن (بعد approval_check)", it["id"]))
    return rows


def pushed_not_merged(items: dict, prs: list[dict] | None, now: datetime, th: Thresholds) -> list[Row]:
    rows = []
    for it in items.values():
        if it["state"] != "pushed":
            continue
        age = _age_min(it["state_ts"], now)
        if age <= th.pushed_min:
            continue
        sev = _severity(age, th.pushed_min)
        if prs is None:
            rows.append(Row("unmeasured", 2, f"مدفوعٌ لم يُدمج — الطلب {UNMEASURED} (gh)", age, "0601", "تحقّقي من الطلب يدوياً", it["id"]))
            continue
        pr = _find_pr(it["id"], prs)
        if pr is None:
            action = "افتحي الطلب وادمجي"
        elif pr["state"] == "MERGED":
            action = f"الطلب #{pr['number']} مدموج: حدّثي الدفتر (merged)"
        elif pr["state"] == "CLOSED":
            action = f"الطلب #{pr['number']} مُغلق بلا دمج: افتحي بديلاً"
        else:
            action = f"ادمجي الطلب #{pr['number']}"
        rows.append(Row(sev, 2, "مدفوعٌ لم يُدمج", age, "0601", action, it["id"]))
    return rows


def red_or_pending_prs(prs: list[dict] | None, now: datetime, th: Thresholds) -> list[Row]:
    if prs is None:
        return [Row("unmeasured", 3, f"فحوصُ الطلبات {UNMEASURED} (gh)", None, "0601 و0702", "تحقّقوا من الطلبات يدوياً", "—")]
    rows = []
    for raw in prs:
        if raw["state"] != "OPEN" or raw.get("isDraft"):
            continue
        p = pr_watch.normalize(raw)
        age = int(pr_watch._age(p["created"], now))
        if p["checks"] not in ("red", "pending") or age <= th.pr_min:
            continue
        cids = CARD_RE.findall(p["text"])
        ref = f"#{p['n']}" + (f" ({cids[0]})" if cids else "")
        if p["checks"] == "red":
            rows.append(Row("red", 3, f"طلبٌ بفحصٍ أحمر — {p['title']}", age, "0601 و0702", "أعيدي التشغيل أو صنّفي العطل", ref))
        else:
            rows.append(Row(_severity(age, th.pr_min), 3, f"طلبٌ معلَّق الفحوص — {p['title']}", age, "0601 و0702", "أعيدي أو صنّفي", ref))
    return rows


def routed_stale_or_not_full(items: dict, now: datetime, th: Thresholds) -> list[Row]:
    rows = []
    for it in items.values():
        if it["state"] != "routed":
            continue
        age = _age_min(it["state_ts"], now)
        tier = ledger.effective_spec_tier(it)
        if tier != "full":
            rows.append(Row("red" if age >= th.routed_hours * 60 else "yellow", 4, f"موجَّهةٌ بمواصفةٍ {tier} لا full", age, "0301", "أكملي المواصفة full أو أعيديها", it["id"]))
        elif age > th.routed_hours * 60:
            rows.append(Row(_severity(age, th.routed_hours * 60), 4, "موجَّهةٌ لم تبدأ", age, f"{_holder(it)} / 0101", "ابدئي أو أعيدي التوجيه", it["id"]))
    return rows


def parse_preview(text: str) -> tuple[list[tuple[str, int]], bool]:
    """(طابورُ الانتظار [(الشجرة، دقائقُ الانتظار)]، أهو تثبيتٌ منتهٍ)."""
    queue, expired = [], False
    for line in text.splitlines():
        m = QUEUE_LINE.match(line)
        if m:
            queue.append((m.group(1), int(m.group(2))))
        elif line.startswith("الوضع:") and "pin" in line and PIN_EXPIRED.search(line):
            expired = True
    return queue, expired


def preview_rows(text: str | None, th: Thresholds) -> list[Row]:
    if text is None:
        return [Row("unmeasured", 5, f"تثبيتُ 8500 والطابور {UNMEASURED} (preview.sh status)", None, "0501", "افحصي preview.sh status يدوياً", "8500")]
    queue, expired = parse_preview(text)
    rows = []
    if expired:
        rows.append(Row("red", 5, "تثبيتُ 8500 منتهٍ", None, "0501", "حرّري التثبيت أو ثبّتي التالي", "8500"))
    if queue:
        name, wait = max(queue, key=lambda q: q[1])
        if wait > th.preview_min:
            rows.append(Row(_severity(wait, th.preview_min), 5, f"طابورُ تثبيت 8500: {len(queue)} بالانتظار، أقدمُها {name}", wait, "0501", "اعرضي التالي أو أخرجي الراكد", name))
    return rows


def ready_without_evidence(items: dict, now: datetime, th: Thresholds) -> list[Row]:
    rows = []
    for it in items.values():
        if it["state"] != "ready_for_review":
            continue
        age = _age_min(it["state_ts"], now)
        if age <= th.ready_min:
            continue
        has_pack = any(
            n["text"].startswith("(0502)") and n["ts"] >= it["state_ts"] and EVIDENCE_NOTE.search(n["text"])
            for n in it["notes"]
        )
        if not has_pack:
            rows.append(Row(_severity(age, th.ready_min), 6, "جاهزٌ للمعاينة بلا حزمة أدلّة", age, "0502", "التقطي الأدلّة وسجّلي ملاحظةً", it["id"]))
    return rows


def _actor_after(events: list[dict], cid: str, since: str, actor: str) -> bool:
    for ev in events:
        if ev["id"] != cid or ev["ts"] <= since:
            continue
        if ev["kind"] == "state" and ev["data"].get("by") == actor:
            return True
        if ev["kind"] == "note" and ev["data"].get("text", "").startswith(f"({actor})"):
            return True
    return False


def silent_sessions(items: dict, events: list[dict], now: datetime, th: Thresholds) -> list[Row]:
    rows = []
    for it in items.values():
        target = {"routed": it.get("held_by") or "", "ready_for_review": "0501"}.get(it["state"], "")
        if not target:
            continue
        age = _age_min(it["state_ts"], now)
        if age > th.silent_min and not _actor_after(events, it["id"], it["state_ts"], target):
            rows.append(Row(_severity(age, th.silent_min), 7, f"إحالةٌ بلا ردّ ({it['state']})", age, target, f"استيقظي على {it['id']} أو أعيدي الإحالة", it["id"]))
    return rows


def collect(events: list[dict], prs: list[dict] | None, preview_text: str | None, now: datetime, th: Thresholds) -> list[Row]:
    items = ledger.reduce_state(events)
    rows = [
        *approved_not_pushed(items, now, th),
        *pushed_not_merged(items, prs, now, th),
        *red_or_pending_prs(prs, now, th),
        *routed_stale_or_not_full(items, now, th),
        *preview_rows(preview_text, th),
        *ready_without_evidence(items, now, th),
        *silent_sessions(items, events, now, th),
    ]
    return sorted(rows, key=lambda r: (SEVERITY_ORDER[r.severity], -(r.age_min or 0), r.case, r.ref))


def _fmt_age(minutes: int | None) -> str:
    if minutes is None:
        return "—"
    return f"{minutes // 60} س {minutes % 60} د" if minutes >= 60 else f"{minutes} د"


def render_text(rows: list[Row]) -> str:
    head = ("الشدّة", "البند", "العمر", "المالك", "الإجراء", "الرمز")
    body = [(SEVERITY_AR[r.severity], f"{r.case}) {r.subject}", _fmt_age(r.age_min), r.owner, r.action, r.ref) for r in rows]
    widths = [max(len(str(x[i])) for x in [head, *body]) for i in range(len(head))]
    lines = [" | ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)) for row in [head, *body]]
    counts = {s: sum(1 for r in rows if r.severity == s) for s in SEVERITY_ORDER}
    summary = f"— أحمر {counts['red']}، أصفر {counts['yellow']}، {UNMEASURED} {counts['unmeasured']}"
    return "\n".join([lines[0], "-" * len(lines[0]), *lines[1:], summary])


def render_html(rows: list[Row], now: datetime) -> str:
    color = {"red": "#fde8e8", "yellow": "#fff6d6", "unmeasured": "#eee"}
    tr = "".join(
        f"<tr style='background:{color[r.severity]}'><td>{SEVERITY_AR[r.severity]}</td><td>{r.case}) {html.escape(r.subject)}</td>"
        f"<td>{_fmt_age(r.age_min)}</td><td>{html.escape(r.owner)}</td><td>{html.escape(r.action)}</td><td>{html.escape(r.ref)}</td></tr>"
        for r in rows
    )
    return (
        "<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>متابعة الفلو</title>"
        "<style>body{font-family:Tajawal,Tahoma,sans-serif;margin:1rem}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #ccc;padding:.4rem .6rem;text-align:start}th{background:#6b1d2a;color:#fff}</style>"
        f"<h1>متابعة الفلو</h1><p>قراءةٌ فقط — {now.astimezone(ledger.DOHA):%Y-%m-%d %H:%M} بتوقيت الدوحة</p>"
        f"<table><tr><th>الشدّة</th><th>البند</th><th>العمر</th><th>المالك</th><th>الإجراء</th><th>الرمز</th></tr>{tr}</table></html>"
    )


def fetch_prs(attempts: int = 3, pause: float = 5.0) -> list[dict] | None:
    """طلباتُ GitHub بدالّة pr_watch نفسِها مع إعادةٍ قصيرة: GraphQL يُسقط الاستعلامَ الكبيرَ بـ504 أحياناً؛ وبعد الإعادات تبقى None = غير مقيس."""
    for i in range(attempts):
        rows = pr_watch.fetch()
        if rows is not None:
            return rows
        if i < attempts - 1:
            time.sleep(pause)
    return None


def read_preview_status(script: Path | None) -> str | None:
    existing = [p for p in PREVIEW_CANDIDATES if p.is_file()]
    candidate = script or (max(existing, key=lambda p: p.stat().st_mtime) if existing else None)  # الأحدثُ لا الأقدمُ من شجراتٍ شتّى
    if candidate is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603  (أمرُ status قراءةٌ فقط، والمسارُ من قائمةٍ ثابتة أو معاملٍ صريح)
            [str(GIT_BASH), "scripts/preview.sh", "status"],
            cwd=candidate.parent.parent, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 and out.stdout.strip() else None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", help="اكتبي ملفَّ HTML عربيّاً بهذا المسار (اختياري)")
    ap.add_argument("--no-live", action="store_true", help="بلا gh ولا preview (يُطبعان غير مقيسَين)")
    ap.add_argument("--now", help="لحظةٌ ISO للاختبار")
    ap.add_argument("--preview-sh", type=Path)
    d = Thresholds()
    for name in ("approved_min", "pushed_min", "pr_min", "routed_hours", "preview_min", "ready_min", "silent_min"):
        ap.add_argument(f"--{name.replace('_', '-')}", type=int, default=getattr(d, name))
    args = ap.parse_args(argv)
    th = Thresholds(**{n: getattr(args, n) for n in Thresholds.__dataclass_fields__})
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone(timedelta(hours=3)))
    try:
        events = ledger.load_events()
    except (OSError, ValueError) as exc:
        print(f"تعذّرت قراءةُ الدفتر: {exc}")
        return 1
    prs = None if args.no_live else fetch_prs()
    preview_text = None if args.no_live else read_preview_status(args.preview_sh)
    rows = collect(events, prs, preview_text, now, th)
    print(render_text(rows))
    if args.html:
        Path(args.html).write_text(render_html(rows, now), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
