#!/usr/bin/env python3
"""تسجيلُ أمرِ المالك المباشر في محادثتك بنصّه الحرفيّ — فيتحقّق منه 0501/0601 بالأداة ولا يُسأل المالكُ.

    python record_owner_confirmation.py --session 0405 --target W-20261002-013 --quote "ادفع" [--question "…"]

وضعُ التفويض الدائم (W-20261019-017، D-443م): `--delegation` يسجّل اعتمادَ 0101 الخفيفة لرأسٍ **بلا واجهةٍ ولا صلاحيّاتٍ ولا هجراتٍ ولا أمنٍ ولا ملفّاتٍ حاكمة**
بنصّ المالك الحرفيّ المسجَّل سلفاً (سطرا 2026-10-18 «نعم، دائم» و«نعم، دائم يغني») لا بنصٍّ يكتبه المستدعي؛ ويرفض ما عدا ذلك ليُعرض على المالك. لا يمسّ approval_check (H2).

    python record_owner_confirmation.py --delegation --session 0101 --target W-… --head <sha8> --tree <شجرة الفرع> --reviewed "ما رُوجع في الفرق"

يُلحَق سطرٌ بـ`owner_confirmations.md` (التاريخ، الجلسة، السؤال، النصُّ الحرفيّ، الهدف). يقرؤه `approval_check.py`. الإفادةُ **إفادةُ جلسة**
تُدقَّق بالعيّنة: 0102 يطابق أسطراً منها مع سجلّات الجلسات (واجبُ التدقيق الدوريّ)، فالنصُّ الحرفيُّ لا الوصفُ، ويُرفض الفارغُ والقصيرُ جدّاً.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "owner_confirmations.md"
DOHA = timezone(timedelta(hours=3))
SESSION = re.compile(r"^0[1-8]\d\d$|^0[1-8]\d\d ·")
#: مصدرُ الإفادة: «مباشر» (سمعتُ المالكَ في محادثتي) أو «نقلاً عن جلسة <رقم>» (W-20261016-030)
SOURCE = re.compile(r"^(?:مباشر|نقلاً عن (?:جلسة )?(0[1-8]\d\d))$")


def normalize_source(source: str) -> str | None:
    """الصيغةُ المخزَّنة («مباشر» أو «نقلاً عن 0101») أو None إن لم تصحّ."""
    m = SOURCE.match(source.strip())
    if not m:
        return None
    return f"نقلاً عن {m.group(1)}" if m.group(1) else "مباشر"


#: وسمُ أمر النافذة: أمرُ المالك بدمجٍ/نشرٍ داخل الدوام، يُسجَّل وقتَ كلامه بلا رأس؛ يشترطه release_follow.sh وwindow_order_present
WINDOW_TAG = "[أمرُ نافذة]"


def window_order_present(text: str, target: str) -> bool:
    """هل في نصّ owner_confirmations.md سطرُ أمرِ نافذةٍ لهذا الهدف (رمزُ البطاقة أو #رقم الطلب)؟"""
    t = target.strip()
    pat = re.compile(rf"(?<![\w#-]){re.escape(t)}(?![\w-])")
    return any(WINDOW_TAG in ln and pat.search(ln.split("|")[-2] if ln.count("|") >= 2 else ln) for ln in text.splitlines())


def row(session: str, target: str, quote: str, question: str, now: datetime | None = None, head: str = "", source: str = "", window: bool = False) -> str:
    now = now or datetime.now(DOHA)
    esc = lambda t: t.replace("|", "/").replace("\n", " ").strip()  # noqa: E731
    tag = (f" مصدره: {source}" if source else "") + (f" {WINDOW_TAG}" if window else "")
    return f"| {now:%Y-%m-%d %H:%M} | {esc(session)} (إفادةُ جلسة){tag} | {esc(question) or 'أمرٌ مباشر'} | «{esc(quote)}» | {esc(target)}{' @' + head[:8] if head else ''} |\n"


# ---- وضع التفويض الدائم (D-443م) ----
#: أنماطُ مساراتٍ لا تُفوَّض أبداً: واجهة، صلاحيات/أمن، هجرات، ملفات حاكمة، وسلسلةُ الاعتماد نفسُها (لا يعتمد المفوَّضُ ما يعدّل بوّابتَه)
FORBIDDEN = (
    (r"(^|/)migrations?/", "هجرة"),
    (r"(^|/)(templates|static)/|\.(html|css|vue|jsx?)$", "واجهة"),
    (r"(^|/)(permissions?|capabilit\w*|rbac|auth\w*|security|secrets?)(/|\.|_|$)", "صلاحيات/أمن"),
    (r"^CLAUDE\.md$|(^|/)\.claude/|(^|/)flow\.md$", "ملف حاكم"),
    (r"(^|/)(approval_check|record_owner_confirmation|ledger)\.py$|(^|/)owner_confirmations\.md$", "سلسلة الاعتماد"),
)
STANDING_TARGETS = ("standing-head-approval", "delegations-no-expiry")
PATH_TOKEN = re.compile(r"[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+|\b[A-Za-z0-9_\-]+\.(?:py|md|js|css|html|yml|yaml|json|sql|txt)\b")


def forbidden_hits(paths) -> list[str]:
    hits = []
    for path in sorted(set(paths)):
        norm = re.sub(r"^(?:\./)+", "", path.replace("\\", "/").strip())  # لا lstrip("./"): يأكل نقطةَ «.claude»
        for pat, why in FORBIDDEN:
            if re.search(pat, norm, re.IGNORECASE):
                hits.append(f"{path} ({why})")
                break
    return hits


def card_paths(item: dict) -> list[str]:
    """مساراتُ ملفّات البطاقة (files و files_allowed) كما ذُكرت؛ النصُّ الحرّ يُستخرج منه ما يشبه مساراً."""
    out: list[str] = []
    for key in ("files", "files_allowed"):
        for entry in item.get(key) or []:
            out += PATH_TOKEN.findall(str(entry))
    return out


def standing_quote(text: str) -> tuple[str, str]:
    """نصُّ المالك الحرفيّ للتفويض الدائم من الملف نفسِه: يلزم السطران المسجَّلان (الاعتماد الدائم ثمّ «يغني») بمصدر «مباشر».
    يعيد (نصَّ «دائم يغني»، الإفادةَ الأولى) أو يرفع ValueError فلا يُكتب نصٌّ منسوبٌ للمالك لم يقله."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 5 or "مصدره: مباشر" not in cols[1]:
            continue
        for target in STANDING_TARGETS:
            if cols[4].startswith(target):
                found[target] = re.sub(r"\s*\(Recommended\)", "", cols[3]).strip("«» ")
    if set(found) != set(STANDING_TARGETS) or "دائم يغني" not in found["delegations-no-expiry"] or "دائم" not in found["standing-head-approval"]:
        raise ValueError("لا يوجد في owner_confirmations.md سطرا المالك المباشران للتفويض الدائم (دائم / دائم يغني)؛ لا يُكتب نصٌّ منسوبٌ إليه")
    return "دائم يغني", found["standing-head-approval"]


def delegation_problem(item: dict | None, card: str, head: str, diff_files: list[str], head_now: str, reviewed: str, session: str) -> str | None:
    """سببُ الرفض أو None إن صحّ التفويض."""
    if session != "0101":
        return "التفويض الدائم لـ0101 الخفيفة وحدَها (D-443م)"
    if item is None:
        return f"بطاقةٌ غيرُ موجودة في الدفتر: {card}"
    if item.get("state") not in ("ready_for_review", "in_progress"):
        return f"حالةُ البطاقة «{item.get('state')}» — يُسجَّل التفويضُ قبل الاعتماد (ready_for_review) لا بعده"
    if len(reviewed.strip()) < 20:
        return "--reviewed إلزاميّ: ما رُوجع في الفرق الفعليّ (20 حرفاً فأكثر)"
    n = min(len(head), len(head_now))
    if n < 7 or head[:n].lower() != head_now[:n].lower():
        return f"رأسُ الشجرة {head_now[:8]} ≠ الرأس المطلوب {head}: التفويضُ يرتبط بالرأس المعاين"
    if not diff_files:
        return "لا فرقَ فعليّاً يُفحص (--tree/--base): المسّ يُحدَّد من ملفّات البطاقة والفرق الفعليّ معاً"
    hits = forbidden_hits([*card_paths(item), *diff_files])
    if hits:
        return "يمسّ ما لا يُفوَّض فيُعرض على المالك: " + "؛ ".join(hits[:6])
    return None


def git_out(tree: str, *args: str) -> str:
    import subprocess  # noqa: PLC0415

    out = subprocess.run(["git", "-C", tree, *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise ValueError(f"git {' '.join(args[:2])} فشل: {out.stderr.strip()[:160]}")
    return out.stdout.strip()


def record_delegation(a) -> int:
    import ledger  # noqa: PLC0415

    item = ledger.reduce_state(ledger.load_events()).get(a.target)
    try:
        head_now = git_out(a.tree, "rev-parse", "HEAD")
        diff = git_out(a.tree, "diff", "--name-only", f"{a.base}...{head_now}").splitlines()
        quote, _ = standing_quote(FILE.read_text(encoding="utf-8") if FILE.exists() else "")
    except ValueError as exc:
        sys.exit(f"✘ {exc}")
    problem = delegation_problem(item, a.target, a.head, diff, head_now, a.reviewed, a.session)
    if problem:
        sys.exit(f"✘ لا تفويضَ: {problem}")
    question = f"اعتماد رأس {a.head} بتفويض D-443م بعد مراجعة الفرق: {a.reviewed.strip()} (ملفّات الفرق: {len(diff)})"
    with FILE.open("a", encoding="utf-8") as f:
        f.write(row(a.session, a.target, quote, question, head=a.head, source="مباشر"))
    print("سُجّل تفويضٌ دائم (D-443م) في owner_confirmations.md — approval_check يعرضه تفويضاً لا قولاً مباشراً")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", required=True, help="رقمُ جلستك (مثل 0405)")
    ap.add_argument("--target", required=True, help="رمزُ البطاقة أو رقمُ الطلب (مثل W-20261002-013 أو #772)")
    ap.add_argument("--quote", help="نصُّ المالك الحرفيّ كما كتبه (إلزاميّ إلا مع --delegation: النصُّ يؤخذ من سطريه المسجَّلين)")
    ap.add_argument("--delegation", action="store_true", help="تفويضُ D-443م الدائم لرأسٍ بلا واجهةٍ ولا صلاحيّاتٍ ولا هجراتٍ ولا أمنٍ ولا ملفّاتٍ حاكمة")
    ap.add_argument("--tree", help="مع --delegation: شجرةُ الفرع لحساب الفرق الفعليّ")
    ap.add_argument("--base", default="origin/main", help="مع --delegation: أساسُ الفرق")
    ap.add_argument("--reviewed", default="", help="مع --delegation: ما رُوجع في الفرق")
    ap.add_argument("--question", default="")
    ap.add_argument("--head", default="", help="رأسُ الإيداع الذي عاينه المالك (sha8) — يربط الاعتمادَ به (v2.23)")
    ap.add_argument("--window-order", action="store_true", help="أمرُ المالك بدمجٍ/نشرٍ وسط الدوام: يُسجَّل بلا --head وقتَ كلامه (يشترطه release_follow.sh)")
    ap.add_argument("--source", help="«مباشر» أو «نقلاً عن جلسة <رقم>» — مصدرُ الإفادة (إلزاميّ إلا مع --delegation)")
    a = ap.parse_args()
    if a.delegation:
        if not (a.tree and re.fullmatch(r"[0-9a-f]{7,40}", a.head or "")):
            sys.exit("--delegation يلزمه --tree و--head")
        if a.quote or a.source:
            sys.exit("--delegation لا يقبل --quote ولا --source: النصُّ من سطريّ المالك المسجَّلين")
        return record_delegation(a)
    if not a.quote or not a.source:
        sys.exit("--quote و--source إلزاميّان")
    source = normalize_source(a.source)
    if source is None:
        sys.exit("--source إلزاميّ: «مباشر» (سمعتُ المالكَ في محادثتي) أو «نقلاً عن جلسة <رقم>»")
    if len(a.quote.strip()) < 2:
        sys.exit("النصُّ الحرفيُّ للمالك مطلوب (لا وصفٌ ولا فراغ)")
    if not a.window_order and not re.fullmatch(r"[0-9a-f]{7,40}", a.head or ""):
        sys.exit("--head إلزاميّ: رأسُ الإيداع المعاين (git rev-parse --short=8 <الفرع>)")
    if not SESSION.match(a.session):
        sys.exit("--session رقمُ جلسةٍ من أربع خانات (مثل 0405)")
    with FILE.open("a", encoding="utf-8") as f:
        f.write(row(a.session, a.target, a.quote, a.question, head=a.head, source=source, window=a.window_order))
    print("سُجّل في owner_confirmations.md — يتحقّق منه approval_check.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
