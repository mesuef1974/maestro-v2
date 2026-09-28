#!/usr/bin/env python3
"""PreToolUse (Bash|PowerShell): يمنع الجلسةَ من دفعٍ أو دمجٍ أو تغييرٍ في أيّ مستودعٍ إلّا مستودعَ المايسترو نفسه.

خلفيّةُ الحاجة: مسوّدةٌ سابقةٌ استعملت permissions.deny بنمط «Bash(git push:*)» ظانّةً أنّ الحظر يخصّ
شجرةَ المنصّة D:/shschool_mvp وحدها. لكنّ permissions.deny يطابق نصَّ استدعاء الأداة بلا وعيٍ بالمجلّد
إطلاقاً — فمنع الدفعَ والدمج في مستودع المايسترو الخاصّ نفسِه أيضاً، وتوقّف عملُ 0101 فوراً (23:03..23:05).

هذا الخطّافُ بديلٌ واعٍ بالمجلّد: **يسمح بأفعال git المؤثّرة (push/commit/merge/...) فقط حين يكون
مجلّدُ الجلسة الحاليّ (الذي يرويه Claude Code نفسُه في الحمولة، لا نصٌّ يُفسَّر) داخل مستودع المايسترو
MAESTRO_REPO أو أيّ مسارٍ مُذكَرٍ صراحةً في SAFE_DIRS، ويمنعه في كلّ ما عدا ذلك — بما فيه شجرةُ المنصّة
وأيُّ مجلّدٍ آخرَ غيرَ معروف (فشلٌ مغلَق، لا قائمةَ حظرٍ لشجرة المنصّة وحدَها).

**حدٌّ معلَنٌ عمداً (فرقٌ عن guard_git.py الأكمل)**: يقرأ حقلَ cwd من حمولة الخطّاف مباشرةً ولا يحلّل
`cd X && ...` ولا `git -C <مسار>` **داخل النصّ نفسِه** (تلك تُنفَّذ من مجلّدٍ آخرَ ضمن الأمر الواحد).
مبرّرُ هذا التبسيط: أمرٌ يبدأ فعلاً من مجلّد الجلسة (وهذا الغالبُ في الاستعمال العاديّ) يُضبَط صحيحاً؛
وتحويلُ الوجهة صراحةً بـ`-C` أو `cd` داخل السطر فعلٌ متعمَّدٌ لا خطأٌ عرَضيّ كما وقع اليوم — فخطرُه أقلّ.
من أراد تغطيةً كاملةً بمستوى guard_git.py (يفكّ eval وbash -c والمستعارات) فذلك عملٌ منفصلٌ يستحقّ
المراجعةَ نفسَها التي أخذها (1060 سطراً، REP-19)، لا يُرتجَل في مسوّدةٍ واحدة.

    echo '{"tool_name":"Bash","tool_input":{"command":"git push"},"cwd":"C:/Users/mesue/delivery_manager_work"}' | python maestro_git_scope.py
"""
from __future__ import annotations

import json
import re
import sys

MAESTRO_REPO = "c:/users/mesue/delivery_manager_work"
# مساراتٌ إضافيّةٌ مسموحٌ فيها بالدفع/الدمج (فارغةٌ افتراضاً؛ أضِف صراحةً لا تُخمَّن)
SAFE_DIRS: tuple[str, ...] = ()

# كلُّ نمطٍ: (اسمُ الأداة الجذر، الفعلُ الفرعيّ أو None لمطابقة أيّ شيء بعد الجذر)
DENIED = [
    ("git", "push"), ("git", "commit"), ("git", "merge"), ("git", "rebase"),
    ("git", "reset"), ("git", "checkout"), ("git", "switch"), ("git", "stash"), ("git", "add"),
    ("gh", "pr merge"), ("gh", "pr create"), ("gh", "pr close"), ("gh", "pr edit"), ("gh", "pr review"),
    ("gh", "api -X"), ("gh", "api --method"),
    ("railway", None),
    ("docker", "compose up"), ("docker", "compose down"),
    ("bash", "scripts/preview.sh up"), ("bash", "scripts/preview.sh down"),
]
SPLIT = re.compile(r"&&|\|\||;|\n|\|(?!\|)")


def norm(path: str | None) -> str | None:
    """تطبيعٌ بسيطٌ: شرطاتٌ أماميّة وحروفٌ صغيرة، بلا فكّ متغيّراتٍ أو ~ (غيرُ معلومٍ يبقى None)."""
    if not path or any(ch in path for ch in "$`~*"):
        return None
    return path.replace("\\", "/").rstrip("/").lower()


def is_safe_cwd(cwd: str | None) -> bool:
    n = norm(cwd)
    if n is None:
        return False  # مجلّدٌ غيرُ معلوم: فشلٌ مغلَق
    if n == MAESTRO_REPO or n.startswith(MAESTRO_REPO + "/"):
        return True
    return any(n == norm(s) or n.startswith(f"{norm(s)}/") for s in SAFE_DIRS)


def denied_verb(simple_cmd: str) -> str | None:
    """يُرجع وصفَ أوّل فعلٍ محظورٍ يبدأ به الأمرُ البسيط بعد تجاهل غلافٍ سطحيّ (env/sudo)، أو None."""
    words = simple_cmd.strip().split()
    while words and (words[0] in ("env", "sudo", "command") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
        words = words[1:]
    if not words:
        return None
    root = words[0].rsplit("/", 1)[-1].removesuffix(".exe").lower()
    rest = " ".join(words[1:]).lower()
    for tool, verb in DENIED:
        if root != tool:
            continue
        if verb is None or rest == verb or rest.startswith(verb + " "):
            return f"{tool} {verb or ''}".strip()
    return None


def check(command: str, cwd: str | None) -> str | None:
    """يُرجع سببَ الحظر أو None إن سُمح."""
    if is_safe_cwd(cwd):
        return None
    for part in SPLIT.split(command):
        v = denied_verb(part)
        if v:
            return v
    return None


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return 0
    tool = payload.get("tool_name", "")
    command = payload["tool_input"].get("command", "")
    if tool not in ("Bash", "PowerShell") or not isinstance(command, str) or not command.strip():
        return 0
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    try:
        hit = check(command, cwd)
    except Exception as exc:  # شبكةُ أمانٍ: خللُ الخطّاف لا يمنع أمراً — لكن سجّله
        print(f"maestro_git_scope: تعذّر تحليلُ الأمر ({type(exc).__name__}) فمرّ بلا فحص", file=sys.stderr)
        return 0
    if not hit:
        return 0
    print(
        f"محجوبٌ خارج مستودع المايسترو [{hit}]: مجلّدُ التنفيذ «{cwd}» ليس {MAESTRO_REPO} ولا مسموحاً صراحةً. "
        f"إن كان هذا خطأً (مثلاً -C أو cd داخل الأمر نفسِه لوجهةٍ آمنة) فأعِد الأمرَ من مجلّد المايسترو مباشرةً.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
