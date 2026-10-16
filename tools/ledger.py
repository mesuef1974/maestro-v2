#!/usr/bin/env python3
"""سجلُّ العمل (ledger) — مصدرُ الحقيقة الآليّ لبطاقات العمل. أحداثٌ تُلحَق فقط (JSONL)، والحالةُ تُشتقّ منها.

اللوحةُ عرضٌ مُولَّد؛ لا يُحرَّر يدويّاً. حمايةُ PDPPL في الكود: لا نصَّ خامّاً طويلاً ولا أرقامَ هويّةٍ ولا بريداً في أيّ حقل.

    python ledger.py add --source owner --type ui --problem "..." --impact "..." --accept "..." --start 2026-09-29T08:00 --priority P1 [--files a b] [--urgent]
    (زمنُ البدء والأولويّة إلزاميّان — قرارُ المالك 2026-09-28)
    python ledger.py move W-20260926-001 in_progress
    python ledger.py list [--state ready_for_review]
    python ledger.py show W-20260926-001
    python ledger.py spec W-... --tier full --ref "طبق الأصل|مسار|http://localhost:8500/..|الدور|لقطة" --assumption "محسوم: ..." --source-of-truth "..." --files-allowed a --files-forbidden b --accept "..." --step "..." --by 0301
    python ledger.py return W-... --reason "..." --by 0501   # تُعاد لنقص المواصفة إلى captured
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
            if data.get("branch"):
                item["branch"] = data["branch"]  # الفرعُ الذي تحقّق منه الدفع على البعيد
            if "held_by" in data:
                item["held_by"] = data["held_by"]
            if data["state"] in RELEASING_STATES:
                item["held_by"] = ""  # إنهاءُ البطاقة يفكّ حجزَها (متوافقٌ مع الأحداث القديمة)
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
             start: str = "", priority: str = "", held_by: str = "") -> str:
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
    if held_by and held_by != "-":
        data["held_by"] = check_session(held_by)
    events = load_events(path)
    item_id = new_id(events)
    append_event("created", item_id, data, path)
    return item_id


#: حالاتٌ تفكّ حجزَ الجلسة للبطاقة تلقائياً
RELEASING_STATES = {"closed", "published", "deferred"}
SESSION_RE = re.compile(r"^\d{4}$")


def check_session(value: str) -> str:
    if not SESSION_RE.match(value):
        raise LedgerError("--held-by رقمُ جلسةٍ من أربع خانات (مثل 0402) أو «-» للتصفير")
    return value


def remote_branch_head(branch: str, repo: str | None = None) -> str | None:
    """رأسُ الفرع على البعيد بـ`git ls-remote origin`؛ None إن لم يوجد. تُحقن بديلاً عنها في الاختبارات (لا شبكة)."""
    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    p = subprocess.run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], capture_output=True, encoding="utf-8",
                       errors="replace", check=False, cwd=cwd)
    if p.returncode != 0:
        raise LedgerError(f"تعذّر الاتصال بالبعيد للتحقّق من الفرع: {p.stderr.strip()[:160]}")
    line = p.stdout.strip().splitlines()
    return line[0].split()[0] if line else None


def check_remote_push(branch: str | None, head: str | None, lookup=None) -> str:
    """لا `pushed` إلا بعد أن يثبت وجودُ الفرع (والرأس إن ذُكر) على البعيد. يعيد الفرعَ المتحقَّق منه."""
    if not branch:
        raise LedgerError('pushed يلزمه --branch <الفرع> (أو فرعٌ مسجَّلٌ في البطاقة) للتحقّق منه على البعيد، أو --waive-remote-check "<سبب>"')
    remote = (lookup or remote_branch_head)(branch)
    if not remote:
        raise LedgerError(f"الفرع «{branch}» غيرُ موجودٍ على البعيد (git ls-remote origin) — لم يُدفع فعلاً؛ لا يُسجَّل pushed")
    if head and not remote.startswith(head) and not head.startswith(remote[: len(head)]):
        raise LedgerError(f"رأسُ الفرع على البعيد {remote[:8]} لا يطابق --head {head[:8]} — الدفعُ لم يشمل الإيداع المذكور")
    return branch


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


# ───────── بوّابة «المواصفة الكاملة» (قرارُ المالك 2026-10-04) ─────────
SPEC_TIERS = ("basic", "full")
SPEC_STEPS_MAX = 7
SPEC_CUTOFF = "2026-10-04"  # بطاقاتٌ أُنشئت قبل هذا اليوم تبقى basic (لا يُعاد عليها بابٌ أُغلق)
ASSUMPTION_STATUSES = ("محسوم", "افتراض")  # «افتراض» = افتراضٌ معلَن يراجعه المالكُ في المعاينة لا قبل البناء
REF_KINDS = ("طبق الأصل", "مشابه")
RETURNED_MARK = "أُعيدت لنقص المواصفة"  # يقيسه intake_kpis
#: قواعدُ الاستنتاج الصريحة للمستوى full (يكفي واحدٌ منها)؛ تُطبَّق على type + problem + accept + files
FULL_TIER_RULES = {
    "واجهة": re.compile(r"\bui\b|\bux\b|واجه|صفح|شاش|قالب|template|\.html|\.css|css|frontend|layout|تخطيط", re.I),
    "طبق الأصل": re.compile(r"طبق\s*الأصل|pixel|بكسل"),
    "صلاحيات": re.compile(r"permission|rbac|صلاحي|\brole\b|دور\s*جديد", re.I),
    "هجرة": re.compile(r"migrat|هجر", re.I),
}
_TREE_RE = re.compile(r"(worktrees[/\\][^/\\\s]+)", re.I)


def infer_spec_tier(item: dict) -> tuple[str, list[str]]:
    """يستنتج مستوى المواصفة ويعيد (المستوى، أسبابه). full إن طابقت إحدى القواعد أو مسّ العملُ أكثرَ من شجرة."""
    text = " ".join([str(item.get("type", "")), str(item.get("problem", "")), str(item.get("accept", "")), " ".join(item.get("files") or [])])
    reasons = [name for name, rx in FULL_TIER_RULES.items() if rx.search(text)]
    trees = {m.group(1).lower() for f in item.get("files") or [] for m in [_TREE_RE.search(f)] if m}
    if len(trees) > 1 or re.search(r"أكثر\s*من\s*شجر|شجرتين|multi-?tree", text, re.I):
        reasons.append("أكثر من شجرة")
    return ("full" if reasons else "basic"), reasons


def effective_spec_tier(item: dict) -> str:
    """المعلَن بـ spec_tier أوّلاً؛ وإلا الاستنتاج للبطاقات الجديدة فقط (القديمةُ basic توافقاً)."""
    if item.get("spec_tier") in SPEC_TIERS:
        return item["spec_tier"]
    if str(item.get("created", ""))[:10] < SPEC_CUTOFF:
        return "basic"
    return infer_spec_tier(item)[0]


def spec_missing(item: dict) -> list[str]:
    """ما ينقص المواصفةَ الكاملة (أسماءٌ عربيّة)؛ قائمةٌ فارغة = مكتملة."""
    miss = []
    ref = item.get("ref") or {}
    if not (ref.get("kind") in REF_KINDS and ref.get("path")):
        miss.append("ref (المرجع: النوع والمسار)")
    if not item.get("files_allowed"):
        miss.append("files_allowed (الملفّات المسموحة)")
    if not item.get("files_forbidden"):
        miss.append("files_forbidden (ما لا يُلمس)")
    if not item.get("accept_measurable"):
        miss.append("accept_measurable (قبولٌ قابلٌ للقياس ≥1)")
    if not item.get("steps"):
        miss.append("steps (خطواتُ العمل ≥1)")
    if not item.get("source_of_truth"):
        miss.append("source_of_truth (مصدرُ الحقيقة)")
    asm = item.get("assumptions")
    if asm is None or any(a.get("status") not in ASSUMPTION_STATUSES for a in asm):
        miss.append("assumptions (كلُّ تعريفٍ دلاليٍّ محسومٌ أو افتراضٌ معلَن)")
    return miss


def spec_status(item: dict) -> str:
    tier = effective_spec_tier(item)
    miss = spec_missing(item)
    return f"{tier}: " + ("مكتملة" if not miss else "ناقصة — " + "؛ ".join(miss))


def brief_lines(it: dict | None, item_id: str = "") -> list[str]:
    """ملخّصُ بطاقةٍ في ≤12 سطراً (--brief، W-20261013-033): قراءةٌ فقط، لا يمسّ الإخراج الافتراضيّ."""
    if not it:
        return [f"بطاقةٌ غيرُ موجودة: {item_id}"]

    def cut(v, n):
        t = " ".join(str(v or "").split())
        return t if len(t) <= n else t[: n - 1] + "…"

    ref = it.get("ref") or {}
    files = it.get("files_allowed") or it.get("files") or []
    acc = it.get("accept_measurable") or []
    steps = it.get("steps") or []
    notes = it.get("notes") or []
    appr = it.get("approvals") or []
    out = [
        f"{it['id']}  {it.get('priority', '—')}  {it.get('state', '?')}",
        "المشكلة: " + cut(it.get("problem"), 140),
        f"الأصل: {it.get('origin', '—')}" + (f" · أمر المالك {str(it.get('owner_order_at', ''))[:10]}" if it.get("owner_order_at") else ""),
        f"الحاجز: {it.get('held_by') or '—'} · الاعتماد: " + (f"{len(appr)} (الرأس {it.get('approved_head')})" if appr and it.get("approved_head") else (str(len(appr)) if appr else "غائب")),
        "المواصفة: " + cut(spec_status(it), 140),
        "المرجع: " + cut(ref.get("path") or ref.get("kind") or "—", 110),
        f"الملفات ({len(files)}): " + cut("؛ ".join(str(f) for f in files[:3]), 150),
        "أوّل خطوة: " + cut(steps[0] if steps else "—", 140),
        "القبول: " + cut(acc[0] if acc else it.get("accept"), 140),
    ]
    if notes:
        out.append("آخر ملاحظة: " + cut(notes[-1].get("text") if isinstance(notes[-1], dict) else notes[-1], 140))
    return out[:12]


def parse_assumption(text: str) -> dict:
    m = re.match(r"^\s*(محسوم|افتراض)(?:\s*معلن)?\s*[:：]\s*(.+)$", text)
    if not m:
        raise LedgerError("--assumption بصيغة «محسوم: <نصّ المالك وتاريخه>» أو «افتراض: <التعريف المعلن>»")
    return {"status": m.group(1), "text": check_text("assumption", m.group(2))}


def parse_ref(text: str) -> dict:
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 2 or parts[0] not in REF_KINDS or not parts[1]:
        raise LedgerError("--ref بصيغة «النوع|المسار|رابط8500|الدور|مسار اللقطة» والنوع: " + " أو ".join(REF_KINDS))
    keys = ("kind", "path", "url", "role", "snapshot")
    return {k: check_text("ref", v) for k, v in zip(keys, parts) if v}


def set_spec(item_id: str, tier: str | None = None, ref: str | None = None, roles_states: str | None = None,
             allowed_diffs: str | None = None, assumptions: list[str] | None = None, source_of_truth: str | None = None,
             files_allowed: list[str] | None = None, files_forbidden: list[str] | None = None,
             accept: list[str] | None = None, steps: list[str] | None = None, by: str | None = None, path=None) -> dict:
    """يضبط حقولَ المواصفة (ما مُرِّر فقط) حدثَ update؛ ويستنتج المستوى إن لم يُفرَض."""
    item = reduce_state(load_events(path)).get(item_id)
    if not item:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if not by:
        raise LedgerError("--by إلزاميّ: رقمُ جلسةٍ أكملت المواصفة")
    data: dict = {"spec_by": check_session(by)}
    if tier:
        if tier not in SPEC_TIERS:
            raise LedgerError(f"--tier واحدٌ من {', '.join(SPEC_TIERS)}")
        data["spec_tier"] = tier
    if ref:
        data["ref"] = parse_ref(ref)
    if roles_states:
        data["roles_states"] = check_text("roles_states", roles_states)
    if allowed_diffs:
        data["allowed_diffs"] = check_text("allowed_diffs", allowed_diffs)
    if assumptions is not None:
        data["assumptions"] = [parse_assumption(a) for a in assumptions]
    if source_of_truth:
        data["source_of_truth"] = check_text("source_of_truth", source_of_truth)
    if files_allowed:
        data["files_allowed"] = [f[:200] for f in files_allowed][:30]
    if files_forbidden:
        data["files_forbidden"] = [f[:200] for f in files_forbidden][:30]
    if accept:
        data["accept_measurable"] = [check_text("accept", a) for a in accept][:20]
    if steps:
        if len(steps) > SPEC_STEPS_MAX:
            raise LedgerError(f"خطواتُ العمل ≤ {SPEC_STEPS_MAX}")
        data["steps"] = [check_text("step", s) for s in steps]
    if "spec_tier" not in data and not item.get("spec_tier"):
        data["spec_tier"] = infer_spec_tier(item)[0]
    if data.get("spec_tier") == "basic":
        inferred, why = infer_spec_tier(item)
        if inferred == "full":
            raise LedgerError(f"لا خفضَ للمستوى: البطاقةُ تستوجب full ({'، '.join(why)})")
    append_event("update", item_id, data, path)
    return data


def check_spec_gate(item: dict, target: str, history_states: set[str], waive: str | None) -> str | None:
    """بوّابةُ المواصفة عند routed (أو in_progress لم يمرّ بـrouted). full: رفضٌ؛ basic: تحذيرٌ يُعاد نصُّه. يعيد نصَّ التحذير أو None."""
    if target not in ("routed", "in_progress"):
        return None
    if target == "in_progress" and "routed" in history_states:
        return None
    miss = spec_missing(item)
    if not miss:
        return None
    if effective_spec_tier(item) == "full":
        if waive:
            return None
        raise LedgerError("المواصفةُ الكاملة ناقصة — لا توجيه: " + "؛ ".join(miss) + ' (تُكمَل بـspec، أو استثناءٌ مسجَّل --waive-spec "<سبب>")')
    return "تحذير: مواصفةٌ ناقصة (basic): " + "؛ ".join(miss)


RETURNABLE = {"verified", "routed", "in_progress", "ready_for_review", "notes"}


def add_note(item_id: str, text: str, by: str, path=None) -> None:
    """ملاحظةٌ على بطاقةٍ دون نقل حالتها (0103، 2026-10-10: تحتاجها 0502 لتسجيل مسار pack.md). لا تغيّر حالةً ولا حاملاً."""
    item = reduce_state(load_events(path)).get(item_id)
    if not item:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if not text or not text.strip():
        raise LedgerError("--text إلزاميّ: نصُّ الملاحظة")
    check_session(by or "")
    append_event("note", item_id, {"text": check_text("note", f"({by}) {text.strip()}")}, path)


def return_card(item_id: str, reason: str, by: str, path=None) -> None:
    """إعادةُ بطاقةٍ إلى captured لنقص مواصفتها بسببٍ مكتوب؛ يعدّها intake_kpis (RETURNED_MARK)."""
    item = reduce_state(load_events(path)).get(item_id)
    if not item:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if not reason or not reason.strip():
        raise LedgerError("--reason إلزاميّ: سببٌ مكتوب")
    if item["state"] not in RETURNABLE:
        raise LedgerError(f"لا تُعاد بطاقةٌ في الحالة «{item['state']}» — المسموح: {sorted(RETURNABLE)}")
    check_session(by or "")
    append_event("state", item_id, {"state": "captured", "by": by, "held_by": ""}, path)
    append_event("note", item_id, {"text": check_text("note", f"{RETURNED_MARK} ({by}): {reason.strip()}")}, path)
    append_event("update", item_id, {"spec_returns": int(item.get("spec_returns", 0)) + 1}, path)


# بوّابةُ WIP (قرارُ المالك 2026-10-05): خفضُ تشتّت المهامّ — لا بطاقتَين جاريتَين لجلسةٍ واحدة.
# كلُّ البطاقات المنشأة قبل هذا الزمن مستثناةٌ بقرار المالك: يريد إنهاءَ موضوع الحضور والغياب أوّلاً
# فلا تُعطَّل بطاقاتُه الجاريةُ بقاعدةٍ جديدة؛ وتسري القاعدةُ على ما يُنشأ بعده.
WIP_CUTOFF = "2026-10-05T06:00+03:00"


def session_in_progress(items: dict, session: str, exclude: str | None = None) -> list[dict]:
    """بطاقاتُ الجلسة الجاريةُ (in_progress) — بحسب من نقلها أو حجزها — مرتّبةً بالأقدم، دون البطاقة المستثناة."""
    out = [i for i in items.values()
           if i["id"] != exclude and i.get("state") == "in_progress" and session in (i.get("state_by"), i.get("held_by"))]
    return sorted(out, key=lambda i: i.get("state_ts", ""))


def check_wip(items: dict, item_id: str, by: str | None, waive: str | None) -> str | None:
    """يرفض بدءَ بطاقةٍ ثانيةٍ لجلسةٍ لها جاريةٌ؛ ويعيد نصَّ التنازل إن وُجد ليُسجَّل ملاحظةً."""
    item = items[item_id]
    if not by or item.get("priority") == "P0":
        return None
    if datetime.fromisoformat(item.get("created", "9999")) < datetime.fromisoformat(WIP_CUTOFF):
        return None
    others = session_in_progress(items, by, exclude=item_id)
    if not others:
        return None
    if waive:
        return f"استثناءُ حدِّ العمل الجاري: {waive}"
    raise LedgerError(f"للجلسة {by} بطاقةٌ جاريةٌ أخرى: {others[0]['id']} — أنهِها أو انقلها إلى ready_for_review قبل بدء {item_id} (أو --waive-wip \"السبب\"، أو أولويّة P0)")


#: حدُّ العمل غير المنشور لكل دور (W-20261014-011): إنذارٌ فقط؛ يُضبط بـROLE_WIP_LIMIT وقلبُه إلى رفضٍ بـROLE_WIP_ENFORCE=1 بقرارٍ موثَّق.
ROLE_WIP_LIMIT = 3
#: approved يخرج من العدّ: صار عند 0501 للدفع (تسليم، توضيح 0101 في 2026-10-14).
ROLE_WIP_STATES = {"in_progress", "ready_for_review", "pushed", "merged"}
#: الجلسات الشقيقة بادئةً واحدةً (مرنة 04SS)؛ وما عداها دورٌ منفردٌ هو الجلسة نفسها.
ROLE_PREFIXES = ("04",)


def role_of(session: str) -> str:
    return next((p for p in ROLE_PREFIXES if session.startswith(p)), session)


def role_unpublished(items: dict, role: str, exclude: str | None = None) -> list[dict]:
    """بطاقاتُ الدور غيرُ المنشورة بحسب حاجزها (held_by)؛ نقلُ الحجز لجلسةٍ أخرى يُخرجها من العدّ."""
    out = [i for i in items.values()
           if i["id"] != exclude and i.get("state") in ROLE_WIP_STATES and i.get("held_by") and role_of(i["held_by"]) == role]
    return sorted(out, key=lambda i: i.get("state_ts", ""))


def role_wip_limit() -> int:
    try:
        return int(os.environ.get("ROLE_WIP_LIMIT", ROLE_WIP_LIMIT))
    except ValueError:
        return ROLE_WIP_LIMIT


def check_role_wip(items: dict, item_id: str, by: str | None) -> str | None:
    """نصُّ الإنذار إن كان للدور فوق الحدّ بطاقاتٌ غيرُ منشورة؛ P0 معفى؛ لا يرفض إلا بـROLE_WIP_ENFORCE=1."""
    if not by or items[item_id].get("priority") == "P0":
        return None
    others = role_unpublished(items, role_of(by), exclude=item_id)
    if len(others) < role_wip_limit():
        return None
    ids = "، ".join(f"{i['id']} [{i['state']}]" for i in others)
    msg = (f"إنذار العمل الجاري للدور {role_of(by)}: عندكم {len(others)} بطاقاتٍ غيرِ منشورة (الحدّ {role_wip_limit()}) "
           f"قبل بدء {item_id} — {ids}. انشروا أو سلّموا (انقلوا الحجز) قبل التوسّع.")
    if os.environ.get("ROLE_WIP_ENFORCE") == "1":
        raise LedgerError(msg)
    return msg


def check_holder_on_route(item: dict, state: str, held_by: str | None) -> None:
    """D-293م: لا توجيهَ (routed) بلا حامل — معاملٌ صريحٌ أو حاملٌ سابق؛ و«-» عند routed تُرفض لأنها تُصفّر الحامل."""
    if state != "routed":
        return
    if held_by == "-":
        raise LedgerError("routed لا يقبل --held-by - (التصفيرُ يترك البطاقةَ بلا مسؤول): سمِّ الحامل برقم جلسته")
    if held_by or item.get("held_by"):
        return
    raise LedgerError("routed يلزمه --held-by <رقم الجلسة> (لا حاملَ سابقاً للبطاقة): البطاقةُ الموجَّهةُ بلا حامل تبقى بلا مسؤول (D-293م)")


def _run_preflight(card_id: str, repo: str) -> tuple[int, str]:
    import subprocess
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("pr_open_prep.py")), card_id, "--repo", repo, "--preflight"],
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    return r.returncode, (r.stdout + r.stderr).strip()


def check_preflight_ready(item: dict, state: str, repo: str | None, waive: str | None, runner=None) -> str | None:
    """الفحصُ المسبق قبل «جاهزٌ للمعاينة» (W-20261014-022): يمنع إعادة الاعتماد من أساسٍ غير مدفوعٍ أو متأخّر أو mypy مختلف.
    مع --preflight-repo يُشغَّل pr_open_prep --preflight ويُرفض الانتقال عند الفشل؛ بدونه إنذارٌ (PREFLIGHT_ENFORCE=1 يجعله رفضاً).
    P0 معفى؛ والاستثناءُ المسجَّل --waive-preflight "السبب" يُدوَّن في ملاحظة."""
    if state != "ready_for_review" or item.get("priority") == "P0":
        return None
    if waive:
        return f"استثناءُ الفحص المسبق: {waive}"
    if not repo:
        msg = "لم يُشغَّل الفحصُ المسبق قبل «جاهزٌ للمعاينة» — مرِّر --preflight-repo <شجرتك> (أو --waive-preflight \"السبب\")"
        if os.environ.get("PREFLIGHT_ENFORCE") == "1":
            raise LedgerError(msg)
        return msg
    code, out = (runner or _run_preflight)(item["id"], repo)
    if code != 0:
        raise LedgerError(f"فشل الفحصُ المسبق (رمز {code}) — أصلِح ثمّ أعِد:{chr(10)}{out}")
    return None


_FINGERPRINT = re.compile(r"^(?:head=)?([0-9a-f]{8})(?:[: ]\s*(?:sha256=)?)([0-9a-f]{16})$")


def check_premerge_fingerprint(item: dict, state: str, fingerprint: str | None, head_now: str | None = None) -> str | None:
    """بصمةُ `make premerge` قبل «جاهزٌ للمعاينة» (W-20261016-021، المكوّن B): `--premerge-sha <head8>:<sha16>` (أو سطر البصمة كما يطبعه الفحص).
    بلا بصمة أو برأسٍ مخالفٍ لرأس الفرع الحاليّ: إنذارٌ في الظلّ، ورفضٌ مع PREMERGE_GATE_ENFORCE=1. نوع docs مستثنىً بنوعه المعلن.
    البصمة تُدوَّن في ملاحظة الحدث؛ وباقي الانتقالات لا تتأثّر."""
    if state != "ready_for_review" or item.get("type") == "docs":
        return None
    problem = None
    if not fingerprint:
        problem = "لم تُمرَّر بصمةُ make premerge قبل «جاهزٌ للمعاينة» — مرِّر --premerge-sha <head8>:<sha16>"
    else:
        m = _FINGERPRINT.match(fingerprint.strip())
        if not m:
            problem = f"بصمةُ premerge بصيغةٍ غير مفهومة: {fingerprint[:40]}"
        elif head_now and m.group(1) != head_now[:8]:
            problem = f"بصمةُ premerge لرأسٍ مخالف ({m.group(1)}) لرأس الفرع الحاليّ ({head_now[:8]}) — أعِد make premerge"
    if problem is None:
        return f"بصمةُ premerge: {fingerprint.strip()}"
    if os.environ.get("PREMERGE_GATE_ENFORCE") == "1":
        raise LedgerError(problem)
    return f"إنذار (الظلّ): {problem}"


def move(item_id: str, state: str, path=None, note: str | None = None, by: str | None = None, head: str | None = None,
         branch: str | None = None, waive_remote_check: str | None = None, held_by: str | None = None, remote_lookup=None, waive_spec: str | None = None, waive_wip: str | None = None, preflight_repo: str | None = None, waive_preflight: str | None = None, premerge_sha: str | None = None, head_now: str | None = None) -> None:
    if state not in STATES:
        raise LedgerError(f"حالةٌ غيرُ معروفة: {state}")
    if held_by is not None and held_by != "-":
        check_session(held_by)
    push_head = head if state == "pushed" else None
    head = check_head(state, head)
    items = reduce_state(load_events(path))
    if item_id not in items:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    check_transition(items[item_id]["state"], state, note)
    check_holder_on_route(items[item_id], state, held_by)
    check_recorder(state, by)
    history = {e["data"].get("state") for e in load_events(path) if e["id"] == item_id and e["kind"] == "state"}
    spec_warning = check_spec_gate(items[item_id], state, history, waive_spec)
    if waive_spec and state in ("routed", "in_progress") and effective_spec_tier(items[item_id]) == "full" and spec_missing(items[item_id]):
        note = f"{note + ' — ' if note else ''}استثناءُ المواصفة: {waive_spec}"
    if spec_warning:
        print(spec_warning, file=sys.stderr)
    if state == "in_progress":
        wip_note = check_wip(items, item_id, by, waive_wip)
        if wip_note:
            note = f"{note + ' — ' if note else ''}{wip_note}"
        role_note = check_role_wip(items, item_id, by)
        if role_note:
            print(role_note, file=sys.stderr)
            note = f"{note + ' — ' if note else ''}{role_note}"
    pre_note = check_preflight_ready(items[item_id], state, preflight_repo, waive_preflight)
    if pre_note:
        print(pre_note, file=sys.stderr)
        note = f"{note + ' — ' if note else ''}{pre_note}"
    fp_note = check_premerge_fingerprint(items[item_id], state, premerge_sha, head_now)
    if fp_note:
        print(fp_note, file=sys.stderr)
        note = f"{note + ' — ' if note else ''}{fp_note}"
    extra: dict = {}
    if state == "pushed":
        if waive_remote_check:
            note = f"{note + ' — ' if note else ''}استثناءُ فحص البعيد: {waive_remote_check}"
        else:
            extra["branch"] = check_remote_push(branch or items[item_id].get("branch"), push_head, remote_lookup)
    if held_by is not None:
        extra["held_by"] = "" if held_by == "-" else held_by
    append_event("state", item_id, {"state": state, "by": by or "غير مُعلَن", **({"head": head} if head else {}), **extra}, path)
    if note:
        append_event("note", item_id, {"text": check_text("note", note)}, path)


FALSE_ALARM_NOTE = "إنذارٌ كاذب"  # النصُّ الثابتُ عند إغلاق إنذارٍ كاذب (D-150م) — يقيسه intake_kpis


def park(item_id: str, decision: str, reason: str, path=None) -> None:
    """وسمُ «مركونٌ بقرار»: بطاقةٌ captured مؤجَّلةٌ بقرارٍ مسجَّل (لا خمولاً) — فلا تُحسب «راكدةً» في مؤشّرات 0201."""
    items = reduce_state(load_events(path))
    if item_id not in items:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if not re.fullmatch(r"D-\d+م", decision):
        raise LedgerError("--decision رقمُ قرارٍ من decisions.md مثل D-120م")
    append_event("update", item_id, {"parked": {"decision": decision, "reason": check_text("reason", reason)}}, path)


RESCHEDULABLE = {"captured", "routed"}


def reschedule(item_id: str, start: str, decision: str, reason: str, by: str, path=None) -> None:
    """إعادةُ جدولةِ بدءِ بطاقةٍ منتظِرةٍ (captured/routed) بقرارٍ مسجَّل: حدثُ update بـstart الجديد وملاحظةٌ تسمّي القرارَ والسببَ والزمنَ القديم؛ لا تمسّ حالةً ولا اعتماداً ولا أولويّةً."""
    items = reduce_state(load_events(path))
    if item_id not in items:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    item = items[item_id]
    if item.get("state") not in RESCHEDULABLE:
        raise LedgerError(f"لا تُعاد جدولةُ بطاقةٍ في الحالة «{item.get('state')}» — المسموح: {sorted(RESCHEDULABLE)}")
    if not re.fullmatch(r"D-\d+م", decision):
        raise LedgerError("--decision رقمُ قرارٍ من decisions.md مثل D-178م")
    if not by:
        raise LedgerError("--by إلزاميّ: رقمُ جلستك")
    new_start = parse_start(start)
    old = item.get("start", "—")
    note = check_text("note", f"إعادةُ جدولةٍ بـ{decision} ({by}): {old[:16]} ← {new_start[:16]}؛ {reason}")
    append_event("update", item_id, {"start": new_start}, path)
    append_event("note", item_id, {"text": note}, path)


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


# اختباراتُ الحراسة الأمنيّة: لا يُعفى إقرارُ تعديلها (D-155م) — قائمةٌ ثابتةٌ تُراجَع مع 0104؛ محافظةٌ عمداً: أيُّ مطابقةٍ تُعرض على المالك
GUARD_TEST_FILES = {
    "test_every_route_is_guarded.py", "test_security_gate.py", "test_deploy_safety_guards.py", "test_uploads_are_photo_cleaned.py",
}
GUARD_TEST_RE = re.compile(
    r"(guard|security|permission|rbac|rls|erasure|audit|consent|encrypt|csp|auth|redirect|pdppl|personal_data|purge|health_record|"
    r"export|immutab|deploy_safety|route|photo_cleaned|gate|conftest|"
    # توسيعُ 0104 (10-02): حراسةٌ أمنيّةٌ لا يطابقها الاسمُ الأوّل — الأمنُ يصعّد ولا يخفّف
    r"scope|tenant|jwt|csrf|cookie|password|lockout|mfa|secret|pii|privacy|sentry|ratelimit|runtime|settings|capabilit|"
    r"developer|unrestricted|breach|injection|middleware|ci_|migration_linter)", re.I)

ASSERT_LINE = re.compile(r"^\s*(assert\b|self\.assert\w*\(|with pytest\.raises|pytest\.raises\()")
WEAKEN_LINE = re.compile(r"(pytest\.mark\.(skip|skipif|xfail)|\bskip\(|importorskip|@unittest\.skip|\bxfail\b)")


def weakened_assertions(diff_text: str) -> list[str]:
    """تعديلٌ داخل اختبارٍ عاديٍّ يُضعف تأكيداً: حذفُ assert أكثرَ مما أُضيف، أو إضافةُ skip/xfail (ملاحظةُ حدٍّ من 0104)."""
    removed = added = 0
    weak = []
    gone: list[str] = []
    came: set[str] = set()
    for ln in diff_text.splitlines():
        if ln.startswith("---") or ln.startswith("+++"):
            continue
        if ln.startswith("-") and ASSERT_LINE.match(ln[1:]):
            removed += 1
            gone.append(ln[1:].strip())
        elif ln.startswith("+"):
            if ASSERT_LINE.match(ln[1:]):
                added += 1
                came.add(ln[1:].strip())
            if WEAKEN_LINE.search(ln[1:]):
                weak.append(ln[1:].strip()[:80])
    if removed > added:
        weak.append(f"حُذف {removed - added} تأكيدٌ بلا بديل")
    # قرارُ المالك 2026-10-09 (تقييدُ D-155م): تأكيدٌ تغيّر مضمونُه لا يُعفى ولو بقي عددُ التأكيدات؛ يُعرض على المالك.
    # (ثغرةُ ae0a2faa: `assert st in OK` ← `assert st != MODEL_INVALID` مرّ لأنّ العدّ متساوٍ فصار INFEASIBLE مقبولاً.)
    changed = [g for g in gone if g not in came]
    if changed:
        weak.append(f"تأكيدٌ تغيّر مضمونُه ({len(changed)}): {changed[0][:70]}")
    return weak


def is_guard_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in GUARD_TEST_FILES or bool(GUARD_TEST_RE.search(path))


def check_tests_only(approved: str, new: str, repo: str | None = None) -> list[str]:
    """«إصلاحُ اختبارٍ لفشل CI» (D-155م): الفرقُ عن المعتمَد في tests/ وحدَها وليس فيه اختبارُ حراسةٍ أمنيّة؛ والإيداعُ يتلو المعتمَد."""
    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, new], cwd=cwd, capture_output=True).returncode != 0:
        raise LedgerError("الإيداعُ الجديد لا يتلو الرأسَ المعتمَد — لا يُعفى")
    changed = [f for f in _git(["diff", "--no-renames", "--name-only", approved, new], repo).split("\n") if f]
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
        raise LedgerError(f"تعديلٌ يُضعف تأكيداً (يُراجَع مع 0104): {weak[:3]}")
    return changed


_TYPING_MODULES = {"typing", "typing_extensions", "collections.abc", "__future__"}


def _strip_types(source: str) -> str:
    """AST مجرَّدٌ من كلّ ما هو أنواعٌ فقط: التعليقاتُ التوضيحيّة، واستيراداتُ typing، وكتلُ TYPE_CHECKING."""
    import ast

    class Strip(ast.NodeTransformer):
        def visit_arg(self, node):
            node.annotation = None
            return node

        def _fn(self, node):
            node.returns = None
            self.generic_visit(node)
            return node

        visit_FunctionDef = visit_AsyncFunctionDef = _fn

        def visit_AnnAssign(self, node):
            if node.value is None:
                return None
            return ast.copy_location(ast.Assign(targets=[node.target], value=self.visit(node.value), type_comment=None), node)

        def visit_ImportFrom(self, node):
            return None if (node.module or "") in _TYPING_MODULES else node

        def visit_Import(self, node):
            node.names = [a for a in node.names if a.name not in _TYPING_MODULES]
            return node if node.names else None

        def visit_If(self, node):
            t = node.test
            if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"):
                return None
            self.generic_visit(node)
            return node

    tree = Strip().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


def check_types_only(approved: str, new: str, repo: str | None = None) -> list[str]:
    """«إصلاحُ أنواعٍ لفشل mypy» (قرارُ المالك 10-10): الفرقُ عن المعتمَد في ملفّات .py وmypy_ratchet_baseline.json وحدَها؛
    وكلُّ .py مطابقٌ بالـAST بعد تجريد الأنواع (تعليقات توضيحيّة، استيرادات typing، TYPE_CHECKING)؛ والخطُّ الأساس لا يرتفع
    لأيّ ملف؛ ولا هجراتٍ ولا ملفّاتٍ حاكمة. يعيد قائمةَ الملفّات المغيَّرة."""
    import json

    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, new], cwd=cwd, capture_output=True).returncode != 0:
        raise LedgerError("الإيداعُ الجديد لا يتلو الرأسَ المعتمَد — لا يُعفى")
    changed = [f for f in _git(["diff", "--no-renames", "--name-only", approved, new], repo).splitlines() if f]
    if not changed:
        raise LedgerError("لا فرقَ عن الرأس المعتمَد — لا حاجةَ لاستثناء")
    baseline = "mypy_ratchet_baseline.json"
    outside = [f for f in changed if not (f.endswith(".py") or f.endswith(baseline))]
    if outside:
        raise LedgerError(f"ملفّاتٌ غيرُ .py وغيرُ خطّ mypy الأساس: {outside[:5]}")
    bad = [f for f in changed if "/migrations/" in f or f.startswith("migrations/")] + governing_files(changed)
    if bad:
        raise LedgerError(f"هجراتٌ أو ملفّاتٌ حاكمة تُعرض على المالك: {bad[:5]}")
    for f in changed:
        if f.endswith(baseline):
            old = json.loads(_git(["show", f"{approved}:{f}"], repo) or "{}").get("files", {})
            cur = json.loads(_git(["show", f"{new}:{f}"], repo) or "{}").get("files", {})
            risen = [k for k, v in cur.items() if v > old.get(k, 0)]
            if risen:
                raise LedgerError(f"الخطُّ الأساس يرتفع (يُعرض على المالك): {risen[:5]}")
            continue
        try:
            before = _strip_types(_git(["show", f"{approved}:{f}"], repo))
        except LedgerError:
            before = None  # ملفٌّ جديد
        after = _strip_types(_git(["show", f"{new}:{f}"], repo))
        if before != after:
            raise LedgerError(f"تغييرٌ يتجاوز الأنواع في {f} (AST بعد تجريد الأنواع يختلف) — يُعرض على المالك")
    return changed


def check_main_merge(approved: str, new: str, repo: str | None = None) -> list[str]:
    """يتحقّق آلياً أنّ الإيداعَ الجديد «دمجُ main فقط» (D-154م، موسَّعٌ بقرار المالك 2026-10-09 «موافق»).

    الشروط: (١) الإيداعُ دمجٌ بأبوين، أوّلُهما الرأسُ المعتمَد أو تالٍ له؛ (٢) الأبُ الثاني سلفٌ لـorigin/main — وإلّا
    طابق أيُّ فرعٍ يحمل كوداً نفسَه؛ (٣) إمّا كلُّ ملفٍّ تغيّر مطابقٌ بمحتواه لجهة main (الأب الثاني)، أو شجرةُ الإيداع
    تساوي حرفياً ناتجَ `git merge-tree --write-tree` بين المعتمَد والأب الثاني بلا تعارضٍ ولا حلٍّ يدويّ (الأبُ الأوّل
    هو المعتمَد نفسُه حينئذٍ) ولا ملفَّ حاكمٌ بين المتغيّر. يعيد قائمةَ الملفّات المغيَّرة."""
    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    parents = _git(["rev-list", "--parents", "-n", "1", new], repo).split()[1:]
    if len(parents) != 2:
        raise LedgerError(f"ليس دمجاً بأبوين ({len(parents)}): لا يُعفى إلا «دمجُ main فقط»")
    first, second = parents
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, first], cwd=cwd, capture_output=True).returncode != 0:
        raise LedgerError("الأبُ الأوّل ليس الرأسَ المعتمَد أو تالياً له — فيه إيداعاتٌ لا نعرفها")
    if subprocess.run(["git", "merge-base", "--is-ancestor", second, "origin/main"], cwd=cwd, capture_output=True).returncode != 0:
        raise LedgerError("الأبُ الثاني ليس من origin/main (fetch أوّلاً؟) — فقد يكون فرعاً يحمل كوداً")
    changed = _git(["diff", "--no-renames", "--name-only", approved, new], repo).split("\n")
    changed = [f for f in changed if f]
    if not changed:
        raise LedgerError("لا فرقَ عن الرأس المعتمَد — لا حاجةَ لاستثناء")

    def blob(rev: str, f: str) -> str:
        return subprocess.run(["git", "rev-parse", "-q", "--verify", f"{rev}:{f}"], capture_output=True, encoding="utf-8",
                              cwd=cwd).stdout.strip()

    bad = [f for f in changed if blob(new, f) != blob(second, f)]
    if not bad:
        return changed
    # الطريقُ الموسَّع: دمجٌ آليٌّ نظيفٌ لملفّاتٍ لمستها الجلسةُ وmain معاً
    if first != _git(["rev-parse", "--verify", f"{approved}^{{commit}}"], repo).strip():  # الدفترُ يخزّن بادئةً قصيرة
        raise LedgerError(f"ملفّاتٌ تختلف عن جهة main والأبُ الأوّل ليس المعتمَد نفسَه فلا merge-tree: {bad[:5]}")
    mt = subprocess.run(["git", "merge-tree", "--write-tree", approved, second], capture_output=True, encoding="utf-8", cwd=cwd)
    tree = mt.stdout.split("\n")[0].strip()
    new_tree = _git(["rev-parse", f"{new}^{{tree}}"], repo).strip()
    if mt.returncode != 0 or tree != new_tree:
        raise LedgerError(f"ملفّاتٌ تختلف عن جهة main وشجرةُ الدمج لا تطابق merge-tree الآليَّ (حلٌّ يدويٌّ أو تعارض): {bad[:5]}")
    gov = governing_files(bad)
    if gov:
        raise LedgerError(f"ملفّاتٌ حاكمةٌ بين المتغيّر تحتاج اعتماداً جديداً: {gov[:5]}")
    return changed


def _patch_id(rev: str, repo: str | None = None) -> str:
    """بصمةُ عملِ الفرع وحدَه: `git patch-id --stable` لـ`origin/main...rev` (فرقٌ عن أساسه المشترك مع main)."""
    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    diff = _git(["diff", "--no-renames", f"origin/main...{rev}"], repo)
    if not diff:
        return ""
    out = subprocess.run(["git", "patch-id", "--stable"], input=diff + chr(10), capture_output=True, encoding="utf-8",
                         errors="replace", cwd=cwd, check=False).stdout.split()
    return out[0] if out else ""


#: مساراتُ صلاحيّاتٍ وأمنٍ وهجراتٍ لا يُعفى فيها أيُّ فرقٍ (كما check_red_fix).
SENSITIVE_PATH_PARTS = ("permission", "auth", "security", "settings", "middleware", "capabilit", "/migrations/")


def check_patch_id(approved: str, new: str, repo: str | None = None) -> list[str]:
    """W-20261014-006: رأسان لهما بصمةُ patch-id مطابقةٌ تماماً لعمل الفرع عن main (أعيد أساسُه أو دُمج فيه main بلا تغيير
    لعمله). يرفض أيَّ فرقٍ في العمل نفسِه، وأيَّ ملفٍّ حاكمٍ أو هجرةٍ أو صلاحيّاتٍ/أمنٍ في الفرق. يعيد ملفّات الفرع."""
    pa, pn = _patch_id(approved, repo), _patch_id(new, repo)
    if not pa or not pn:
        raise LedgerError("فرقٌ فارغٌ عن origin/main (fetch أوّلاً؟) — لا بصمةَ تقارَن")
    if pa != pn:
        raise LedgerError("بصمةُ patch-id تختلف: عملُ الفرع تغيّر عن المعتمَد — يحتاج اعتماداً جديداً")
    changed = [f for f in _git(["diff", "--no-renames", "--name-only", f"origin/main...{new}"], repo).splitlines() if f]
    bad = governing_files(changed) + [f for f in changed if "/migrations/" in f or f.startswith("migrations/")
                                       or any(k in f.lower() for k in SENSITIVE_PATH_PARTS)]
    if bad:
        raise LedgerError(f"ملفّاتٌ حاكمةٌ أو هجراتٌ أو صلاحيّاتٌ/أمنٌ في العمل تُعرض على المالك: {sorted(set(bad))[:5]}")
    return changed


WAIVER_BY = {"0501"}

#: ملفّاتٌ حاكمةٌ لا يُستثنى تعديلُها بـwaive-head «وثائق» (W-20261003-040، مواصفة 0103): تُحمَّل في كلّ جلسةٍ أو بالمسار فتوجّه السلوك.
#: تُطابَق بعد التطبيع (`\` ← `/`، حذفُ `./`، حروفٌ صغيرة).
GOVERNING_RE = (
    r"^claude\.md$",  # الدستور في الجذر
    r"(^|/)claude\.md$",  # دستورٌ متداخل (يُحمَّل عند القراءة في مجلّده)
    r"^\.claude/",  # قواعد وإعدادات وhooks
    r"^docs/governance/flow\.md$",  # الفلو المستورَد بـ@ من CLAUDE.md
)


def normalize_path(path: str) -> str:
    """مسارٌ للمقارنة: الشرطةُ المائلةُ العكسيّةُ ← `/`، حذفُ `./` البادئة (مكرَّرةً)، حروفٌ صغيرة."""
    value = path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lower()


def governing_files(changed: list[str]) -> list[str]:
    """الملفّاتُ الحاكمةُ بين المتغيّرة، بأسمائها كما وردت."""
    return [f for f in changed if any(re.search(p, normalize_path(f)) for p in GOVERNING_RE)]


def _docs_changed_files(approved: str, new_head: str, passed: list[str] | None) -> list[str]:
    """ما يُفحص لاستثناء «وثائق»: `git diff` الحقيقيُّ **اتّحاداً** مع القائمة الممرَّرة — فلا يتجاوز الفحصَ من يمرّر قائمةً حميدةً.

    فإن تعذّرت قراءةُ git (اختبارٌ بلا مستودع) والقائمةُ ممرَّرةٌ فُحصت وحدَها؛ وبلا قائمةٍ يفشل بصوتٍ عالٍ كما كان.
    """
    try:
        real = [f for f in _git_read(["git", "diff", "--no-renames", "--name-only", approved, new_head]).splitlines() if f.strip()]
    except LedgerError:
        if passed is None:
            raise
        real = []
    return list(dict.fromkeys([*(passed or []), *real]))


def reapprove(item_id: str, new_head: str, by: str, note: str, path=None) -> None:
    """اعتمادُ المالك المباشر لرأسٍ جديدٍ على بطاقةٍ معتمَدةٍ أصلاً (D-146م: الاعتمادُ مربوطٌ بالرأس).

    سدٌّ لثغرة 10-09 (W-20261008-013): اعتمد المالكُ رأساً جديداً بعد التعديل ولا أداةَ تنقل رأسَ البطاقة إليه
    (`move approved` مكرَّرٌ مرفوض، و`waive-head` لا يغطّي تغييرَ كود). التسجيلُ لـ0501/0101 فقط كـ`move approved`،
    والملاحظةُ تسمّي المالكَ والرأسَ الجديد؛ ولا يجوز بعد الدمج (merged/published) لأنّ الرأسَ حينها قد دُمج."""
    check_recorder("approved", by)
    if not by:
        raise LedgerError("--by مطلوب: 0501 أو 0101")
    head = new_head[:8]
    if not HEAD_RE.match(new_head):
        raise LedgerError("--head <sha8> رأسُ الإيداع الذي عاينه المالكُ")
    items = reduce_state(load_events(path))
    item = items.get(item_id)
    if item is None:
        raise LedgerError(f"بطاقةٌ غيرُ موجودة: {item_id}")
    if item["state"] not in ("approved", "pushed"):
        raise LedgerError(f"«{item['state']}»: إعادةُ الاعتماد لبطاقةٍ في approved أو pushed فقط (بعد الدمج الرأسُ دُمج)")
    if (item.get("approved_head") or "")[:8] == head:
        raise LedgerError("الرأسُ هو المعتمَد أصلاً — لا حاجةَ لإعادة الاعتماد")
    if "المالك" not in note or head not in note:
        raise LedgerError("الملاحظةُ يلزمها تسميةُ المالك والرأس الجديد (مثل: اعتمد المالك مباشرةً <الرأس> «نصُّ قوله»)")
    append_event("state", item_id, {"state": item["state"], "by": by, "head": head}, path)
    append_event("note", item_id, {"text": check_text("note", f"إعادةُ اعتمادٍ برأسٍ جديد {item.get('approved_head')}→{head} بتوقيع {by}: {note}")}, path)


def check_red_fix(item: dict, approved: str, new: str, repo: str | None = None) -> list[str]:
    """«إصلاحُ فحصٍ أحمر بعد الدفع» (قرارُ المالك 10-10، D-332م): الرأسُ المعتمَد دُفع فعلاً (حالةُ البطاقة pushed)؛
    والجديدُ يتلوه؛ ولا هجراتٍ ولا ملفّاتٍ حاكمةً ولا واجهةً (templates وstatic/css وstatic/js) ولا مساراتِ صلاحيّاتٍ/أمن.
    لا ينطبق على عملٍ لم يُدفع. يعيد الملفّاتِ المغيَّرة."""
    if item.get("state") != "pushed":
        raise LedgerError("إعفاءُ إصلاح الفحص الأحمر لعملٍ دُفع فقط (حالة pushed)؛ ما لم يُدفع يحتاج اعتماداً جديداً")
    cwd = repo or os.environ.get("SCHOOLOS_REPO", "D:/shschool_mvp")
    if subprocess.run(["git", "merge-base", "--is-ancestor", approved, new], cwd=cwd, capture_output=True).returncode != 0:
        raise LedgerError("الإيداعُ الجديد لا يتلو الرأسَ المعتمَد — لا يُعفى")
    changed = [f for f in _git(["diff", "--no-renames", "--name-only", approved, new], repo).splitlines() if f]
    if not changed:
        raise LedgerError("لا فرقَ عن الرأس المعتمَد — لا حاجةَ لاستثناء")
    ui = ("templates/", "static/css/", "static/js/")
    sensitive = ("permission", "auth", "security", "settings", "middleware", "capabilit", "/migrations/")
    bad = [f for f in changed if f.startswith(ui) or "/templates/" in f or f.startswith("migrations/")
           or any(k in f.lower() for k in sensitive)] + governing_files(changed)
    if bad:
        raise LedgerError(f"واجهةٌ أو هجراتٌ أو صلاحيّاتٌ/أمنٌ أو ملفّاتٌ حاكمة تُعرض على المالك: {bad[:5]}")
    return changed


def waive_head(item_id: str, new_head: str, by: str, reason: str, path=None, changed=None, kind: str = "docs", repo: str | None = None) -> None:
    """استثناءٌ صريحٌ مسجَّلٌ لا ضمنيّ: تعديلٌ تافهٌ (وثائق أو .md) بعد الاعتماد بتوقيع 0501؛ لا كودَ ولا صلاحيّاتٍ ولا هجرات."""
    if by not in WAIVER_BY:
        raise LedgerError(f"الاستثناءُ لـ{sorted(WAIVER_BY)} وحدَها")
    if not HEAD_RE.match(new_head):
        raise LedgerError("--head غيرُ صالح")
    item = reduce_state(load_events(path)).get(item_id)
    if not item or not item.get("approved_head"):
        raise LedgerError("لا اعتمادَ مربوطاً برأسٍ لهذه البطاقة")
    if kind == "auto":  # (W-20261016-018) يجرّب النوعين المأذونين وحدَهما بفحص الشجرة؛ لا توسيعَ لصنفٍ ثالث
        for cand, check in (("main-merge", check_main_merge), ("tests-only", check_tests_only)):
            try:
                check(item["approved_head"], new_head, repo)
            except LedgerError:
                continue
            kind = cand
            break
        else:
            raise LedgerError("لا إعفاءَ آليّاً: الفرقُ ليس دمجَ main خالصاً ولا إصلاحَ اختباراتٍ فقط (الباقي يحتاج اعتماداً جديداً بالرأس)")
    if kind == "main-merge":
        check_main_merge(item["approved_head"], new_head, repo)
        reason = f"دمجُ main فقط (تحقّق آليّ) — {reason}"
    elif kind == "patch-id":
        check_patch_id(item["approved_head"], new_head, repo)
        reason = f"تطابقُ patch-id تامٌّ لعمل الفرع بعد دمج main/إعادة الأساس (تحقّق آليّ، W-20261014-006) — {reason}"
    elif kind == "tests-only":
        check_tests_only(item["approved_head"], new_head, repo)
        reason = f"إصلاحُ اختباراتٍ فقط بلا حراسةٍ أمنيّة (تحقّق آليّ) — {reason}"
    elif kind == "types-only":
        check_types_only(item["approved_head"], new_head, repo)
        reason = f"إصلاحُ أنواعٍ فقط لفشل mypy بقرار المالك 10-10 (تحقّق آليّ: AST مطابق) — {reason}"
    elif kind == "red-fix":
        check_red_fix(item, item["approved_head"], new_head, repo)
        reason = f"إصلاحُ فحصٍ أحمر بعد الدفع بقرار المالك 10-10 D-332م (تحقّق آليّ: pushed، بلا واجهة/هجرات/أمن) — {reason}"
    elif kind == "docs":
        changed = _docs_changed_files(item["approved_head"], new_head, changed)
        governing = governing_files(changed)
        if governing:
            raise LedgerError(
                f"ملفّاتٌ حاكمةٌ (CLAUDE.md أو .claude/** أو flow.md) تحتاج اعتماداً جديداً بالرأس لا waive-head: {governing[:5]}"
            )
        bad = [f for f in changed if not (f.startswith("docs/") or f.endswith(".md"))]
        if not changed or bad:
            raise LedgerError(f"الاستثناءُ للوثائق وحدَها؛ ملفّاتٌ غيرُ وثائقيّة أو فرقٌ فارغ: {bad[:5]}")
    else:
        raise LedgerError("--kind: docs أو main-merge أو tests-only أو types-only أو red-fix أو patch-id أو auto")
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
    a.add_argument("--start", required=True, help="زمنُ البدء الفعليّ ISO بتوقيت الدوحة"); a.add_argument("--priority", required=True, choices=PRIORITIES); a.add_argument("--held-by")
    m = sub.add_parser("move"); m.add_argument("id"); m.add_argument("state"); m.add_argument("--note"); m.add_argument("--by", help="رقمُ جلستك (0501/0101/0601…)؛ يُسجَّل مع الحالة"); m.add_argument("--head", help="للاعتماد: رأسُ الإيداع المعاين (sha8)؛ ولـpushed: يُقارَن بالبعيد")
    m.add_argument("--branch", help="لـpushed: الفرعُ المتحقَّق من وجوده على البعيد"); m.add_argument("--waive-remote-check", help="استثناءٌ مسجَّل لفحص البعيد (السبب)")
    m.add_argument("--held-by", help="الجلسةُ الحاجزة للبطاقة؛ «-» للتصفير")
    m.add_argument("--waive-spec", help="استثناءٌ مسجَّل لبوّابة المواصفة الكاملة (السبب)")
    m.add_argument("--waive-wip", help="استثناءٌ مسجَّل لحدِّ العمل الجاري: بطاقةٌ واحدةٌ جاريةٌ للجلسة (السبب)")
    m.add_argument("--preflight-repo", help="لـready_for_review: مجلّدُ شجرتك لتشغيل الفحص المسبق (pr_open_prep --preflight)")
    m.add_argument("--premerge-sha", help="لـready_for_review: بصمةُ make premerge بصيغة <head8>:<sha16> (إنذارٌ في الظلّ ثم إلزام)")
    m.add_argument("--head-now", help="رأسُ الفرع الحاليّ للمطابقة مع البصمة (sha8)")
    m.add_argument("--waive-preflight", help="استثناءٌ مسجَّل للفحص المسبق (السبب)")
    sp = sub.add_parser("spec", help="يضبط حقولَ المواصفة الكاملة")
    sp.add_argument("id"); sp.add_argument("--tier", choices=SPEC_TIERS); sp.add_argument("--ref"); sp.add_argument("--roles-states")
    sp.add_argument("--allowed-diffs"); sp.add_argument("--assumption", action="append"); sp.add_argument("--source-of-truth")
    sp.add_argument("--files-allowed", nargs="*"); sp.add_argument("--files-forbidden", nargs="*")
    sp.add_argument("--accept", action="append"); sp.add_argument("--step", action="append"); sp.add_argument("--by", required=True)
    nt = sub.add_parser("note", help="ملاحظةٌ على بطاقةٍ دون نقل حالتها")
    nt.add_argument("id"); nt.add_argument("--text", required=True); nt.add_argument("--by", required=True)
    rt = sub.add_parser("return", help="تعيد بطاقةً لنقص المواصفة إلى captured")
    rt.add_argument("id"); rt.add_argument("--reason", required=True); rt.add_argument("--by", required=True)
    pk = sub.add_parser("park", help="وسمُ بطاقةٍ مركونةٍ بقرارٍ مسجَّل")
    pk.add_argument("id"); pk.add_argument("--decision", required=True); pk.add_argument("--reason", required=True)
    rs = sub.add_parser("reschedule", help="إعادةُ جدولةِ بدءِ بطاقةٍ منتظِرةٍ بقرارٍ مسجَّل")
    rs.add_argument("id"); rs.add_argument("--start", required=True); rs.add_argument("--decision", required=True); rs.add_argument("--by", required=True); rs.add_argument("--reason", required=True)
    rp = sub.add_parser("raise-priority", help="رفعُ أولويّةِ بطاقةٍ (رفعٌ فقط)")
    rp.add_argument("id"); rp.add_argument("priority", choices=PRIORITIES); rp.add_argument("--by", required=True); rp.add_argument("--reason", required=True)
    wv = sub.add_parser("waive-head", help="استثناءُ تافهٍ (وثائق فقط) بتوقيع 0501: يُنقل الاعتمادُ إلى رأسٍ جديد")
    wv.add_argument("id"); wv.add_argument("--head", required=True); wv.add_argument("--by", required=True); wv.add_argument("--reason", required=True); wv.add_argument("--kind", default="docs", choices=["docs", "main-merge", "tests-only", "types-only", "red-fix", "patch-id", "auto"])
    ra = sub.add_parser("reapprove", help="اعتمادُ المالك المباشر لرأسٍ جديدٍ على بطاقةٍ معتمَدةٍ أصلاً (0501/0101)")
    ra.add_argument("id"); ra.add_argument("--head", required=True); ra.add_argument("--by", required=True); ra.add_argument("--note", required=True)
    ls = sub.add_parser("list"); ls.add_argument("--state")
    sh = sub.add_parser("show"); sh.add_argument("id"); sh.add_argument("--brief", action="store_true", help="ملخّصٌ ≤12 سطراً")
    tg = sub.add_parser("tag", help="يكتب خطورةَ البطاقة ومجالها من مسارات عملها")
    tg.add_argument("id")
    src = tg.add_mutually_exclusive_group(required=True)
    src.add_argument("--branch"); src.add_argument("--pr", type=int); src.add_argument("--paths", nargs="+")
    tg.add_argument("--raise-to", default=""); tg.add_argument("--reason", default=""); tg.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        if args.cmd == "add":
            print(add_item(args.source, args.type, args.problem, args.impact, args.accept, args.files, args.urgent,
                           start=args.start, priority=args.priority, held_by=args.held_by or ""))
        elif args.cmd == "move":
            move(args.id, args.state, note=args.note, by=args.by, head=args.head, branch=args.branch,
                 waive_remote_check=args.waive_remote_check, held_by=args.held_by, waive_spec=args.waive_spec, waive_wip=args.waive_wip, preflight_repo=args.preflight_repo, waive_preflight=args.waive_preflight, premerge_sha=args.premerge_sha, head_now=args.head_now); print("ok")
        elif args.cmd == "spec":
            set_spec(args.id, args.tier, args.ref, args.roles_states, args.allowed_diffs, args.assumption, args.source_of_truth,
                     args.files_allowed, args.files_forbidden, args.accept, args.step, args.by); print("ok")
        elif args.cmd == "note":
            add_note(args.id, args.text, args.by); print("ok")
        elif args.cmd == "return":
            return_card(args.id, args.reason, args.by); print("ok")
        elif args.cmd == "raise-priority":
            raise_priority(args.id, args.priority, args.reason, args.by); print("ok")
        elif args.cmd == "reschedule":
            reschedule(args.id, args.start, args.decision, args.reason, args.by); print("ok")
        elif args.cmd == "park":
            park(args.id, args.decision, args.reason); print("ok")
        elif args.cmd == "reapprove":
            reapprove(args.id, args.head, args.by, args.note); print("ok")
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
                it = items.get(args.id)
                if args.brief:
                    print(chr(10).join(brief_lines(it, args.id)))
                    return
                print(json.dumps(it, ensure_ascii=False, indent=2))
                if it:
                    print("المواصفة — " + spec_status(it))
            else:
                for it in sorted(items.values(), key=order_key):
                    if not args.state or it["state"] == args.state:
                        print(f"{it['id']}  {it.get('priority','—')}  بدء={it.get('start','—')[:16]}  {it['state']:16} {it['type']:16} {it['problem'][:50]}"
                              + (f"  [حاجزها {it['held_by']}]" if it.get("held_by") else "")
                              + f"  [مواصفة {spec_status(it).split(' — ')[0]}]")
    except LedgerError as exc:
        sys.exit(f"رُفض: {exc}")


if __name__ == "__main__":
    main()
