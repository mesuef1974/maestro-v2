#!/usr/bin/env python3
"""إنذارُ توقّف مراقب الطلبات (W-20261002-036، قاعدةُ المالك: الأتمتةُ داخل كود المنصّة لا سكربت ويندوز).

مراقبُ الطلبات `pr_watch --loop` يعيش في Monitor مهلتُه 30 دقيقةً فيموت صامتاً (توقّف 820 دقيقةً). هذه الأداةُ تقرأ نبضتَه
(`pr_watch.heartbeat_age`) وتقارنها بعتبةٍ قابلةٍ للضبط (الافتراضيّ 10 د، أو `PR_WATCH_ALARM_MIN`)، فإن تجاوزتها أو كانت آخرُ دورةٍ
فاشلةً طبعت **إنذاراً واحداً لكلّ توقّفٍ** لـ0601 (المناوبة) ولـ0101 (يُبلغ المالكَ)، ثمّ لا تُكرّره حتى يعود النبضُ حيّاً فيُعاد تسليحُها.
لا إنذارَ قبل أوّل نبضةٍ ولا ليلاً (23:00 حتى 07:00 بتوقيت الدوحة). لا تعدّل شيئاً سوى ملفّ حالتها.

سطرُ الخرج كـred_notify (مفصولٌ بـTab):  إحالة <رقم المستلم> <معرّف الجلسة أو —> <نصّ الرسالة>
وتُشغَّل من Monitor منفصلٍ عن pr_watch (أو من `--once` دورياً): فلا تموتُ بموت المراقب الذي تحرسه.

    python heartbeat_alarm.py --once [--dry-run]
    python heartbeat_alarm.py --loop [--interval 300]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

STATE_FILE = ROOT / "ledger" / "heartbeat_alarm_state.json"
DOHA = timezone(timedelta(hours=3))
DEFAULT_THRESHOLD_MIN = 10
ON_DUTY, OWNER_PROXY = "0601", "0101"


def threshold_min() -> float:
    try:
        return float(os.environ.get("PR_WATCH_ALARM_MIN", DEFAULT_THRESHOLD_MIN))
    except ValueError:
        return float(DEFAULT_THRESHOLD_MIN)


def in_hours(now: datetime) -> bool:
    return 7 <= now.astimezone(DOHA).hour < 23


def evaluate(age_min: float | None, ok: bool, state: dict, now: datetime, threshold: float) -> str | None:
    """نصُّ الإنذار إن وجب إنذارٌ جديدٌ لهذا التوقّف، وإلّا None. يعدّل `state` في مكانه.

    الحيّ (نبضٌ حديثٌ وناجح) يُعيد التسليحَ؛ والتوقّفُ الواحدُ يُنذَر مرّةً واحدةً ما دام لم يعد حيّاً.
    """
    if age_min is None:
        return None  # لا نبضةَ قطّ: لا شيءَ يُحرس بعد
    if ok and age_min <= threshold:
        state["alarmed"] = False
        return None
    if state.get("alarmed") or not in_hours(now):
        return None
    state["alarmed"] = True
    state["at"] = now.isoformat(timespec="seconds")
    if not ok and age_min <= threshold:
        why = f"آخرُ دورةٍ قبل {int(age_min)} د فشلت (تعذّر gh)"
    else:
        why = f"آخرُ نبضةٍ قبل {int(age_min)} د (العتبة {int(threshold)} د)"
    return f"مراقبُ الطلبات pr_watch متوقّفٌ: {why}. أعِد تسليحَه بأداة Monitor: python C:/Users/mesue/delivery_manager_work/tools/pr_watch.py --loop"


def load_state(path: Path = STATE_FILE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def messages(text: str, directory: dict) -> list[tuple[str, str, str]]:
    return [(to, (directory.get(to) or {}).get("id", "—"), text) for to in (ON_DUTY, OWNER_PROXY)]


def cycle(
    now: datetime,
    dry_run: bool = False,
    directory: dict | None = None,
    state_path: Path = STATE_FILE,
    heartbeat_path: Path | None = None,
) -> list[tuple[str, str, str]]:
    import pr_watch

    if directory is None:
        import session_directory

        directory = session_directory.entries()
    hb = heartbeat_path or pr_watch.HEARTBEAT
    state = load_state(state_path)
    text = evaluate(pr_watch.heartbeat_age(now, hb), pr_watch.heartbeat_ok(hb), state, now, threshold_min())
    if not dry_run:
        save_state(state, state_path)
    return messages(text, directory) if text else []


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="لا يحفظ الحالة")
    args = ap.parse_args(argv)
    if not (args.once or args.loop):
        ap.error("اختر --once أو --loop")
    while True:
        for to, sid, text in cycle(datetime.now(UTC), args.dry_run):
            print(f"إحالة\t{to}\t{sid}\t{text}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
