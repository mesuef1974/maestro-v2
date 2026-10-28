#!/usr/bin/env python3
"""سجلُّ الردود المنتظَرة وإعادةُ السؤال تلقائيّاً (أمرُ المالك 2026-10-03: متابعةُ الردّ تكون منّي، وإن لم يرد أسأل مرّةً أخرى).

    python pending_replies.py add --to 0101 --about "قرارُ pr_red (أ)/(ب)"
    python pending_replies.py list
    python pending_replies.py overdue [--minutes 30]     ما تأخّر ردُّه → أعيد السؤالَ فوراً بلا أمرٍ
    python pending_replies.py autoclose                 يغلق ما كُتب تقريرُه أو بلغت بطاقتُه merged/published أو اندمج/أُغلق طلبُه
    python pending_replies.py done <رقم> [--note "…"]
    python pending_replies.py asked <رقم>               سجّلتُ إعادةَ سؤال (يُحسب العدّاد)

الملفُّ `ledger/pending_replies.jsonl` يُلحَق فقط. القاعدةُ عندي: في **كلّ دورة** (رسالةُ المالك أو جلسةٍ) أشغّل `overdue` وأعيد السؤالَ لكلّ ما تأخّر، وأذكر في ختم ردّي «أنتظر: …» من هذا السجلّ لا من الذاكرة.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "ledger" / "pending_replies.jsonl"
DOHA = timezone(timedelta(hours=3))


def _rows(path: Path = FILE) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []


def _append(row: dict, path: Path = FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _now() -> datetime:
    return datetime.now(DOHA)


#: رمزُ بطاقةٍ أو طلبٍ في نصّ الإحالة: يربط البند بما يُغلقه آلياً (W-20261028-031)
CARD_RE = re.compile(r"(?<![A-Za-z0-9])W-\d{8}-\d{3}(?!\d)")
PR_RE = re.compile(r"(?<![A-Za-z0-9&])#(\d{1,6})(?!\d)")
#: حالاتُ البطاقة التي تنتهي عندها المتابعة
DONE_CARD_STATES = {"merged", "published"}
DONE_PR_STATES = {"MERGED", "CLOSED"}


def add(to: str, about: str, path: Path = FILE, now: datetime | None = None, from_: str = "", strict: bool = False) -> int:
    """from_ (اختياري): الجلسةُ المنتظِرة، فتظهر في حقل waiting من حالتها (W-20261025-001).
    strict: يرفض about بلا رمز بطاقةٍ W-… أو طلبٍ #… فلا تبقى إحالةٌ لا يُعرف متى تنتهي (W-20261028-031)."""
    if strict and not (CARD_RE.search(about) or PR_RE.search(about)):
        raise ValueError("about بلا رمز بطاقة W-YYYYMMDD-NNN ولا رقم طلب #N — اذكر ما تنتظره")
    n = sum(1 for r in _rows(path) if r["kind"] == "add") + 1
    row = {"kind": "add", "n": n, "ts": (now or _now()).isoformat(timespec="minutes"), "to": to, "about": about.strip()}
    if from_:
        row["from"] = from_
    _append(row, path)
    return n


def open_items(path: Path = FILE) -> list[dict]:
    rows = _rows(path)
    closed = {r["n"] for r in rows if r["kind"] == "done"}
    asked: dict[int, list[str]] = {}
    for r in rows:
        if r["kind"] == "asked":
            asked.setdefault(r["n"], []).append(r["ts"])
    out = []
    for r in rows:
        if r["kind"] == "add" and r["n"] not in closed:
            last = asked.get(r["n"], [r["ts"]])[-1]
            out.append({**r, "last": last, "asks": len(asked.get(r["n"], []))})
    return out


def overdue(minutes: float = 30.0, path: Path = FILE, now: datetime | None = None) -> list[dict]:
    now = now or _now()
    return [r for r in open_items(path) if (now - datetime.fromisoformat(r["last"])).total_seconds() / 60 >= minutes]


def done(n: int, note: str = "", path: Path = FILE) -> None:
    if not any(r["kind"] == "add" and r["n"] == n for r in _rows(path)):
        raise ValueError(f"لا بندَ برقم {n}")
    _append({"kind": "done", "n": n, "ts": _now().isoformat(timespec="minutes"), "note": note.strip()}, path)


#: مسارُ تقريرٍ مذكورٌ في نصّ الإحالة: ملفٌّ md أو json تحت handover_notes (نسبيٌّ للجذر أو مطلق)
REPORT_RE = re.compile(r"((?:[A-Za-z]:)?[\w./\\-]*handover_notes[/\\][\w./\\-]+\.(?:md|json))")


