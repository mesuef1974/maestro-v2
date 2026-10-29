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
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ROOT / "projects" / "schoolos" / "session_names.json"
PLATFORM = "shschool_mvp"
ROOT_NAME = "delivery_manager_work"
#: جلساتُ تطبيق Claude على القرص: الهويّةُ الحيّةُ (معرّفُ الجلسة ← عنوانُها) أصدقُ من خريطة الأشجار حين تشترك جلستان في شجرة (0423 عُرّفت 0405، 2026-10-19)
NUM = re.compile(r"\s*\d{4}(?:-[ء-ي])?(?![\w-])")
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


def _newest_first(base: Path) -> list[Path]:
    """ملفّاتُ الجلسات من الأحدث تعديلاً إلى الأقدم (الجلسةُ الحيّةُ تُوجَد في الأوائل)."""
    out = []
    for f in base.glob("*/*/local_*.json"):
        try:
            out.append((f.stat().st_mtime, f))
        except OSError:
            continue
    out.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in out]


#: التطبيقُ يكتب cliSessionId الجديد في ملفّ الجلسة بعد SessionStart لا قبله (مقيس 2026-10-26 بعد مسح 0101 الذاتيّ، W-20261026-006)
#: W-20261028-011: 3 ثوانٍ لم تكفِ (0101 عُرّفت 0104 يوم 10-28)؛ نصبر حتى 15 ثانيةً ثمّ نقول «لا أعرف» ولا نخمّن
ID_WAIT_S = 15.0
ID_POLL_S = 0.5
def app_title(cwd: str, session_id: str = "", base: Path | None = None, wait_s: float = ID_WAIT_S,
              sleep=time.sleep) -> tuple[str | None, list[str]]:
    """(العنوانُ الحيّ، المرشَّحون) كما في `_resolve`؛ مع معرّفِ جلسةٍ لم يُطابَق بعدُ نعيد قراءةَ الملفّات حتى `wait_s` ثانيةً
    قبل السقوط إلى الشجرة (التطبيقُ يكتب cliSessionId بعد الـhook)."""
    waited = 0.0
    while True:
        title, candidates, by_id = _resolve(cwd, session_id, base)
        if by_id or not session_id or waited >= wait_s:
            break
        sleep(ID_POLL_S)
        waited += ID_POLL_S
    return title, candidates


def _in_root(cwd: str) -> bool:
    """جذرُ المجلّد المشترك (أو شجرةٌ داخله غير المنصّة): جلساتُه تُعرَف بالمعرّف لا بالشجرة."""
    return bool(cwd) and ROOT_NAME in cwd.replace("\\", "/").lower() and PLATFORM not in cwd.replace("\\", "/")


def _resolve(cwd: str, session_id: str, base: Path | None) -> tuple[str | None, list[str], bool]:
    """(العنوانُ الحيّ، المرشَّحون عند الالتباس): أوّلاً بمعرّف الجلسة (cliSessionId أو ما سبقه)، ثمّ بالشجرة إن لم تشاركها جلسةٌ حيّةٌ أخرى.

    شجرةٌ تشترك فيها جلستان حيّتان بلا معرّفٍ يميّز: (None، العناوين) فيسأل الهوك 0101 بدل أن يخمّن ويضلّل."""
    base = SESSIONS if base is None else base
    by_tree: dict[str, str] = {}
    files = _newest_first(base)
    if session_id:  # مسارٌ سريع: الجلسةُ الحيّةُ أحدثُ الملفّات؛ لا نحلّل إلا ما يحوي معرّفها نصّاً
        prior_hit = None  # تدرّج الأولويّة: sessionId/cliSessionId يغلبان priorCliSessionIds، والأحدثُ تعديلاً داخل كلٍّ
        for f in files:
            try:
                raw = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if session_id not in raw:
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            title = str(d.get("title", ""))
            if not NUM.match(title) or d.get("isArchived"):
                continue
            if session_id in (d.get("sessionId"), d.get("cliSessionId")):
                return title, [], True
            if prior_hit is None and session_id in (d.get("priorCliSessionIds") or []):
                prior_hit = title
        if prior_hit is not None:
            return prior_hit, [], True
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        title = str(d.get("title", ""))
        if not NUM.match(title) or d.get("isArchived"):
            continue
        ids = {d.get("sessionId"), d.get("cliSessionId"), *(d.get("priorCliSessionIds") or [])}
        if session_id and session_id in ids:
            return title, [], True
        tree = _norm(str(d.get("worktreePath") or d.get("cwd") or ""))
        if tree and _norm(cwd).startswith(tree):
            by_tree[title] = tree
    if len(by_tree) > 1:  # الأخصّ يغلب: شجرةٌ داخل مجلّد جلسةٍ أخرى لا تلتبس بها
        longest = max(len(t) for t in by_tree.values())
        by_tree = {k: v for k, v in by_tree.items() if len(v) == longest}
    if len(by_tree) == 1 and not (session_id and _in_root(cwd)):  # W-20261028-024: معرّفٌ غير مطابق في الجذر لا يُحسب رقماً بالشجرة
        return next(iter(by_tree)), [], False
    return None, sorted(by_tree), False


