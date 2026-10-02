#!/usr/bin/env python3
"""سجلُّ العمل (ledger) — مصدرُ الحقيقة الآليّ لبطاقات العمل. أحداثٌ تُلحَق فقط (JSONL)، والحالةُ تُشتقّ منها.

اللوحةُ عرضٌ مُولَّد؛ لا يُحرَّر يدويّاً. حمايةُ PDPPL في الكود: لا نصَّ خامّاً طويلاً ولا أرقامَ هويّةٍ ولا بريداً في أيّ حقل.

    python ledger.py add --source owner --type ui --problem "..." --impact "..." --accept "..." --start 2026-09-29T08:00 --priority P1 [--files a b] [--urgent]
    (زمنُ البدء والأولويّة إلزاميّان — قرارُ المالك 2026-09-28)
    python ledger.py move W-20260926-001 in_progress
    python ledger.py list [--state ready_for_review]
    python ledger.py show W-20260926-001
    python ledger.py tag W-20260926-001 --branch claude/<فرع> [--raise-to high --reason "..."] [--apply]   # وسمُ الخطورة والمجال؛ عرضٌ فقط بلا --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOHA = timezone(timedelta(hours=3))
FIELD_MAX = 240
STATES = [
    "captured", "verified", "routed", "in_progress", "ready_for_review", "notes",
    "approved", "pushed", "merged", "published", "closed", "deferred",
]
SOURCES = ("owner", "intake", "roadmap", "kpi_guard", "alert", "advisor", "repo_keeper", "discovery")
TEXT_FIELDS = ("problem", "impact", "accept", "note")
PRIORITIES = ("P0", "P1", "P2", "P3")  # P0 استعجال · P1 هذا الأسبوع · P2 هذا الشهر · P3 لاحقاً مؤرَّخ
_PII = re.compile(r"\b\d{9,}\b|[\w.+-]+@[\w-]+\.[\w.]+")


class LedgerError(ValueError):
    pass


def ledger_path(path: str | os.PathLike | None = None) -> Path:
    return Path(path or os.environ.get("LEDGER_PATH") or ROOT / "ledger" / "events.jsonl")


def now_doha() -> str:
    return datetime.now(DOHA).isoformat(timespec="seconds")


def check_text(name: str, value: str) -> str:
    if len(value) > FIELD_MAX:
        raise LedgerError(f"الحقل {name} أطول من {FIELD_MAX} حرفاً — لخّص ولا تلصق نصَّ رسالةٍ خامّاً")
    if _PII.search(value):
        raise LedgerError(f"الحقل {name} يبدو فيه رقمُ هويّةٍ أو بريد — تُمنع البياناتُ الشخصيّة في السجلّ")
    return value.strip()


def parse_start(value: str) -> str:
    """زمنُ البدء الفعليّ إلزاميّ (قرارُ المالك 2026-09-28: «لا شيءَ بدون زمن»). يُقبل ISO بتوقيت الدوحة أو بمنطقةٍ صريحة."""
    if not value:
        raise LedgerError("زمنُ البدء إلزاميّ — لا مهمّةَ بلا زمن (مثال: 2026-09-29T08:00)")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"زمنُ بدءٍ غيرُ صالح: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DOHA)
    return dt.astimezone(DOHA).isoformat(timespec="minutes")


def load_events(path=None) -> list[dict]:
    p = ledger_path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_event(kind: str, item_id: str, data: dict | None = None, path=None) -> dict:
    p = ledger_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": now_doha(), "id": item_id, "kind": kind, "data": data or {}}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def reduce_state(events: list[dict]) -> dict[str, dict]:
    items: dict[str, dict] = {}
    for ev in events:
        data, item_id = ev["data"], ev["id"]
        if ev["kind"] == "created":
            items[item_id] = {"id": item_id, "created": ev["ts"], "state": "captured", "approvals": [], "notes": [], **data}
            continue
        item = items.get(item_id)
        if item is None:
            continue
        if ev["kind"] == "state":
            if data.get("head"):
                item["approved_head"] = data["head"]  # رأسُ الإيداع الذي رآه المالكُ وقتَ الاعتماد (v2.23)
            item["state"] = data["state"]
            item["state_ts"] = ev["ts"]
            item["state_by"] = data.get("by", "—")
        elif ev["kind"] == "update":
            item.update(data)
        elif ev["kind"] == "approval":
            item["approvals"].append({"ts": ev["ts"], **data})
        elif ev["kind"] == "note":
            item["notes"].append({"ts": ev["ts"], **data})
    return items


def new_id(events: list[dict], today: str | None = None) -> str:
    day = today or datetime.now(DOHA).strftime("%Y%m%d")
    n = sum(1 for e in events if e["kind"] == "created" and e["id"].startswith(f"W-{day}-")) + 1
    return f"W-{day}-{n:03d}"


def add_item(source: str, problem_type: str, problem: str, impact: str, accept: str,
             files: list[str] | None = None, urgent: bool = False, path=None, scores: dict | None = None,
             start: str = "", priority: str = "") -> str:
    if source not in SOURCES:
        raise LedgerError(f"مصدرٌ غيرُ معروف: {source} (المسموح: {', '.join(SOURCES)})")
    if priority not in PRIORITIES:
        raise LedgerError(f"الأولويّة إلزاميّة، واحدةٌ من {', '.join(PRIORITIES)}")
    if urgent and priority != "P0":
        raise LedgerError("الاستعجالُ أولويّتُه P0")
    data = {
        "source": source, "type": problem_type, "priority": priority, "start": parse_start(start),
        "problem": check_text("problem", problem), "impact": check_text("impact", impact),
        "accept": check_text("accept", accept), "files": [f[:200] for f in (files or [])][:20],
        "urgent": bool(urgent), "scores": scores or {},
    }
    events = load_events(path)
    item_id = new_id(events)
    append_event("created", item_id, data, path)
    return item_id


# مراحلُ حياة البطاقة: الحالةُ الهدف ← الحالاتُ السابقةُ المقبولة (بوّاباتٌ لا يُقفز فوقها)
GATES = {
    "pushed": {"approved"},
    "merged": {"pushed"},
    "published": {"merged"},
}


# من يحقّ له تسجيل الحالة (أمر المالك 2026-10-02: تداخلاتُ الأدوار بين الجلسات في الدفتر): `approved` لـ0501 (بعد المعاينة) أو 0101 (اعتمادٌ مباشرٌ
# في محادثتها)؛ و`merged` و`published` لـ0601. بلا --by تُسجَّل «غيرُ مُعلَن» وتمرّ (انتقالٌ لطيف) ويحصيها `approval_check`؛ و--by غيرُ المأذون يُرفض.
RECORDERS = {"approved": {"0501", "0101"}, "merged": {"0601", "0101"}, "published": {"0601", "0101"}}
ALREADY_APPROVED = {"approved", "pushed", "merged", "published"}


def check_recorder(state: str, by: str | None) -> None:
    allowed = RECORDERS.get(state)
    if allowed and by and by not in allowed:
        raise LedgerError(f"«{by}» لا يسجّل الحالة «{state}»: المأذونُ لهم {sorted(allowed)} (تداخلُ أدوار — سجّل الطلبَ عند صاحب الدور)")


def check_transition(current: str, state: str, note: str | None) -> None:
    """يرفض القفزَ فوق بوّابات الفلو: لا دفعَ بلا اعتماد، ولا دمجَ بلا دفع، ولا نشرَ بلا دمج، ولا اعتمادَ بلا ملاحظةٍ تسمّي من اعتمد وأين."""
    allowed = GATES.get(state)
    if allowed and current not in allowed:
        raise LedgerError(f"لا قفزَ فوق مراحل البطاقة: «{current}» ← «{state}» ممنوع؛ الحالةُ السابقةُ المطلوبة: {'، '.join(sorted(allowed))}")
    if state == "approved" and current in ALREADY_APPROVED:
        raise LedgerError(f"اعتمادٌ مكرَّر: البطاقةُ في «{current}» أصلاً — لا يُعاد تسجيلُ الاعتماد (أعد القراءةَ بـshow)")
    if state == "approved" and not note:
        raise LedgerError("الاعتمادُ يلزمه --note يسمّي من اعتمد وأين ومتى (سطرُ الاعتماد الرسميّ v2.12)")


HEAD_RE = re.compile(r"^[0-9a-f]{7,40}$")


def check_head(state: str, head: str | None) -> str | None:
    """الاعتمادُ يُربَط برأس الإيداع الذي عاينه المالكُ؛ فإيداعٌ لاحقٌ لا يرث اعتماداً لم يره (v2.23، D-139م)."""
    if state != "approved":
        return None
    if not head or not HEAD_RE.match(head):
        raise LedgerError("الاعتمادُ يلزمه --head <sha8> رأسُ الإيداع الذي عاينه المالكُ (git rev-parse --short=8 <الفرع>)")
    return head[:8]


def move(item_id: str, state: str, path=None, note: str | None = None, by: str | None = None, head: str | None = None) -> None:
    if state not in STATES:
        raise LedgerError(f"حالةٌ غيرُ معروفة: {state}")
    head = check_head(state, head)
    items = reduce_state(load_events(path))
    if item_id not in items:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    check_transition(items[item_id]["state"], state, note)
    check_recorder(state, by)
    append_event("state", item_id, {"state": state, "by": by or "غير مُعلَن", **({"head": head} if head else {})}, path)
    if note:
        append_event("note", item_id, {"text": check_text("note", note)}, path)


FALSE_ALARM_NOTE = "إنذارٌ كاذب"  # النصُّ الثابتُ عند إغلاق إنذارٍ كاذب (D-150م) — يقيسه intake_kpis


def park(item_id: str, decision: str, reason: str, path=None) -> None:
    """وسمُ «مركونٌ بقرار»: بطاقةٌ captured مؤجَّلةٌ بقرارٍ مسجَّل (لا خمولاً) — فلا تُحسب «راكدةً» في مؤشّرات 0204."""
    items = reduce_state(load_events(path))
    if item_id not in items:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if not re.fullmatch(r"D-\d+م", decision):
        raise LedgerError("--decision رقمُ قرارٍ من decisions.md مثل D-120م")
    append_event("update", item_id, {"parked": {"decision": decision, "reason": check_text("reason", reason)}}, path)


def raise_priority(item_id: str, priority: str, reason: str, by: str, path=None) -> None:
    """رفعُ الأولويّة فقط (P3→P2…) بحدثِ update وملاحظةٍ تسمّي السبب والقرار؛ لا خفضَ بهذا الأمر (الخفضُ قرارُ المايسترو بتسجيلٍ آخر)."""
    if priority not in PRIORITIES:
        raise LedgerError(f"الأولويّةُ واحدةٌ من {', '.join(PRIORITIES)}")
    item = reduce_state(load_events(path)).get(item_id)
    if not item:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if PRIORITIES.index(priority) >= PRIORITIES.index(item.get("priority", "P3")):
        raise LedgerError(f"ليس رفعاً: {item.get('priority')} ← {priority} (هذا الأمرُ للرفع فقط)")
    append_event("update", item_id, {"priority": priority}, path)
    append_event("note", item_id, {"text": check_text("note", f"رفعُ الأولويّة {item.get('priority')}→{priority} بتسجيل {by}: {reason}")}, path)


def _git(args: list[str], repo: str | None = None) -> str:
    repo = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    p = subprocess.run(["git", *args], capture_output=True, encoding="utf-8", errors="replace", check=False, cwd=repo)
    if p.returncode != 0:
        raise LedgerError(f"فشل git {' '.join(args[:3])}: {p.stderr.strip()[:160]}")
    return p.stdout.strip()


# اختباراتُ الحراسة الأمنيّة: لا يُعفى إقرارُ تعديلها (D-155م) — قائمةٌ ثابتةٌ تُراجَع مع 0105؛ محافظةٌ عمداً: أيُّ مطابقةٍ تُعرض على المالك
GUARD_TEST_FILES = {
    "test_every_route_is_guarded.py", "test_security_gate.py", "test_deploy_safety_guards.py", "test_uploads_are_photo_cleaned.py",
}
GUARD_TEST_RE = re.compile(
    r"(guard|security|permission|rbac|rls|erasure|audit|consent|encrypt|csp|auth|redirect|pdppl|personal_data|purge|health_record|"
    r"export|immutab|deploy_safety|route|photo_cleaned|gate|conftest|"
    # توسيعُ 0105 (10-02): حراسةٌ أمنيّةٌ لا يطابقها الاسمُ الأوّل — الأمنُ يصعّد ولا يخفّف
    r"scope|tenant|jwt|csrf|cookie|password|lockout|mfa|secret|pii|privacy|sentry|ratelimit|runtime|settings|capabilit|"
    r"developer|unrestricted|breach|injection|middleware|ci_|migration_linter)", re.I)

ASSERT_LINE = re.compile(r"^\s*(assert\b|self\.assert\w*\(|with pytest\.raises|pytest\.raises\()")
WEAKEN_LINE = re.compile(r"(pytest\.mark\.(skip|skipif|xfail)|\bskip\(|importorskip|@unittest\.skip|\bxfail\b)")


def weakened_assertions(diff_text: str) -> list[str]:
    """تعديلٌ داخل اختبارٍ عاديٍّ يُضعف تأكيداً: حذفُ assert أكثرَ مما أُضيف، أو إضافةُ skip/xfail (ملاحظةُ حدٍّ من 0105)."""
    removed = added = 0
    weak = []
    for ln in diff_text.splitlines():
        if ln.startswith("---") or ln.startswith("+++"):
            continue
        if ln.startswith("-") and ASSERT_LINE.match(ln[1:]):
            removed += 1
        elif ln.startswith("+"):
            if ASSERT_LINE.match(ln[1:]):
                added += 1
            if WEAKEN_LINE.search(ln[1:]):
                weak.append(ln[1:].strip()[:80])
    if removed > added:
        weak.append(f"حُذف {removed - added} تأكيدٌ بلا بديل")
    return weak


def is_guard_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in GUARD_TEST_FILES or bool(GUARD_TEST_RE.search(path))


def check_tests_only(approved: str, new: str, repo: str | None = None) -> list[str]:
    """«إصلاحُ اختبارٍ لفشل CI» (D-155م): الفرقُ عن المعتمَد في tests/ وحدَها وليس فيه اختبارُ حراسةٍ أمنيّة؛ والإيداعُ يتلو المعتمَد."""
    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, new], cwd=cwd, capture_output=True).returncode != 0:
        raise LedgerError("الإيداعُ الجديد لا يتلو الرأسَ المعتمَد — لا يُعفى")
    changed = [f for f in _git(["diff", "--name-only", approved, new], repo).split("\n") if f]
    if not changed:
        raise LedgerError("لا فرقَ عن الرأس المعتمَد — لا حاجةَ لاستثناء")
    outside = [f for f in changed if not f.startswith("tests/")]
    if outside:
        raise LedgerError(f"ملفّاتٌ خارج tests/: {outside[:5]}")
    guards = [f for f in changed if is_guard_test(f)]
    if guards:
        raise LedgerError(f"اختباراتُ حراسةٍ أمنيّةٍ تُعرض على المالك: {guards[:5]}")
    weak = weakened_assertions(_git(["diff", "-U0", approved, new, "--", "tests/"], repo))
    if weak:
        raise LedgerError(f"تعديلٌ يُضعف تأكيداً (يُراجَع مع 0105): {weak[:3]}")
    return changed


def check_main_merge(approved: str, new: str, repo: str | None = None) -> list[str]:
    """يتحقّق آلياً أنّ الإيداعَ الجديد «دمجُ main فقط» (D-154م): لا كودَ من الجلسة بعد الرأس المعتمَد.

    الشروط: (١) الإيداعُ دمجٌ بأبوين، أوّلُهما الرأسُ المعتمَد أو تالٍ له؛ (٢) كلُّ ملفٍّ تغيّر بين المعتمَد والجديد
    **مطابقٌ بمحتواه** لما في أبيه الثاني (جهةِ main) — فلا شيءَ من عمل الجلسة اختلط؛ ويرفض غيرَ ذلك. يعيد قائمةَ الملفّات المغيَّرة."""
    parents = _git(["rev-list", "--parents", "-n", "1", new], repo).split()[1:]
    if len(parents) != 2:
        raise LedgerError(f"ليس دمجاً بأبوين ({len(parents)}): لا يُعفى إلا «دمجُ main فقط»")
    first, second = parents
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, first], cwd=repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp"),
                      capture_output=True).returncode != 0:
        raise LedgerError("الأبُ الأوّل ليس الرأسَ المعتمَد أو تالياً له — فيه إيداعاتٌ لا نعرفها")
    changed = _git(["diff", "--name-only", approved, new], repo).split("\n")
    changed = [f for f in changed if f]
    bad = []
    for f in changed:
        ours = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{new}:{f}"], capture_output=True, encoding="utf-8",
                              cwd=repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")).stdout.strip()
        theirs = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{second}:{f}"], capture_output=True, encoding="utf-8",
                                cwd=repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")).stdout.strip()
        if ours != theirs:
            bad.append(f)
    if bad:
        raise LedgerError(f"ملفّاتٌ تختلف عن جهة main (عملُ جلسةٍ مختلط): {bad[:5]}")
    if not changed:
        raise LedgerError("لا فرقَ عن الرأس المعتمَد — لا حاجةَ لاستثناء")
    return changed


WAIVER_BY = {"0501"}


def waive_head(item_id: str, new_head: str, by: str, reason: str, path=None, changed=None, kind: str = "docs", repo: str | None = None) -> None:
    """استثناءٌ صريحٌ مسجَّلٌ لا ضمنيّ: تعديلٌ تافهٌ (وثائق أو .md) بعد الاعتماد بتوقيع 0501؛ لا كودَ ولا صلاحيّاتٍ ولا هجرات."""
    if by not in WAIVER_BY:
        raise LedgerError(f"الاستثناءُ لـ{sorted(WAIVER_BY)} وحدَها")
    if not HEAD_RE.match(new_head):
        raise LedgerError("--head غيرُ صالح")
    item = reduce_state(load_events(path)).get(item_id)
    if not item or not item.get("approved_head"):
        raise LedgerError("لا اعتمادَ مربوطاً برأسٍ لهذه البطاقة")
    if kind == "main-merge":
        check_main_merge(item["approved_head"], new_head, repo)
        reason = f"دمجُ main فقط (تحقّق آليّ) — {reason}"
    elif kind == "tests-only":
        check_tests_only(item["approved_head"], new_head, repo)
        reason = f"إصلاحُ اختباراتٍ فقط بلا حراسةٍ أمنيّة (تحقّق آليّ) — {reason}"
    elif kind == "docs":
        if changed is None:
            changed = _git_read(["git", "diff", "--name-only", item["approved_head"], new_head]).split()
        bad = [f for f in changed if not (f.startswith("docs/") or f.endswith(".md"))]
        if not changed or bad:
            raise LedgerError(f"الاستثناءُ للوثائق وحدَها؛ ملفّاتٌ غيرُ وثائقيّة أو فرقٌ فارغ: {bad[:5]}")
    else:
        raise LedgerError("--kind: docs أو main-merge أو tests-only")
    append_event("state", item_id, {"state": item["state"], "by": by, "head": new_head[:8]}, path)
    append_event("note", item_id, {"text": check_text("note", f"استثناءُ رأسٍ تافه بتوقيع {by}: {item['approved_head']}→{new_head[:8]} — {reason}")}, path)


def wsjf(item: dict) -> float:
    """(قيمة + إلحاحُ وقت + خفضُ مخاطرة) ÷ الحجم؛ كلٌّ من 1 إلى 5؛ الاستعجالُ يرفع الإلحاح إلى 5."""
    s = item.get("scores") or {}
    value, urgency, risk, size = (max(1, min(5, int(s.get(k, 3)))) for k in ("value", "urgency", "risk", "size"))
    if item.get("urgent"):
        urgency = 5
    return round((value + urgency + risk) / size, 2)


def order_key(item: dict) -> tuple:
    """الأولويّةُ أوّلاً، ثمّ زمنُ البدء الأقرب، ثمّ WSJF الأعلى."""
    pr = item.get("priority", "P3")
    return (PRIORITIES.index(pr) if pr in PRIORITIES else len(PRIORITIES), item.get("start", "9999"), -wsjf(item))


def late_items(items: dict, now: datetime | None = None) -> list[dict]:
    """مهامُّ حان زمنُ بدئها ولم تبدأ (ما زالت captured/verified/routed)."""
    now = now or datetime.now(DOHA)
    waiting = ("captured", "verified", "routed")
    return [i for i in items.values() if i.get("state") in waiting and i.get("start") and datetime.fromisoformat(i["start"]) <= now]


def _git_read(cmd: list[str]) -> str:
    """أمرٌ قرائيٌّ على غيت أو gh؛ يفشل بصوتٍ عالٍ لا صامتاً."""
    repo = os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", check=False, cwd=repo)
    if proc.returncode != 0:
        raise LedgerError(f"فشل: {' '.join(cmd[:4])} — {proc.stderr.strip()[:200]}")
    return proc.stdout


def tag_item(card: str, paths: list[str], head: str = "", pr: int | None = None, raise_to: str = "",
             reason: str = "", apply: bool = False, path=None) -> dict:
    """يصنّف مساراتِ العمل ويكتب خطورةَ البطاقة ومجالَها حدثَ update (يُلحَق فقط). بلا apply عرضٌ فقط. لا خفضَ للخطورة أبداً."""
    from risk_tier import TIER_ORDER, classify_paths

    if card not in reduce_state(load_events(path)):
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {card}")
    if not paths:
        raise LedgerError("لا مساراتٍ متغيّرة — تحقّق من اسم الفرع أو أنّ العملَ أُودِع")
    info = classify_paths(paths)
    tier = info["tier"]
    if raise_to:
        if not reason:
            raise LedgerError("--raise-to يلزمه --reason")
        if TIER_ORDER.index(raise_to) < TIER_ORDER.index(tier):
            raise LedgerError(f"لا خفضَ للخطورة ({tier} ← {raise_to}): الأداةُ حدٌّ أدنى لا أعلى")
        tier = raise_to
    data = {"tier": tier, "category": info["category"], "area": info["area"], "flags": info["flags"], "files_changed": len(paths)}
    if head:
        data["head"] = head  # الإيداعُ المصنَّف: يُقارَن لاحقاً برأس الطلب قبل الدمج
    if pr:
        data["pr"] = pr
    if raise_to:
        data["tier_reason"] = check_text("note", reason)
    if apply:
        append_event("update", card, data, path)
    return {"card": card, "update": data, "categories": info["categories"], "applied": apply}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--source", required=True); a.add_argument("--type", required=True)
    a.add_argument("--problem", required=True); a.add_argument("--impact", required=True); a.add_argument("--accept", required=True)
    a.add_argument("--files", nargs="*", default=[]); a.add_argument("--urgent", action="store_true")
    a.add_argument("--start", required=True, help="زمنُ البدء الفعليّ ISO بتوقيت الدوحة"); a.add_argument("--priority", required=True, choices=PRIORITIES)
    m = sub.add_parser("move"); m.add_argument("id"); m.add_argument("state"); m.add_argument("--note"); m.add_argument("--by", help="رقمُ جلستك (0501/0101/0601…)؛ يُسجَّل مع الحالة"); m.add_argument("--head", help="للاعتماد: رأسُ الإيداع المعاين (sha8)")
    pk = sub.add_parser("park", help="وسمُ بطاقةٍ مركونةٍ بقرارٍ مسجَّل")
    pk.add_argument("id"); pk.add_argument("--decision", required=True); pk.add_argument("--reason", required=True)
    rp = sub.add_parser("raise-priority", help="رفعُ أولويّةِ بطاقةٍ (رفعٌ فقط)")
    rp.add_argument("id"); rp.add_argument("priority", choices=PRIORITIES); rp.add_argument("--by", required=True); rp.add_argument("--reason", required=True)
    wv = sub.add_parser("waive-head", help="استثناءُ تافهٍ (وثائق فقط) بتوقيع 0501: يُنقل الاعتمادُ إلى رأسٍ جديد")
    wv.add_argument("id"); wv.add_argument("--head", required=True); wv.add_argument("--by", required=True); wv.add_argument("--reason", required=True); wv.add_argument("--kind", default="docs", choices=["docs", "main-merge", "tests-only"])
    ls = sub.add_parser("list"); ls.add_argument("--state")
    sh = sub.add_parser("show"); sh.add_argument("id")
    tg = sub.add_parser("tag", help="يكتب خطورةَ البطاقة ومجالها من مسارات عملها")
    tg.add_argument("id")
    src = tg.add_mutually_exclusive_group(required=True)
    src.add_argument("--branch"); src.add_argument("--pr", type=int); src.add_argument("--paths", nargs="+")
    tg.add_argument("--raise-to", default=""); tg.add_argument("--reason", default=""); tg.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        if args.cmd == "add":
            print(add_item(args.source, args.type, args.problem, args.impact, args.accept, args.files, args.urgent,
                           start=args.start, priority=args.priority))
        elif args.cmd == "move":
            move(args.id, args.state, note=args.note, by=args.by, head=args.head); print("ok")
        elif args.cmd == "raise-priority":
            raise_priority(args.id, args.priority, args.reason, args.by); print("ok")
        elif args.cmd == "park":
            park(args.id, args.decision, args.reason); print("ok")
        elif args.cmd == "waive-head":
            waive_head(args.id, args.head, args.by, args.reason, kind=args.kind); print("ok")
        elif args.cmd == "tag":
            head, pr = "", None
            if args.branch:
                paths = _git_read(["git", "diff", "--name-only", f"origin/main...{args.branch}"]).split()
                head = _git_read(["git", "rev-parse", "--short=8", args.branch]).strip()
            elif args.pr:
                data = json.loads(_git_read(["gh", "pr", "view", str(args.pr), "--json", "files,headRefOid"]))
                paths, head, pr = [f["path"] for f in data.get("files", [])], data.get("headRefOid", "")[:8], args.pr
            else:
                paths = args.paths
            out = tag_item(args.id, paths, head, pr, args.raise_to, args.reason, args.apply)
            print(json.dumps(out, ensure_ascii=False, indent=2))
            print("أُلحق حدثُ update" if args.apply else "عرضٌ فقط — أضِف --apply للكتابة")
        else:
            items = reduce_state(load_events())
            if args.cmd == "show":
                print(json.dumps(items.get(args.id), ensure_ascii=False, indent=2))
            else:
                for it in sorted(items.values(), key=order_key):
                    if not args.state or it["state"] == args.state:
                        print(f"{it['id']}  {it.get('priority','—')}  بدء={it.get('start','—')[:16]}  {it['state']:16} {it['type']:16} {it['problem'][:50]}")
    except LedgerError as exc:
        sys.exit(f"رُفض: {exc}")


if __name__ == "__main__":
    main()
