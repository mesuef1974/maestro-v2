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


def card_evidence(card: str, pr_head: str | None = None) -> list[tuple[str, str]]:
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d, _ = json.JSONDecoder().raw_decode(out.lstrip())  # show يطبع نصّاً بعد الـJSON
    except ValueError:
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


def pr_evidence(num: str) -> tuple[list[tuple[str, str]], str | None, str | None]:
    code, out = run(["gh", "pr", "view", num, "--json", "title,body,state,headRefOid"], cwd=REPO_DIR)
    if code != 0:
        return [], None, None
    d = json.loads(out)
    pr_head = (d.get("headRefOid") or "")[:8] or None
    ev = []
    for m in APPROVAL_LINE.findall(d.get("body") or "")[:1]:
        h = HEAD_IN_LINE.search(m)
        ev.append((f"الطلب #{num} ({d['state']}): {m.strip()[:110]}", head_status(h.group(1) if h else None, pr_head)))
    card = re.search(r"W-\d{8}-\d{3}", d.get("title", "") + (d.get("body") or ""))
    return ev, card.group(0) if card else None, pr_head


def confirmations_evidence(key: str, pr_head: str | None = None) -> list[tuple[str, str]]:
    f = ROOT / "owner_confirmations.md"
    if not f.exists():
        return []
    out = []
    lines = f.read_text(encoding="utf-8").splitlines()
    # ملحقُ تصحيح: «ملغى[<بطاقة>@<رأس>]» يُبقي السطرَ الأصليّ ولا يُحسب دليلاً (لا حذفَ لسجلّ تأكيدات المالك)
    voided = re.findall(r"ملغى\[(\S+?)@(\w+)\]", chr(10).join(lines))
    for ln in lines:
        if "ملغى[" in ln:
            continue
        if any(re.search(re.escape(c) + r"\s*@" + re.escape(h), ln) for c, h in voided):
            continue
        if key in ln:
            h = HEAD_IN_LINE.search(ln)
            tail = " ← إفادةُ جلسةٍ تُدقَّق بالعيّنة" if "إفادةُ جلسة" in ln else ""
            out.append((f"owner_confirmations.md: {ln.strip()[:120]}{tail}", head_status(h.group(1) if h else None, pr_head)))
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


def visual_problem(card: str, head: str | None, respect_cutoff: bool = False) -> str | None:
    """رسالةُ الفشل إن كانت البطاقةُ واجهةً بلا أدلّتها البصريّة السليمةِ للرأس؛ وإلّا `None`."""
    code, out = run([sys.executable, str(ROOT / "tools" / "ledger.py"), "show", card])
    try:
        d, _ = json.JSONDecoder().raw_decode(out.lstrip())
    except ValueError:
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


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kind", choices=["card", "pr", "visual"])
    ap.add_argument("target")
    ap.add_argument("--head", help="للبطاقة: رأسُ الإيداع الحاليّ للمقارنة (sha8)")
    a = ap.parse_args()
    ev: list[tuple[str, str]] = []
    pr_head = a.head
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
    ev += confirmations_evidence(a.target, pr_head)
    good = [e for e in ev if e[1] in ("ok", "legacy")]
    stale = [e for e in ev if e[1] == "stale"]
    if good:
        card_key = a.target if a.kind == "card" else (card if a.kind == "pr" and card else None)
        problem = visual_problem(card_key, pr_head, respect_cutoff=True) if card_key else None
        if problem:
            print("✘ " + problem)
            return 4
        problem = card_identity_problem(card_key, pr_head) if card_key else None
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
    print("✘ لا اعتمادَ مسجَّلاً في المصدر. لا تسألي المالكَ مباشرةً: اسألي 0501 (إن كان معاينةً) أو 0101 أن تسجّل الاعتمادَ بـ`ledger.py move … approved --head <sha8> --note` ثمّ أعيدي الفحص.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
