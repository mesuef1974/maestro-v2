#!/usr/bin/env python3
"""هويّةُ الجلسة عند كلّ بدء أو مسح (SessionStart hook) — قرارُ المالك 2026-10-04 (الحزمة أ).

يقرأ مجلّد العمل (cwd) من مدخل الـhook (JSON على stdin) ويطابق اسمَ شجرة العمل بـ`projects/schoolos/session_names.json`
فيطبع للجلسة: اسمَها ورقمَها وبطاقةَ دورها وأوّل ما تفعله. فلا تفقد الجلسةُ هويّتَها بعد المسح (واقعةُ 2026-10-04:
0301 رفضت العملَ، و0103 و0201 عرّفتا نفسيهما 04SS). لا يطبع شيئاً خارج أشجار المنصّة.

    python session_identity.py            # يقرأ stdin (مدخل الـhook)
    python session_identity.py --cwd <مسار>   # للاختبار اليدويّ
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ROOT / "projects" / "schoolos" / "session_names.json"
PLATFORM = "shschool_mvp"
#: جلساتُ تطبيق Claude على القرص: الهويّةُ الحيّةُ (معرّفُ الجلسة ← عنوانُها) أصدقُ من خريطة الأشجار حين تشترك جلستان في شجرة (0423 عُرّفت 0405، 2026-10-19)
NUM = re.compile(r"\s*\d{4}\b")
SESSIONS = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code-sessions"


def tree_name(cwd: str) -> str | None:
    """اسمُ شجرة العمل من المسار: .../.claude/worktrees/<الاسم>[/…]؛ وإلا None."""
    parts = Path(cwd.replace("\\", "/")).parts
    for i, p in enumerate(parts):
        if p == "worktrees" and i + 1 < len(parts) and PLATFORM in "/".join(parts):
            return parts[i + 1]
    return None


def lookup(cwd: str, names: dict[str, str]) -> str | None:
    tree = tree_name(cwd)
    return names.get(tree) if tree else None


def _norm(p: str) -> str:
    return p.replace("\\", "/").rstrip("/").lower()


def app_title(cwd: str, session_id: str = "", base: Path | None = None) -> tuple[str | None, list[str]]:
    """(العنوانُ الحيّ، المرشَّحون عند الالتباس): أوّلاً بمعرّف الجلسة (cliSessionId أو ما سبقه)، ثمّ بالشجرة إن لم تشاركها جلسةٌ حيّةٌ أخرى.

    شجرةٌ تشترك فيها جلستان حيّتان بلا معرّفٍ يميّز: (None، العناوين) فيسأل الهوك 0101 بدل أن يخمّن ويضلّل."""
    base = SESSIONS if base is None else base
    by_tree: dict[str, str] = {}
    for f in base.glob("*/*/local_*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        title = str(d.get("title", ""))
        if not NUM.match(title) or d.get("isArchived"):
            continue
        ids = {d.get("sessionId"), d.get("cliSessionId"), *(d.get("priorCliSessionIds") or [])}
        if session_id and session_id in ids:
            return title, []
        tree = _norm(str(d.get("worktreePath") or d.get("cwd") or ""))
        if tree and _norm(cwd).startswith(tree):
            by_tree[title] = tree
    if len(by_tree) == 1:
        return next(iter(by_tree)), []
    return None, sorted(by_tree)


def message(title: str | None, tree: str | None) -> str:
    if title is None:
        return ("[هويّة الجلسة] لم أجد اسمَ هذه الشجرة (" + str(tree) + ") في session_names.json — "
                "اسأل 0101 عن رقمك قبل أيّ عمل، ولا تفترض أنّك مرنة 04SS.")
    m = re.match(r"\s*(\d{4})\b", title)
    num = m.group(1) if m else "؟؟؟؟"
    flexible = num.startswith("04")
    card = "role_cards/04.md (المرنة) ثمّ ledger.py show <رمز بطاقتك>" if flexible else f"role_cards/{num}.md"
    return (f"[هويّة الجلسة] أنت «{title}» — رقمُك {num}. "
            f"اقرأ بطاقتك `C:/Users/mesue/delivery_manager_work/{card}` ثمّ شغّل "
            f"`python C:/Users/mesue/delivery_manager_work/tools/my_state.py {num}` قبل أيّ ردّ. "
            + ("" if flexible else "لا تفترض أنّك مرنة 04SS. ")
            + "إن رأيت ما يناقض هذا فاسأل 0101 ولا تُكمل.")


#: إيداع ترقية مهارة الهويّة البصريّة (#897) على main؛ غيابُه من سلف الشجرة = مهارةٌ قديمة
SKILL_UPGRADE = "130d8a56f"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd")
    args = ap.parse_args()
    cwd = args.cwd
    session_id = ""
    if not cwd:
        try:
            hook = json.loads(sys.stdin.read() or "{}")
            cwd, session_id = hook.get("cwd", ""), str(hook.get("session_id", ""))
        except Exception:  # noqa: BLE001 — الـhook لا يسقط الجلسة أبداً
            cwd = ""
    if not cwd or PLATFORM not in cwd.replace("\\", "/"):
        return 0
    tree = tree_name(cwd)
    if tree is None:
        return 0
    try:
        names = json.loads(NAMES.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        names = {}
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        live, candidates = app_title(cwd, session_id)
    except Exception:  # noqa: BLE001
        live, candidates = None, []
    if live is None and len(candidates) > 1:
        print("[هويّة الجلسة] تشترك في هذه الشجرة (" + tree + ") جلساتٌ حيّةٌ: " + "؛ ".join(candidates)
              + " — لا أعرف أيَّها أنت: اسأل 0101 عن رقمك قبل أيّ عمل، ولا تفترض.")
    else:
        print(message(live or lookup(cwd, names), tree))
    try:  # دليلُ عناوين الجلسات: الإرسالُ بالمعرّف لا بالاسم (الاسمُ لا يوقظ خاملةً) — لا يُسقط الـhook أبداً
        import session_directory

        d = session_directory.entries()
        print("[قاعدة المالك] المالكُ في الاعتماد والمعاينة فقط: لا تسأله «هل أرفع/أكلّف/أبلغ؟» ولا تطلب منه إذنًا بالتوجيه بين الجلسات؛ أرسل إلى 0101 بالمعرّف (هو من يوجّه المنفّذين ولا تتجاوزه إلى جلسةٍ منفّذة)، أو إلى الجلسة صاحبة السلسلة المقرَّرة في الفلو (0501←0601←0701)، ثمّ أبلغ المالكَ بما تمّ. ما عدا ذلك قرارُه وحده: دمجٌ وقراراتٌ تغيّر قاعدةً.")
        print("[متابعة الإحالة] كلُّ إحالةٍ تُتابَع بقراءة نتيجةِ الإرسال: `delivered` = مبلّغة (بلغت)؛ `queued` = في الطابور فلا تُعاد، وتحقّق بعد دقيقتين من list_events ثمّ أعِدها مرةً واحدةً إن لم تبدأ؛ `undelivered` = لم تبلغ فأعِد الإرسال بعد دقيقة. أبلغ الحالةَ بإحدى ثلاث: (بلغت / في الطابور / لم تبلغ)، ولا تسأل المالكَ عن إعادة الإرسال. وبعد 30 دقيقةً تحقّق من git/الدفتر أنّ عملاً ظهر (فرعٌ أو إيداعٌ أو حالةُ بطاقة)، وإلا فأعِد الإحالةَ وأبلغ 0101.")
        print("[عناوين الجلسات] أرسل بالمعرّف `to: local_<uuid>` لا بالاسم، ولا تُمرِّر رسالتك عبر المالك (دورُه الاعتماد والمعاينة فقط). "
              "المعرّفُ يتبدّل عند إعادة التشغيل فتحقّق قبل الإرسال: `python C:/Users/mesue/delivery_manager_work/tools/session_directory.py <الرقم>`. "
              + "؛ ".join(f"{k}={v['id']}" for k, v in d.items()))
    except Exception:  # noqa: BLE001
        pass
    try:  # تحذيرٌ فقط (لا حجب): شجرةٌ بلا ترقية مهارة الهويّة البصريّة (#897) تعمل بنسخةٍ قديمةٍ منها
        import subprocess

        gate = subprocess.run(["git", "merge-base", "--is-ancestor", SKILL_UPGRADE, "HEAD"], cwd=cwd, capture_output=True, timeout=10)
        if gate.returncode == 1:
            print("[تحذير: مهارة الهويّة قديمة] شجرتك لا تحتوي ترقية web-design-mastery (#897: قائمة المراجعة 95 والتحقّق البصريّ بالدور 55 وخانتا عقد جاهز). "
                  "قبل أيّ عمل واجهة (قالب/CSS/JS) ادمج origin/main في شجرتك (أداة sync_with_base_branch أو git fetch ثمّ merge) ثمّ اقرأ .claude/skills/web-design-mastery/references/95-checklist.md؛ ولا تُعلن «جاهزٌ للمعاينة» لعمل واجهة دون خانتَي «الأجهزة المقيسة» و«نتيجة المسبار».")
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
