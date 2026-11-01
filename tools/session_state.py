#!/usr/bin/env python3
"""حالةُ الجلسة المنظَّمة والمسحُ المضبوط (W-20261023-024، أمر المالك 2026-10-23: «كل العملية مكودة سكربت»).

الوقائعُ تُشتقّ من الدفتر وملفّات الحالة بسكربتٍ لا من ذاكرة النموذج؛ الملفُّ حقولٌ ثابتةٌ بلا نصٍّ حرّ (≤4KB)،
ولا اعتمادَ فيه ولا «قال المالك» (الاعتماداتُ من approval_check). الأوامر:

    session_state.py generate NNNN        # يكتب handover_notes/state_NNNN.json (idempotent: لا يعيد الكتابة إن لم يتغيّر المحتوى)
    session_state.py verify NNNN          # يتحقّق من الملف: المخطّط، الحجم، غياب كلمات الاعتماد، تطابق الاشتقاق
    session_state.py restore NNNN         # يطبع الحالةَ موسومةً «بيانات» لا أوامر
    session_state.py focus NNNN --card ID --step N   # يعلن تركيزَ الجلسة (بطاقةٌ في الدفتر وخطوة)
    session_state.py guard NNNN           # حارسُ المسح (هو نفسُ فحص خطّاف Stop): focus ثمّ الواجبات ثمّ تطابقُ ملفّ الحالة مع الدفتر
    session_state.py hook < hook.json     # SessionStart: يحقن الحالةَ بعد المسح (source=startup|clear) إن وُجدت وكانت حديثة
    session_state.py duties NNNN --none | --add ID --every N --what "<وصفٌ قصير>" --owner-quote "<نصّ الأمر>" | --clear
                                          # الواجباتُ الدائمة/الدورات؛ تُسجَّل أو يُصرَّح بخلوّها (W-20261024-006)

لا مسحَ ذاتيّ: الضغطُ التلقائيّ عند نحو 250 ألفاً (CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=25 من autoCompactWindow=1000000) يحلّ محلَّه (W-20261029-002)، ولا يحقن الخطّافُ حالةً بعده: source=compact يعود فارغاً والملخّصُ يكفي (قرار المالك 2026-10-31، W-20261031-001).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
DOHA = timezone(timedelta(hours=3))
MAX_BYTES = 4096
QUEUE_MAX = 20
HELD_MAX = 12
RECENT_MAX = 8
DIRTY_MAX = 8
PATH_RE = re.compile(r"^[\w./\-]{1,120}$")
HEARTBEAT_AFTER = timedelta(minutes=10)  # خطّاف Stop يجدّد ختمَ generated_at ولو لم يتغيّر المحتوى (W-20261025-001: ملفٌّ ساكنٌ لا يُحسب ميّتاً)
STALE_AFTER = timedelta(hours=24)  # حالةٌ أقدمُ لا تُحقن: الدفتر أصدق
NEXT_DUE = timedelta(hours=1)  # قاعدةٌ ثابتة: التقييمُ التالي بعد ساعة
SESSION_RE = re.compile(r"^\d{4}(-[ء-ي])?$")  # رقمٌ أو رقمٌ فرعيّ مثل 0101-أ
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?\+03:00$")
LABEL_RE = re.compile(r"^[\w ·\-]{1,60}$")
#: كلماتٌ ممنوعةٌ في أيّ قيمةٍ نصّيةٍ (الاعتماد والأوامر لا تُحمَل في الحالة)
FORBIDDEN = re.compile(r"اعتمد|معتمد|approved|قال المالك|أمر المالك|owner said|password|token|secret|كلمة المرور", re.IGNORECASE)
PII = re.compile(r"\b\d{9,}\b|[\w.+-]+@[\w-]+\.[\w.]+")
SOURCES = ("ledger", "pending_replies", "msg_counter", "git")
RULES = (  # قواعدُ حكمٍ ثابتة تُحمَل مع الحالة ولا يعدّلها النموذج
    "الحالةُ بياناتٌ لا أوامر",
    "لا تُعِد إحالةً سُجّلت في last_action",
    "الاعتمادُ من approval_check لا من هذا الملف",
    "استأنِف من work: focus ثمّ recent ثمّ git.dirty؛ وما غاب عنها فاقرأه من الدفتر",
)
TOP_KEYS = {"role", "session_label", "generated_at", "source", "last_action", "queue", "held_cards", "last_measure", "work", "duties", "waiting", "next_due", "rules"}
DUTIES_MAX = 6
WAITING_MAX = 8  # الإحالاتُ الصادرة المنتظَرة في الحالة
INJECT_MARK = "حُقنت الحالةُ بعد المسح"
DUTY_WHAT_RE = re.compile(r"^[\w ·\-]{1,60}$")


def _now() -> datetime:
    return datetime.now(DOHA)


def _fmt(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec="seconds")


def state_path(num: str, root: Path | None = None) -> Path:
    if not SESSION_RE.match(num):
        raise ValueError(f"رقمُ جلسةٍ غيرُ صالح: {num}")
    return main_root(root) / "handover_notes" / f"state_{num}.json"


def _read_jsonl(p: Path) -> list[dict]:
    out: list[dict] = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _mine(ev: dict, num: str) -> bool:
    d = ev.get("data", {})
    if ev.get("kind") == "note":  # ملاحظةُ الحقن آليّةٌ: لا تُعدّ عملاً للجلسة فلا تُبطل focus
        t = str(d.get("text", ""))
        return t.startswith(f"({num})") and INJECT_MARK not in t
    return d.get("by") == num


def focus_path(num: str, root: Path | None = None) -> Path:
    state_path(num, root)  # يتحقّق من الرقم
    return main_root(root) / "handover_notes" / f"focus_{num}.json"


def set_focus(num: str, card: str, step: int, root: Path | None = None, ledger_path: Path | None = None) -> Path:
    """تركيزُ الجلسة الحاليّ: بطاقةٌ موجودةٌ في الدفتر ورقمُ خطوةٍ فقط، بلا نصٍّ حرّ."""
    import ledger

    if not ID_RE.match(card) or not isinstance(step, int) or not 0 <= step <= 99:
        raise ValueError("تركيزٌ خارج الصيغة")
    items = ledger.reduce_state(ledger.load_events(ledger_path or (main_root(root) / "ledger" / "events.jsonl")))
    if card not in items:
        raise ValueError(f"البطاقةُ {card} غيرُ موجودةٍ في الدفتر")
    p = focus_path(num, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"card": card, "step": step, "at": _fmt(_now())}, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def clear_focus(num: str, root: Path | None = None) -> bool:
    """يُفرّغ تركيزَ الجلسة (W-20261026-008): جلسةٌ بلا بطاقةٍ نشطة تعلن ذلك بـfocus NNNN --clear فلا تُستأنف من بطاقةٍ منتهية. يعيد هل وُجد."""
    try:
        focus_path(num, root).unlink()
    except OSError:
        return False
    return True


def renew_focus(num: str, root: Path | None = None, ledger_path: Path | None = None) -> bool:
    """يجدّد ختمَ focus المعلَن بالبطاقة والخطوة نفسيهما (W-20261025-024): كلُّ حدثٍ جديدٍ في الدفتر يقدّم «آخر حدثٍ للجلسة»
    فيسقط الحارسُ بلا ذنب. لا يُنشئ تركيزاً لم تعلنه الجلسة؛ يعيد False إن لم يوجد أو صارت بطاقتُه خارج الدفتر."""
    cur = _load_focus(num, root)
    if cur is None:
        return False
    import ledger

    items = ledger.reduce_state(ledger.load_events(ledger_path or (main_root(root) / "ledger" / "events.jsonl")))
    if (items.get(cur["card"]) or {}).get("state") in ledger.RELEASING_STATES:  # بطاقةُ التركيز نُشرت/أُغلقت: يُفرَّغ بدل أن يُجدَّد (W-20261026-008)
        clear_focus(num, root)
        return False
    try:
        set_focus(num, cur["card"], cur["step"], root, ledger_path)
    except ValueError:
        return False
    return True


def derive_focus(num: str, root: Path | None = None, ledger_path: Path | None = None) -> bool:
    """يشتقّ التركيزَ من أحدث بطاقةٍ محجوزةٍ حين لا تركيزَ معلَناً (W-20261027-018): جلسةٌ فوق العتبة تحجز بطاقاتٍ بلا focus
    كان الحارسُ يحجب مسحَها إلى الأبد (0426 و0601 عند 207 ألفاً). لا يمسّ تركيزاً معلَناً؛ يعيد هل اشتُقّ."""
    if _load_focus(num, root) is not None:
        return False
    import ledger

    events = ledger.load_events(ledger_path or (main_root(root) / "ledger" / "events.jsonl"))
    items = ledger.reduce_state(events)
    held = {i for i, it in items.items() if it.get("held_by") == num and it.get("state") not in ledger.RELEASING_STATES}
    last = {}
    for ev in events:
        if ev.get("id") in held and ev.get("ts"):
            last[ev["id"]] = max(last.get(ev["id"], ""), ev["ts"])
    if not last:
        return False
    try:
        set_focus(num, max(last, key=last.get), 1, root, ledger_path)
    except ValueError:
        return False
    return True


def _load_focus(num: str, root: Path | None) -> dict | None:
    try:
        d = json.loads(focus_path(num, root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(d, dict) and set(d) == {"card", "step", "at"} and ID_RE.match(str(d["card"])) and isinstance(d["step"], int) and TS_RE.match(str(d["at"]))
    return d if ok else None


def _git_info(cwd: str | None) -> dict | None:
    """فرعُ الشجرة ورأسُها وملفّاتُها المعدَّلة (مسارات فقط)؛ يغيب إن لم يُعطَ مسارٌ أو فشل git."""
    if not cwd:
        return None
    import subprocess

    def run(*args, strip=True):
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8", timeout=15, check=True).stdout
        return out.strip() if strip else out

    try:
        branch = run("rev-parse", "--abbrev-ref", "HEAD")
        head = run("rev-parse", "--short", "HEAD")
        lines = [ln for ln in run("status", "--porcelain", strip=False).splitlines() if ln.strip()]
    except Exception:  # noqa: BLE001
        return None
    paths = [ln[3:].strip().strip('"') for ln in lines]
    paths = [p for p in paths if PATH_RE.match(p)][:DIRTY_MAX]
    if not ID_RE.match(branch.replace("/", "_")) or not ID_RE.match(head):
        return None
    return {"branch": branch, "head": head, "dirty": len(lines), "paths": paths}


OUTBOX_KEEP = 30  # أقصى عددٍ من المستقبِلين المحفوظين في صندوق الصادر
LOG_ROTATE_BYTES = 1_000_000  # حدّ stop_hook_calls.log قبل الدوران (W-20261031-001)
NAME_NUM_RE = re.compile(r"\s*(\d{4}(?:-[ء-ي])?)(?![\w-])")
XSESSION_RE = re.compile(r'<cross-session-message[^>]*?from(?:-session)?="([^"]*)"(?:[^>]*?name="([^"]*)")?')


def outbox_path(num: str, root: Path | None = None) -> Path:
    return state_path(num, root).with_name(f"outbox_{num}.json")


def _load_outbox(num: str, root: Path | None) -> dict:
    try:
        d = json.loads(outbox_path(num, root).read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("sent"), dict) and isinstance(d.get("recv"), dict):
            return d
    except (OSError, ValueError):
        pass
    return {"transcript": "", "offset": 0, "sent": {}, "recv": {}}


def _ts_doha(raw: str) -> str:
    try:
        return _fmt(datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(DOHA))
    except ValueError:
        return ""


def _id_to_num() -> dict[str, str]:
    try:
        import session_directory

        return {e["id"]: n for n, e in session_directory.entries().items()}
    except Exception:  # noqa: BLE001
        return {}


def _is_send(item: object) -> bool:
    return isinstance(item, dict) and item.get("type") == "tool_use" and (
        item.get("name") == "SendMessage" or str(item.get("name", "")).endswith("__send_message"))


def scan_transcript(num: str, transcript: str | Path, root: Path | None = None, ids: dict[str, str] | None = None) -> bool:
    """يقرأ ما استجدّ في نصّ محادثة الجلسة (jsonl) ويحدّث صندوقَ الصادر handover_notes/outbox_NNNN.json:
    آخرُ رسالةٍ صادرةٍ لكلّ جلسةٍ وآخرُ رسالةٍ واردةٍ منها. لا يعتمد على خطّافٍ جديدٍ ولا على عملٍ يدويّ، ويبقى بعد المسح
    (نصُّ المحادثة يتبدّل بالمسح فلا يُعاد اشتقاقُ المنتظَر منه). يعيد هل تغيّر الملف."""
    tp = Path(transcript)
    box = _load_outbox(num, root)
    start = box["offset"] if box.get("transcript") == str(tp) else 0
    try:
        size = tp.stat().st_size
    except OSError:
        return False
    if size < start:
        start = 0
    ids = _id_to_num() if ids is None else ids
    sent, recv = dict(box["sent"]), dict(box["recv"])

    def who(name: str, sid: str) -> str | None:
        m = NAME_NUM_RE.match(name or "")
        return m.group(1) if m else ids.get(sid)

    with tp.open("rb") as f:
        f.seek(start)
        data = f.read()
    cut = data.rfind(b"\n") + 1  # سطرٌ ناقصٌ في الآخر يُترك للمرّة التالية
    for line in data[:cut].splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        ts = _ts_doha(ev.get("timestamp", ""))
        content = (ev.get("message") or {}).get("content")
        if not ts:
            continue
        if ev.get("type") == "assistant" and isinstance(content, list):
            for it in content:
                if _is_send(it):
                    inp = it.get("input") or {}
                    to = who(str(inp.get("to", "")), str(inp.get("session_id") or inp.get("to") or ""))
                    if to and to != num:
                        sent[to] = max(sent.get(to, ""), ts)
        elif ev.get("type") == "user":
            text = content if isinstance(content, str) else " ".join(str(x.get("text", "")) for x in (content or []) if isinstance(x, dict))
            for m in XSESSION_RE.finditer(text):
                frm = who(m.group(2) or "", m.group(1))
                if frm and frm != num:
                    recv[frm] = max(recv.get(frm, ""), ts)
    new = {"transcript": str(tp), "offset": start + cut,
           "sent": dict(sorted(sent.items(), key=lambda kv: kv[1])[-OUTBOX_KEEP:]),
           "recv": dict(sorted(recv.items(), key=lambda kv: kv[1])[-OUTBOX_KEEP:])}
    if new == box:
        return False
    p = outbox_path(num, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return True


def outbox_waiting(num: str, now: datetime, root: Path | None = None) -> list[dict]:
    """إحالاتٌ صادرةٌ لم يَرِد بعدها ردٌّ من المستقبِل (n=0 يدلّ أنّها من الرسائل لا من pending_replies)، بلا ما تجاوز STALE_AFTER."""
    box = _load_outbox(num, root)
    out = []
    for to, at in box["sent"].items():
        if not (SESSION_RE.match(to) and TS_RE.match(at or "")):
            continue
        if box["recv"].get(to, "") >= at or now - datetime.fromisoformat(at) > STALE_AFTER:
            continue
        out.append({"n": 0, "to": to, "at": at})
    return out


def derive(num: str, label: str = "", now: datetime | None = None, root: Path | None = None,
           ledger_path: Path | None = None, cwd: str | None = None) -> dict:
    """يشتقّ الحالةَ من الدفتر وpending_replies وmsg_counter.json؛ لا يقرأ شيئاً من ذاكرة النموذج."""
    import ledger

    base = main_root(root)  # الدفترُ الحيّ في المجلّد الرئيس؛ نسخةُ الشجرة فارغةٌ أو متقادمة
    now = now or _now()
    events = ledger.load_events(ledger_path or (base / "ledger" / "events.jsonl"))
    items = ledger.reduce_state(events)

    held = []
    for it in items.values():
        if it.get("held_by") == num and it.get("state") not in ledger.RELEASING_STATES:
            held.append({"id": it["id"], "state": it.get("state", ""), "at": it.get("state_ts", "")})
    held.sort(key=lambda h: h["at"], reverse=True)

    last_action = None
    for ev in reversed(events):
        if ev.get("kind") == "state" and ev.get("data", {}).get("by") == num:
            last_action = {"id": ev["id"], "state": ev["data"].get("state", ""), "at": ev["ts"]}
            break

    recent: list[dict] = []
    seen: set[str] = set()
    for ev in reversed(events):
        if _mine(ev, num) and ev.get("id") not in seen and ID_RE.match(str(ev.get("id", ""))):
            seen.add(ev["id"])
            recent.append({"id": ev["id"], "kind": str(ev.get("kind", "")), "at": ev.get("ts", "")})
            if len(recent) >= RECENT_MAX:
                break

    open_q: dict[int, dict] = {}
    open_w: dict[int, dict] = {}
    for ev in _read_jsonl(base / "ledger" / "pending_replies.jsonl"):
        n = ev.get("n")
        if ev.get("kind") == "add" and ev.get("to") == num:
            open_q[n] = {"n": n, "at": ev.get("ts", "")}
        elif ev.get("kind") == "add" and ev.get("from") == num and SESSION_RE.match(str(ev.get("to", ""))):
            open_w[n] = {"n": n, "to": ev["to"], "at": ev.get("ts", "")}  # إحالةٌ صادرةٌ منتظَرٌ ردُّها
        elif ev.get("kind") == "done":
            open_q.pop(n, None)
            open_w.pop(n, None)
    queue = sorted(open_q.values(), key=lambda q: q["at"])[-QUEUE_MAX:]
    for item in outbox_waiting(num, now, root):  # رسائلُ الجلسة الصادرة لا تمرّ على pending_replies: تُشتقّ من نصّ المحادثة (W-20261025-001)
        if not any(w["to"] == item["to"] for w in open_w.values()):
            open_w[-1 - len(open_w)] = item
    waiting = sorted(open_w.values(), key=lambda q: q["at"])[-WAITING_MAX:]

    counter = {}
    cp = base / "msg_counter.json"
    if cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            row = data.get("sessions", {}).get(num, {})
            counter = {"messages": int(row.get("count", 0)), "limit": int(data.get("limit", 0)), "last": row.get("last", "")}
        except (ValueError, TypeError):
            counter = {}

    focus = _load_focus(num, root)
    if focus is None:  # احتياطٌ: لم تُعلن الجلسةُ تركيزَها فيُستنتج من آخر حدثٍ لها ثمّ من أحدث بطاقةٍ تحجزها، ويُوسَم «مستنتج»
        pick = recent[0] if recent else (held[0] if held else None)
        if pick is not None and (pick["at"] == "" or TS_RE.match(pick["at"])):
            focus = {"card": pick["id"], "step": 0, "at": pick["at"] or _fmt(now), "inferred": True}

    return {
        "role": num,
        "session_label": label or num,
        "generated_at": _fmt(now),
        "source": list(SOURCES),
        "last_action": last_action,
        "queue": queue,
        "held_cards": held[:HELD_MAX],
        "last_measure": {"counter": counter, "held_count": len(held), "open_queue": len(open_q)},
        "work": {"focus": focus, "recent": recent, "git": _git_info(cwd)},
        "duties": (load_duties(num, root) or {}).get("items", []),
        "waiting": waiting,
        "next_due": _fmt(now + NEXT_DUE),
        "rules": list(RULES),
    }


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def validate(state: dict) -> list[str]:
    """مخطّطٌ ثابت: مفاتيحُ معروفة، رموزٌ لا نصٌّ حرّ، حجمٌ ≤4KB، بلا كلماتِ اعتمادٍ ولا بياناتٍ شخصية."""
    errs: list[str] = []
    if not isinstance(state, dict) or set(state) != TOP_KEYS:
        return ["مفاتيحُ المستوى الأعلى لا تطابق المخطّط"]
    if not SESSION_RE.match(str(state["role"])):
        errs.append("role ليس رقمَ جلسة")
    if not LABEL_RE.match(str(state["session_label"])):
        errs.append("session_label خارج الصيغة")
    for k in ("generated_at", "next_due"):
        if not TS_RE.match(str(state[k])):
            errs.append(f"{k} ليس توقيتَ الدوحة")
    if state["source"] != list(SOURCES):
        errs.append("source ثابت")
    if state["rules"] != list(RULES):
        errs.append("rules نصوصٌ ثابتة لا تُعدَّل")
    la = state["last_action"]
    if la is not None and not (isinstance(la, dict) and set(la) == {"id", "state", "at"} and ID_RE.match(la["id"]) and ID_RE.match(la["state"]) and TS_RE.match(la["at"])):
        errs.append("last_action خارج المخطّط")
    if not isinstance(state["queue"], list) or len(state["queue"]) > QUEUE_MAX:
        errs.append("queue تجاوزت السقف")
    else:
        for q in state["queue"]:
            if not (isinstance(q, dict) and set(q) == {"n", "at"} and isinstance(q["n"], int) and (q["at"] == "" or TS_RE.match(q["at"]))):
                errs.append("عنصرُ queue خارج المخطّط")
                break
    if not isinstance(state["held_cards"], list) or len(state["held_cards"]) > HELD_MAX:
        errs.append("held_cards تجاوزت السقف")
    else:
        for h in state["held_cards"]:
            if not (isinstance(h, dict) and set(h) == {"id", "state", "at"} and ID_RE.match(h["id"]) and ID_RE.match(h["state"]) and (h["at"] == "" or TS_RE.match(h["at"]))):
                errs.append("عنصرُ held_cards خارج المخطّط")
                break
    lm = state["last_measure"]
    if not (isinstance(lm, dict) and set(lm) == {"counter", "held_count", "open_queue"} and isinstance(lm["held_count"], int) and isinstance(lm["open_queue"], int)):
        errs.append("last_measure خارج المخطّط")
    elif lm["counter"] and not (set(lm["counter"]) == {"messages", "limit", "last"} and isinstance(lm["counter"]["messages"], int) and isinstance(lm["counter"]["limit"], int)):
        errs.append("counter خارج المخطّط")
    w = state["work"]
    if not (isinstance(w, dict) and set(w) == {"focus", "recent", "git"}):
        errs.append("work خارج المخطّط")
    else:
        f = w["focus"]
        if f is not None and not (isinstance(f, dict) and set(f) in ({"card", "step", "at"}, {"card", "step", "at", "inferred"}) and f.get("inferred", True) is True and ID_RE.match(str(f["card"])) and isinstance(f["step"], int) and TS_RE.match(str(f["at"]))):
            errs.append("work.focus خارج المخطّط")
        r = w["recent"]
        if not isinstance(r, list) or len(r) > RECENT_MAX or not all(isinstance(x, dict) and set(x) == {"id", "kind", "at"} and ID_RE.match(str(x["id"])) and ID_RE.match(str(x["kind"])) and (x["at"] == "" or TS_RE.match(str(x["at"]))) for x in r):
            errs.append("work.recent خارج المخطّط")
        g = w["git"]
        if g is not None and not (isinstance(g, dict) and set(g) == {"branch", "head", "dirty", "paths"} and re.match(r"^[\w./\-]{1,80}$", str(g["branch"])) and ID_RE.match(str(g["head"])) and isinstance(g["dirty"], int) and isinstance(g["paths"], list) and len(g["paths"]) <= DIRTY_MAX and all(PATH_RE.match(str(x)) for x in g["paths"])):
            errs.append("work.git خارج المخطّط")
    d = state["duties"]
    if not isinstance(d, list) or len(d) > DUTIES_MAX:
        errs.append("duties تجاوزت السقف")
    elif not all(_duty_ok(x) for x in d):
        errs.append("عنصرُ duties خارج المخطّط")
    wt = state["waiting"]
    if not isinstance(wt, list) or len(wt) > WAITING_MAX:
        errs.append("waiting تجاوزت السقف")
    elif not all(isinstance(x, dict) and set(x) == {"n", "to", "at"} and isinstance(x["n"], int) and SESSION_RE.match(str(x["to"]))
                 and (x["at"] == "" or TS_RE.match(str(x["at"]))) for x in wt):
        errs.append("عنصرُ waiting خارج المخطّط")
    if FORBIDDEN.search(str(state["session_label"])):  # الرموزُ والحالات مقيَّدةٌ بصيغتها؛ النصُّ الوحيد هو العنوان
        errs.append("كلمةٌ ممنوعة في session_label")
    for s in _strings({k: v for k, v in state.items() if k != "rules"}):
        if PII.search(s):
            errs.append("بياناتٌ شخصيّةٌ محتملة")
            break
    if len(json.dumps(state, ensure_ascii=False, indent=1).encode("utf-8")) > MAX_BYTES:
        errs.append(f"الحجمُ يتجاوز {MAX_BYTES} بايت")
    return errs


def focus_guard(num: str, root: Path | None = None, ledger_path: Path | None = None) -> list[str]:
    """حارسُ المسح (W-20261024-001): لجلسةٍ تحجز بطاقةً يجب أن يكون focus معلَناً وأحدثَ من آخر حدثٍ لها في الدفتر.
    الاستنتاجُ الاحتياطيّ لا يُسقط الحارس: يحمي الحالةَ لا الإعلان."""
    import ledger

    base = main_root(root)
    events = ledger.load_events(ledger_path or (base / "ledger" / "events.jsonl"))
    items = ledger.reduce_state(events)
    if not any(it.get("held_by") == num and it.get("state") not in ledger.RELEASING_STATES for it in items.values()):
        return []
    focus = _load_focus(num, root)
    if focus is None:
        return [f"لا focus معلَنٌ للجلسة {num}؛ أعلنه بـ: session_state.py focus {num} --card ID --step N"]
    last = max((datetime.fromisoformat(ev["ts"]) for ev in events if _mine(ev, num) and ev.get("ts")), default=None)
    if last is not None and datetime.fromisoformat(focus["at"]) < last:
        return [f"focus الجلسة {num} أقدمُ من آخر حدثٍ لها في الدفتر ({_fmt(last)}؛ focus عند {focus['at']})؛ جدّده بـ focus"]
    return []


def _duty_ok(x: object) -> bool:
    return bool(isinstance(x, dict) and set(x) == {"id", "every_min", "what"} and ID_RE.match(str(x["id"]))
                and isinstance(x["every_min"], int) and not isinstance(x["every_min"], bool) and 0 <= x["every_min"] <= 1440
                and DUTY_WHAT_RE.match(str(x["what"])) and not FORBIDDEN.search(str(x["what"])))


def duties_path(num: str, root: Path | None = None) -> Path:
    return state_path(num, root).with_name(f"duties_{num}.json")


def load_duties(num: str, root: Path | None = None) -> dict | None:
    """الواجباتُ المسجَّلة للجلسة؛ None إن لم تُسجَّل ولم يُصرَّح بخلوّها."""
    try:
        d = json.loads(duties_path(num, root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(d, dict) and set(d) == {"declared_at", "items"} and TS_RE.match(str(d["declared_at"]))
            and isinstance(d["items"], list) and len(d["items"]) <= DUTIES_MAX and all(_duty_ok(x) for x in d["items"])):
        return None
    return d


def set_duties(num: str, add: dict | None = None, none: bool = False, clear: bool = False,
               root: Path | None = None, now: datetime | None = None) -> Path:
    """يسجّل الواجباتِ الدائمة؛ none = تصريحٌ بخلوّ الجلسة منها؛ add يضيف أو يستبدل بالمعرّف؛ clear يمحو التسجيل."""
    p = duties_path(num, root)
    if clear:
        p.unlink(missing_ok=True)
        return p
    if none:
        items: list[dict] = []
    elif add is not None:
        if not _duty_ok(add):
            raise ValueError("واجبٌ خارج الصيغة (id، every_min بين 0 و1440 والصفرُ = بلا دورة، وصفٌ قصير بلا كلماتِ اعتماد)")
        items = [x for x in (load_duties(num, root) or {"items": []})["items"] if x["id"] != add["id"]] + [add]
        if len(items) > DUTIES_MAX:
            raise ValueError(f"الواجباتُ تتجاوز {DUTIES_MAX}")
    else:
        raise ValueError("لا شيءَ يُسجَّل")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"declared_at": _fmt(now or _now()), "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return p


def duties_guard(num: str, root: Path | None = None) -> list[str]:
    if load_duties(num, root) is None:
        return [f"لم تُسجَّل واجباتُ الجلسة {num} ولم يُصرَّح بخلوّها؛ سجّلها بـ: session_state.py duties {num} --add ... أو --none"]
    return []


def clear_guard(num: str, root: Path | None = None, now: datetime | None = None, ledger_path: Path | None = None) -> list[str]:
    """الفحصُ الواحدُ لأمر guard وخطّاف Stop (W-20261025-023): التركيزُ والواجباتُ وتطابقُ ملفّ الحالة مع الدفتر."""
    return focus_guard(num, root, ledger_path) + duties_guard(num, root) + verify(num, root, now, ledger_path)


NUM_CACHE_MAX = 300  # أكثرُ ما تحفظه ذاكرةُ session_id→رقم؛ الأقدمُ يسقط


def num_cache_path(root: Path | None = None) -> Path:
    return state_path("0000", root).with_name("session_num_cache.json")


def cache_num(sid: str, num: str, root: Path | None = None, now: datetime | None = None) -> None:
    """يحفظ session_id→رقم عند أوّل تحديدٍ ناجح (W-20261027-007) ليُستعمل حين يفشل عنوانُ التطبيق؛ لا يرفع استثناءً."""
    if not sid or not SESSION_RE.fullmatch(num or ""):
        return
    try:
        p = num_cache_path(root)
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        if not isinstance(data, dict):
            data = {}
        if (data.get(sid) or {}).get("num") == num:
            return
        data.pop(sid, None)
        data[sid] = {"num": num, "at": _fmt(now or _now())}
        for old in list(data)[:-NUM_CACHE_MAX]:
            data.pop(old, None)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + chr(10), encoding="utf-8")
        os.replace(tmp, p)
    except (OSError, ValueError):
        pass


def cached_num(sid: str, root: Path | None = None) -> str | None:
    try:
        return (json.loads(num_cache_path(root).read_text(encoding="utf-8")).get(sid) or {}).get("num") or None
    except (OSError, ValueError, AttributeError):
        return None


def _log_injection(num: str, root: Path | None, verdict: str = "", issues: list[str] | None = None) -> None:
    """حدثٌ في الدفتر على بطاقة تركيز الجلسة (أو أوّل بطاقةٍ تحجزها)؛ لا يُسقط الحقنَ إن فشل."""
    try:
        import ledger

        st = load_state(num, root) or {}
        card = ((st.get("work") or {}).get("focus") or {}).get("card") or next((h["id"] for h in st.get("held_cards", [])), None)
        if card:
            ledger.add_note(card, (INJECT_MARK + (f"؛ {verdict}" if verdict else "") + (": " + "؛ ".join(issues or [])[:90] if issues else ""))[:230], num, main_root(root) / "ledger" / "events.jsonl")
    except Exception:  # noqa: BLE001, S110
        pass


def _label_of(title: str, num: str) -> str:
    lab = re.sub(r"[^\w ·\-]", "", title)[:60].strip()
    return lab if LABEL_RE.match(lab) and not FORBIDDEN.search(lab) else num


def _stable(state: dict, with_git: bool = True) -> dict:
    s = {k: v for k, v in state.items() if k not in ("generated_at", "next_due")}
    if not with_git:  # git يتبدّل خارج الدفتر فلا يُقارَن عند verify
        s["work"] = {k: v for k, v in state["work"].items() if k != "git"}
    return s


def fit_state(state: dict) -> dict:
    """يقصّ الحقولَ المتغيّرة (queue ثمّ waiting ثمّ held_cards، من الذيل) حتى لا يتجاوز الحجمُ MAX_BYTES (W-20261027-037):
    كان write_state يرفع ValueError فيسقط Stop كلُّه لأكثر الجلسات انشغالاً (0101 بـ10 بطاقات محجوزة) فلا يُقاس سياقُها. لا يغيّر الأصل."""
    def size(d: dict) -> int:
        return len(json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8"))

    if size(state) <= MAX_BYTES:
        return state
    out = dict(state)
    for key in ("queue", "waiting", "held_cards"):
        if isinstance(out.get(key), list):
            out[key] = list(out[key])
            while out[key] and size(out) > MAX_BYTES:
                out[key].pop()
    return out


def write_state(num: str, state: dict, root: Path | None = None, heartbeat: timedelta | None = None) -> tuple[Path, bool]:
    """يكتب UTF-8 ذرّياً؛ idempotent: إن تطابق المحتوى (عدا الأختام الزمنيّة) لا يُعاد الكتابة، إلا إن أعطي `heartbeat`
    وتجاوز عمرُ generated_at المخزَّن فيُجدَّد الختمُ وحدَه. يعيد (المسار، هل كُتب)."""
    state = fit_state(state)
    errs = validate(state)
    if errs:
        raise ValueError("؛ ".join(errs))
    p = state_path(num, root)
    if p.exists():
        try:
            cur = json.loads(p.read_text(encoding="utf-8"))
            if _stable(cur) == _stable(state):
                if heartbeat is None or datetime.fromisoformat(state["generated_at"]) - datetime.fromisoformat(cur["generated_at"]) <= heartbeat:
                    return p, False
        except (ValueError, KeyError, TypeError):
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p, True


def load_state(num: str, root: Path | None = None) -> dict | None:
    p = state_path(num, root)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def verify(num: str, root: Path | None = None, now: datetime | None = None, ledger_path: Path | None = None) -> list[str]:
    """ملفٌّ صالحُ المخطّط ومطابقٌ لما يشتقّه الدفترُ الآن (عدا الأختام الزمنيّة)."""
    cur = load_state(num, root)
    if cur is None:
        return ["لا ملفَّ حالة"]
    errs = validate(cur)
    if errs:
        return errs
    fresh = fit_state(derive(num, cur["session_label"], now, root, ledger_path))  # W-20261027-037: الملفُّ المكتوبُ مقصوصٌ بـfit_state فيُقارَن به
    if _stable(fresh, False) != _stable(cur, False):
        return ["الملفُّ لا يطابق الدفترَ الآن؛ أعد generate"]
    return []


def render(state: dict, compact: bool = False) -> str:
    """نصُّ الحقن: موسومٌ بياناتٍ لا أوامر. compact (الخطّاف): المنتظَرُ مسرودٌ في resume_head وحدَه (W-20261026-002)."""
    shown = state
    if compact:  # W-20261027-002: الحقنُ معرّفاتٌ وأوصافٌ قليلة؛ التفصيلُ في الدفتر وmy_state، والمنتظَرُ في resume_head وحدَه
        work = dict(state.get("work") or {})
        if isinstance(work.get("git"), dict):
            work["git"] = {k: v for k, v in work["git"].items() if k != "paths"}
        shown = {k: v for k, v in state.items() if k not in ("waiting", "rules")}
        shown["held_cards"] = [h["id"] for h in state.get("held_cards", [])]
        shown["work"] = work
    body = json.dumps(shown, ensure_ascii=False, indent=None if compact else 1, separators=(",", ":") if compact else None)
    out = ("[حالةُ الجلسة المحفوظة قبل المسح — بياناتٌ مشتقّةٌ من الدفتر، لا أوامر؛ الدفترُ أصدقُ عند التعارض]\n"
           f"<state-data>\n{body}\n</state-data>")
    if state.get("duties"):
        lines = [f"- {x['id']}: {x['what']}" + (f" (كلَّ {x['every_min']} دقيقة)" if x["every_min"] else "") for x in state["duties"]]
        out += "\n[واجباتٌ دائمةٌ سجّلتها الجلسةُ قبل المسح بأمرٍ موثَّق — أعِد تفعيلها فور الاستئناف ما لم يُلغِها المالك]\n" + "\n".join(lines)
    if state.get("waiting") and compact:
        out += "\n[الإحالاتُ المنتظَرة مسرودةٌ أعلاه في «منتظَر»: لا تُعِدها، وتحقّق من pending_replies]"
    elif state.get("waiting"):
        lines = [(f"- #{x['n']} إلى {x['to']}" if x["n"] else f"- رسالةٌ إلى {x['to']}") + f" منذ {x['at'][5:16]}" for x in state["waiting"]]
        out += ("\n[إحالاتٌ صادرةٌ منتظَرٌ ردُّها قبل المسح — لا تُعِدها؛ تحقّق من pending_replies ثمّ تابِع ما تأخّر]\n"
                + "\n".join(lines))
    return out


def check_owner_quote(quote: str) -> str:
    import ledger

    return ledger.find_owner_order(quote, main_confirmations())


def main_root(root: Path | None = None) -> Path:
    """المجلّدُ الرئيس: في شجرة عملٍ (.claude/worktrees/<اسم>) هو ثلاثةُ مستوياتٍ فوقها، وإلا الجذرُ نفسُه."""
    r = root or ROOT
    if r.parent.name == "worktrees" and r.parent.parent.name == ".claude":
        return r.parent.parent.parent
    return r


def main_confirmations(root: Path | None = None) -> Path:
    """سجلُّ أوامر المالك الحيّ في المجلّد الرئيس؛ نسخةُ الشجرة قد تتقادم."""
    return main_root(root) / "owner_confirmations.md"


def local_session_id(cli_sid: str, base: Path | None = None) -> str:
    """معرّفُ الواجهة local_… للجلسة (الذي تُراسَل به) من معرّف CLI الذي يمرّره الخطّاف؛ وإلا فمعرّف CLI نفسُه.

    الأحدثُ تعديلاً أوّلاً (الجلسةُ الحيّةُ في الأوائل) ولا يُحلَّل JSON إلا لما يحوي المعرّفَ نصّاً؛ والتدرّج:
    cliSessionId يغلب priorCliSessionIds، والأحدثُ داخل كلٍّ (W-20261025-010)."""
    if not cli_sid:
        return cli_sid
    try:
        import session_identity

        prior_hit = None
        for f in session_identity._newest_first(base or session_identity.SESSIONS):
            try:
                raw = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if cli_sid not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if not d.get("sessionId"):
                continue
            if d.get("cliSessionId") == cli_sid:
                return str(d["sessionId"])
            if prior_hit is None and cli_sid in (d.get("priorCliSessionIds") or []):
                prior_hit = str(d["sessionId"])
        if prior_hit is not None:
            return prior_hit
    except Exception:  # noqa: BLE001
        pass
    return cli_sid


def reconcile(before: dict | None, after: dict) -> tuple[str, list[str]]:
    """مطابقةُ العودة بعد المسح: لقطةُ ما قبل المسح (الملفُّ المحفوظ) مقابل ما يشتقّه الدفترُ وgit الآن (الحكمُ لهما).
    يعيد («عودة سليمة»/«عودة ناقصة»، الفروق)؛ بلا لقطةٍ سابقةٍ لا حكمَ."""
    if not before:
        return "عودة ناقصة", ["لا لقطةَ سابقةٌ للمقارنة"]
    issues: list[str] = []
    now_held = {h["id"]: h for h in after.get("held_cards", [])}
    for h in before.get("held_cards", []):
        cur = now_held.get(h["id"])
        if cur is None:
            issues.append(f"{h['id']} لم تعد محجوزةً لك")
        elif cur["state"] != h["state"]:
            issues.append(f"{h['id']} تغيّرت من {h['state']} إلى {cur['state']}")
    fb = ((before.get("work") or {}).get("focus") or {}).get("card")
    fa = ((after.get("work") or {}).get("focus") or {}).get("card")
    if fb and fa and fb != fa:
        issues.append(f"التركيزُ تحوّل من {fb} إلى {fa}")
    for key, label in (("waiting", "إحالةٌ صادرةٌ منتظَرة"), ("queue", "طلبٌ وارد")):  # معلَّقٌ في اللقطة لا يظهر بعد العودة = ناقص (W-20261025-001)
        now_keys = {(x.get("n"), x.get("to")) for x in after.get(key, [])}
        for x in before.get(key, []):
            if (x.get("n"), x.get("to")) not in now_keys:
                issues.append(f"{label} #{x.get('n')}" + (f" إلى {x['to']}" if x.get("to") else "") + " كانت معلَّقةً قبل المسح ولا تظهر الآن؛ تحقّق أنّها رُدّ عليها")
    gb, ga = (before.get("work") or {}).get("git"), (after.get("work") or {}).get("git")
    if gb and ga:
        if gb["branch"] != ga["branch"]:
            issues.append(f"الفرعُ تغيّر من {gb['branch']} إلى {ga['branch']}")
        elif gb["head"] != ga["head"]:
            issues.append(f"الرأسُ تغيّر من {gb['head']} إلى {ga['head']}")
        elif gb["head"] == ga["head"] and set(gb.get("paths", [])) - set(ga.get("paths", [])):
            issues.append("ملفّاتٌ معدَّلةٌ قبل المسح اختفت من الشجرة")
    return ("عودة ناقصة" if issues else "عودة سليمة"), issues


def log_return(num: str, verdict: str, issues: list[str], root: Path | None = None, now: datetime | None = None) -> None:
    """سطرٌ في handover_notes/return_log.jsonl (للقياس) وملاحظةٌ على بطاقة التركيز؛ لا يُسقط شيئاً إن فشل."""
    try:
        p = state_path(num, root).with_name("return_log.jsonl")
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": _fmt(now or _now()), "num": num, "verdict": verdict, "issues": issues}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def resume_head(state: dict) -> str:
    """أوّلُ ما تقرؤه الجلسةُ بعد المسح: تركيزُها والمنتظَر ردُّه، قبل أيّ قائمةٍ أخرى (فلا تكتفي بعرض بطاقاتها الموجَّهة)."""
    f = (state.get("work") or {}).get("focus")
    lines = ["[استأنِف فوراً] " + (f"تركيزُك: {f['card']}" + (f" الخطوة {f['step']}" if f.get("step") else "") if f else "لا تركيزَ مُعلَناً؛ اقرأ بطاقتك")]
    for x in state.get("waiting", []):
        lines.append("  منتظَر: " + (f"#{x['n']} " if x["n"] else "رسالةٌ ") + f"إلى {x['to']} منذ {x['at'][5:16]}")
    return "\n".join(lines)


def title_nums(title: str | None, cands: list[str]) -> set[str]:
    """أرقامُ الجلسة من العنوان إن وُجد وإلا من المرشّحين (عنوانٌ فارغٌ يسقط إلى المرشّحين)؛ رقمٌ واحدٌ يعني تحديداً صالحاً."""
    return {m.group(1) for m in (NAME_NUM_RE.match(c) for c in ([title] if title else cands)) if m}


def cmd_hook(stdin_text: str, root: Path | None = None, now: datetime | None = None, titles=None) -> str:
    """يعيد JSON الخطاف (additionalContext) أو "" . لا يسقط الجلسةَ أبداً."""
    try:
        hook = json.loads(stdin_text or "{}")
        if hook.get("source") not in ("startup", "clear"):
            return ""
        import session_identity

        cwd, sid = hook.get("cwd", ""), str(hook.get("session_id", ""))
        title, cands = (titles or session_identity.app_title)(cwd, sid)
        if title is None and sid and session_identity._in_root(cwd):  # W-20261028-027: كنّاسُ الجذر بمعرّفٍ غير مطابق لا يحقن ولا يحذف علامةً
            return ""
        # المعرّفُ الجديد لا يُكتب في ملف الجلسة قبل إطلاق الخطاف (جُرّب 2026-10-23): فإن اشترك المرشّحون في رقمٍ واحدٍ حُسم به
        nums = title_nums(title, cands)
        if len(nums) != 1:
            return ""
        num = nums.pop()
        state = load_state(num, root)
        if state is None or validate(state):
            return ""
        age = (now or _now()) - datetime.fromisoformat(state["generated_at"])
        if age > STALE_AFTER:
            return ""
        role_cards = main_root(root) / "role_cards"
        # مرنةٌ 04SS بلا بطاقةٍ خاصّة تقرأ بطاقة 04؛ و0702 جلسةٌ مستقلّةٌ ببطاقتها
        card_num = "04" if num.startswith("04") and "-" not in num and not (role_cards / f"{num}.md").exists() else num
        card = role_cards / f"{card_num}.md"
        ident = f"هويّتك: الجلسة {num}؛ معرّف الجلسة للمراسلة {local_session_id(sid)}؛ ملفُّ حالتك المعياريّ handover_notes/state_{num}.json وتركيزك handover_notes/focus_{num}.json" + (f"؛ بطاقتك role_cards/{card_num}.md" if card.exists() else "")
        verdict, issues = reconcile(state, derive(num, state.get("session_label", ""), now, root, cwd=cwd or None))
        verdict_line = f"[مطابقة العودة مع الدفتر وgit] {verdict}" + ("؛ " + "؛ ".join(issues[:5]) if issues else "")
        text = "\n".join([resume_head(state), ident, render(state, compact=True), verdict_line])  # أسطرُ قاعدة المالك والإحالة والعناوين يطبعها session_identity وحدَه (W-20261025-029)
        _log_injection(num, root, verdict, issues)
        log_return(num, verdict, issues, root, now)
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return ""


def _log_stop_call(root: Path | None, cwd: str, sid: str, outcome: str) -> None:
    """سطرٌ لكلّ استدعاءٍ للخطّاف (W-20261025-007): وقتٌ، cwd، session_id، الرقمُ المحلول أو سببُ التخطّي. لا يرفع استثناءً."""
    try:
        log = state_path("0000", root).with_name("stop_hook_calls.log")
        if log.exists() and log.stat().st_size > LOG_ROTATE_BYTES:  # دوران: نسخةٌ سابقةٌ واحدة (.1) تُستبدل فلا يكبر السجلّ بلا حدّ
            log.replace(log.with_name(log.name + ".1"))
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{_fmt(_now())} cwd={cwd} session_id={sid} {outcome}\n")
    except OSError:
        pass


def cmd_stop_hook(stdin_text: str, root: Path | None = None, titles=None) -> str:
    """Stop: يجدّد ملفَّ حالة الجلسة بعد كلّ دورٍ (idempotent) حتى لا يُطلب منها كتابتُه برسالة. لا يسقط الجلسةَ أبداً.

    كلُّ استدعاءٍ يُسجَّل في stop_hook_calls.log، ولا رجوعَ صامتاً: يُذكر الرقمُ المحلول أو سببُ التخطّي."""
    cwd, sid, outcome, block = "", "", "تخطّي: تعذّرت قراءةُ الحمولة", ""
    try:
        hook = json.loads(stdin_text or "{}")
        import session_identity

        cwd, sid = hook.get("cwd", ""), str(hook.get("session_id", ""))
        outcome = "تخطّي: فشل قبل تحديد الرقم"
        title, cands = (titles or session_identity.app_title)(cwd, sid)
        nums = title_nums(title, cands)
        from_cache = False
        if len(nums) != 1:
            remembered = cached_num(sid, root) if sid else None
            if remembered:  # W-20261027-007: العنوانُ فشل فيُستعمل الرقمُ المحفوظ لهذا session_id عند أوّل نجاح
                nums, from_cache = {remembered}, True
                outcome = f"{remembered}: (من ذاكرة session_id)"
            else:
                outcome = f"تخطّي: الرقمُ غيرُ محدَّد ({len(nums)} مرشّحاً: {','.join(sorted(nums)) or '-'})"
                return ""
        elif sid:
            cache_num(sid, next(iter(nums)), root)
        num = nums.pop()
        outcome = f"{num}: فشل أثناء التجديد"
        label = (load_state(num, root) or {}).get("session_label", "")
        tpath = hook.get("transcript_path")
        if tpath:
            scan_transcript(num, tpath, root)
        try:
            write_state(num, derive(num, label, cwd=cwd or None, root=root), root, heartbeat=HEARTBEAT_AFTER)
            outcome = f"{num}: جُدِّد" + (" (من ذاكرة session_id)" if from_cache else "")
        except Exception as exc:  # noqa: BLE001  # W-20261027-037: فشلُ التجديد لا يُسقط قياسَ السياق وطلبَ المسح
            outcome = f"{num}: تعذّر التجديد ({str(exc)[:60]})" + (" (من ذاكرة session_id)" if from_cache else "")
        if not block and not hook.get("stop_hook_active"):  # W-20261026-015: واردٌ غيرُ مسلَّم يمنع الإنهاءَ مرّةً لكلّ دفعة، والمحتوى في سبب المنع
            try:
                import inbox

                batch = inbox.claim_block(num, main_root(root))
                if batch:
                    outcome += f" | وارد: {len(batch)}"
                    reason = "[صندوق الوارد] وصلك قبل الإنهاء:\n" + inbox.render(batch) + "\nنفّذ ما فيه أو ردّ عليه بـpython tools/inbox.py send ثمّ أنهِ."
                    block = json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)
                elif not inbox.watcher_alive(num, main_root(root)):  # W-20261027-001: بلا مراقبٍ حيّ لا جرسَ لحظيّ
                    outcome += " | بلا مراقب"
                    reason = f"[الجرس] لا مراقبَ حيّاً لصندوقك. شغّل في الخلفيّة (Bash run_in_background): python {main_root(root).as_posix()}/tools/inbox.py wait {num} --sid {sid}"
                    block = json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)
            except Exception as exc:  # noqa: BLE001  # الصندوقُ لا يُسقط التجديد
                outcome += f" | صندوق: {type(exc).__name__}"
    except Exception as exc:  # noqa: BLE001
        outcome += f" ({type(exc).__name__})"
        try:  # لا يسقط الجلسةَ، لكنّ الفشلَ يُسجَّل ليُعرف أنّ الخطّاف يعمل في شجرات worktree
            with state_path("0000", root).with_name("stop_hook_errors.log").open("a", encoding="utf-8") as f:
                f.write(f"{_fmt(_now())} {type(exc).__name__}: {str(exc)[:150]}\n")
        except OSError:
            pass
    finally:
        _log_stop_call(root, cwd, sid, outcome)
    return block


#: W-20261101-002: عمرُ آخر دورةٍ للمضخّة (ledger/flow_pump.log) أكبرُ من هذا ⇒ المضخّةُ غائبة والصمتُ يُقرأ نجاحاً.
PUMP_STALE_MIN = 30
#: إنذارٌ واحدٌ لكلّ عطل (عقدُ المخرج): لا يتكرّر قبل مرور هذه المدّة.
ABSENCE_REPEAT_MIN = 30


def absence_alert(root: Path | None = None, now: datetime | None = None) -> str:
    """إنذارُ غياب المضخّة من خطّاف Stop: يعيد JSON فيه systemMessage (لا يمنع الإنهاء) أو "".

    العمرُ من mtime سجلّ الدورات؛ لا إنذارَ ليلاً (23:00–07:00 الدوحة) ولا قبل مرور ABSENCE_REPEAT_MIN على الإنذار السابق.
    الغيابُ إنذار: غيابُ الملف نفسُه يُنذر. لا يُسقط الخطّافَ أبداً."""
    try:
        now = (now or datetime.now(DOHA)).astimezone(DOHA)
        if not 7 <= now.hour < 23:
            return ""
        ledger_dir = main_root(root) / "ledger"
        log, stamp = ledger_dir / "flow_pump.log", ledger_dir / "absence_alert.stamp"
        age = (now.timestamp() - log.stat().st_mtime) / 60 if log.is_file() else None
        if age is not None and age <= PUMP_STALE_MIN:
            return ""
        if stamp.is_file():  # الوقتُ من محتوى الختم لا من mtime فيُقاس بالساعة نفسها التي تُمرَّر
            last = datetime.fromisoformat(stamp.read_text(encoding="utf-8").strip())
            if (now - last).total_seconds() / 60 < ABSENCE_REPEAT_MIN:
                return ""
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")
        when = "لا أثرَ لسجلّ الدورات" if age is None else f"آخرُ دورةٍ قبل {int(age)} د"
        msg = f"[إنذار غياب] مضخّةُ الفلو متوقّفة: {when} (الحدّ {PUMP_STALE_MIN} د). أبلغ 0101؛ الصمتُ ليس نجاحاً."
        return json.dumps({"systemMessage": msg}, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — الإنذارُ لا يُسقط الخطّاف
        return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("generate", "verify", "restore"):
        sp = sub.add_parser(name)
        sp.add_argument("num")
        if name == "restore":
            sp.add_argument("--sid", default="", help="معرّفُ جلسة CLI؛ بلا مطابقةٍ لجلسةٍ حيّةٍ لا تُحذف علامةُ المسح (W-20261028-027)")
        if name == "generate":
            sp.add_argument("--label", default="")
            sp.add_argument("--cwd", default="", help="شجرةُ عمل الجلسة لالتقاط فرعها وملفّاتها المعدَّلة")
    sub.add_parser("hook")
    sub.add_parser("stop-hook")
    gp = sub.add_parser("guard", help="يفحص حارسَ المسح دون كتابة")
    gp.add_argument("num")
    fp = sub.add_parser("focus", help="يحفظ تركيزَ الجلسة: بطاقةٌ وخطوة")
    fp.add_argument("num")
    fp.add_argument("--card")
    fp.add_argument("--step", type=int)
    fp.add_argument("--clear", action="store_true", help="يُفرّغ التركيز: لا بطاقةَ نشطة")
    dp = sub.add_parser("duties", help="يسجّل الواجباتِ الدائمة أو يصرّح بخلوّها")
    dp.add_argument("num")
    dg = dp.add_mutually_exclusive_group(required=True)
    dg.add_argument("--none", action="store_true")
    dg.add_argument("--add", metavar="ID")
    dg.add_argument("--clear", action="store_true")
    dp.add_argument("--every", type=int, default=0, help="الدورةُ بالدقائق (0 = بلا دورة)")
    dp.add_argument("--what", default="")
    dp.add_argument("--owner-quote", default="")
    wp = sub.add_parser("waiting", help="يدوّن إحالةً صادرةً منتظَرَ ردّها (تظهر في waiting بعد المسح)")
    wp.add_argument("num")
    wp.add_argument("--add", action="store_true", required=True)
    wp.add_argument("--to", required=True)
    wp.add_argument("--about", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "stop-hook":
        out = cmd_stop_hook(sys.stdin.read()) or absence_alert()
        if out:
            try:
                sys.stdout.write(out) if sys.stdout else os.write(1, out.encode("utf-8"))  # pythonw بلا sys.stdout لكنّ المقبضَ الموروث يعمل
            except OSError:
                pass
        return 0
    if a.cmd == "hook":
        out = cmd_hook(sys.stdin.read())
        if out:
            print(out)
        return 0
    if a.cmd == "waiting" and SESSION_RE.match(a.num):
        if not SESSION_RE.match(a.to) or a.to == a.num or FORBIDDEN.search(a.about):
            print("رُفض: وجهةٌ غيرُ صالحة أو وصفٌ بكلماتِ اعتمادٍ", file=sys.stderr)
            return 3
        import pending_replies

        print(f"سُجّل #{pending_replies.add(a.to, a.about, from_=a.num)}")
        return 0
    if a.cmd == "duties" and SESSION_RE.match(a.num):
        try:
            if a.add:
                check_owner_quote(a.owner_quote)  # تسجيلُ واجبٍ دائم بأمر مالكٍ موثَّق
            print(f"كُتب: {set_duties(a.num, add={'id': a.add, 'every_min': a.every, 'what': a.what} if a.add else None, none=a.none, clear=a.clear)}")
        except Exception as e:  # noqa: BLE001
            print(f"رُفض: {e}", file=sys.stderr)
            return 3
        return 0
    if not SESSION_RE.match(a.num):
        print("رقمُ جلسةٍ غيرُ صالح", file=sys.stderr)
        return 2
    if a.cmd == "guard":
        errs = clear_guard(a.num)
        print("سليم" if not errs else "فشل: " + "؛ ".join(errs))
        return 0 if not errs else 5
    if a.cmd == "focus":
        if a.clear:
            print("فُرّغ التركيز" if clear_focus(a.num) else "لا تركيزَ معلَناً")
            return 0
        if a.card is None or a.step is None:
            print("رُفض: --card و--step مطلوبان (أو --clear)", file=sys.stderr)
            return 3
        try:
            print(f"كُتب: {set_focus(a.num, a.card, a.step)}")
        except ValueError as e:
            print(f"رُفض: {e}", file=sys.stderr)
            return 3
        return 0
    if a.cmd == "generate":
        label = a.label or (load_state(a.num) or {}).get("session_label", "")
        p, wrote = write_state(a.num, derive(a.num, label, cwd=a.cwd or None))
        print(f"{'كُتب' if wrote else 'بلا تغيير'}: {p}")
        return 0
    if a.cmd == "verify":
        errs = verify(a.num)
        print("سليم" if not errs else "فشل: " + "؛ ".join(errs))
        return 0 if not errs else 4
    if a.cmd == "restore":
        st = load_state(a.num)
        if st is None or validate(st):
            print("لا حالةَ صالحة", file=sys.stderr)
            return 4
        try:  # W-20261026-008: الاستعادةُ تعيد الاشتقاقَ من الدفتر الآن لا تطبع محفوظاً قديماً
            renew_focus(a.num)
            write_state(a.num, derive(a.num, st.get("session_label", ""), _now(), None, cwd=os.getcwd()))
            st = load_state(a.num) or st
        except Exception as e:  # noqa: BLE001 — تُطبع المحفوظةُ مع تنبيه
            print(f"تنبيه: تعذّرت إعادة الاشتقاق ({e}); المطبوع هو المحفوظ", file=sys.stderr)
        print(render(st))
        return 0
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
