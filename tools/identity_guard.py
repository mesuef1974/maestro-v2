#!/usr/bin/env python3
"""حارسُ إلزام الهويّة البصريّة (PreToolUse hook) — بطاقة W-20261009-008، أمر المالك 2026-10-09.

يمنع (أو يحذّر) من تعديل واجهة المنصّة — `templates/` و`static/css/` و`static/js/` — في شجرةٍ لا تحتوي ترقيةَ
مهارة التصميم (#897، الإيداع 130d8a56f)، أو لم تُقرأ فيها قائمةُ المراجعة 95 (إيصالٌ من identity_ack.py).

ما يُفحص: أدواتُ Edit وWrite وMultiEdit وNotebookEdit على ملفٍّ في مساراتِ الواجهة، وBash لأوامر `git add` و`git commit`
حين تمسّ واجهةً. وما عداها يمرّ بلا أثر (ولا يُحجب شيءٌ خارج شجرات المنصّة ولا ملفٌّ غير واجهة).

الوضعان (يقرّر المالكُ الانتقالَ بينهما — بدءاً بالتحذير لا الحجب):
    warn  (الافتراضيّ): يمرّ الإجراءُ ويُحقن في سياق الجلسة تحذيرٌ عربيّ.
    block: يُمنع الإجراءُ برسالةٍ عربيّة تقول ماذا تفعل.
يُحدَّد الوضعُ بمتغيّر البيئة IDENTITY_GUARD_MODE، وإلا بالملفّ `identity_guard.mode` في جذر delivery_manager_work.

لا يُسقط الجلسةَ أبداً: أيُّ خللٍ (غيابُ git، مسارٌ غريب، JSON فاسد) = سماحٌ مع تحذير. والشجرةُ المرقّاةُ بإيصالٍ
مطابقٍ لا تُمنع. زمنُه أقلّ من نصف ثانية (3 استدعاءات git صغيرة على الأكثر).

    echo '{"tool_name":"Edit","tool_input":{"file_path":"…/templates/x.html"},"cwd":"…"}' | python identity_guard.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODE_FILE = ROOT / "identity_guard.mode"
PLATFORM = "shschool_mvp"
#: إيداع ترقية مهارة الهويّة (#897) على main؛ غيابُه من سلف الشجرة = مهارةٌ قديمة
SKILL_UPGRADE = os.environ.get("IDENTITY_SKILL_COMMIT", "130d8a56f")
CHECKLIST = ".claude/skills/web-design-mastery/references/95-checklist.md"
ACK_NAME = "identity_ack.json"
UI_PREFIXES = ("templates/", "static/css/", "static/js/")
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
GIT_WRITE = re.compile(r"\bgit\s+(?:-\S+\s+\S+\s+)*(add|commit)\b")
GIT_TIMEOUT = 5


def mode() -> str:
    env = os.environ.get("IDENTITY_GUARD_MODE", "").strip().lower()
    if env in ("warn", "block"):
        return env
    try:
        text = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        return text if text in ("warn", "block") else "warn"
    except OSError:
        return "warn"


def git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=GIT_TIMEOUT,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def existing_dir(path: str) -> str | None:
    """أقربُ مجلّدٍ قائمٍ للمسار (الملفُّ الجديد في Write لا مجلّدَ له بعد)."""
    p = Path(path)
    for cand in [p, *p.parents]:
        if cand.is_dir():
            return str(cand)
    return None


def toplevel(cwd: str) -> Path | None:
    r = git(cwd, "rev-parse", "--show-toplevel")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    top = Path(r.stdout.strip())
    return top if PLATFORM in str(top).replace("\\", "/") else None


def is_ui(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("./")
    return rel.startswith(UI_PREFIXES)


def rel_to(top: Path, path: str) -> str | None:
    try:
        return Path(os.path.normcase(os.path.abspath(path))).relative_to(os.path.normcase(str(top))).as_posix()
    except ValueError:
        return None


def checklist_sha(top: Path) -> str | None:
    f = top / CHECKLIST
    try:
        return hashlib.sha256(f.read_bytes()).hexdigest()
    except OSError:
        return None


def ack_path(top: Path) -> Path | None:
    r = git(str(top), "rev-parse", "--absolute-git-dir")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return Path(r.stdout.strip()) / ACK_NAME


def ack_valid(top: Path) -> bool:
    sha, ap = checklist_sha(top), ack_path(top)
    if not sha or not ap:
        return False
    try:
        return json.loads(ap.read_text(encoding="utf-8")).get("sha256") == sha
    except (OSError, ValueError):
        return False


def stale(top: Path) -> bool | None:
    """True = الترقيةُ ليست سلفاً (مهارةٌ قديمة)، False = مرقّاة، None = لا يُعرف (يُسمح بتحذير).

    دمجٌ جارٍ (MERGE_HEAD) يجلب الترقيةَ نفسَها لا يُعدّ قديماً: الإيداعُ الذي يُحجَب هو ما يرقّي الشجرة (واقعةُ 0501، 2026-10-27:
    دمجُ origin/main حُجب لأنّ HEAD قبل الدمج أقدمُ من 130d8a56f، فبقي الدمجُ معلّقاً بلا مخرجٍ إلا --no-verify؛ بإذن المالك)."""
    for ref in ("HEAD", "MERGE_HEAD"):
        rc = git(str(top), "merge-base", "--is-ancestor", SKILL_UPGRADE, ref).returncode
        if rc == 0:
            return False
        if ref == "HEAD" and rc != 1:
            return None
    return True


def staged_or_target_ui(command: str, cwd: str, top: Path) -> bool:
    """هل يمسّ `git add|commit` ملفّاً من الواجهة؟"""
    if re.search(r"\bgit\b.*\bcommit\b", command):
        names = git(str(top), "diff", "--cached", "--name-only").stdout.splitlines()
        if re.search(r"\bcommit\b.*(\s-a\b|\s--all\b|\s-[a-z]*a[a-z]*\s)", command):
            names += git(str(top), "diff", "--name-only").stdout.splitlines()
        return any(is_ui(n) for n in names)
    if re.search(r"\badd\b.*(\s-A\b|\s--all\b|\s\.(\s|$)|\s-u\b)", command):
        names = [ln[3:] for ln in git(str(top), "status", "--porcelain").stdout.splitlines()]
        return any(is_ui(n) for n in names)
    return bool(re.search(r"(?:^|[\s\"'/\\])(templates|static[/\\](?:css|js))[/\\]", command))


MSG_STALE = ("[حارس الهويّة] شجرتك لا تحتوي ترقيةَ مهارة التصميم (#897، الإيداع {c}) فلا يجوز تعديل الواجهة فيها. "
             "ادمج main أوّلاً (أداة sync_with_base_branch أو `git fetch origin main` ثمّ `git merge origin/main`)، ثمّ شغّل "
             "`python C:/Users/mesue/delivery_manager_work/tools/identity_ack.py` لتقرأ قائمةَ المراجعة 95 وتسجّل الإيصال، ثمّ أعد الإجراء.")
MSG_NO_ACK = ("[حارس الهويّة] لم تُقرأ قائمةُ المراجعة 95 في هذه الشجرة (أو تغيّرت بعد قراءتك). شغّل "
              "`python C:/Users/mesue/delivery_manager_work/tools/identity_ack.py` (يطبعها ويسجّل إيصالاً ببصمتها) ثمّ أعد الإجراء.")
MSG_UNKNOWN = ("[حارس الهويّة] تعذّر التحقّق من ترقية مهارة التصميم (git غائب أو الشجرة غير معروفة)؛ سُمح بالإجراء. "
               "تأكّد بنفسك أنّ شجرتك تحوي 130d8a56f وأنّك قرأت references/95-checklist.md.")


def decide(payload: dict) -> tuple[str, str] | None:
    """(الإجراء 'deny'|'warn', الرسالة) أو None للسماح الصامت."""
    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()
    if tool in FILE_TOOLS:
        target = inp.get("file_path") or inp.get("notebook_path") or ""
        if not target:
            return None
        base = existing_dir(str(Path(target).parent if not Path(target).is_dir() else target)) or cwd
        top = toplevel(base)
        if top is None:
            return None
        rel = rel_to(top, target)
        if rel is None or not is_ui(rel):
            return None
    elif tool == "Bash":
        command = inp.get("command", "")
        if not GIT_WRITE.search(command):
            return None
        top = toplevel(cwd)
        if top is None or not staged_or_target_ui(command, cwd, top):
            return None
    else:
        return None
    try:
        st = stale(top)
    except (OSError, subprocess.SubprocessError):
        st = None
    if st is None:
        return "warn", MSG_UNKNOWN
    if st:
        return "deny", MSG_STALE.format(c=SKILL_UPGRADE)
    if not ack_valid(top):
        return "deny", MSG_NO_ACK
    return None


def emit(action: str, message: str, current_mode: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    event = {"hookEventName": "PreToolUse"}
    if action == "deny" and current_mode == "block":
        event.update(permissionDecision="deny", permissionDecisionReason=message)
    else:
        suffix = "" if action == "warn" and current_mode == "warn" and "سُمح" in message else (
            " (وضعُ التحذير: سُمح بالإجراء الآن، ويصير منعاً بقرار المالك.)" if current_mode == "warn" else "")
        event["additionalContext"] = message + suffix
    print(json.dumps({"hookSpecificOutput": event}, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = decide(payload)
    except Exception:  # noqa: BLE001 — الحارس لا يُسقط جلسةً أبداً
        return 0
    if result:
        emit(*result, mode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
