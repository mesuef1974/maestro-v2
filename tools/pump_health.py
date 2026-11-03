#!/usr/bin/env python3
"""صحةُ المضخّة (W-20261025-002، البندان 3 و4) — تصعيدُ الركود وسجلٌّ يوميٌّ تقرؤه المضخّة ويغذّي النبضَ الأسبوعيّ.

التصعيد: بطاقةٌ راكدةٌ في مرحلةٍ تعالجها المضخّة (approved/pushed/merged) —
  30 دقيقة: إعادةُ إحالةٍ آليّةٌ واحدةٌ (ملاحظةٌ على البطاقة في الدفتر توقظ حاملها) مرّةً لكلّ دخولٍ في المرحلة؛
  90 دقيقة: سطرٌ في تقرير 0101 (ledger/pump_report_0101.txt) بالسبب. لا رسائلَ للمالك.
السجلّ اليوميّ: سطرٌ لكلّ يومٍ في ledger/pump_health.jsonl (idempotent): رسائلُ كلّ جلسةٍ (msg_counter)، وعمرُ كلّ بطاقةٍ في مرحلتها،
ونسبةُ العبور بلا تدخّل = حصّةُ انتقالات pushed/merged/published المسجَّلة بـ«0101» (المضخّة) من كلّها في آخر 24 ساعة.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

ROOT = HERE.parent
STAGES = ("approved", "pushed", "merged")
AGE_STATES = ("ready_for_review", *STAGES)
REREFER_MIN = 30
REPORT_MIN = 90
PUMP_BY = "0101"
#: (D-512م، أمر المالك 2026-11-03 «لا يزال المالك يصدر الأوامر») مراحلُ انتظارٍ لفاعلٍ معيَّن: الركودُ فيها يُدفع برسالةِ صندوقٍ
#: توقظ الفاعلَ التالي بخطوته (لا ملاحظةَ دفترٍ لا يقرؤها أحد ولا رسالةً للمالك). المفتاحُ (بطاقة، state_ts، مستوى) فلا تكرار.
WAIT_STATES = {
    "ready_for_review": ("0101", "راجعي الفرق واعتمدي الرأس (ledger.py move <id> approved --head) أو أعيديها بملاحظة"),
    "approved": (None, "رأسُك المعتمَد لم يُدفع: إن كانت واجهةً فاطلب تثبيتَ 8500 من 0501 ثمّ visual_gate.py run؛ وإلا فإيصال prepush على الرأس ليدفعه الآليّ"),
    "pushed": (None, "دُفع بلا طلبٍ مفتوح: افتح الطلب أو أبلغ 0101 بالعائق"),
    "merged": ("0601", "مدموجٌ غيرُ منشور: النشر في النافذة التالية ثمّ verify_deploy وتسجيل published"),
    "routed": (None, "بطاقةٌ محالةٌ إليك بلا حركةٍ يومين: ابدأها (move in_progress) أو أعدها إلى 0101 بسبب"),
    "in_progress": (None, "جاريةٌ بلا حركةٍ يومين: أبلغ 0101 بالرأس الحاليّ أو العائق في سطر"),
}
#: «pushed» وطلبُها مفتوح (W-20261028-028): لا يصحّ «دُفع بلا طلب»؛ العائقُ عند الدمج لا عند الحامل فالفاعلُ 0601
PR_WAIT = ("0601", "طلبُها #{pr} مفتوحٌ لم يندمج: راجع فحوصَه ونافذةَ الدمج (المضخّةُ تدمجه حين يخضرّ)")
#: عتباتُ الدفع بالدقائق لكلّ حالة: (الأولى، الثانية)؛ المحالةُ والجاريةُ بيومين وأربعة
NUDGE_LEVELS = {"routed": (1440, 2880), "in_progress": (1440, 2880)}
#: أقدمُ من هذا (بالدقائق) تراكمٌ لا ركود: لا يُدفع (يبقى في تقرير 0101 اليوميّ) — وإلا غمر أوّلُ تشغيلٍ الصناديقَ بعشرات البطاقات القديمة
BACKLOG_MIN = 7 * 1440
#: أقصى دفعاتٍ لفاعلٍ واحدٍ في الدورة؛ الباقي في الدورة التالية
NUDGES_PER_TARGET = 3
#: (W-20261028-006، D-429م) نافذتا الدمج الآليّ بتوقيت الدوحة: (الدفعة، البداية، النهاية) بالدقائق من منتصف الليل؛ البدايةُ مشمولةٌ والنهايةُ لا
MERGE_WINDOWS = ((1, 14 * 60 + 30, 16 * 60 + 30), (2, 19 * 60, 21 * 60))
PASS_STATES = ("pushed", "merged", "published")
COUNTER = ROOT / "msg_counter.json"


def _ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def age_minutes(item: dict, now: datetime) -> float | None:
    t = _ts(item.get("state_ts", ""))
    return None if t is None else (now - t).total_seconds() / 60


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def pr_of(cid: str, item: dict, open_prs: dict | None) -> int | None:
    """رقمُ طلب البطاقة: من الطلبات المفتوحة الحيّة إن قُرئت، وإلا من الحقل `pr` المسجَّل في الدفتر عند الفتح."""
    if open_prs is not None:
        return open_prs.get(cid)
    return item.get("pr") or None


def plan_escalations(states: dict[str, dict], done: list[dict], now: datetime, open_prs: dict | None = None) -> list[dict]:
    """[{card, level, state, state_ts, age, reason}] لم يُنفَّذ بعد؛ المفتاحُ (بطاقة، state_ts، مستوى) فلا تكرار.
    open_prs: بطاقة ← رقم طلبها المفتوح (None = لم يُقرأ)؛ لبطاقة pushed بطلبٍ يُحمل `pr` في العنصر."""
    seen = {(d["card"], d["state_ts"], d["level"]) for d in done}
    out = []
    for cid, item in sorted(states.items()):
        state = item.get("state")
        if state not in WAIT_STATES:
            continue
        age = age_minutes(item, now)
        first, second = NUDGE_LEVELS.get(state, (REREFER_MIN, REPORT_MIN))
        if age is None or age < first or age >= BACKLOG_MIN:
            continue
        # مستوىً واحدٌ في الدورة: الأعلى المستحقُّ غيرُ المنفَّذ (فلا رسالتان لبطاقةٍ واحدةٍ دفعةً واحدة)
        due = [lv for lv in (first, second) if age >= lv and (cid, item["state_ts"], lv) not in seen]
        if due:
            level = max(due)
            entry = {"card": cid, "level": level, "state": state, "state_ts": item["state_ts"], "age": int(age),
                     "held_by": item.get("held_by", ""), "first": level == first, "skipped": [lv for lv in due if lv != level]}
            if state == "pushed":
                pr = pr_of(cid, item, open_prs)
                if pr:
                    entry["pr"] = pr
            out.append(entry)
    return out


def nudge_target(e: dict) -> str:
    """الفاعلُ التالي للبطاقة الراكدة: فاعلُ الحالة الثابت أو حاملُها؛ وبلا حاملٍ 0101."""
    fixed, _ = PR_WAIT if e.get("pr") else WAIT_STATES[e["state"]]
    return fixed or e.get("held_by") or PUMP_BY


def nudge_text(e: dict) -> str:
    _, step = PR_WAIT if e.get("pr") else WAIT_STATES[e["state"]]
    step = step.replace("{pr}", str(e.get("pr", "")))
    return (f"[دفعُ المضخّة] {e['card']} راكدةٌ {e['age']} دقيقةً في «{e['state']}» — خطوتُك التالية: {step}. "
            f"لا تنتظر أمراً من المالك ولا من 0101؛ أبلغ 0101 بالعائق وحده إن وُجد.")


def _beside_ledger(name: str) -> Path:
    """ملفاتُ الصحة بجوار دفتر الجلسة الجاري (LEDGER_PATH) فلا تكتب الاختباراتُ في الدفتر الحيّ."""
    return ledger.ledger_path(None).parent / name


def _inbox_send(to: str, text: str) -> None:
    import inbox  # noqa: PLC0415

    inbox.send(to, PUMP_BY, text)


def escalation_pass(states: dict[str, dict], apply: bool, now: datetime | None = None, log=None, report=None, path=None, send=None, open_prs: dict | None = None) -> list[str]:
    """الركودُ يُدفع برسالةِ صندوقٍ توقظ الفاعلَ التالي (D-512م): المستوى الأوّل للفاعل، والثاني للفاعل و0101 معاً مع سطرٍ في التقرير."""
    now = now or datetime.now(ledger.DOHA)
    log = log or _beside_ledger("pump_escalations.jsonl")
    report = report or _beside_ledger("pump_report_0101.txt")
    send = send or _inbox_send
    out = []
    per_target: dict[str, int] = {}
    for e in plan_escalations(states, _read_jsonl(log), now, open_prs):
        mark = f"{e['card']}: راكدةٌ {e['age']} دقيقةً في «{e['state']}»"
        to = nudge_target(e)
        if per_target.get(to, 0) >= NUDGES_PER_TARGET:
            out.append(f"{mark} — مؤجَّلةٌ للدورة التالية (سقف {NUDGES_PER_TARGET} دفعاتٍ لـ{to})")
            continue
        per_target[to] = per_target.get(to, 0) + 1
        if e["first"]:
            out.append(f"{mark} — إعادةُ إحالةٍ آليّةٌ واحدة: دفعٌ إلى {to}" + ("" if apply else " (عرض)"))
            if apply:
                ledger.add_note(e["card"], f"إعادةُ إحالةٍ آليّة: {e['age']} دقيقةً في «{e['state']}» بلا حركة؛ دُفعت إلى {to}", PUMP_BY, path)
                send(to, nudge_text(e))
        else:
            out.append(f"{mark} — يدخل تقرير 0101 ويُدفع إلى {to} ثانيةً" + ("" if apply else " (عرض)"))
            if apply:
                report.parent.mkdir(parents=True, exist_ok=True)
                with report.open("a", encoding="utf-8") as f:
                    f.write(f"{now.isoformat(timespec='minutes')} {e['card']} {e['state']} {e['age']}د حامل={e['held_by'] or '—'}: ركودٌ فوق {e['level']} دقيقةً بعد إعادة الإحالة\n")
                send(to, nudge_text(e))
                if to != PUMP_BY:
                    send(PUMP_BY, f"[ركود] {e['card']} {e['age']} د في «{e['state']}» عند {to} بعد دفعتين؛ تدخّلي إن كان عائقاً.")
        if apply:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                for lv in (e["level"], *e.get("skipped", [])):  # المستوياتُ الأدنى المتجاوَزة تُختم أيضاً فلا تُرسَل لاحقاً
                    f.write(json.dumps({"card": e["card"], "level": lv, "state_ts": e["state_ts"], "ts": now.isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
    return out


def _window_end(window: str) -> datetime | None:
    """نهايةُ نافذةٍ بمعرّفها «2026-10-30:1»؛ None لمعرّفٍ غير مفهوم."""
    try:
        day, batch = window.split(":")
        end = {b: e for b, _s, e in MERGE_WINDOWS}[int(batch)]
        return datetime.fromisoformat(day).replace(hour=end // 60, minute=end % 60, tzinfo=ledger.DOHA)
    except (ValueError, KeyError):
        return None


def missed_window_pass(apply: bool, now: datetime | None = None, path: Path | None = None, report: Path | None = None) -> list[str]:
    """نافذةٌ مرّت وفيها طلبٌ مؤهَّلٌ لم يُفعَّل عليه الدمجُ الآليّ تُنتج تنبيهاً واحداً في تقرير 0101 (المضخّةُ بالخطّاف فإن لم تتحرّك
    جلسةٌ داخل النافذة فاتت). الحالةُ يكتبها merge_pass داخل النافذة؛ نافذةٌ لم تدُر فيها المضخّةُ أصلاً لا أثرَ لها هنا."""
    now = now or datetime.now(ledger.DOHA)
    path = path or _beside_ledger("merge_window_state.json")
    report = report or _beside_ledger("pump_report_0101.txt")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out, dirty = [], False
    for window, entry in sorted(state.items()):
        end = _window_end(window)
        missed = sorted(set(entry.get("eligible", [])) - set(entry.get("armed", [])))
        if end is None or now < end or entry.get("alerted") or not missed:
            continue
        nums = "، ".join(f"#{n}" for n in missed)
        out.append(f"نافذة {window} مرّت وفيها طلبٌ مؤهَّلٌ غيرُ مفعَّل ({nums})" + ("" if apply else " (عرض)"))
        if apply:
            report.parent.mkdir(parents=True, exist_ok=True)
            with report.open("a", encoding="utf-8") as f:
                f.write(f"{now.isoformat(timespec='minutes')} نافذة {window}: طلباتٌ مؤهَّلة فاتها الدمجُ الآليّ {nums}\n")
            entry["alerted"] = True
            dirty = True
    if dirty:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def pass_through(events: list[dict], now: datetime) -> dict:
    """نسبةُ العبور بلا تدخّل في آخر 24 ساعة: انتقالات PASS_STATES بتسجيل المضخّة ÷ كلّها."""
    since = now - timedelta(hours=24)
    total = pump = 0
    for ev in events:
        if ev.get("kind") != "state" or ev["data"].get("state") not in PASS_STATES:
            continue
        t = _ts(ev["ts"])
        if t is None or t < since:
            continue
        total += 1
        pump += ev["data"].get("by") == PUMP_BY
    return {"total": total, "by_pump": pump, "rate": round(pump / total, 3) if total else None}


def messages_per_session(counter: Path = COUNTER) -> dict[str, int]:
    try:
        data = json.loads(counter.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: int(v.get("count", 0)) for k, v in (data.get("sessions") or {}).items()}


def snapshot(states: dict[str, dict], events: list[dict], now: datetime, counter: Path = COUNTER) -> dict:
    ages = {}
    for cid, item in sorted(states.items()):
        if item.get("state") in AGE_STATES:
            a = age_minutes(item, now)
            if a is not None:
                ages[cid] = {"state": item["state"], "age_min": int(a)}
    return {"date": now.strftime("%Y-%m-%d"), "ts": now.isoformat(timespec="seconds"), "messages": messages_per_session(counter),
            "ages": ages, "pass_through": pass_through(events, now)}


def write_daily(states: dict[str, dict], events: list[dict], now: datetime | None = None, path: Path | None = None, counter: Path = COUNTER) -> bool:
    """يكتب لقطةَ اليوم مرّةً واحدة؛ يعيد True إن كتب."""
    now = now or datetime.now(ledger.DOHA)
    path = path or _beside_ledger("pump_health.jsonl")
    if any(r.get("date") == now.strftime("%Y-%m-%d") for r in _read_jsonl(path)):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot(states, events, now, counter), ensure_ascii=False) + "\n")
    return True


def weekly_summary(path: Path | None = None, days: int = 7, today: datetime | None = None) -> dict:
    """ما يقرؤه النبضُ الأسبوعيّ (weekly_pulse): متوسّطُ نسبة العبور وأقدمُ بطاقةٍ ومجموع الرسائل في آخر `days` يوماً."""
    today = today or datetime.now(ledger.DOHA)
    path = path or _beside_ledger("pump_health.jsonl")
    floor = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [r for r in _read_jsonl(path) if r.get("date", "") >= floor]
    rates = [r["pass_through"]["rate"] for r in rows if r.get("pass_through", {}).get("rate") is not None]
    oldest = max((a["age_min"] for r in rows for a in r.get("ages", {}).values()), default=0)
    return {"days": len(rows), "avg_pass_rate": round(sum(rates) / len(rates), 3) if rates else None, "oldest_age_min": oldest,
            "messages_latest": rows[-1].get("messages", {}) if rows else {}}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    evs = ledger.load_events()
    st = ledger.reduce_state(evs)
    if "--weekly" in sys.argv:
        print(json.dumps(weekly_summary(), ensure_ascii=False))
    else:
        print("كُتبت لقطةُ اليوم" if write_daily(st, evs) else "لقطةُ اليوم موجودةٌ أصلاً")
