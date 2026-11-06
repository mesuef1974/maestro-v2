"""الدفع إلى origin بعد كل إيداع بخطّاف post-commit (قرار المالك 2026-11-06، بدل الساعة المحددة).

الفرعُ نفسُه بلا force ولا main؛ وكلُّ ما سيخرج (كلُّ commit لا كلُّ فرق، لأنّ المستودع عامّ والتاريخ يبقى) يُفحص قبل الدفع،
وأيُّ إصابةٍ توقفه بسطرٍ في طابور المالك. ما لم يُودَع لا يخرج أصلاً."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "origin"
PROTECTED = ("main", "master")
SAFE_EMAIL = re.compile(r"@(?:[\w.-]*\.)?(?:example\.(?:com|org|net|test)|anthropic\.com|users\.noreply\.github\.com)$", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RULES = {
    "مفتاح خاصّ": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    "رمز GitHub": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_\w{30,})"),
    "مفتاح Anthropic": re.compile(r"\bsk-ant-[\w-]{20,}"),
    "مفتاح AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "مفتاح Slack": re.compile(r"\bxox[abprs]-[\w-]{10,}"),
    "رابط بكلمة مرور": re.compile(r"\b[a-z][a-z0-9+]*://[^\s:/@]+:[^\s:/@{}$<]+@"),
    "كلمة مرور صريحة": re.compile(r"(?i)\b(?:password|passwd|secret|api_?key|token)\b\s*[=:]\s*[\"'][^\"'\s{}$<]{8,}[\"']"),
    "رقم شخصيّ قطريّ": re.compile(r"(?<![\w.-])[23]\d{10}(?![\w.-])"),
    "هاتف قطريّ": re.compile(r"(?:\+|00)974[ -]?\d{8}\b"),
}
BAD_FILE = re.compile(r"(?i)(?:^|/)(?:\.env(?:\..+)?|.*\.pem|.*\.key|.*\.p12|local_preview_pw\.txt|\.preview_accounts\.env|events\.jsonl)$")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)  # noqa: S603, S607


def scan_line(line: str) -> list[str]:
    """أسماءُ القواعد لا القيم: التقريرُ نفسُه لا يجوز أن يحمل السرّ."""
    hits = [name for name, rule in RULES.items() if rule.search(line)]
    if any(not SAFE_EMAIL.search(m) for m in EMAIL.findall(line)):
        hits.append("بريد إلكترونيّ")
    return hits


def scan_patch(patch: str) -> list[str]:
    found, path = [], "?"
    for ln in patch.splitlines():
        if ln.startswith("+++ "):
            path = ln[6:] if ln.startswith("+++ b/") else ln[4:]
        elif ln.startswith("Binary files "):
            found.append(f"ملفّ ثنائيّ: {ln[:120]}")
        elif ln.startswith("+"):
            found += [f"{name}: {path}" for name in scan_line(ln[1:])]
    return sorted(set(found))


def scan_outgoing(revs: list[str]) -> list[str]:
    """الرسائلُ والأسماءُ والإضافاتُ في كلِّ commit خارج، فسرٌّ أُضيف ثمّ حُذف يبقى في التاريخ."""
    found = [f"{n}: رسالة commit" for ln in git("log", "--format=%B", *revs).stdout.splitlines() for n in scan_line(ln)]
    found += [f"اسم ملفّ ممنوع: {f}" for f in git("log", "--name-only", "--format=", *revs).stdout.splitlines() if BAD_FILE.search(f)]
    found += scan_patch(git("log", "-p", "--format=", "--no-color", *revs).stdout)
    return sorted(set(found))


def stop(message: str, code: int) -> int:
    print(message)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import runner  # noqa: PLC0415

    runner.refer("PUSH", message[:600])
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="الدفع اليومي بعد فحص الأسرار والبيانات الشخصيّة")
    ap.add_argument("--dry", action="store_true", help="فحصٌ بلا دفع")
    args = ap.parse_args(argv)
    branch = git("branch", "--show-current").stdout.strip()
    if not branch or branch in PROTECTED:
        return stop(f"الدفع اليومي توقّف: الفرع «{branch or 'بلا فرع'}» لا يُدفع", 2)
    fetched = git("fetch", REMOTE)
    if fetched.returncode:
        return stop(f"الدفع اليومي توقّف: تعذّر الجلب: {fetched.stderr.strip()[-200:]}", 2)
    revs = ["HEAD", "--not", f"--remotes={REMOTE}"]
    count = len(git("rev-list", *revs).stdout.split())
    if not count:
        print("لا جديد")
        return 0
    found = scan_outgoing(revs)
    if found:
        return stop(f"الدفع اليومي توقّف: {len(found)} إصابة في {count} commit: " + "؛ ".join(found[:8]), 1)
    if args.dry:
        print(f"نظيف: {count} commit جاهزة، بلا دفع")
        return 0
    pushed = git("push", REMOTE, f"HEAD:refs/heads/{branch}")
    if pushed.returncode:
        return stop(f"الدفع اليومي فشل: {pushed.stderr.strip()[-300:]}", 2)
    print(f"دُفع {count} commit إلى {REMOTE}/{branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
