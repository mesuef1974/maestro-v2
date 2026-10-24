#!/usr/bin/env python3
"""مراقبُ الإيقاظ — W-20261009-021 (أتمتةُ الرسائل «ب»): يحسب من أحداث الدفتر من يُوقَظ، ولا يرسل بنفسه.

المُطلِق: تغيّرُ حالةِ بطاقةٍ لها حاملٌ (held_by) بعد المؤشّر المحفوظ. الإرسالُ الفعليّ بيد المنفِّذ
(`send_message` أداةُ التطبيق لا تُستدعى من بايثون)؛ والأداةُ تطبع لكلّ جلسةٍ رسالةً واحدةً مدمجةً بمعرّفها `local_<uuid>`.

الضوابط: لا إيقاظ إلا بعد نجاح ground_truth على الحالة وعلى حامل الدفتر؛ فشلُه يمنع الإرسالَ ويُسجَّل.
جلسةٌ بلا بطاقةٍ فعلاً لا تُوقَظ. الحمولةُ معرّفٌ وحالةٌ وعبارةُ «اقرأ ledger show» لا غير. حدُّ الدفعات 20 وسقفُ الجلسات الحيّة 14.

    python tools/wake_monitor.py            # عرضٌ فقط: الخطّةُ بلا كتابة
    python tools/wake_monitor.py --commit   # يقدّم المؤشّر ويسجّل في wake_log.jsonl بعد أن تُرسَل الرسائل
    python tools/wake_monitor.py --stale    # يتتبّع الحالةَ القائمة: بطاقةٌ بقيت في انتظارٍ فوق حدّها تُعاد إيقاظُ مسؤولها كلَّ ساعة

وضعُ --stale (10-20، تكليف المالك): الحدثُ يُرسَل مرّةً فإن لم تتجاوب الجلسة ضاعت البطاقة (39 موجَّهةً بقيت أياماً).
فهنا الحالةُ لا الحدثُ هي المُطلِق، بحدودٍ تحمي الجلسات: رسالةٌ لكلّ جلسةٍ في الساعة، وسقفُ DAILY_CAP في اليوم.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import ledger  # noqa: E402  (قراءةٌ فقط)
import msg_counter  # noqa: E402  (الحصّةُ مصدرُها الواحد: msg_counter.LIMIT)
import session_alias as sa  # noqa: E402  (الأسماءُ المستعارة من tabs.json)

EVENTS = ROOT / "ledger" / "events.jsonl"
CURSOR = ROOT / "wake_cursor.json"
LOG = ROOT / "wake_log.jsonl"
FINGERPRINT = ROOT / "wake_fingerprint.json"  # بصمةُ آخر حالةٍ عولجت (الإيقاظُ بالتغيير لا بالزمن، أمر المالك 10-22 لتقليل التوكنز)
MAX_BATCH = 20
MAX_PER_MINUTE = 3  # أقصى جلساتٍ تُوقَظ (تبدأ عملاً) في الدقيقة؛ الزائدُ يُؤجَّل لا يُسقط (أمر المالك 10-20 بند5)
MAX_LIVE = 6  # الموجة 0.13 (W-20261023-004): لا أكثر من 6 جلسات تعمل معاً (الحيّةُ + الموقَظةُ)؛ الزائدُ يُؤجَّل في الطابور لا يُسقط
TEST_CHANNEL = frozenset({"0701", "0301"})  # أسبوعُ التجربة (W-20261017-007) قبل تعميم الإرسال؛ خرجت 0702 و0102 بدمجهما في 0701 و0103 (أمر المالك 2026-10-21)، ثمّ صارت 0103 ← 0301 بترقيم 01 (14:02)
COUNTER_MARGIN = 60  # هامشٌ تحت الحصّة لا يُرسَل بعده
COUNTER_GUARD = msg_counter.LIMIT - COUNTER_MARGIN  # فوقه (من الحصّة المقروءة) لا إرسال ويُبلَّغ 0101
COUNTER = ROOT / "msg_counter.json"
LIVE_WINDOW_MS = 15 * 60 * 1000  # «حيّة» = نشاطٌ خلال 15 دقيقة (الخاملةُ المنتهيةُ دورتُها لا تستهلك ذاكرةً ولا تُعدّ؛ كانت ساعتين فتجاوزت السقفَ دائماً)
SESSION_NUM = re.compile(r"^\d{4}")
# حالةٌ ← (من يُوقَظ: «holder» حاملُ الدفتر أو رقمُ جلسةٍ ثابتٌ، ساعاتُ الانتظار قبل أن تُعدّ عالقة)
STALE_RULES = {
    "routed": ("holder", 3),
    "in_progress": ("holder", 12),
    "approved": ("holder", 1),  # معتمدٌ لم يُدفع: الدفعُ إلزاميّ فوراً (D-429م)
    "ready_for_review": ("0501", 2),
    "pushed": ("0601", 2),
    "merged": ("0601", 3),
}
REWAKE_MIN = 10  # جلسةٌ أُوقظت للتوّ لا تُوقَظ ثانيةً قبل 10 دقائق (قرار المالك 2026-10-21؛ كان 60)
DAILY_CAP = 60  # أقصى رسائل إيقاظٍ في 24 ساعة (حدُّ التراسل 150 لكلّ جلسة)
MAX_SESSIONS_PER_RUN = 5  # لا انفجارَ رسائل: أقدمُ خمسِ جلساتٍ في الدورة والباقي في الساعة التالية
STALE_PER_MSG = 5  # أقدمُ خمس بطاقاتٍ لكلّ رسالة
PAYLOAD = "{id} {state} — اقرأ: python tools/ledger.py show {id}"
CLEAR_ID = "after_clear"  # معرّفٌ خاصٌّ لإيقاظ ما بعد المسح: لا بطاقةَ له
CLEAR_MSG = "بعد المسح — اقرأ بطاقتك role_cards/{num}.md ثمّ شغّل: python tools/my_state.py {num}"
PAYLOAD_OK = re.compile(r"^W-\d{8}-\d{3} [a-z_]+ — اقرأ: python tools/ledger\.py show W-\d{8}-\d{3}$")


class WakePlan:
    def __init__(self) -> None:
        self.wakes: dict[str, list[tuple[str, str]]] = {}
        self.skipped: list[tuple[str, str]] = []
        self.halted: str = ""
        self.cursor: str = ""
        self.deferred = False  # أُجّل بعضُها: لا يتقدّم المؤشّر فيعاد في الدورة التالية (والمُوقَظ منها لا يتكرّر بـ already)


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


def payload(item_id: str, state: str, num: str = "") -> str:
    if item_id == CLEAR_ID:
        if not SESSION_NUM.match(num):
            raise ValueError("إيقاظُ ما بعد المسح بلا رقم جلسة")
        return CLEAR_MSG.format(num=num)
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


def cap_live(p: "WakePlan", live) -> None:
    """سقفُ التزامن MAX_LIVE: الموقَظةُ الحيّةُ أصلاً لا تزيد العدّ؛ الجديدةُ تُقبل بقدر ما بقي من السقف بترتيب الخطّة، والباقي يُؤجَّل
    (p.deferred فلا يتقدّم المؤشّر فيعاد في الدورة التالية). إن امتلأ السقفُ فلا إيقاظ وتُسجَّل halted."""
    fresh = [h for h in p.wakes if h not in live]
    room = max(0, MAX_LIVE - len(set(live)))
    if len(fresh) <= room:
        return
    for holder in fresh[room:]:
        for item_id, _ in p.wakes.pop(holder):
            p.skipped.append((item_id, f"تأجيل: سقفُ {MAX_LIVE} جلساتٍ تعمل معاً"))
    p.deferred = True
    if not p.wakes:
        p.halted = f"الجلساتُ الحيّةُ مع الموقَظين تتجاوز {MAX_LIVE}: لا إيقاظ"


def plan(events, cursor, directory, live, verify=ground_truth_ok, channel=None, sent=0, already=frozenset(), recent=0,
         aliases=None) -> WakePlan:
    """directory: رقم←معرّف؛ live: أرقامُ الجلسات الحيّة؛ channel: الحاملون المسموح إيقاظُهم (None = الكلّ)؛
    aliases: رقمٌ مدمَج ← مستقبِلته (session_alias.number_map) يُحلّ به الحاملُ قبل القناة والدليل (None = بلا إحالة)؛
    sent: ما أرسله المرسِلُ حتى الآن؛ already: أزواجُ (بطاقة، حالة) أُيقظ لها من قبلُ فلا تتكرّر؛
    recent: ما أُيقظ في الدقيقة الأخيرة (سقفُ MAX_PER_MINUTE). دالّةٌ نقيّةٌ إلّا ما يفعله verify."""
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
        holder = sa.canonical(holder, aliases)  # بطاقةٌ تاريخيّةٌ بحاملٍ مدمَج تُوقظ مستقبِلتَه
        if channel is not None and holder not in channel:
            p.skipped.append((item_id, f"{holder} خارج قناة التجربة"))
            continue
        if holder not in directory:
            p.skipped.append((item_id, f"لا معرّفَ للجلسة {holder}"))
            continue
        if (item_id, state) in already:
            p.skipped.append((item_id, "أُيقظ لهذا الحدث من قبلُ: لا تكرار"))
            continue
        if not verify(item_id, state):
            p.skipped.append((item_id, "فشل ground_truth: لا إرسال"))
            continue
        p.wakes.setdefault(holder, []).append((item_id, state))
    room = max(0, MAX_PER_MINUTE - recent)
    if len(p.wakes) > room:
        for holder in list(p.wakes)[room:]:
            for item_id, _ in p.wakes.pop(holder):
                p.skipped.append((item_id, f"تأجيل: سقفُ {MAX_PER_MINUTE} إيقاظاتٍ في الدقيقة"))
        p.deferred = True
    if p.wakes and sent + len(p.wakes) > COUNTER_GUARD:
        p.halted = f"حارس msg_counter: {sent} + {len(p.wakes)} رسالةً يتجاوز {COUNTER_GUARD} من {msg_counter.LIMIT}: لا إرسال، أبلغ 0101"
        p.wakes = {}
    elif p.wakes:
        cap_live(p, live)
    return p


def woken_history(path: Path = LOG, now: datetime | None = None) -> tuple[frozenset, int]:
    """(أزواجُ (بطاقة، حالة) أُيقظ لها، وعددُ الجلسات الموقَظة في آخر دقيقة) من wake_log.jsonl."""
    now = now or datetime.now(timezone(timedelta(hours=3)))
    done, recent = set(), 0
    if not path.is_file():
        return frozenset(), 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
            at = datetime.fromisoformat(rec["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        done.update((i, st) for i, st in rec.get("pairs") or [])
        if at.tzinfo and 0 <= (now - at).total_seconds() < 60:
            recent += len(rec.get("wakes") or {})
    return frozenset(done), recent


def log_halt(p: WakePlan, path: Path = LOG, now: datetime | None = None) -> bool:
    """يسجّل التوقّفَ في wake_log.jsonl كي لا يكون صامتاً (مرّةً لكلّ نصٍّ في الساعة). يعيد True إن كتب."""
    if not p.halted:
        return False
    now = now or datetime.now(timezone(timedelta(hours=3)))
    if path.is_file():
        for line in reversed(path.read_text(encoding="utf-8").splitlines()[-20:]):
            try:
                rec = json.loads(line)
                at = datetime.fromisoformat(rec["ts"])
            except (ValueError, KeyError, TypeError):
                continue
            if rec.get("halted") == p.halted and at.tzinfo and 0 <= (now - at).total_seconds() < 60 * 60:
                return False
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": now.isoformat(timespec="seconds"), "wakes": {}, "pairs": [], "skipped": [], "halted": p.halted}, ensure_ascii=False) + "\n")
    return True


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


def read_log(path: Path = LOG) -> list[dict]:
    out = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "ts" in row:
                out.append(row)
    return out


def stale_plan(events, directory, live, now, log=(), verify=ground_truth_ok, channel=None, sent=0, aliases=None, cleared=()) -> WakePlan:
    """يوقظ مسؤولَ كلّ بطاقةٍ بقيت في حالةٍ منتظِرةٍ فوق حدّها، مرّةً في الساعة لكلّ جلسة، بسقفٍ يوميّ.
    aliases كما في plan: الحاملُ المدمَج يُحلّ إلى مستقبِلته قبل القناة والدليل.
    دالّةٌ نقيّةٌ إلّا ما يفعله verify. الحالةُ هي المُطلِق لا الحدث."""
    p = WakePlan()
    p.cursor = ""
    items = ledger.reduce_state(events)
    since: dict[str, datetime] = {}
    for ev in events:
        if ev["kind"] == "state" and ev["data"].get("state"):
            since[ev["id"]] = _dt(ev["ts"])
    last_wake: dict[str, datetime] = {}
    day_count = 0
    for row in log:
        t = _dt(row["ts"])
        for num in (row.get("wakes") or {}):
            last_wake[num] = max(t, last_wake.get(num, t))
            if now - t <= timedelta(hours=24):
                day_count += 1
    cands: dict[str, list[tuple[datetime, str, str]]] = {}
    for item_id, it in items.items():
        st = it.get("state")
        rule = STALE_RULES.get(st)
        if rule is None or item_id not in since:
            continue
        who, hours = rule
        age = now - since[item_id]
        if age < timedelta(hours=hours):
            continue
        target = str(it.get("held_by") or "") if who == "holder" else who
        if not target or not SESSION_NUM.match(target):
            p.skipped.append((item_id, f"{st} منذ {int(age.total_seconds() // 3600)}س بلا مسؤولٍ يُوقَظ"))
            continue
        target = sa.canonical(target, aliases)
        cands.setdefault(target, []).append((since[item_id], item_id, st))
    for num in sorted(cands):
        if channel is not None and num not in channel:
            p.skipped.append((num, "خارج القناة"))
            continue
        if num not in directory:
            p.skipped.append((num, f"لا معرّفَ للجلسة {num}"))
            continue
        if num in last_wake and now - last_wake[num] < timedelta(minutes=REWAKE_MIN):
            p.skipped.append((num, f"أُوقظت قبل أقلّ من {REWAKE_MIN} دقيقة"))
            continue
        for _t, item_id, st in sorted(cands[num])[:STALE_PER_MSG]:
            if verify(item_id, st):
                p.wakes.setdefault(num, []).append((item_id, st))
            else:
                p.skipped.append((item_id, "فشل ground_truth: لا إرسال"))
    for num in sorted(set(cleared)):  # جلسةٌ عليها علامةُ «مسح معلّق» ورُصدت خاملةً: تُوقَظ لتقرأ بطاقتها (W-20261025-001)
        if num in live:
            p.skipped.append((num, "علامةُ مسحٍ لجلسةٍ حيّةٍ تعمل: لا إيقاظ"))
        elif channel is not None and num not in channel:
            p.skipped.append((num, "خارج القناة"))
        elif num not in directory:
            p.skipped.append((num, f"لا معرّفَ للجلسة {num}"))
        elif num in last_wake and now - last_wake[num] < timedelta(minutes=REWAKE_MIN):
            p.skipped.append((num, f"أُوقظت قبل أقلّ من {REWAKE_MIN} دقيقة"))
        else:
            p.wakes.setdefault(num, []).append((CLEAR_ID, "pending_clear"))
            since[CLEAR_ID + num] = now
    if len(p.wakes) > MAX_SESSIONS_PER_RUN:
        oldest = sorted(p.wakes, key=lambda n: min(since[i if i != CLEAR_ID else CLEAR_ID + n] for i, _ in p.wakes[n]))[:MAX_SESSIONS_PER_RUN]
        for num in [n for n in p.wakes if n not in oldest]:
            p.skipped.append((num, "يُؤجَّل إلى الدورة التالية (حدُّ الجلسات في الدورة)"))
            del p.wakes[num]
    if p.wakes and day_count + len(p.wakes) > DAILY_CAP:
        p.halted = f"سقفُ الإيقاظ اليوميّ {DAILY_CAP}: {day_count} + {len(p.wakes)}"
        p.wakes = {}
    elif p.wakes and sent + len(p.wakes) > COUNTER_GUARD:
        p.halted = f"حارس msg_counter: {sent} + {len(p.wakes)} يتجاوز {COUNTER_GUARD} من {msg_counter.LIMIT}: لا إرسال"
        p.wakes = {}
    elif p.wakes:
        cap_live(p, live)
    return p


def fingerprint(events: list[dict], now: datetime, extra: str = "") -> str:
    """بصمةُ حالةِ الدفتر: لكلّ بطاقةٍ في حالةٍ منتظِرةٍ (id، الحالة، الحامل، وهل تجاوزت حدَّها) ثمّ `extra` (لقطةُ الطلبات).
    تغيُّرُ أيٍّ منها يغيّر البصمةَ؛ وعبورُ البطاقةِ حدَّ عُلوقها يغيّرها أيضاً فلا يضيع العالقُ بصمتِ الدفتر. دالّةٌ نقيّةٌ."""
    since: dict[str, datetime] = {}
    for ev in events:
        if ev["kind"] == "state" and ev["data"].get("state"):
            since[ev["id"]] = _dt(ev["ts"])
    rows = []
    for item_id, it in ledger.reduce_state(events).items():
        st = it.get("state")
        rule = STALE_RULES.get(st)
        if rule is None or item_id not in since:
            continue
        stale = now - since[item_id] >= timedelta(hours=rule[1])
        rows.append([item_id, st, str(it.get("held_by") or ""), stale])
    body = json.dumps([sorted(rows), extra], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def read_fingerprint(path: Path | None = None) -> str:
    path = path or FINGERPRINT  # يُقرأ عند الاستدعاء لا عند التعريف فيصحّ تبديلُه في الاختبار
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("fp", ""))
    except (OSError, ValueError, AttributeError):
        return ""  # بلا ملفٍّ أو بملفٍّ تالفٍ: «تغيّر» فيُعالَج ولا يُسكَت


def write_fingerprint(fp: str, path: Path | None = None) -> None:
    path = path or FINGERPRINT
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fp": fp, "ts": ledger.now_doha()}), encoding="utf-8")
    tmp.replace(path)  # كتابةٌ ذرّيّة: انقطاعٌ في منتصفها لا يترك بصمةً مبتورة


def report(events: list[dict], now: datetime, fp: str) -> str:
    """تقريرٌ بسكربت من الأرقام (لا قراءةَ نموذجٍ): عددُ بطاقاتِ كلّ حالةٍ منتظِرةٍ وعدد العالقِ منها."""
    since: dict[str, datetime] = {}
    for ev in events:
        if ev["kind"] == "state" and ev["data"].get("state"):
            since[ev["id"]] = _dt(ev["ts"])
    counts: dict[str, list[int]] = {}
    for item_id, it in ledger.reduce_state(events).items():
        st = it.get("state")
        rule = STALE_RULES.get(st)
        if rule is None or item_id not in since:
            continue
        c = counts.setdefault(st, [0, 0])
        c[0] += 1
        c[1] += now - since[item_id] >= timedelta(hours=rule[1])
    parts = " ؛ ".join(f"{st} {c[0]} (عالقة {c[1]})" for st, c in sorted(counts.items())) or "لا بطاقاتٍ منتظِرة"
    return f"تغيّرت الحالة [{fp}]: {parts}"


def read_pr_state(path: str | None) -> str:
    """لقطةُ الطلبات من ملفٍّ يكتبه المُنفِّذ (مثلاً خرجُ gh pr list) تدخل البصمةَ نصّاً كما هي؛ غيابُه لا يكسر."""
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def live_sessions() -> set[str]:
    import session_directory as sd

    now_ms = int(time.time() * 1000)
    return {n for n, e in sd.entries().items() if now_ms - e["at"] <= LIVE_WINDOW_MS}


def running_from_arg(text: str | None) -> set[str] | None:
    """«--running 0101,0501»: الجلساتُ العاملةُ فعلاً (isRunning) يقدّمها المنفِّذُ من list_sessions؛ ملفاتُ الجلسات على القرص بلا هذا الحقل،
    فنافذةُ النشاط تقديرٌ لا قياس. بلا القيمة يبقى التقدير القديم. تُقبل أرقامٌ من أربع خاناتٍ فقط."""
    if not text:
        return None
    return {t for t in re.split(r"[,\s]+", text.strip()) if SESSION_NUM.match(t) and len(t) == 4}


def live_minus_cleared(live: set[str], cleared, running: set[str] | None) -> set[str]:
    """جلسةٌ عليها علامةُ مسحٍ معلَّقةٍ لم تُستهلك لا تُعدّ حيّةً بنافذة النشاط: المسحُ نفسُه يجدّد ختمَ نشاطها فتبدو عاملةً وهي خاملة
    (تجربة 0101 على 0301: تُخطّيَت «حيّةً تعمل»). أمّا إن قُدِّم `--running` الفعليُّ فيُحكَم به وحدَه."""
    return set(live) if running is not None else set(live) - set(cleared)


def live_for(a) -> set[str]:
    running = running_from_arg(getattr(a, "running", None))
    return running if running is not None else live_sessions()


def message_for(session: str, rows: list[tuple[str, str]]) -> str:
    return "\n".join(payload(i, s, session) for i, s in rows)


def watch_lines(p: WakePlan, directory: dict[str, str], seen: set) -> list[str]:
    """أسطرُ المراقبة (Monitor) لما لم يُعلَن بعدُ: سطرٌ واحدٌ لكلّ جلسةٍ بمعرّفها، تبويبٌ بين الحقول والصفوفُ تفصلها « ؛ ».
    ما أُعلن بالنصّ نفسِه لا يُعاد؛ لا خرجَ إن لم يتغيّر شيء. توقّفُ الخطّة (halted) يُعلن مرّةً بنصّه."""
    out = []
    for num, rows in sorted(p.wakes.items()):
        text = " ؛ ".join(payload(i, s, num) for i, s in rows)
        if (num, text) not in seen:
            seen.add((num, text))
            out.append(f"إيقاظ\t{num}\t{directory.get(num, '—')}\t{text}")
    if p.halted and ("halt", p.halted) not in seen:
        seen.add(("halt", p.halted))
        out.append(f"توقّف\t—\t—\t{p.halted}")
    return out


def make_plan(a, events, cursor, directory) -> WakePlan:
    channel = None if a.all else TEST_CHANNEL
    aliases = sa.number_map()
    if a.stale:
        now = datetime.now().astimezone()
        import session_state

        cleared = session_state.pending_markers(ROOT, now)
        return stale_plan(events, directory, live_minus_cleared(live_for(a), cleared, running_from_arg(getattr(a, "running", None))), now,
                          log=read_log(), channel=channel, sent=sender_count(a.sender), aliases=aliases, cleared=cleared)
    hist = woken_history()
    return plan(events, cursor, directory, live_for(a), channel=channel, sent=sender_count(a.sender), already=hist[0], recent=hist[1],
                aliases=aliases)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commit", action="store_true", help="يقدّم المؤشّر ويسجّل wake_log ويزيد عدّاد المرسِل بعدد الرسائل")
    ap.add_argument("--sender", default="0701", help="الجلسة التي ترسل فعلاً (عدّادها هو المحروس)")
    ap.add_argument("--running", default="", help="أرقام الجلسات العاملة فعلاً (isRunning من list_sessions) مفصولةً بفواصل؛ تحلّ محلّ نافذة النشاط")
    ap.add_argument("--all", action="store_true", help="يعمّم على كلّ الحاملين بدل قناة التجربة")
    ap.add_argument("--stale", action="store_true", help="يتتبّع الحالةَ القائمة لا الحدث: يعيد إيقاظَ مسؤولِ كلّ بطاقةٍ عالقةٍ كلَّ ساعة (بلا تقديمِ مؤشّر)")
    ap.add_argument("--json", action="store_true", help="خطّةٌ آليّة: قائمة {to,session_id,message}")
    ap.add_argument("--watch", action="store_true", help="مراقبةٌ (Monitor): سطرٌ لكلّ جلسةٍ عند التغيّر فقط، بلا كتابة ولا تقديمِ مؤشّر؛ الإرسالُ بيد المنفِّذ")
    ap.add_argument("--interval", type=int, default=300, help="مع --watch: ثوانٍ بين الدورات")
    ap.add_argument("--changed-only", action="store_true", help="لا خطّةَ ولا إيقاظَ ولا قرارَ إلا إن تغيّرت بصمةُ الحالة عن المحفوظة (wake_fingerprint.json)، ويطبع تقريراً بسكربت عند التغيّر؛ ومع --commit تُحفَظ البصمةُ بعد المعالجة الكاملة")
    ap.add_argument("--pr-state", default="", help="ملفٌّ فيه لقطةُ الطلبات (حالاتٌ ورؤوسٌ وفحوص) تدخل البصمةَ؛ غيابُه يُهمَل")
    ap.add_argument("--once", action="store_true", help="مع --watch: دورةٌ واحدة")
    a = ap.parse_args(argv)
    import session_directory as sd

    hist = woken_history()
    if a.watch:
        seen: set = set()
        last_fp = read_fingerprint() if a.changed_only else ""
        cleared = time.time()
        while True:
            if a.stale and time.time() - cleared >= REWAKE_MIN * 60:
                seen.clear()  # الحالةُ العالقة تُعلَن من جديدٍ كلَّ ساعة
                cleared = time.time()
            try:
                events = read_events(EVENTS)
                if a.changed_only:
                    fp = fingerprint(events, datetime.now().astimezone(), read_pr_state(a.pr_state))
                    if fp == last_fp:
                        if a.once:
                            return 0
                        time.sleep(a.interval)
                        continue
                    last_fp = fp
                    print(f"# {report(events, datetime.now().astimezone(), fp)}", flush=True)
                cursor = json.loads(CURSOR.read_text(encoding="utf-8"))["ts"] if CURSOR.is_file() else (events[-1]["ts"] if events else "")
                directory = {n: e["id"] for n, e in sd.entries().items()}
                p = make_plan(a, events, cursor, directory)
                for line in watch_lines(p, directory, seen):
                    print(line, flush=True)
            except Exception as exc:  # noqa: BLE001 — المراقبةُ لا تسقط من عطلٍ عابر
                print(f"# فشلت الدورة: {exc}", file=sys.stderr, flush=True)
            if a.once:
                return 0
            time.sleep(a.interval)

    events = read_events(EVENTS)
    fp = ""
    if a.changed_only:
        fp = fingerprint(events, datetime.now().astimezone(), read_pr_state(a.pr_state))
        if fp == read_fingerprint():
            print("لا تغيّر عن آخر بصمة: لا إيقاظَ ولا قرار")
            return 0
        print(report(events, datetime.now().astimezone(), fp))
    cursor = json.loads(CURSOR.read_text(encoding="utf-8"))["ts"] if CURSOR.is_file() else (events[-1]["ts"] if events else "")
    directory = {n: e["id"] for n, e in sd.entries().items()}
    p = make_plan(a, events, cursor, directory)
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
        if not a.commit:
            log_halt(p)
    if not p.wakes and not p.halted and not p.skipped:
        print("لا شيءَ يوقظ أحداً")
    if a.commit:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"ts": ledger.now_doha(), "wakes": {k: [i for i, _ in v] for k, v in p.wakes.items()},
                 "pairs": [[i, st] for v in p.wakes.values() for i, st in v], "skipped": p.skipped, "halted": p.halted}, ensure_ascii=False) + "\n")
        if p.wakes:
            subprocess.run([sys.executable, str(HERE / "msg_counter.py"), "add", a.sender, str(len(p.wakes))], check=False)  # noqa: S603
        if not p.halted and not p.deferred and not a.stale:
            CURSOR.write_text(json.dumps({"ts": p.cursor}), encoding="utf-8")
        if fp and not p.halted and not p.deferred:
            write_fingerprint(fp)  # لا تُحفَظ عند التوقّف أو التأجيل فيُعاد النظرُ في الدورة التالية
    return 0


if __name__ == "__main__":
    sys.exit(main())
