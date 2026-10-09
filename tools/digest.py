"""ملخّصٌ مجمَّعٌ للمايسترو ملفّاً — W-20261009-020 (قراءةٌ فقط، لا يرسل ولا يوقظ ولا يغيّر حالة).

المصدر: ledger/events.jsonl وحده (+ violations.md للمخالفات الجديدة). الناتج: digest/latest.md.
الأقسام الخمسة: انتقالاتُ الحالة، تغيّرُ held_by، routed بلا حامل، routed بلا حركة فوق 30 دقيقة،
مخالفاتٌ جديدة. النافذةُ متحرّكةٌ (افتراضاً 180 دقيقة) فلا يضيع بندٌ لم يقرأه المايسترو بعدُ، ويبقى
الملفُّ مستقرّاً (idempotent): تشغيلان متتاليان بلا تغيّرٍ لا يعيدان كتابته.

الاستعمال:
    python tools/digest.py           # مرّةً واحدة
    python tools/digest.py --loop    # كلَّ 15 دقيقة داخل الأداة (بلا جدولة Claude Code)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import ledger  # noqa: E402  (قراءةٌ فقط: reduce_state وDOHA، لا نكتب بأيٍّ من دوالّه)

OUT_DIR = ROOT / "digest"
EVENTS = ROOT / "ledger" / "events.jsonl"
VIOLATIONS = ROOT / "violations.md"
WINDOW_MIN = 180
MAX_LIST = 15  # سقفُ طول كلّ قائمةٍ في الملخّص؛ الباقي يُعدّ ولا يُسرد
STALE_MIN = 30
INTERVAL_SEC = 15 * 60
OPEN_STATE = "routed"


def read_events(path: Path) -> list[dict]:
    """قراءةٌ متسامحةٌ: سطرٌ تالفٌ يُتخطّى ولا يُسقط الملخّص."""
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and {"ts", "id", "kind", "data"} <= ev.keys():
            events.append(ev)
    return events


def parse_ts(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ledger.DOHA)


def replay(events: list[dict], since: datetime) -> tuple[dict, list[dict], list[dict]]:
    """يعيد الحالةَ الحاليّة، وانتقالاتِ الحالة، وتغيّراتِ held_by منذ since — بإعادة تشغيل الأحداث الحديثة وحدها."""
    transitions: list[dict] = []
    holders: list[dict] = []
    for i, ev in enumerate(events):
        if not (_touches(ev) and _recent(ev, since)):
            continue
        before = ledger.reduce_state(events[:i]).get(ev["id"], {})
        after = ledger.reduce_state(events[: i + 1]).get(ev["id"], {})
        if ev["kind"] in ("state", "created") and after.get("state") != before.get("state", "—"):
            transitions.append(
                {"ts": ev["ts"], "id": ev["id"], "from": before.get("state", "—"), "to": after.get("state", "—"),
                 "by": ev["data"].get("by") or after.get("state_by", "—")}
            )
        if after.get("held_by", "") != before.get("held_by", ""):
            holders.append(
                {"ts": ev["ts"], "id": ev["id"], "from": before.get("held_by") or "—", "to": after.get("held_by") or "—"}
            )
    return ledger.reduce_state(events), transitions, holders


def _touches(ev: dict) -> bool:
    return ev["kind"] in ("state", "update", "created")


def _recent(ev: dict, since: datetime) -> bool:
    ts = parse_ts(ev["ts"])
    return ts is not None and ts >= since


def last_activity(item: dict) -> datetime | None:
    """آخرُ حركةٍ للبطاقة: انتقالُ حالةٍ أو ملاحظةٌ (الإقرارُ = أن تتحرّك أو تُكتب لها ملاحظة)."""
    stamps = [parse_ts(item.get("state_ts", "")) or parse_ts(item.get("created", ""))]
    stamps += [parse_ts(n.get("ts", "")) for n in item.get("notes", [])]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


def classify_open(items: dict, now: datetime) -> tuple[list[dict], list[dict], int]:
    """(routed بلا حامل، routed بلا حركة فوق 30د، عددُ ما موعدُ بدئه لم يحن بعدُ)."""
    no_holder: list[dict] = []
    stale: list[dict] = []
    future = 0
    for item in items.values():
        if item.get("state") != OPEN_STATE:
            continue
        start = parse_ts(item.get("start", ""))
        if start and start > now:
            future += 1  # لم يحن موعدُها: لا يُنتظر إقرارٌ منها
            continue
        age = now - (last_activity(item) or now)
        if not item.get("held_by"):
            no_holder.append({"id": item["id"], "age": age})
        if age > timedelta(minutes=STALE_MIN):
            stale.append({"id": item["id"], "age": age, "held_by": item.get("held_by") or "—"})
    key = lambda r: -r["age"].total_seconds()  # noqa: E731
    return sorted(no_holder, key=key), sorted(stale, key=key), future


def violation_rows(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]


def row_key(row: str) -> str:
    return hashlib.sha1(row.encode("utf-8")).hexdigest()[:12]


def update_seen(rows: list[str], seen: dict, now: datetime) -> dict:
    """أوّلُ مشاهدةٍ لكلّ سطر؛ أوّلُ تشغيلٍ خطُّ أساسٍ (لا يُغرق الملخّصَ بتاريخ كلّه)."""
    first_run = not seen
    out = dict(seen)
    for row in rows:
        k = row_key(row)
        if k not in out:
            out[k] = {"first_seen": "baseline" if first_run else now.isoformat(timespec="seconds")}
    return out


def fmt_age(age: timedelta) -> str:
    """عمرٌ مقرَّبٌ إلى الأسفل (5 دقائق ثمّ ساعة) فلا تتبدّل الأرقام كلَّ دقيقةٍ ويبقى الملفُّ مستقرّاً."""
    minutes = int(age.total_seconds() // 60)
    if minutes >= 60:
        return f"{minutes // 60} س"
    return f"{minutes // 5 * 5} د"


def short(text: str, n: int = 140) -> str:
    text = " ".join(text.replace("|", "¦").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def render(now: datetime, window: int, transitions, holders, no_holder, stale, future, new_violations) -> str:
    lines = [
        "# ملخّصُ الدفتر للمايسترو",
        f"> نافذةٌ متحرّكةٌ: آخرُ {window} دقيقة. قراءةٌ فقط من ledger/events.jsonl؛ لا يرسل ولا يوقظ. تُحدَّث الأداةُ كلَّ 15 دقيقة، وطابعُ آخرِ فحصٍ في digest/.state.json.",
        "",
        f"## 1) انتقالاتُ الحالة ({len(transitions)})",
    ]
    lines += [f"- {t['ts'][11:16]} {t['id']}: {t['from']} ← {t['to']} (بواسطة {t['by']})" for t in transitions] or ["- لا شيء"]
    lines += ["", f"## 2) تغيّرُ الحامل held_by ({len(holders)})"]
    lines += [f"- {h['ts'][11:16]} {h['id']}: {h['from']} ← {h['to']}" for h in holders] or ["- لا شيء"]
    lines += ["", f"## 3) routed بلا حامل ({len(no_holder)})"]
    lines += [f"- {r['id']} (منذ {fmt_age(r['age'])})" for r in no_holder[:MAX_LIST]] or ["- لا شيء"]
    lines += [f"- … و{len(no_holder) - MAX_LIST} أخرى أقدمُها أعلاه"] if len(no_holder) > MAX_LIST else []
    lines += ["", f"## 4) routed بلا حركةٍ فوق {STALE_MIN} دقيقة ({len(stale)})"]
    lines += [f"- {r['id']} — الحامل {r['held_by']} — بلا حركةٍ منذ {fmt_age(r['age'])}" for r in stale[:MAX_LIST]] or ["- لا شيء"]
    lines += [f"- … و{len(stale) - MAX_LIST} أخرى"] if len(stale) > MAX_LIST else []
    lines += [f"- (استُبعدت {future} بطاقةٌ موعدُ بدئها لم يحن)"] if future else []
    lines += ["", f"## 5) مخالفاتٌ جديدةٌ في violations.md ({len(new_violations)})"]
    lines += [f"- {short(v)}" for v in new_violations] or ["- لا شيء"]
    lines += ["", f"**مقياسُ W-20261009-020:** routed بلا إقرارٍ فوق {STALE_MIN} دقيقة = {len(stale)}"]
    return "\n".join(lines) + "\n"


def build(now: datetime, events_path=EVENTS, violations_path=VIOLATIONS, seen: dict | None = None,
          window: int = WINDOW_MIN) -> tuple[str, dict]:
    events = read_events(events_path)
    since = now - timedelta(minutes=window)
    items, transitions, holders = replay(events, since)
    no_holder, stale, future = classify_open(items, now)
    seen = update_seen(violation_rows(violations_path), seen or {}, now)
    new = []
    for row in violation_rows(violations_path):
        first = seen.get(row_key(row), {}).get("first_seen", "baseline")
        ts = parse_ts(first) if first != "baseline" else None
        if ts and ts >= since:
            new.append(row)
    return render(now, window, transitions, holders, no_holder, stale, future, new), seen


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run_once(now: datetime | None = None, out_dir: Path = OUT_DIR, events_path=EVENTS,
             violations_path=VIOLATIONS, window: int = WINDOW_MIN) -> bool:
    """يكتب latest.md إن تغيّر متنُه فقط؛ يعيد True إن كُتب."""
    now = now or datetime.now(ledger.DOHA)
    state_path = out_dir / ".state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    body, seen = build(now, events_path, violations_path, state.get("violations", {}), window)
    latest = out_dir / "latest.md"
    changed = not latest.is_file() or latest.read_text(encoding="utf-8") != body
    if changed:
        write_atomic(latest, body)
    write_atomic(state_path, json.dumps({"last_check": now.isoformat(timespec="seconds"), "violations": seen},
                                        ensure_ascii=False, indent=1))
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ملخّصُ الدفتر للمايسترو (قراءةٌ فقط)")
    ap.add_argument("--loop", action="store_true", help="كلَّ 15 دقيقة داخل الأداة")
    ap.add_argument("--window", type=int, default=WINDOW_MIN, help="نافذةُ الملخّص بالدقائق")
    args = ap.parse_args(argv)
    while True:
        changed = run_once(window=args.window)
        print(("كُتب" if changed else "لا تغيير"), OUT_DIR / "latest.md")
        if not args.loop:
            return 0
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    sys.exit(main())
