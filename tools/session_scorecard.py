#!/usr/bin/env python3
"""بطاقةُ تقييم الجلسات ومساءلتها — قراءةٌ فقط: سطرٌ واحد لكل جلسة بحكمٍ (ملتزمة / تحتاج متابعة / تحتاج مساءلة).

    python session_scorecard.py [--html out.html] [--json out.json] [--now ISO] [--no-context]
                                [--suggest-state ledger/scorecard_state.json --save-state]

يبني على flow_watch (عتبات المهل) وledger_stale (آخر حالة) وrole_cards (الميثاق). أمرُ المالك 2026-10-16 (بلا بطاقة).
لا يكتب في الدفتر ولا يرسل رسائل. الكتابةُ الوحيدة: --html/--json المطلوبان وملفُّ سقف الاقتراح الأسبوعيّ بـ--save-state.
ما لا يُقاس من الدفتر (تجاوزُ المالك) يُطبع «غير مقيس» ولا يُعدّ التزاماً.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import flow_watch  # noqa: E402
import ledger  # noqa: E402
import ledger_stale  # noqa: E402

TERMINAL = ("published", "closed", "deferred", "verified")
OK, WATCH, ACCOUNT, NONE = "ملتزمة", "تحتاج متابعة", "تحتاج مساءلة", "بلا بطاقات"
HEAVY_TOKENS = 200_000
CHARTER_STALE_DAYS = 30
SESSION_NO = re.compile(r"^\d{4}$")
HEALTH_LINE = re.compile(r"(\d{4}).*?(\d+)k")
LIMITS = {
    "approved": "approved_min",
    "pushed": "pushed_min",
    "ready_for_review": "ready_min",
}


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def charter_line(root: Path, number: str) -> str:
    p = root / "role_cards" / f"{number}.md"
    if not p.is_file():
        return "—"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip()[:90]
    return "—"


def charter_age_days(root: Path, number: str, now: datetime) -> int | None:
    p = root / "role_cards" / f"{number}.md"
    if not p.is_file():
        return None
    return int((now.timestamp() - p.stat().st_mtime) // 86400)


def last_move(events: list[dict], number: str) -> str | None:
    """آخرُ حركةٍ فعليّة: حالةٌ بـ`by` الجلسة أو ملاحظةٌ تبدأ بـ«(رقمها)»."""
    best = None
    for ev in events:
        mine = (ev["kind"] == "state" and ev["data"].get("by") == number) or (
            ev["kind"] == "note"
            and ev["data"].get("text", "").startswith(f"({number})")
        )
        if mine and (best is None or _ts(ev["ts"]) > _ts(best)):
            best = ev["ts"]
    return best


def violations_open(root: Path, number: str) -> int:
    """مخالفاتٌ غير مغلقة باسم الجلسة في violations.md (صفوفُ الجدول المؤرَّخة)."""
    p = root / "violations.md"
    if not p.is_file():
        return 0
    n = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (
            len(cells) >= 6
            and re.match(r"\d{4}-\d{2}-\d{2}", cells[0])
            and number in cells[1]
            and "مفتوحة" in cells[5]
        ):
            n += 1
    return n


def reapprovals(events: list[dict], card: str) -> int:
    heads = [
        e["data"].get("head")
        for e in events
        if e["id"] == card
        and e["kind"] == "state"
        and e["data"].get("state") == "approved"
    ]
    return sum(1 for a, b in zip(heads, heads[1:], strict=False) if a and b and a != b)


def skipped_ready(events: list[dict], card: str, number: str) -> bool:
    """دفعَتها الجلسةُ دون أن يمرّ «جاهزٌ للمعاينة» قبل الدفع."""
    seen_ready = False
    for e in events:
        if e["id"] != card or e["kind"] != "state":
            continue
        st = e["data"].get("state")
        if st == "ready_for_review":
            seen_ready = True
        if st == "pushed" and e["data"].get("by") == number and not seen_ready:
            return True
    return False


def sessions_in(
    items: dict, events: list[dict], now: datetime, days: int = 14
) -> list[str]:
    nums = {
        it["held_by"]
        for it in items.values()
        if SESSION_NO.match(it.get("held_by") or "") and it["state"] not in TERMINAL
    }
    cut = now - timedelta(days=days)
    for ev in events:
        by = ev["data"].get("by") if ev["kind"] == "state" else None
        if by and SESSION_NO.match(by) and _ts(ev["ts"]) >= cut:
            nums.add(by)
    return sorted(nums)


def load_contexts(timeout: int = 60) -> dict[str, int] | None:
    """سياقُ كل جلسة بالرمز من session_health (قراءةٌ فقط)؛ فشلُه = غير مقيس (None)."""
    try:
        out = subprocess.run(  # noqa: S603
            [sys.executable, str(HERE / "session_health.py"), "--hours", "72"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    ctx: dict[str, int] = {}
    for line in out.splitlines():
        m = HEALTH_LINE.search(line)
        if m:
            ctx[m.group(1)] = max(ctx.get(m.group(1), 0), int(m.group(2)) * 1000)
    return ctx or None


def suggestions(number, items, now, root, move, viol, tokens) -> list[str]:
    """اقتراحاتُ تحديث الذاكرة/الميثاق عند محفّزٍ فقط."""
    out = []
    mine = [
        it
        for it in items.values()
        if it.get("held_by") == number or it.get("state_by") == number
    ]
    finished = any(
        it["state"] in ("published", "closed")
        and it.get("state_ts")
        and _ts(it["state_ts"]) >= now - timedelta(hours=24)
        for it in mine
    )
    started = any(
        it["state"] == "in_progress" and it.get("held_by") == number
        for it in items.values()
    )
    if finished and started:
        out.append("تغيّرت المهمة: حدّثي ذاكرتك وميثاقك المختصر بالمهمة الجديدة")
    if viol:
        out.append(f"{viol} مخالفة مفتوحة: أضيفي قاعدتها لذاكرتك")
    if tokens is not None and tokens >= HEAVY_TOKENS:
        out.append(
            f"سياقٌ {tokens // 1000}k ≥ 200k: لخّصي الذاكرة أو استبدلي الجلسة (D-441م)"
        )
    age = charter_age_days(root, number, now)
    if (
        age is not None
        and age > CHARTER_STALE_DAYS
        and (move is None or _ts(move) < now - timedelta(days=CHARTER_STALE_DAYS))
    ):
        out.append(
            f"الميثاق أقدم من {CHARTER_STALE_DAYS} يوماً ({age}) بلا حركة: راجعيه"
        )
    return out


def score(events, now, root: Path = ROOT, contexts=None, th=None) -> list[dict]:
    th = th or flow_watch.Thresholds()
    items = ledger.reduce_state(events)
    rows = []
    for number in sessions_in(items, events, now):
        mine = [
            it
            for it in items.values()
            if it.get("held_by") == number and it["state"] not in TERMINAL
        ]
        cards = [f"{it['id']}:{it['state']}" for it in mine]
        overdue, severe = [], []
        for it in mine:
            age = int(
                (now - _ts(ledger_stale.last_state_time(it))).total_seconds() // 60
            )
            if it["state"] == "routed":
                limit = th.routed_hours * 60
            else:
                key = LIMITS.get(it["state"])
                limit = getattr(th, key) if key else None
            if limit and age > limit:
                overdue.append(it["id"])
                if age >= 2 * limit:
                    severe.append(it["id"])
        all_mine = [it for it in items.values() if it.get("held_by") == number]
        skipped = [
            it["id"] for it in all_mine if skipped_ready(events, it["id"], number)
        ]
        reapp = [it["id"] for it in all_mine if reapprovals(events, it["id"]) > 0]
        move = last_move(events, number)
        move_h = round((now - _ts(move)).total_seconds() / 3600, 1) if move else None
        silent = bool(mine) and (move_h is None or move_h > 6)
        viol = violations_open(root, number)
        if severe or len(skipped) >= 2 or viol >= 2:
            verdict = ACCOUNT
        elif overdue or skipped or viol or len(reapp) >= 2 or silent:
            verdict = WATCH
        else:
            verdict = OK
        if not mine and not move:
            verdict = NONE
        rows.append(
            {
                "session": number,
                "charter": charter_line(root, number),
                "cards": cards,
                "last_move": move,
                "last_move_hours": move_h,
                "overdue": overdue,
                "severe": severe,
                "skipped_ready": skipped,
                "reapproved": reapp,
                "open_violations": viol,
                "owner_bypass": "غير مقيس",
                "verdict": verdict,
                "suggestions": suggestions(
                    number, items, now, root, move, viol, (contexts or {}).get(number)
                ),
            }
        )
    return rows


def apply_weekly_cap(rows: list[dict], state: dict, now: datetime) -> list[dict]:
    """اقتراحٌ واحد كحدٍّ أقصى لكل جلسة أسبوعياً."""
    week = now.strftime("%G-W%V")
    for r in rows:
        if not r["suggestions"]:
            continue
        if state.get(r["session"]) == week:
            r["suggestions"] = []
        else:
            r["suggestions"] = r["suggestions"][:1]
            state[r["session"]] = week
    return rows


def render_text(rows: list[dict]) -> str:
    out = [
        f"{'الجلسة':8} {'الحكم':14} {'متأخر':6} {'بلا جاهز':9} {'إعادات':7} {'آخر حركة':10} البطاقات"
    ]
    for r in rows:
        mv = "—" if r["last_move_hours"] is None else f"{r['last_move_hours']}س"
        out.append(
            f"{r['session']:8} {r['verdict']:14} {len(r['overdue']):<6} {len(r['skipped_ready']):<9} "
            f"{len(r['reapproved']):<7} {mv:10} {' '.join(r['cards'][:3])}"
        )
    return "\n".join(out)


def render_html(rows: list[dict], now: datetime) -> str:
    color = {OK: "#e6f4ea", WATCH: "#fff6d6", ACCOUNT: "#fde8e8", NONE: "#eee"}
    tr = "".join(
        f"<tr style='background:{color[r['verdict']]}'><td>{r['session']}</td><td>{html.escape(r['charter'])}</td>"
        f"<td>{html.escape('، '.join(r['cards']) or '—')}</td>"
        f"<td>{'—' if r['last_move_hours'] is None else str(r['last_move_hours']) + ' س'}</td>"
        f"<td>{html.escape('، '.join(r['overdue']) or '—')}</td>"
        f"<td>بلا جاهز: {len(r['skipped_ready'])} · إعادات اعتماد: {len(r['reapproved'])} · "
        f"مخالفات: {r['open_violations']} · تجاوز المالك: {r['owner_bypass']}</td>"
        f"<td><b>{r['verdict']}</b></td></tr>"
        for r in rows
    )
    sug = (
        "".join(
            f"<li><b>{r['session']}</b>: {html.escape(s)}</li>"
            for r in rows
            for s in r["suggestions"]
        )
        or "<li>لا محفّز اليوم</li>"
    )
    return (
        "<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>تقييم الجلسات ومساءلتها</title>"
        "<style>:root{--bg:#fff;--fg:#1c1c1c}@media(prefers-color-scheme:dark){:root{--bg:#181818;--fg:#eee}}"
        "body{background:var(--bg);color:var(--fg);font-family:Tajawal,Tahoma,sans-serif;margin:1rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #888;padding:.4rem .6rem;text-align:start;color:#1c1c1c}"
        "th{background:#6b1d2a;color:#fff}</style>"
        f"<h1>تقييم الجلسات ومساءلتها</h1><p>قراءةٌ فقط — {now.astimezone(ledger.DOHA):%Y-%m-%d %H:%M} بتوقيت الدوحة. "
        "«تجاوز المالك» غير مقيس من الدفتر.</p>"
        "<table><tr><th>الجلسة</th><th>الميثاق</th><th>البطاقات</th><th>آخر حركة</th><th>تجاوز المهلة</th>"
        f"<th>الالتزام بالفلو</th><th>الحكم</th></tr>{tr}</table>"
        f"<h2>تحديث الذاكرة والميثاق (عند محفّز، اقتراحٌ واحد أسبوعياً)</h2><ul>{sug}</ul></html>"
    )


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html")
    ap.add_argument("--json")
    ap.add_argument("--now")
    ap.add_argument("--no-context", action="store_true")
    ap.add_argument(
        "--suggest-state", type=Path, default=ROOT / "ledger" / "scorecard_state.json"
    )
    ap.add_argument("--save-state", action="store_true")
    args = ap.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(ledger.DOHA)
    try:
        events = ledger.load_events()
    except (OSError, ValueError) as exc:
        print(f"تعذّرت قراءةُ الدفتر: {exc}")
        return 1
    rows = score(events, now, ROOT, None if args.no_context else load_contexts())
    try:
        state = (
            json.loads(args.suggest_state.read_text(encoding="utf-8"))
            if args.suggest_state.is_file()
            else {}
        )
    except (OSError, ValueError):
        state = {}
    rows = apply_weekly_cap(rows, state, now)
    if args.save_state:
        args.suggest_state.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
    print(render_text(rows))
    if args.html:
        Path(args.html).write_text(render_html(rows, now), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