def _num_of(title: str | None) -> str | None:
    m = re.match(r"\s*(\d{4})\b", title or "")
    return m.group(1) if m else None


def ambiguous_message(where: str, candidates: list[str]) -> str:
    """الالتباسُ بين جلستين: لا تخمين (لا بآخر تركيزٍ ولا بغيره)؛ تتحقّق الجلسةُ من عنوانها الحيّ قبل أيّ كتابةٍ باسم رقم (W-20261028-011)."""
    return (f"[هويّة الجلسة] تشترك في {where} جلساتٌ حيّةٌ: " + "؛ ".join(candidates)
            + " — لا أعرف أيَّها أنت. قبل أيّ كتابةٍ باسم رقمٍ (حالة أو ملاحظة بطاقة أو أمر أو رسالة صندوق أو عدّاد) "
            "شغّل أداة get_session بالمعرّف self (mcp__ccd_session_mgmt__get_session) فيعيد عنوانَك الحيّ وفيه رقمُك؛ "
            "وإن تعذّر فاسأل 0101 ولا تفترض.")


def message(title: str | None, tree: str | None, sid: str = "") -> str:
    if title is None:
        return ("[هويّة الجلسة] لم أجد اسمَ هذه الشجرة (" + str(tree) + ") في session_names.json — "
                "اسأل 0101 عن رقمك قبل أيّ عمل، ولا تفترض أنّك مرنة 04SS.")
    m = re.match(r"\s*(\d{4}(?:-[ء-ي])?)(?![\w-])", title)
    num = m.group(1) if m else "؟؟؟؟"
    if "-" in num:  # جلسةٌ فرعيّة (0101-أ): بلا بطاقة دورٍ ولا my_state؛ ملفُّ حالتها المعياريّ هو مرجعُها
        return (f"[هويّة الجلسة] أنت «{title}» — رقمُك {num} (فرعيّة، لست {num.split('-')[0]}). "
                f"ملفُّ حالتك المعياريّ `C:/Users/mesue/delivery_manager_work/handover_notes/state_{num}.json` "
                f"وتركيزك `handover_notes/focus_{num}.json`؛ اقرأهما قبل أيّ ردّ. "
                "إن رأيت ما يناقض هذا فاسأل 0101 ولا تُكمل.")
    flexible = num.startswith("04")
    own = (ROOT / "role_cards" / f"{num}.md").exists()
    card = (f"role_cards/{num}.md (بطاقتك) ثمّ role_cards/04.md (المشتركة) ثمّ ledger.py show <رمز بطاقتك>" if own
            else "role_cards/04.md (المرنة) ثمّ ledger.py show <رمز بطاقتك>") if flexible else f"role_cards/{num}.md"
    return (f"[هويّة الجلسة] أنت «{title}» — رقمُك {num}. "
            f"اقرأ بطاقتك `C:/Users/mesue/delivery_manager_work/{card}` ثمّ شغّل "
            f"`python C:/Users/mesue/delivery_manager_work/tools/my_state.py {num}` قبل أيّ ردّ (اكتب وصفَ أداة Bash بالعربيّة، مثل «قراءة حالة جلستي»، وإلا رفضه lang_guard). "
            + ("" if flexible else "لا تفترض أنّك مرنة 04SS. ")
            + "إن رأيت ما يناقض هذا فاسأل 0101 ولا تُكمل.")


