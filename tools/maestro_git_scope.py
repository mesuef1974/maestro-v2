#!/usr/bin/env python3
"""PreToolUse (Bash|PowerShell): يمنع الجلسةَ من دفعٍ أو دمجٍ أو تغييرٍ في أيّ مستودعٍ إلّا مستودعَ المايسترو نفسه.

خلفيّةُ الحاجة: مسوّدةٌ سابقةٌ استعملت permissions.deny بنمط «Bash(git push:*)» ظانّةً أنّ الحظر يخصّ
شجرةَ المنصّة D:/shschool_mvp وحدها. لكنّ permissions.deny يطابق نصَّ استدعاء الأداة بلا وعيٍ بالمجلّد
إطلاقاً — فمنع الدفعَ والدمج في مستودع المايسترو الخاصّ نفسِه أيضاً، وتوقّف عملُ 0101 فوراً (23:03..23:05).

هذا الخطّافُ بديلٌ واعٍ بالمجلّد: **يسمح بأفعال git المؤثّرة (push/commit/merge/...) فقط حين يكون
مجلّدُ الجلسة الحاليّ (الذي يرويه Claude Code نفسُه في الحمولة، لا نصٌّ يُفسَّر) داخل مستودع المايسترو
MAESTRO_REPO أو أيّ مسارٍ مُذكَرٍ صراحةً في SAFE_DIRS، ويمنعه في كلّ ما عدا ذلك — بما فيه شجرةُ المنصّة
وأيُّ مجلّدٍ آخرَ غيرَ معروف (فشلٌ مغلَق، لا قائمةَ حظرٍ لشجرة المنصّة وحدَها).

**تصحيحٌ (23:35)**: الإصدارُ الأوّل قرأ حقلَ cwd من حمولة الخطّاف وحدَه، ولا يحلّل `cd X && ...`
ولا `git -C <مسار>` داخل النصّ نفسِه — ووُصف هذا "استثناءً نادراً". اختبار 0101 الحيّ كذّب هذا: صيغةُ
سطرٍ واحدٍ `cd <مسارُه> && git ...` هي **الوحيدةُ** التي يستدعي بها git في مستودعه طوال الجلسة (لا
يعتمد على cwd الفارسيّ بين نداءات Bash)، فحُجب عملُه المشروع كلُّه، لا حالةٌ شاذّة. صُحّح: يتتبّع
الآن `cd`/`pushd`/`chdir` بين الأجزاء المفصولة بـ&&/;/| بالترتيب (كـcur_dir في guard_git.py)، وكذلك
`-C <مسار>` داخل نداء git نفسِه — فمسارُ المايسترو الحرفيّ في نصّ الأمر يكفي الآن، لا حقلَ cwd وحده.

**حدٌّ ما زال قائماً**: لا يفكّ `eval`/`bash -c`/المتغيّرات غيرَ المحلولة ولا يحلّل محتوى سكربتٍ
يُستدعى — من أراد تغطيةً كاملةً بمستوى guard_git.py (1060 سطراً) فذلك عملٌ منفصلٌ يستحقّ المراجعةَ
نفسَها التي أخذها (REP-19)، لا يُرتجَل في مسوّدةٍ واحدة.

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
CD_NAMES = {"cd", "pushd", "chdir", "set-location", "sl"}
MSYS = re.compile(r"^/([a-zA-Z])(?:/(.*))?$")


def norm(path: str | None) -> str | None:
    """تطبيعٌ: شرطاتٌ أماميّة وحروفٌ صغيرة، وتحويلُ مسار MSYS (/c/x ← C:/x)؛ غيرُ معلومٍ (متغيّرٌ أو ~) يبقى None."""
    if not path or any(ch in path for ch in "$`~*"):
        return None
    p = path.replace("\\", "/").rstrip("/")
    m = MSYS.match(p)
    if m:
        p = f"{m.group(1).upper()}:/{m.group(2) or ''}".rstrip("/")
    return p.lower()


def is_safe_dir(path: str | None) -> bool:
    n = norm(path)
    if n is None:
        return False  # مجلّدٌ غيرُ معلوم: فشلٌ مغلَق
    if n == MAESTRO_REPO or n.startswith(MAESTRO_REPO + "/"):
        return True
    return any(n == norm(s) or n.startswith(f"{norm(s)}/") for s in SAFE_DIRS)


def _strip_wrappers(words: list[str]) -> list[str]:
    while words and (words[0] in ("env", "sudo", "command") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
        words = words[1:]
    return words


def cd_target(simple_cmd: str) -> str | None:
    """إن كان الجزءُ بأكمله أمرَ تنقّلٍ (cd/pushd/...) يُرجع مقصدَه، وإلّا None."""
    words = _strip_wrappers(simple_cmd.strip().split())
    if len(words) < 2:
        return None
    root = words[0].rsplit("/", 1)[-1].removesuffix(".exe").lower()
    if root not in CD_NAMES:
        return None
    return words[-1]  # آخرُ كلمةٍ: يتجاهل خياراتٍ مثل pushd -n <مسار>


def dash_c_target(words: list[str]) -> str | None:
    """يستخرج مقصدَ `-C <مسار>` من نداء git، إن وُجد."""
    for i, w in enumerate(words):
        if w == "-C" and i + 1 < len(words):
            return words[i + 1]
        if w.startswith("-C") and len(w) > 2:
            return w[2:]
    return None


def denied_verb(simple_cmd: str) -> tuple[str, str | None] | None:
    """يُرجع (وصفَ الفعل المحظور، مقصدَ -C إن وُجد) لأوّل فعلٍ محظورٍ يبدأ به الأمر، أو None."""
    words = _strip_wrappers(simple_cmd.strip().split())
    if not words:
        return None
    root = words[0].rsplit("/", 1)[-1].removesuffix(".exe").lower()
    dash_c = dash_c_target(words) if root == "git" else None
    # خياراتُ git العامّة (-C <مسار>، -c k=v) تسبق الفعلَ الفرعيّ؛ تُزال قبل مطابقة الفعل لا بعدها
    tail = words[1:]
    if root == "git":
        cleaned: list[str] = []
        i = 0
        while i < len(tail):
            w = tail[i]
            if w == "-C" and i + 1 < len(tail):
                i += 2; continue
            if w.startswith("-C") and len(w) > 2:
                i += 1; continue
            if w == "-c" and i + 1 < len(tail):
                i += 2; continue
            cleaned.append(w); i += 1
        tail = cleaned
    rest = " ".join(tail).lower()
    for tool, verb in DENIED:
        if root != tool:
            continue
        if verb is None or rest == verb or rest.startswith(verb + " "):
            return f"{tool} {verb or ''}".strip(), dash_c
    return None


def check(command: str, cwd: str | None) -> str | None:
    """يُرجع سببَ الحظر أو None إن سُمح. يتتبّع cd/pushd بين الأجزاء بالترتيب، و-C داخل النداء نفسِه."""
    cur = cwd
    for part in SPLIT.split(command):
        moved = cd_target(part)
        if moved is not None:
            cur = moved  # مسارٌ نسبيٌّ بعد cd نادرٌ في هذا الاستعمال؛ يبقى كما كُتب فيفشل is_safe_dir مغلَقاً
            continue
        hit = denied_verb(part)
        if hit is None:
            continue
        verb, dash_c = hit
        effective = dash_c if dash_c is not None else cur
        if not is_safe_dir(effective):
            return verb
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
        f"محجوبٌ خارج مستودع المايسترو [{hit}]: لا مجلّدُ الجلسة ولا cd/-C داخل الأمر نفسِه يشير إلى "
        f"{MAESTRO_REPO} ولا مسموحاً صراحةً. أعِد الأمرَ بمسار المايسترو صراحةً (cd أو -C) إن كانت وجهتُه آمنة.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