def close_reported(path: Path = FILE, base: Path | None = None) -> list[int]:
    """يُغلق آلياً كلَّ بندٍ مفتوحٍ يذكر نصُّه ملفَّ تقرير handover_notes وقد كُتب بعد تسجيل البند (W-20261026-008):
    الجلسةُ التي كتبت تقريرَها لا تبقى منتظِرةً ولا يُسأل عنها. يعيد أرقامَ ما أُغلق؛ لا يرفع استثناءً."""
    base = base or FILE.parent.parent
    closed: list[int] = []
    for r in open_items(path):
        m = REPORT_RE.search(r["about"])
        if not m:
            continue
        f = Path(m.group(1).replace("\\", "/"))
        f = f if f.is_absolute() else base / f
        try:
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime, DOHA) >= datetime.fromisoformat(r["ts"]):
                done(r["n"], f"أُغلق آلياً: كُتب التقرير {m.group(1)}", path)
                closed.append(r["n"])
        except (OSError, ValueError):
            continue
    return closed


def _default_card_state(card: str) -> str | None:
    import ledger  # noqa: PLC0415 — تأخيرٌ حتى لا يُحمَّل الدفترُ لمن لا يغلق آلياً

    item = ledger.reduce_state(ledger.load_events()).get(card)
    return item.get("state") if item else None


def _default_pr_state(num: str) -> str | None:
    import ground_truth  # noqa: PLC0415

    return ground_truth.default_pr_state(num)


def close_by_state(path: Path = FILE, card_state=None, pr_state=None) -> list[int]:
    """يُغلق كلَّ بندٍ مفتوحٍ تبلغ كلُّ بطاقاته merged/published وكلُّ طلباته MERGED/CLOSED، ويكتب الدليلَ في note.
    بندٌ بلا رمزٍ (قديم) أو برمزٍ مجهولٍ أو غيرِ منتهٍ يبقى؛ ولا يرفع استثناءً (W-20261028-031)."""
    card_state = card_state or _default_card_state
    pr_state = pr_state or _default_pr_state
    closed: list[int] = []
    for r in open_items(path):
        cards = CARD_RE.findall(r["about"])
        prs = PR_RE.findall(r["about"])
        if not cards and not prs:
            continue
        evidence: list[str] = []
        try:
            for c in dict.fromkeys(cards):
                st = card_state(c)
                if st not in DONE_CARD_STATES:
                    break
                evidence.append(f"{c} {st}")
            else:
                for num in dict.fromkeys(prs):
                    st = pr_state(num)
                    if not st or st.split()[0] not in DONE_PR_STATES:
                        break
                    evidence.append(f"#{num} {st}")
                else:
                    done(r["n"], "أُغلق آلياً: " + "؛ ".join(evidence), path)
                    closed.append(r["n"])
        except Exception:  # noqa: BLE001 — مصدرٌ غائب (شبكة/دفتر) لا يوقف الإغلاق لغيره
            continue
    return closed


def asked(n: int, path: Path = FILE) -> None:
    if not any(r["kind"] == "add" and r["n"] == n for r in _rows(path)):
        raise ValueError(f"لا بندَ برقم {n}")
    _append({"kind": "asked", "n": n, "ts": _now().isoformat(timespec="minutes")}, path)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("--to", required=True); a.add_argument("--about", required=True); a.add_argument("--from", dest="from_", default="", help="الجلسةُ المنتظِرة (تُدوَّن في waiting)")
    sub.add_parser("list")
    o = sub.add_parser("overdue"); o.add_argument("--minutes", type=float, default=30.0)
    d = sub.add_parser("done"); d.add_argument("n", type=int); d.add_argument("--note", default="")
    k = sub.add_parser("asked"); k.add_argument("n", type=int)
    sub.add_parser("autoclose", help="يُغلق البنودَ التي كُتب تقريرُها أو بلغت بطاقتُها/طلبُها حالةً منتهية")
    x = ap.parse_args()
    if x.cmd == "add":
        try:
            print(f"سُجّل #{add(x.to, x.about, from_=x.from_, strict=True)}")
        except ValueError as e:
            print(f"رُفض: {e}", file=sys.stderr)
            return 2
    elif x.cmd in ("list", "overdue"):
        items = open_items() if x.cmd == "list" else overdue(x.minutes)
        for r in items:
            print(f"#{r['n']} إلى {r['to']} منذ {r['ts'][5:16]} (آخرُ سؤال {r['last'][5:16]}، أُعيد {r['asks']} مرّة): {r['about'][:90]}")
        if not items:
            print("لا ردودَ منتظَرة" if x.cmd == "list" else "لا ما تأخّر")
    elif x.cmd == "autoclose":
        print("أُغلق: " + ("، ".join(f"#{n}" for n in close_reported() + close_by_state()) or "لا شيء"))
    elif x.cmd == "done":
        done(x.n, x.note); print("ok")
    else:
        asked(x.n); print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
