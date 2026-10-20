#!/usr/bin/env python3
"""هل اعتمد المالكُ هذا؟ — تحقّقٌ آليٌّ من المصدر بدل سؤال المالك أو الجلسات (أمر المالك 2026-10-02).

    python approval_check.py card W-20260930-005
    python approval_check.py pr 772
    python approval_check.py visual W-20261009-007 --head ab12cd34   # الأدلّةُ البصريّة وحدَها — قبل «جاهزٌ للمعاينة»

المصادر بالترتيب: (١) حالةُ البطاقة في الدفتر — لا تبلغ approved وما بعدها إلا بـ`ledger.py move … --note` (قاعدةُ D-73م)،
(٢) أحداثُ الاعتماد approvals في الدفتر، (٣) سطرُ الاعتماد في وصف طلب الدمج، (٤) `owner_confirmations.md`.
يخرج برمز 0 إن ثبت الاعتماد من مصدرٍ واحد على الأقلّ، و2 إن لم يثبت — وحينها تسأل الجلسةُ **0501 أو 0101** (من تلقّى الاعتماد) لا المالك.
قراءةٌ فقط.

**البوّابةُ البصريّة (W-20261009-007):** لبطاقةٍ تلمس واجهةً (`templates/` أو `static/css|js` في `files` أو في فرق رأسها عن main)
يرجع بالرمز 4 برسالة «لا أدلة بصرية للرأس» عند غياب `evidence/<بطاقة>/<رأس8>/manifest.json` أو اختلاف رأسه أو مخالفةٍ غيرِ مبرَّرة
(`visual_gate.py`). وغيرُ الواجهة لا يتغيّر سلوكُه.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR = "D:/shschool_mvp"
APPROVED_STATES = {"approved", "pushed", "merged", "published", "closed"}
APPROVAL_LINE = re.compile(r"اعتُمد من المالك[^\n]*|اعتمد المالك[^\n]*")


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


# اعتماداتٌ قديمةٌ بلا رأسٍ تُقبل بتحذيرٍ حتى هذا التاريخ ثمّ تُرفض (قرار 0101، v2.23)
LEGACY_DEADLINE = date(2026, 10, 9)
HEAD_IN_LINE = re.compile(r"(?:الرأس|@)\s*([0-9a-f]{7,40})")


def head_status(approved: str | None, pr_head: str | None, today: date | None = None) -> str:
    """ok: متطابقان أو لا رأسَ للمقارنة؛ stale: اختلفا؛ legacy: اعتمادٌ بلا رأس؛ expired: بلا رأسٍ وبعد المهلة."""
    today = today or date.today()
    if not approved:
        return "legacy" if today <= LEGACY_DEADLINE else "expired"
    if pr_head and approved[:8] != pr_head[:8]:
        return "stale"
    return "ok"


#: (W-20261016-018) السطرُ المؤرَّخ من هذا اليوم يجب أن يحمل رمزَ البطاقة نفسَها؛ الأقدمُ يبقى كما كان.
LINE_CARD_FROM = "2026-10-17"
_LINE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CARD_IN_LINE = re.compile(r"W-\d{8}-\d{3}")


def line_card_problem(line: str, card: str | None, cutoff: str | None = None) -> str | None:
    """سبب رفض سطر اعتمادٍ جديدٍ لا يربط رمزَ البطاقة (أو يربط رمزاً مخالفاً)؛ وإلا None."""
    cutoff = cutoff or LINE_CARD_FROM
    d = _LINE_DATE.search(line)
    if not d or d.group(0) < cutoff:
        return None
    codes = set(_CARD_IN_LINE.findall(line))
    if not codes:
        return "سطرُ الاعتماد لا يحمل رمزَ البطاقة (القالبُ: اعتُمد من المالك على 8500 — <التاريخ> — <رمز البطاقة> — الرأس <sha8>)"
    if card and card not in codes:
        return f"رمزُ البطاقة في السطر {sorted(codes)} لا يطابق {card}"
    return None


def card_evidence(card: str, pr_head: str | None = None) -> list[tuple[str, str]]:
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d, _ = json.JSONDecoder().raw_decode(out.lstrip())  # show يطبع نصّاً بعد الـJSON
    except ValueError:
        return []
    if not isinstance(d, dict):  # بطاقةٌ غيرُ موجودة: show يطبع null
        return []
    ev: list[tuple[str, str]] = []
    st = head_status(d.get("approved_head"), pr_head)
    if d.get("state") in APPROVED_STATES:
        ev.append((f"الدفتر: حالةُ {card} = {d['state']} (رأسُ الاعتماد {d.get('approved_head') or 'غيرُ مسجَّل'})", st))
    for a in d.get("approvals", []):
        ev.append((f"الدفتر: اعتمادٌ by={a.get('by')} via={a.get('via', '')} {a.get('ts', '')[:16]}", st))
    for n in d.get("notes", []):
        txt = str(n.get("note", n.get("text", "")))
        if txt.startswith("استثناءُ رأس"):
            ev.append((f"الدفتر: تنازلٌ مسجَّل {n.get('ts', '')[:16]}: {txt[:110]}", st))
        if "اعتمد" in str(n.get("note", n.get("text", ""))):
            ev.append((f"الدفتر: ملاحظةٌ {n.get('ts', '')[:16]}: {str(n.get('note', n.get('text', '')))[:100]}", st))
    return ev


def pr_card(d: dict) -> tuple[str | None, str | None]:
    """بطاقةُ الطلب (W-018): بالترتيب اسمُ الفرع ثمّ العنوان ثمّ الوصف؛ أوّلُ مصدرٍ فيه معرّفٌ يُعتمد.

    في المصدر الواحد معرّفان مختلفان => (None، رسالةُ التعارض) فلا يُخمَّن. غيابُه في الثلاثة => (None، None) «لا بطاقة».
    """
    for name, text in (("الفرع", d.get("headRefName")), ("العنوان", d.get("title")), ("الوصف", d.get("body"))):
        ids = sorted(set(_CARD_IN_LINE.findall(text or "")))
        if len(ids) > 1:
            return None, f"تعارضُ بطاقاتٍ في {name}: {', '.join(ids)} — لا أخمّن؛ صحّحي الطلب"
        if ids:
            return ids[0], None
    return None, None


def pr_evidence(num: str) -> tuple[list[tuple[str, str]], str | None, str | None]:
    code, out = run(["gh", "pr", "view", num, "--json", "title,body,state,headRefOid,headRefName"], cwd=REPO_DIR)
    if code != 0:
        return [], None, None
    d = json.loads(out)
    pr_head = (d.get("headRefOid") or "")[:8] or None
    ev = []
    card_id, conflict = pr_card(d)
    if conflict:
        return [(f"الطلب #{num}: ✘ {conflict}", "conflict")], None, pr_head
    for m in APPROVAL_LINE.findall(d.get("body") or "")[:1]:
        h = HEAD_IN_LINE.search(m)
        status = head_status(h.group(1) if h else None, pr_head)
        problem = line_card_problem(m, card_id)
        if problem:
            status = "stale"
            m = f"{m.strip()[:80]} ✘ {problem}"
        ev.append((f"الطلب #{num} ({d['state']}): {m.strip()[:110]}", status))
    return ev, card_id, pr_head


#: مصدرُ الإفادة (W-20261016-030): «مصدره: مباشر» أو «مصدره: نقلاً عن 0101» بعد «(إفادةُ جلسة)»؛ والسطرُ بلا وسمٍ قديمٌ = «مباشر (قديم)».
SOURCE_IN_LINE = re.compile(r"مصدره:\s*(?:(مباشر)|نقلاً عن (?:جلسة )?(0[1-8]\d\d))")
SESSION_IN_LINE = re.compile(r"^\|[^|]*\|\s*(0[1-8]\d\d)")
#: وضعُ المنقول بلا «مباشر» من السامعة: إنذارٌ يطبع ولا يرفض؛ والإلزامُ بـ`APPROVAL_PROVENANCE=enforce` أو بقلب الثابت.
PROVENANCE_ENFORCE = False


def provenance_enforced() -> bool:
    return PROVENANCE_ENFORCE or os.environ.get("APPROVAL_PROVENANCE", "").lower() == "enforce"


def line_source(ln: str) -> tuple[str, str | None, str | None]:
    """(النوع، الجلسةُ الكاتبة، السامعة): النوعُ direct أو legacy (بلا وسم) أو relayed."""
    s = SESSION_IN_LINE.match(ln.strip())
    writer = s.group(1) if s else None
    m = SOURCE_IN_LINE.search(ln)
    if not m:
        return "legacy", writer, None
    if m.group(1):
        return "direct", writer, None
    return "relayed", writer, m.group(2)


def _has_key(key: str, ln: str) -> bool:
    """H3 (مراجعة 10-16): المطابقةُ بحدٍّ لفظيّ؛ «pr 7» لا تطابق «pr 77»."""
    return re.search(r"(?<![0-9A-Za-z_-])" + re.escape(key) + r"(?![0-9A-Za-z_-])", ln) is not None  # حدٌّ لاتيني: الحروفُ العربيّةُ بعد الرقم لا تُحسب جزءاً منه


def source_line() -> str:
    """مسارُ owner_confirmations.md المقروء مطلقاً وتاريخُ آخر تعديل، ليُكشف الاستعمالُ الصامتُ لنسخةٍ قديمةٍ في شجرةٍ أخرى."""
    f = ROOT / "owner_confirmations.md"
    if not f.exists():
        return f"المصدر المقروء: {f} — غير موجود"
    import datetime  # noqa: PLC0415
    return f"المصدر المقروء: {f} — آخر تعديل {datetime.datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M}"


def confirmations_evidence(key: str, pr_head: str | None = None, enforce: bool | None = None, path: Path | None = None) -> list[tuple[str, str]]:
    f = path or ROOT / "owner_confirmations.md"
    if not f.exists():
        return []
    enforce = provenance_enforced() if enforce is None else enforce
    out = []
    lines = f.read_text(encoding="utf-8").splitlines()
    # ملحقُ تصحيح: «ملغى[<بطاقة>@<رأس>]» يُبقي السطرَ الأصليّ ولا يُحسب دليلاً (لا حذفَ لسجلّ تأكيدات المالك)
    voided = re.findall(r"ملغى\[(\S+?)@(\w+)\]", chr(10).join(lines))
    live = [
        ln
        for ln in lines
        if "ملغى[" not in ln and not any(re.search(re.escape(c) + r"\s*@" + re.escape(h), ln) for c, h in voided)
    ]
    # الجلساتُ التي سجّلت تأكيداً «مباشراً» (أو قديماً) لهذا الهدف نفسه
    direct = {w for ln in live if _has_key(key, ln) for k, w, _ in [line_source(ln)] if k in ("direct", "legacy") and w}
    for ln in live:
        if _has_key(key, ln):
            h = HEAD_IN_LINE.search(ln)
            tail = " ← إفادةُ جلسةٍ تُدقَّق بالعيّنة" if "إفادةُ جلسة" in ln else ""
            st = head_status(h.group(1) if h else None, pr_head)
            kind, _, hearer = line_source(ln)
            if kind == "relayed" and hearer not in direct:
                tail += f" ⚠ منقولٌ عن {hearer} بلا تأكيد «مباشر» منها لهذا الهدف" + ("" if enforce else " (إنذار)")
                if enforce:
                    st = "unverified"
            out.append((f"owner_confirmations.md: {ln.strip()[:120]}{tail}", st))
    return out


#: تفعيلُ الحجب في `card`/`pr`: فارغٌ = مُعطَّل (مرجع 55 ينتظر اعتمادَ المالك، قرار 0101)؛ وبعد الاعتماد يُضبط تاريخاً
#: `"YYYY-MM-DD"` فلا تُلزَم بالأدلّة بطاقاتٌ أُنشئت قبله (سبقت البوّابة). وأمرُ `visual` الصريحُ يفحص دائماً.
VISUAL_GATE_FROM = "2026-10-10"  # قرار المالك 10-10: حجبٌ لبطاقات الواجهة المُنشأة من هذا اليوم بلا أدلّة بصريّة
UI_PREFIXES = ("templates/", "static/css/", "static/js/")


def _is_ui_path(path: str) -> bool:
    norm = path.replace("\\", "/").lstrip("./")
    norm = norm.replace(REPO_DIR.rstrip("/") + "/", "")
    return norm.startswith(UI_PREFIXES)


def ui_touched(ledger_files: list[str], head: str | None) -> bool:
    """هل تلمس البطاقةُ واجهةً: في `files` الدفتر، أو في فرق رأسها عن origin/main (إن عُرف الرأسُ في المستودع)."""
    if head:
        code, out = run(["git", "diff", "--name-only", f"origin/main...{head}"], cwd=REPO_DIR)
        if code == 0:  # الرأسُ معروفٌ في المستودع: الحكمُ بالفرق الفعليّ وحدَه، وملفّاتُ الدفتر الواسعةُ لا تُحجب به (0103، 10-10)
            return any(_is_ui_path(f) for f in out.splitlines())
    return any(_is_ui_path(f) for f in ledger_files or [])


#: إيصالُ قراءة الهويّة لرأس الإيداع (D-376م): يطبعه حارسُ prepush ويُحفظ بجانب manifest.json في
#: `evidence/<بطاقة>/<رأس8>/identity_ack.txt` بسطر «identity_ack: <رأس8> نجح». فارغٌ = مُعطَّل حتى تجهز الخطوتان
#: (تسجيلُ الرأس في identity_ack.py، وطباعةُ السطر في prepush)، وإلا سقطت كلُّ بطاقةٍ واجهيّةٍ قبل أن يمكن إنتاجُ السطر.
IDENTITY_ACK_FROM = ""
IDENTITY_ACK_FILE = "identity_ack.txt"


def identity_ack_problem(card: str, head: str | None, created: str = "", enforce: bool | None = None) -> str | None:
    """رسالةُ الفشل إن كانت بطاقةُ واجهةٍ بلا سطر «identity_ack: <رأس8> نجح» لرأسها؛ وإلّا `None`.

    «واجهيّة» بدالة `ui_touched` نفسها التي تحكم الأدلّةَ البصريّة. `enforce=None` يعني تطبيقَ `IDENTITY_ACK_FROM`.
    """
    if enforce is None:
        enforce = bool(IDENTITY_ACK_FROM) and str(created)[:10] >= IDENTITY_ACK_FROM
    if not enforce:
        return None
    if not head:
        return "لا إيصالَ هويّةٍ للرأس: بطاقةُ واجهةٍ بلا رأسٍ للمقارنة (مرّري --head)"
    h8 = head[:8]
    import visual_gate

    f = visual_gate.EVIDENCE_DIR / card / h8 / IDENTITY_ACK_FILE
    want = f"identity_ack: {h8} نجح"
    if f.is_file() and want in f.read_text(encoding="utf-8").splitlines():
        return None
    return f"لا إيصالَ هويّةٍ للرأس {h8}: شغّلي identity_ack.py ثمّ prepush على هذا الرأس (السطر المطلوب «{want}» في {f.name})"


def card_identity_problem(card: str, head: str | None) -> str | None:
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d, _ = json.JSONDecoder().raw_decode(out.lstrip())
    except ValueError:
        return None
    head = head or d.get("approved_head")
    if not ui_touched(d.get("files") or [], head):
        return None
    return identity_ack_problem(card, head, str(d.get("created", "")))


VISUAL_WAIVER_MARK = "تنازلٌ بصريّ بقرار المالك"
#: ما يمسّه رأسٌ جديدٌ فيمنع امتدادَ التنازل إليه (قرار المالك D-356م): الواجهةُ لا الخلفيّة.
WAIVER_UI_PREFIXES = ("templates/", "static/")
_HEX8 = re.compile(r"\b[0-9a-f]{8}\b")
#: `ledger.py note --by NNNN` يسبق النصَّ بـ«(NNNN) » فلا تُعدّ البادئةُ جزءاً من العبارة.
_AUTHOR_PREFIX = re.compile(r"^\(\d{4}\)\s*")


def _waived_heads(card: dict) -> list[str]:
    """رؤوسُ (ثماني خانات) ملاحظاتِ التنازل في دفتر هذه البطاقة وحدَها: تبدأ الملاحظةُ بالعبارة."""
    heads: list[str] = []
    for n in card.get("notes", []):
        txt = _AUTHOR_PREFIX.sub("", str(n.get("note", n.get("text", ""))), count=1)
        if txt.startswith(VISUAL_WAIVER_MARK):
            heads += _HEX8.findall(txt)
    return heads


def _diff_paths(old: str, new: str) -> list[str] | None:
    """مساراتُ ما بين رأسَين من git؛ `None` عند أيّ فشل (غيابُ الرأس في المستودع أو خطأ git) فيُرفض الامتداد بأمان."""
    code, out = run(["git", "diff", "--name-only", old, new], cwd=REPO_DIR)
    return [ln.strip() for ln in out.splitlines() if ln.strip()] if code == 0 else None


def visual_waived(card: dict, head: str) -> bool:
    """تنازلٌ عن ملفّ الأدلّة البصريّة (قرار المالك D-352م) مقيَّدٌ بالبطاقة والرأس.

    ملاحظةٌ في دفتر البطاقة نفسها تبدأ بالعبارة وفيها ثماني خانات الرأس. ويمتد (D-356م) لرأسٍ جديدٍ في دفتر البطاقة
    نفسها إن كان فرقُه عن الرأس المعفى لا يلمس `templates/` ولا `static/` وتحقّقت الأداةُ بـgit؛ وفشلُ git يعني لا امتداد.
    """
    h8 = head[:8]
    waived = _waived_heads(card)
    if h8 in waived:
        return True
    for h0 in dict.fromkeys(waived):
        paths = _diff_paths(h0, head)
        if paths is not None and not any(p.startswith(WAIVER_UI_PREFIXES) for p in paths):
            return True
    return False



def visual_problem(card: str, head: str | None, respect_cutoff: bool = False) -> str | None:
    """رسالةُ الفشل إن كانت البطاقةُ واجهةً بلا أدلّتها البصريّة السليمةِ للرأس؛ وإلّا `None`."""
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d, _ = json.JSONDecoder().raw_decode(out.lstrip())
    except ValueError:
        return None
    if not isinstance(d, dict):  # بطاقةٌ غيرُ موجودة: show يطبع null
        return None
    if respect_cutoff and (not VISUAL_GATE_FROM or str(d.get("created", ""))[:10] < VISUAL_GATE_FROM):
        return None
    head = head or d.get("approved_head")
    if not ui_touched(d.get("files") or [], head):
        return None
    if not head:
        return "لا أدلة بصرية للرأس: بطاقةُ واجهةٍ بلا رأسٍ للمقارنة (مرّري --head)"
    if visual_waived(d, head):
        return None
    import visual_gate

    ok, msg = visual_gate.evidence_status(card, head)
    return None if ok else msg


def _waiver_checker(txt: str):
    """اسمُ فاحصِ ledger للإعفاء حسب نصّ ملاحظته؛ None إن لم يكن من الأنواع المحمولة."""
    if "دمجُ main فقط (تحقّق آليّ)" in txt:
        return "check_main_merge"
    if "سلسلةُ إصلاح tests/ ودمج main فقط (تحقّق آليّ" in txt:
        return "check_tests_main_chain"
    return None


def waiver_carry(card: str | None, pr_head: str | None, target: str, depth: int = 6) -> list[tuple[str, str]]:
    """D-154م وقرار المالك 2026-10-17 (W-20261017-012): يحمل اعتمادَ المالك المباشر على رأسٍ معتمَدٍ سابقٍ إلى رأسٍ لاحقٍ
    بتنازلٍ من 0501 في دفتر البطاقة (`waive-head --kind main-merge` أو `tests-main-chain`) على الرأس نفسه، مع إعادة تحقّقٍ
    آليّةٍ من الفرق بفاحص ledger المطابق؛ وتُتتبَّع حلقاتُ التنازلات المتتالية (حتى depth) إلى رأسٍ له اعتمادٌ مباشر.
    لا يثبت شيئاً وحده؛ وأيُّ فشلٍ يُرجع قائمةً فارغة فيبقى الحكمُ كما كان."""
    if not card or not pr_head:
        return []
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d, _ = json.JSONDecoder().raw_decode(out.lstrip())
    except ValueError:
        return []
    if not isinstance(d, dict):  # بطاقةٌ غيرُ موجودة: show يطبع null
        return []
    waivers = []
    for n in d.get("notes", []):
        txt = re.sub(r"^\(\d{4}\)\s*", "", str(n.get("note", n.get("text", ""))))
        if not txt.startswith("استثناءُ رأسٍ تافه بتوقيع 0501:"):
            continue
        m = re.search(r"([0-9a-f]{8})→([0-9a-f]{8})", txt)
        checker = _waiver_checker(txt)
        if m and checker:
            waivers.append((m.group(1), m.group(2), checker))
    import ledger  # noqa: PLC0415 — الوحدةُ في tools/ ومُضافةٌ إلى sys.path أعلاه

    head, hops = pr_head[:8], []
    for _ in range(depth):
        step = next((w for w in waivers if w[1] == head), None)
        if step is None:
            return []
        base, _new, checker = step
        try:
            getattr(ledger, checker)(base, head, REPO_DIR)
        except Exception:
            return []
        hops.append(f"{base}→{head}")
        direct = [(t, st) for t, st in confirmations_evidence(target, base) if st == "ok"]
        if direct:
            return [(f"{t} ← محمولٌ بتنازلات ({' ، '.join(reversed(hops))}) تحقّقٌ آليّ (D-154م/12)", "ok") for t, _st in direct]
        head = base
    return []


def main_merge_carry(card: str | None, pr_head: str | None, target: str) -> list[tuple[str, str]]:
    """اسمٌ قديمٌ محفوظٌ للتوافق: الحملُ العامّ في waiver_carry."""
    return waiver_carry(card, pr_head, target)


def _owner_direct(e: tuple[str, str]) -> bool:
    """H2: أيُّ دليلٍ يُقبل اعتماداً؟ سطرُ owner_confirmations (مباشرٌ أو تفويضٌ دائمٌ مسجَّل) لا الدفترُ ولا وصفُ الطلب ولا المنقول."""
    text = e[0]
    if not text.startswith("owner_confirmations.md:"):
        return False
    return "منقولٌ عن" not in text


def label_delegation(text: str) -> str:
    """D-443م: سطرُ 0101 «دائم يغني» تفويضٌ دائمٌ بعد مراجعة الفرق، فيُعرض تفويضاً لا قولاً مباشراً من المالك على الرأس."""
    if "0101 (" in text and "دائم يغني" in text:
        return text + " ← تفويضٌ دائمٌ (D-443م) لا قولٌ مباشرٌ من المالك على هذا الرأس"
    return text


def ready_problem(repo: str) -> str | None:
    """(W-20261020-013) شرطُ قبول «جاهزٌ للمعاينة»: إيصالُ prepush ناجحٌ للرأس نفسه، والرأسُ غيرُ متأخّرٍ ولا متصادمٍ مع main.
    يُشغَّل بالصرامة الكاملة دائماً (هذا الأمرُ لـ0501؛ الظلُّ للانتقال في الدفتر وحدَه)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ledger

    old = os.environ.get("PREPUSH_RECEIPT_ENFORCE")
    os.environ["PREPUSH_RECEIPT_ENFORCE"] = "1"
    try:
        ledger.check_prepush_receipt(repo)
        return None
    except ledger.LedgerError as exc:
        return str(exc)
    finally:
        if old is None:
            os.environ.pop("PREPUSH_RECEIPT_ENFORCE", None)
        else:
            os.environ["PREPUSH_RECEIPT_ENFORCE"] = old


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=["card", "pr", "visual", "ready"])
    ap.add_argument("target")
    ap.add_argument("--head", help="للبطاقة: رأسُ الإيداع الحاليّ للمقارنة (sha8)")
    ap.add_argument("--repo", default=".", help="ready: شجرةُ عملِ الجلسة المراد قبولُ «جاهزٌ للمعاينة» منها")
    a = ap.parse_args()
    print(source_line())
    ev: list[tuple[str, str]] = []
    pr_head = a.head
    if a.kind == "ready":
        problem = ready_problem(a.repo)
        print(("✘ " + problem) if problem else "✔ إيصالُ prepush للرأس نفسه وحداثةُ main بلا تصادم — تُقبل الثلاثيّة")
        return 4 if problem else 0
    if a.kind == "visual":
        problem = visual_problem(a.target, a.head)
        print(("✘ " + problem) if problem else "✔ لا أدلةَ بصريّةً مطلوبة أو هي سليمة للرأس")
        return 4 if problem else 0
    if a.kind == "card":
        ev += card_evidence(a.target, pr_head)
    else:
        pev, card, pr_head = pr_evidence(a.target)
        ev += pev
        if card:
            ev += card_evidence(card, pr_head)
            ev += confirmations_evidence(card, pr_head)  # أسطرُ المالك المسجَّلة باسم البطاقة
    ev += confirmations_evidence(a.target, pr_head)
    ev += waiver_carry(card if a.kind == "pr" else a.target, pr_head, a.target)
    conflicts = [e for e in ev if e[1] == "conflict"]
    if conflicts:
        for t, _ in conflicts:
            print(t)
        return 3
    # H2 (مراجعة 10-16، قرار المالك «اعتمد»): الاعتمادُ لا يثبت إلا من قولِ المالك المباشر في owner_confirmations، أو تفويضٍ دائمٍ مسجَّل (يُبيَّن تفويضاً).
    # الدفترُ ووصفُ الطلب وسطرُ منقولٍ عن جلسةٍ أخرى ليست اعتماداً وحدها. الأسطرُ القديمةُ بلا مصدرٍ (legacy) تبقى مقبولةً.
    good = [e for e in ev if e[1] in ("ok", "legacy") and _owner_direct(e)]
    ledger_only = [e for e in ev if e[1] in ("ok", "legacy") and not _owner_direct(e)]
    good = [(label_delegation(t), s) for t, s in good]
    stale = [e for e in ev if e[1] == "stale"]
    if good:
        card_key = a.target if a.kind == "card" else (card if a.kind == "pr" and card else None)
        problem = (visual_problem(card_key, pr_head, respect_cutoff=True) or card_identity_problem(card_key, pr_head)) if card_key else None
        if problem:
            print("✘ " + problem)
            return 4
        print("✔ الاعتمادُ ثابتٌ من المصدر — لا تسألي المالكَ:")
        for t, st in good:
            print(f"  - {t}" + ("  ⚠ بلا رأسٍ (مقبولٌ حتى 2026-10-09 ثمّ يُرفض)" if st == "legacy" else ""))
        if stale:
            print("  (تجاهلتُ اعتماداتٍ على رأسٍ مختلف:)")
            for t, _ in stale:
                print(f"  - {t}")
        return 0
    if stale:
        print(f"✘ الاعتمادُ على رأسٍ غيرِ رأس الإيداع الحاليّ ({pr_head}): لا يسري على إيداعاتٍ لاحقةٍ لم يرها المالك.")
        for t, _ in stale:
            print(f"  - {t}")
        print("  أعيدي المعاينةَ على الرأس الجديد ثمّ سجّلي اعتماداً بـ--head، أو استثناءَ تافهٍ بتوقيع 0501 (`ledger.py waive-head`: وثائقُ، أو دمجُ main فقط D-154م، أو إصلاحُ اختباراتٍ فقط D-155م).")
        return 3
    if ev:
        print("✘ اعتماداتٌ بلا رأسٍ انتهت مهلتُها (2026-10-09): سجّلي اعتماداً جديداً بـ--head.")
        return 3
    if ledger_only:
        print("✘ وُجد دليلٌ من الدفتر أو وصف الطلب، لكنه لا يكفي: الاعتمادُ يلزمه قولُ المالك المباشر في owner_confirmations.md (H2).")
        for t, _ in ledger_only:
            print(f"  - {t}")
        return 2
    print("✘ لا اعتمادَ مسجَّلاً في المصدر. لا تسألي المالكَ مباشرةً: اسألي 0501 (إن كان معاينةً) أو 0101 أن تسجّل الاعتمادَ بـ`ledger.py move … approved --head <sha8> --note` ثمّ أعيدي الفحص.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
