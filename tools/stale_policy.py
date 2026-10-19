"""سياسةُ البطاقات الراكدة (P0-1 ملحق، قرار المالك 2026-10-19 05:04) — وضعُ العرض فقط: تحسب ما كان سيحدث ولا تكتب.

    - بطاقةٌ موجَّهة (routed أو in_progress) لها حاملٌ بلا إيداعٍ على فرعها 72 ساعةً ← «تُعاد إلى طابور 0101» برسالةٍ واحدة له.
    - بطاقةٌ approved بلا دفعٍ ساعتين ← «تنبيهُ الحامل» مرّةً كلَّ ساعتين.
    لا إغلاقَ ولا أرشفةَ ولا تغييرَ حالةٍ هنا أبداً. غيابُ قياسِ نشاط الفرع يعني «غير مقيس» لا «راكدة».
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable

BRANCH_CODE = re.compile(r"w(\d{8})-(\d{3})", re.I)
STALE_ROUTED_H = 72
STALE_APPROVED_H = 2
NUDGE_EVERY_H = 2


def _age_h(ts: str | None, now: dt.datetime) -> float | None:
    if not ts:
        return None
    try:
        return (now - dt.datetime.fromisoformat(ts)).total_seconds() / 3600
    except ValueError:
        return None


def branches_of(code: str, branches: list[str]) -> list[str]:
    n = code.removeprefix("W-")
    tag = n.lower()
    return [b for b in branches if any(f"{m.group(1)}-{m.group(2)}" == tag for m in BRANCH_CODE.finditer(b))]


def plan(
    items: dict[str, dict],
    now: dt.datetime,
    branches: list[str] | None,
    last_commit: Callable[[str], dt.datetime | None],
    last_nudge: dict[str, str] | None = None,
) -> dict:
    """{return_to_queue, nudge, unmeasured}؛ كلُّ عنصرٍ يحمل الرمزَ والحاملَ والعمرَ بالساعات."""
    out: dict = {"return_to_queue": [], "nudge": [], "unmeasured": []}
    last_nudge = last_nudge or {}
    for code, it in sorted(items.items()):
        state, holder = it.get("state"), it.get("held_by")
        age = _age_h(it.get("state_ts"), now)
        if state in ("routed", "in_progress") and holder and age is not None and age >= STALE_ROUTED_H:
            if branches is None:
                out["unmeasured"].append(code)
                continue
            latest = [c for b in branches_of(code, branches) if (c := last_commit(b))]
            idle_h = min((_age_h(c.isoformat(), now) for c in latest), default=age)
            if idle_h is not None and idle_h >= STALE_ROUTED_H:
                out["return_to_queue"].append({"card": code, "holder": holder, "state": state, "idle_h": round(idle_h)})
        elif state == "approved" and holder and age is not None and age >= STALE_APPROVED_H:
            since = _age_h(last_nudge.get(code), now)
            if since is None or since >= NUDGE_EVERY_H:
                out["nudge"].append({"card": code, "holder": holder, "waiting_h": round(age, 1)})
    return out
