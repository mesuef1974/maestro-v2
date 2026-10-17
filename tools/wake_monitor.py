#!/usr/bin/env python3
"""مراقبُ الإيقاظ — W-20261009-021 (أتمتةُ الرسائل «ب»): يحسب من أحداث الدفتر من يُوقَظ، ولا يرسل بنفسه.

المُطلِق: تغيّرُ حالةِ بطاقةٍ لها حاملٌ (held_by) بعد المؤشّر المحفوظ. الإرسالُ الفعليّ بيد المنفِّذ
(`send_message` أداةُ التطبيق لا تُستدعى من بايثون)؛ والأداةُ تطبع لكلّ جلسةٍ رسالةً واحدةً مدمجةً بمعرّفها `local_<uuid>`.

الضوابط: لا إيقاظ إلا بعد نجاح ground_truth على الحالة وعلى حامل الدفتر؛ فشلُه يمنع الإرسالَ ويُسجَّل.
جلسةٌ بلا بطاقةٍ فعلاً لا تُوقَظ. الحمولةُ معرّفٌ وحالةٌ وعبارةُ «اقرأ ledger show» لا غير. حدُّ الدفعات 20 وسقفُ الجلسات الحيّة 14.

    python tools/wake_monitor.py            # عرضٌ فقط: الخطّةُ بلا كتابة
    python tools/wake_monitor.py --commit   # يقدّم المؤشّر ويسجّل في wake_log.jsonl بعد أن تُرسَل الرسائل
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import ledger  # noqa: E402  (قراءةٌ فقط)

EVENTS = ROOT / "ledger" / "events.jsonl"
CURSOR = ROOT / "wake_cursor.json"
LOG = ROOT / "wake_log.jsonl"
MAX_BATCH = 20
MAX_LIVE = 14
TEST_CHANNEL = frozenset({"0701", "0702", "0103", "0102"})  # أسبوعُ التجربة (W-20261017-007) قبل تعميم الإرسال
COUNTER_GUARD = 130  # فوقها (من 150) لا إرسال ويُبلَّغ 0101
COUNTER = ROOT / "msg_counter.json"
LIVE_WINDOW_MS = 120 * 60 * 1000  # «حيّة» = نشاطٌ خلال ساعتين
SESSION_NUM = re.compile(r"^\d{4}")
PAYLOAD = "{id} {state} — اقرأ: python tools/ledger.py show {id}"
PAYLOAD_OK = re.compile(r"^W-\d{8}-\d{3} [a-z_]+ — اقرأ: python tools/ledger\.py show W-\d{8}-\d{3}$")


class WakePlan:
    def __init__(self) -> None:
        self.wakes: dict[str, list[tuple[str, str]]] = {}
        self.skipped: list[tuple[str, str]] = []
        self.halted: str = ""
        self.cursor: str = ""


def read_events(path: Path) -> list[dict]:
    out = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and {"ts", "id", "kind", "data"} <= ev.keys():
            out.append(ev)
    return out


def payload(item_id: str, state: str) -> str:
    text = PAYLOAD.format(id=item_id, state=state)
    if not PAYLOAD_OK.match(text):
        raise ValueError(f"حمولةٌ خارج الصيغة المسموحة: {text!r}")
    return text


def changed(events: list[dict], cursor: str) -> dict[str, str]:
    """بطاقاتٌ تغيّرت حالتُها بعد المؤشّر ← الحالةُ الجديدة؛ والأحدثُ يغلب لكلّ بطاقة."""
    out: dict[str, str] = {}
    for ev in events:
        if ev["ts"] > cursor and ev["kind"] == "state" and ev["data"].get("state"):
            out[ev["id"]] = ev["data"]["state"]
    return out


def ground_truth_ok(item_id: str, state: str) -> bool:
    r = subprocess.run(  # noqa: S603
        [sys.executable, str(HERE / "ground_truth.py"), "card", item_id],
        capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
    )
    # ground_truth card يطبع «الحالة: X» أو JSONَ الخامَ حين تتبعه سطورُ المواصفة؛ نقبل الصيغتين
    return r.returncode == 0 and (f"الحالة: {state}" in r.stdout or f'"state": "{state}"' in r.stdout)


def sender_count(sender: str, path: Path = COUNTER) -> int:
    """عدّادُ رسائل المرسِل من msg_counter.json؛ ملفٌّ غائبٌ أو تالفٌ يُعدّ حارساً مغلقاً (لا نفترض الصفر)."""
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["sessions"].get(sender, {}).get("count", 0))
    except (OSError, ValueError, KeyError, TypeError):
        return COUNTER_GUARD


def plan(events, cursor, directory, live, verify=ground_truth_ok, channel=None, sent=0) -> WakePlan:
    """directory: رقم←معرّف؛ live: أرقامُ الجلسات الحيّة؛ channel: الحاملون المسموح إيقاظُهم (None = الكلّ)؛
    sent: ما أرسله المرسِلُ حتى الآن. دالّةٌ نقيّةٌ إلّا ما يفعله verify."""
    p = WakePlan()
    p.cursor = events[-1]["ts"] if events else cursor
    items = ledger.reduce_state(events)
    todo = changed(events, cursor)
    if len(todo) > MAX_BATCH:
        p.halted = f"دفعةٌ {len(todo)} تتجاوز الحدّ {MAX_BATCH}: لا إيقاظ"
        return p
    for item_id, state in todo.items():
        it = items.get(item_id, {})
        holder = str(it.get("held_by") or "")
        if not holder or not SESSION_NUM.match(holder) or it.get("state") != state:
            p.skipped.append((item_id, "لا حاملَ فعليّاً أو الحالةُ تغيّرت بعدُ"))
            continue
        if channel is not None and holder not in channel:
            p.skipped.append((item_id, f"{holder} خارج قناة التجربة"))
            continue
        if holder not in directory:
            p.skipped.append((item_id, f"لا معرّفَ للجلسة {holder}"))
            continue
        if not verify(item_id, state):
            p.skipped.append((item_id, "فشل ground_truth: لا إرسال"))
            continue
        p.wakes.setdefault(holder, []).append((item_id, state))
    if p.wakes and sent + len(p.wakes) > COUNTER_GUARD:
        p.halted = f"حارس msg_counter: {sent} + {len(p.wakes)} رسالةً يتجاوز {COUNTER_GUARD} من 150: لا إرسال، أبلغ 0101"
        p.wakes = {}
    elif len(set(p.wakes) | set(live)) > MAX_LIVE:
        p.halted = f"الجلساتُ الحيّةُ مع الموقَظين تتجاوز {MAX_LIVE}: لا إيقاظ"
        p.wakes = {}
    return p


def live_sessions() -> set[str]:
    import session_directory as sd

    now_ms = int(time.time() * 1000)
    return {n for n, e in sd.entries().items() if now_ms - e["at"] <= LIVE_WINDOW_MS}


def message_for(session: str, rows: list[tuple[str, str]]) -> str:
    return "\n".join(payload(i, s) for i, s in rows)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commit", action="store_true", help="يقدّم المؤشّر ويسجّل wake_log ويزيد عدّاد المرسِل بعدد الرسائل")
    ap.add_argument("--sender", default="0701", help="الجلسة التي ترسل فعلاً (عدّادها هو المحروس)")
    ap.add_argument("--all", action="store_true", help="يعمّم على كلّ الحاملين بدل قناة التجربة")
    ap.add_argument("--json", action="store_true", help="خطّةٌ آليّة: قائمة {to,session_id,message}")
    a = ap.parse_args(argv)
    import session_directory as sd

    events = read_events(EVENTS)
    cursor = json.loads(CURSOR.read_text(encoding="utf-8"))["ts"] if CURSOR.is_file() else (events[-1]["ts"] if events else "")
    directory = {n: e["id"] for n, e in sd.entries().items()}
    p = plan(events, cursor, directory, live_sessions(), channel=None if a.all else TEST_CHANNEL, sent=sender_count(a.sender))
    if a.json:
        print(json.dumps([{"to": n, "session_id": directory[n], "message": message_for(n, r)} for n, r in sorted(p.wakes.items())],
                         ensure_ascii=False))
    else:
        for num, rows in sorted(p.wakes.items()):
            print(f"إلى {num} ({directory[num]}):\n{message_for(num, rows)}")
    for item_id, why in p.skipped:
        print(f"تخطٍّ {item_id}: {why}")
    if p.halted:
        print(f"توقّف: {p.halted}")
    if not p.wakes and not p.halted and not p.skipped:
        print("لا شيءَ يوقظ أحداً")
    if a.commit:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"ts": ledger.now_doha(), "wakes": {k: [i for i, _ in v] for k, v in p.wakes.items()},
                 "skipped": p.skipped, "halted": p.halted}, ensure_ascii=False) + "\n")
        if p.wakes:
            subprocess.run([sys.executable, str(HERE / "msg_counter.py"), "add", a.sender, str(len(p.wakes))], check=False)  # noqa: S603
        if not p.halted:
            CURSOR.write_text(json.dumps({"ts": p.cursor}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
