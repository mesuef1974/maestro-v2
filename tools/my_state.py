#!/usr/bin/env python3
"""«أين بطاقتي الآن؟» — بطاقاتُ جلسةٍ مجمَّعةً بالفعل المطلوب منها، من الدفتر وحدَه (W-20261003-007).

    python my_state.py 0402          # ما يلزم الجلسةَ الآن
    python my_state.py 0402 --all    # ومعها المنتهيةُ (منشورةٌ/مغلقةٌ/مؤجَّلة)

قراءةٌ فقط: لا يكتب في الدفتر شيئاً.

**المالكُ مستنتَجٌ لا مسجَّل:** الدفترُ لا يحمل حقلَ مالك (قرارُ 0101: لا مساسَ بمخطّطه قبل أسبوعِ
استعمال). فالمالكُ آخرُ رقمِ جلسةٍ عاملةٍ ظهر في صدر ملاحظةٍ («0402: …») أو في `by` حدثِ حالة؛ وجلساتُ
التنسيق (المايسترو والمعاينة والدمج والخارطة…) لا تُعدّ مالكاً لأنّها تمرّ على كلّ بطاقة. ولذلك يُطبع
كلُّ سطرٍ موسوماً «مستنتَج».

والمقابلةُ بالمصدر (رأسُ الفرع، حالةُ الطلب) ليست هنا: `ground_truth.py` و`branch_status.py` لها.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime

import ledger

#: جلساتٌ تمرّ على البطاقات توجيهاً أو معاينةً أو دمجاً أو خارطةً — لا تملكها.
COORDINATORS = frozenset({"0101", "0102", "0103", "0501", "0601", "0701", "0701"})

#: رقمُ جلسةٍ في صدر ملاحظة: «0402: …» أو «0402 — …» أو «من 0402 …».
NOTE_OWNER = re.compile(r"^\s*(?:من\s+)?(\d{4})\b")
SESSION_CODE = re.compile(r"\b(\d{4})\b")

#: ملاحظةٌ بعد الدمج تدلّ على أنّ الخارطةَ أُبلغت.
ROADMAP_MARK = re.compile(r"0701|0701|خارط|roadmap", re.IGNORECASE)

DONE = ("published", "closed", "deferred")

#: الأفعالُ الخمسة بترتيب العرض.
ACTIONS = (
    ("roadmap", "بعد الدمج: أبلغي 0701 برقم الطلب"),
    ("now", "عليكِ الآن"),
    ("push", "اعتُمدت: ادفعي بالرأس المعتمَد"),
    ("waiting", "تنتظر غيرَكِ"),
    ("late", "متأخّرة: حان بدؤها ولم تبدأ"),
)


def _owner_events(events: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """لكلّ بطاقة: (زمن، رقمُ جلسةٍ عاملة) بترتيب الأحداث."""
    seen: dict[str, list[tuple[str, str]]] = {}
    for ev in events:
        data = ev.get("data") or {}
        code = None
        if ev["kind"] == "note":
            m = NOTE_OWNER.match(str(data.get("text", "")))
            code = m.group(1) if m else None
        elif ev["kind"] == "state":
            m = SESSION_CODE.search(str(data.get("by", "")))
            code = m.group(1) if m else None
        if code and code not in COORDINATORS:
            seen.setdefault(ev["id"], []).append((ev["ts"], code))
    return seen


def infer_owners(events: list[dict]) -> dict[str, str]:
    """المالكُ المستنتَج لكلّ بطاقة: آخرُ جلسةٍ عاملةٍ ظهرت فيها."""
    return {card: marks[-1][1] for card, marks in _owner_events(events).items()}


def _merged_at(events: list[dict], card: str) -> str | None:
    stamps = [e["ts"] for e in events if e["id"] == card and e["kind"] == "state" and (e.get("data") or {}).get("state") == "merged"]
    return stamps[-1] if stamps else None


def roadmap_notified(events: list[dict], card: str) -> bool:
    """ملاحظةٌ بعد آخر دمجٍ تذكر الخارطةَ أو 0701."""
    since = _merged_at(events, card)
    if since is None:
        return False
    return any(
        e["id"] == card and e["kind"] == "note" and e["ts"] >= since and ROADMAP_MARK.search(str((e.get("data") or {}).get("text", "")))
        for e in events
    )


def classify(item: dict, events: list[dict], late_ids: set[str]) -> str | None:
    """الفعلُ المطلوب من المالك، أو None لما انتهى."""
    state = item.get("state")
    if item["id"] in late_ids:
        return "late"
    if state in ("in_progress", "notes"):
        return "now"
    if state == "approved":
        return "push"
    if state in ("ready_for_review", "pushed"):
        return "waiting"
    if state == "merged":
        return None if roadmap_notified(events, item["id"]) else "roadmap"
    if state in ("captured", "verified", "routed"):
        return "now"
    return None


def describe(item: dict) -> str:
    state = item.get("state", "?")
    extra = ""
    if state == "approved" and item.get("approved_head"):
        extra = f" — الرأس {item['approved_head']}"
    elif state == "ready_for_review":
        extra = " — عند 0501"
    elif state == "pushed":
        extra = " — عند 0601"
    elif state == "notes" and item.get("notes"):
        extra = f" — آخرُ ملاحظة: {str(item['notes'][-1].get('text', ''))[:90]}"
    title = str(item.get("problem", ""))[:70]
    return f"  {item['id']} [{state}] {item.get('priority', '')} {title}{extra}  (مستنتَج)"


def pushed_without_remote(items: dict, lookup=None) -> list[str]:
    """رموزُ بطاقات pushed التي لا فرعَ بعيداً لها (أو لا فرعَ مسجَّلاً). `lookup` قابلةٌ للحقن؛ بلا شبكةٍ افتراضيّاً."""
    lookup = lookup or ledger.remote_branch_head
    bad = []
    for cid, it in items.items():
        if it.get("state") != "pushed":
            continue
        branch = it.get("branch")
        try:
            if not branch or not lookup(branch):
                bad.append(cid)
        except ledger.LedgerError:
            continue  # تعذّر الاتصال ليس دليلاً على غياب الفرع
    return sorted(bad)


def report(session: str, events: list[dict], show_all: bool = False, now: datetime | None = None,
           check_remote: bool = False, remote_lookup=None) -> str:
    items = ledger.reduce_state(events)
    warn = pushed_without_remote(items, remote_lookup) if (check_remote or remote_lookup) else []
    held = [i for i in items.values() if i.get("held_by") == session and i.get("state") not in DONE]
    owners = infer_owners(events)
    mine = {cid: it for cid, it in items.items() if owners.get(cid) == session}
    late_ids = {i["id"] for i in ledger.late_items(mine, now=now)}

    groups: dict[str, list[dict]] = {key: [] for key, _ in ACTIONS}
    finished: list[dict] = []
    for item in sorted(mine.values(), key=ledger.order_key):
        action = classify(item, events, late_ids)
        if action is None:
            finished.append(item)
        else:
            groups[action].append(item)

    lines = []
    if warn:
        lines.append(f"!! تحذير: بطاقات pushed بلا فرع بعيد ({len(warn)}): {'، '.join(warn)}\n")
    lines.append(f"== {session}: {len(mine)} بطاقةً بالمالك المستنتَج")
    if held:
        lines.append(f"محجوزةٌ باسمكِ (held_by) ({len(held)}): " + "، ".join(i["id"] for i in held))
    empty = True
    for key, label in ACTIONS:
        if groups[key]:
            empty = False
            lines.append(f"\n{label} ({len(groups[key])}):")
            lines.extend(describe(i) for i in groups[key])
    if empty:
        lines.append("\nلا شيءَ يلزمكِ الآن.")
    if show_all and finished:
        lines.append(f"\nمنتهية ({len(finished)}):")
        lines.extend(describe(i) for i in finished)
    return "\n".join(lines)


def brief_report(session: str, events: list[dict], now: datetime | None = None) -> str:
    """حالةٌ موجزةٌ ≤12 سطراً (--brief، W-20261013-033): رأسٌ بالعدد ثمّ سطرٌ لكلّ بطاقةٍ حتى عشرة."""
    items = ledger.reduce_state(events)
    owners = infer_owners(events)
    mine = {cid: it for cid, it in items.items() if owners.get(cid) == session}
    late_ids = {i["id"] for i in ledger.late_items(mine, now=now)}
    label = dict(ACTIONS)
    rows = []
    for item in sorted(mine.values(), key=ledger.order_key):
        action = classify(item, events, late_ids)
        if action is not None:
            rows.append(f"{item['id']} [{item.get('state', '?')}] {label[action]}")
    head = f"== {session}: {len(mine)} بطاقةً، المطلوب {len(rows)}"
    if not rows:
        return head + " — لا شيءَ يلزم الآن."
    lines = [head, *rows[:10]]
    if len(rows) > 10:
        lines.append(f"+{len(rows) - 10} أخرى")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="أين بطاقتي الآن؟ — من الدفتر، قراءةٌ فقط")
    parser.add_argument("session", help="رقمُ الجلسة (0402) أو اسمُها الظاهر («0402 · …»)")
    parser.add_argument("--all", action="store_true", help="اعرض المنتهيةَ أيضاً")
    parser.add_argument("--check-remote", action="store_true", help="افحص بـgit ls-remote بطاقاتِ pushed (شبكة)")
    parser.add_argument("--brief", action="store_true", help="حالةٌ موجزةٌ ≤12 سطراً")
    args = parser.parse_args()
    m = re.match(r"\s*(\d{4})\b", args.session)  # يقبل الاسمَ الظاهر كاملاً: نأخذ أوّل أربع خانات
    if not m:
        sys.exit("رقمُ الجلسة أربعةُ أرقام، مثلاً 0402")
    args.session = m.group(1)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.brief:
        print(brief_report(args.session, ledger.load_events()))
        return
    print(report(args.session, ledger.load_events(), show_all=args.all, check_remote=args.check_remote))


if __name__ == "__main__":
    main()