#: إيداع ترقية مهارة الهويّة البصريّة (#897) على main؛ غيابُه من سلف الشجرة = مهارةٌ قديمة
SKILL_UPGRADE = "130d8a56f"


def directory_lines(num: str | None = None) -> list[str]:
    """سطورُ «قاعدة المالك» و«متابعة الإحالة» و«عناوين الجلسات» — لكلّ جلسةٍ ثابتةٍ أيّاً كان مجلّدُها؛ فارغةٌ عند أيّ عطل (لا تُسقط الـhook)."""
    out: list[str] = []
    try:
        import session_directory

        d = {k: v for k, v in session_directory.entries().items() if k in (num, "0101")}  # معرّفُ الجلسة نفسها و0101 فقط؛ لغيرهما session_directory.py (W-20261026-002)
        out.append("[المراسلة بين الجلسات] ما تريده من المالك يُرفع إلى 0101 وهي وحدَها تطرحه بأداة ask (D-495م)؛ قاعدةُ المالك ومتابعةُ الإحالة وعناوينُ الجلسات: `C:/Users/mesue/delivery_manager_work/role_cards/PROCEDURES.md` قسم «المراسلة بين الجلسات» (اقرأه قبل أول إرسال). "
                   "المعرّفاتُ الحيّة (تتبدّل عند إعادة التشغيل؛ للتحقّق `python C:/Users/mesue/delivery_manager_work/tools/session_directory.py <الرقم>`): "
                   + "؛ ".join(f"{k}={v['id']}" for k, v in d.items()))
    except Exception:  # noqa: BLE001
        return []
    return out


#: بدءٌ ملتبسٌ (المعرّفُ لم يُكتب بعدُ): علامةٌ تُحذف عند أوّل رسالةٍ تنجح فيها إعادةُ التعرّف، وتُهمَل بعد ساعة (W-20261026-017)
PENDING_TTL_S = 3600


def _pending_path(session_id: str, root: Path | None = None) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:60]
    return (root or ROOT) / "handover_notes" / f"identity_pending_{safe}.json"


def mark_pending(session_id: str, cwd: str, root: Path | None = None, now: datetime | None = None) -> None:
    """يسجّل بدءاً ملتبساً لتُعاد الهويّةُ عند أوّل رسالة (UserPromptSubmit). لا يرفع استثناءً ولا يُبطئ البدء."""
    if not session_id:
        return
    try:
        p = _pending_path(session_id, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"session_id": session_id, "cwd": cwd, "at": (now or datetime.now()).isoformat(timespec="seconds")}, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass


