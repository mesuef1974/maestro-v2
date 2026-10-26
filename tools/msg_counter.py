#!/usr/bin/env python3
"""عدّادُ رسائل الجلسات — حصّةُ 600 رسالةٍ لكلّ جلسة (قرار المالك 2026-10-22؛ كانت 300 في D-447م، و150 في D-414م، وأصله D-347م).

تنبيهٌ صريح: هذا عدّادٌ طوعيّ تُحدّثه كلُّ جلسةٍ بنفسها بعد كلّ إرسال؛ لا يفرض حدّاً ولا يرفع
القيدَ الفعليَّ في تطبيق Claude Desktop (يُعاد ضبطه حين يكتب المالكُ في الجلسة). وظيفته أن
ترى الجلسةُ والمالكُ كم بقي قبل الحدّ فتجمع الأسئلة وتتوقّف عند الاقتراب منه.

الاستعمال:
  python msg_counter.py add <رقم الجلسة> [عدد]   # بعد كلّ إرسال (الافتراضي 1)
  python msg_counter.py status [رقم الجلسة]      # الحالة (لجلسةٍ أو للجميع)
  python msg_counter.py reset [رقم الجلسة]       # تصفيرٌ يبدأ العدّ من الآن (يُنفَّذ بأمر المالك فقط)
  python msg_counter.py show                     # جدولُ الجميع مرتّباً بالأكثر استهلاكاً
  python msg_counter.py hook                     # من خطّاف PostToolUse لأداة الإرسال (JSON على stdin): يزيد عدّاد المرسِل عند التسليم أو الطابور فقط (W-20261026-008)

الملف: ../msg_counter.json (بجوار مجلّد tools). كلُّ كتابةٍ ذرّيّة (ملفٌّ مؤقّت ثمّ استبدال).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

LIMIT = 600  # قرار المالك 2026-10-22 (كان 300 D-447م، وقبله 150 D-414م)
WARN_AT = 80  # عند هذا العدد يُنبَّه إلى اقتراب الحدّ
STATE = Path(__file__).resolve().parent.parent / "msg_counter.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"limit": LIMIT, "started": _now(), "sessions": {}}


def _save(data: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    for attempt in range(5):  # جلساتٌ متوازية قد تتصادم؛ نعيد المحاولة قصيراً
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(tmp, STATE)
            return
        except OSError:
            time.sleep(0.2 * (attempt + 1))
    raise SystemExit("تعذّرت كتابةُ العدّاد بعد عدّة محاولات")


def _line(num: str, row: dict, limit: int) -> str:
    used = row["count"]
    left = limit - used
    flag = ""
    if used >= limit:
        flag = " — بلغت الحدّ: توقّف وانتظر أن يكتب المالكُ في الجلسة"
    elif used >= WARN_AT:
        flag = " — اقتربت من الحدّ: اجمع الأسئلة في رسالةٍ واحدة"
    return f"{num}: أُرسل {used} من {limit} (بقي {left})، آخر إرسال {row.get('last', '—')}{flag}"


SEND_TOOLS = ("SendMessage", "send_message")  # اسمُ الأداة ينتهي بأحدهما (mcp__ccd_session_mgmt__send_message)
DELIVERED = re.compile(r"delivery:\s*(?:delivered|queued)", re.IGNORECASE)


def _flatten(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " ".join(_flatten(v) for v in x.values())
    if isinstance(x, list):
        return " ".join(_flatten(v) for v in x)
    return str(x or "")


def sent_ok(payload: dict) -> bool:
    """هل أُرسلت الرسالةُ فعلاً (delivered أو queued)؟ الرفضُ والخطأ وundelivered لا تُعدّ."""
    if not str(payload.get("tool_name", "")).endswith(SEND_TOOLS):
        return False
    resp = payload.get("tool_response")
    if isinstance(resp, dict) and resp.get("is_error"):
        return False
    return bool(DELIVERED.search(_flatten(resp)))


def sender_num(payload: dict) -> str | None:
    """رقمُ المرسِل من عنوان الجلسة الحيّ (session_identity) بلا انتظار؛ None إن لم يُحسَم."""
    try:
        import session_identity as si

        title, _ = si.app_title(str(payload.get("cwd", "")), str(payload.get("session_id", "")), wait_s=0)
        m = re.match(r"\s*(\d{4})(?![\w-])", title or "")
        return m.group(1) if m else None
    except Exception:  # noqa: BLE001 — الخطّاف لا يُسقط الجلسة
        return None


APP_LIMIT = 10  # حدُّ التطبيق: عشرُ رسائلَ بين الجلسات منذ آخر رسالةٍ كتبها المالك (قرار 0101 على 008)
APP_WARN_AT = 8
TRANSCRIPT_TAIL = 2_000_000
_NOT_OWNER = ("<system-reminder", "<cross-session-message", "<ci-monitor-event", "<side-sessions-event", "<command-", "<local-command")


def _is_owner_message(d: dict) -> bool:
    """رسالةُ مستخدمٍ حقيقيّة: نصٌّ لا tool_result ولا حقنٌ آليّ ولا رسالةُ جلسةٍ أخرى."""
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return False
    content = (d.get("message") or {}).get("content")
    parts = [content] if isinstance(content, str) else [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
    texts = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
    return bool(texts) and not any(t.startswith(_NOT_OWNER) for t in texts)


def sends_since_owner(transcript_path: str, current_id: str = "") -> int:
    """عددُ الإرسالات الناجحة (delivered/queued) بعد آخر رسالةٍ كتبها المالكُ فعلاً، من ذيل transcript.
    `current_id` معرّفُ الاستدعاء الجاري: يُحسب إن لم يكن نتيجتُه مكتوبةً بعدُ في الملفّ. 0 عند تعذّر القراءة."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - TRANSCRIPT_TAIL))
            lines = f.read().decode("utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    send_ids: set[str] = set()
    counted: set[str] = set()
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        if _is_owner_message(d):
            send_ids, counted = set(), set()
            continue
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and str(b.get("name", "")).endswith(SEND_TOOLS):
                send_ids.add(b.get("id", ""))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in send_ids and DELIVERED.search(_flatten(b.get("content"))):
                counted.add(b["tool_use_id"])
    return len(counted | ({current_id} if current_id and current_id not in counted else set()))


def hook(raw: str) -> int:
    """خطّاف PostToolUse: يزيد عدّادَ المرسِل بواحدٍ عند نجاح الإرسال فقط، ويطبع التنبيهَ عند اقتراب الحدّ."""
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict) or not sent_ok(payload):
        return 0
    num = sender_num(payload)
    if not num:
        return 0
    data = _load()
    data["limit"] = LIMIT
    row = data["sessions"].setdefault(num, {"count": 0, "since": data["started"]})
    row["count"] += 1
    row["last"] = _now()
    _save(data)
    notes = []
    if row["count"] >= WARN_AT:
        notes.append(_line(num, row, LIMIT))
    since = sends_since_owner(str(payload.get("transcript_path", "")), str(payload.get("tool_use_id", "")))
    if since >= APP_WARN_AT:
        notes.append(f"تنبيه حدّ التطبيق: أرسلتَ {since} رسائل بين الجلسات منذ آخر رسالةٍ كتبها المالك (الحدّ {APP_LIMIT}): "
                     "اجمع ما تبقّى في رسالةٍ واحدة أو توقّف حتى يكتب المالك.")
    if notes:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": " ".join(notes)}}, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd == "hook":
        return hook(sys.stdin.read())
    data = _load()
    # الحدّ من الشيفرة لا من الملفّ: الحقل المخزَّن أبقى 150 بعد رفعه إلى 300 (D-447م)
    data["limit"] = limit = LIMIT
    sessions = data["sessions"]

    if cmd == "add":
        if len(argv) < 3:
            print("أعطِ رقم الجلسة: add <رقم> [عدد]")
            return 2
        num = argv[2]
        n = int(argv[3]) if len(argv) > 3 else 1
        row = sessions.setdefault(num, {"count": 0, "since": data["started"]})
        row["count"] += n
        row["last"] = _now()
        _save(data)
        print(_line(num, row, limit))
        return 0 if row["count"] < limit else 1

    if cmd == "status":
        if len(argv) > 2:
            num = argv[2]
            row = sessions.get(num, {"count": 0, "since": data["started"]})
            print(_line(num, row, limit))
        else:
            print(f"بدأ العدّ {data['started']} والحدّ {limit} لكلّ جلسة")
            for num, row in sorted(sessions.items()):
                print(_line(num, row, limit))
        return 0

    if cmd == "reset":
        if len(argv) > 2:
            sessions[argv[2]] = {"count": 0, "since": _now()}
        else:
            data["started"] = _now()
            data["sessions"] = {}
        _save(data)
        print(f"صُفّر العدّاد؛ يبدأ العدّ من {_now()}")
        return 0

    if cmd == "show":
        print(f"بدأ العدّ {data['started']} والحدّ {limit} لكلّ جلسة")
        for num, row in sorted(sessions.items(), key=lambda kv: -kv[1]["count"]):
            print(_line(num, row, limit))
        if not sessions:
            print("لا إرسال مسجَّلاً بعد")
        return 0

    print(f"أمرٌ غير معروف: {cmd}")
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