def prompt_identity(raw: str, root: Path | None = None, resolver=None, now: datetime | None = None) -> list[str]:
    """خطّاف UserPromptSubmit: إن كانت لهذه الجلسة علامةُ بدءٍ ملتبس وصار عنوانُها الحيُّ معروفاً (cliSessionId كُتب) فتُحقن سطورُ
    الهويّة الصحيحة مرّةً واحدةً وتُحذف العلامة؛ وإلا لا شيء (فلا إبطاءَ للرسائل العاديّة: فحصُ وجود ملفٍّ واحد)."""
    try:
        hook = json.loads(raw or "{}")
        sid, cwd = str(hook.get("session_id", "")), str(hook.get("cwd", ""))
        if not sid:
            return []
        p = _pending_path(sid, root)
        if not p.is_file():
            return []
        mark = json.loads(p.read_text(encoding="utf-8"))
        if ((now or datetime.now()) - datetime.fromisoformat(mark["at"])).total_seconds() > PENDING_TTL_S:
            p.unlink(missing_ok=True)
            return []
        where = cwd or mark.get("cwd", "")
        live, _ = resolver(where, sid) if resolver else app_title(where, sid, wait_s=0)
        if live is None:
            return []
        p.unlink(missing_ok=True)
        return ["[تصحيح هويّة الجلسة — كان بدؤك ملتبساً]", message(live, None), *directory_lines(_num_of(live))]
    except Exception:  # noqa: BLE001 — الخطّاف لا يُسقط الجلسة
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cwd")
    ap.add_argument("--prompt", action="store_true", help="خطّاف UserPromptSubmit: يعيد التعرّفَ بعد بدءٍ ملتبس ويحقن الهويّة مرّةً واحدة")
    args = ap.parse_args()
    if args.prompt:
        sys.stdout.reconfigure(encoding="utf-8")
        for line in prompt_identity(sys.stdin.read()):
            print(line)
        return 0
    cwd = args.cwd
    session_id = ""
    if not cwd:
        try:
            hook = json.loads(sys.stdin.read() or "{}")
            cwd, session_id = hook.get("cwd", ""), str(hook.get("session_id", ""))
        except Exception:  # noqa: BLE001 — الـhook لا يسقط الجلسة أبداً
            cwd = ""
    if cwd and ROOT_NAME in cwd.replace("\\", "/").lower() and PLATFORM not in cwd.replace("\\", "/"):
        # جلساتُ مجلّد delivery_manager_work (0101/0104/0108/0109/0110): لا شجرةَ منصّةٍ لها فالهويّةُ من عنوان الجلسة الحيّ بمعرّفها (واقعةُ 2026-10-24: صمتُ الـhook بعد الكلير)
        sys.stdout.reconfigure(encoding="utf-8")
        try:
            live, candidates = app_title(cwd, session_id)
        except Exception:  # noqa: BLE001
            live, candidates = None, []
        if live is None:
            mark_pending(session_id, cwd)
        if live is not None:
            print(message(live, None, session_id))
        elif candidates:
            print(ambiguous_message("هذا المجلّد", candidates))
        else:
            return 0
        for line in directory_lines(_num_of(live)):
            print(line)
        return 0
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
        mark_pending(session_id, cwd)
        print(ambiguous_message(f"هذه الشجرة ({tree})", candidates))
    else:
        print(message(live or lookup(cwd, names), tree, session_id))
    for line in directory_lines(_num_of(live or lookup(cwd, names))):
        print(line)
    try:  # تحذيرٌ فقط (لا حجب): شجرةٌ بلا ترقية مهارة الهويّة البصريّة (#897) تعمل بنسخةٍ قديمةٍ منها
        import subprocess

        gate = subprocess.run(["git", "merge-base", "--is-ancestor", SKILL_UPGRADE, "HEAD"], cwd=cwd, capture_output=True, timeout=10,  # noqa: S603,S607 — أمرٌ ثابتٌ بلا مدخلٍ خارجيّ
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if gate.returncode == 1:
            print("[تحذير: مهارة الهويّة قديمة] شجرتك لا تحتوي ترقية web-design-mastery (#897: قائمة المراجعة 95 والتحقّق البصريّ بالدور 55 وخانتا عقد جاهز). "
                  "قبل أيّ عمل واجهة (قالب/CSS/JS) ادمج origin/main في شجرتك (أداة sync_with_base_branch أو git fetch ثمّ merge) ثمّ اقرأ .claude/skills/web-design-mastery/references/95-checklist.md؛ ولا تُعلن «جاهزٌ للمعاينة» لعمل واجهة دون خانتَي «الأجهزة المقيسة» و«نتيجة المسبار».")
    except Exception:  # noqa: BLE001,S110 — التحذيرُ اختياريّ ولا يُسقط الهويّة
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
