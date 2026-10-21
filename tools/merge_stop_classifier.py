#!/usr/bin/env python3
"""مصنِّفُ شروط التوقف للدمج الآليّ — بطاقة W-20261020-020، بتعريف 0301 (stop_conditions_no_auto_merge_020).

    python merge_stop_classifier.py 1234 [--repo sh-school/shschool_mvp] [--base main]

يطبع قيمةً واحدةً لكلّ طلب: `MERGE_OK` أو `STOP_SECURITY` أو `STOP_MIGRATION` أو `STOP_PERMISSION` أو
`STOP_GOVERNING` أو `STOP_GENERAL`، ثمّ سطراً لكلّ سبب (الرمز ← المسار/العلّة). وإن تحقّق أكثرُ من شرطٍ
تُطبع كلُّ الأسباب لا أوّلُها، والقيمةُ الأولى هي الأعلى أولويّةً (أمن ← هجرة ← صلاحية ← حاكم ← عامّ).

**الفشل آمن:** أيُّ خطأٍ أو مخرجٍ فارغٍ أو قائمةٍ أمنيّةٍ غير مقروءة ⇒ `STOP_GENERAL` أو `STOP_SECURITY`، لا `MERGE_OK`.
قائمةُ المسارات الحسّاسة تُقرأ من فرع الأساس لا من رأس الطلب، فطلبٌ يخفّفها بنفسه لا ينجو (يُوقفه كونُ
`security/sensitive_paths.json` ملفاً حاكماً).

**بلا تفعيل:** هذا مصنِّفٌ يُطبع وحسب؛ لا يدمج ولا يُغيّر شيئاً. و`release_follow.sh` يستدعيه ظلّاً (يطبع حكمَه ولا يُغيّر
سلوكَه) حتى يعتمد المالكُ تفعيلَه.

ما لا يغطّيه المصنِّف عمداً (له فاحصٌ آخر قائم): أدلّةُ الواجهة البصريّة (رمز approval_check 4)، وثغرةُ pip-audit/Bandit
الجديدة (فحصٌ مطلوبٌ في CI)، وفحوصُ CI نفسُها. وعتبةُ التأخّر 20 إيداعاً من قائمة «جاهز للمعاينة» لا من قياس.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field

DEFAULT_REPO = "sh-school/shschool_mvp"
SENSITIVE_LIST = "security/sensitive_paths.json"

#: ترتيبُ الأولويّة لاختيار القيمة الأولى عند تعدّد الأسباب.
PRIORITY = (
    "STOP_SECURITY",
    "STOP_MIGRATION",
    "STOP_PERMISSION",
    "STOP_GOVERNING",
    "STOP_GENERAL",
)

#: المجموعةُ من القائمة الأمنيّة التي تُعامَل صلاحيةً لا أمناً (ج) — وباقي المجموعات أمنٌ (أ).
PERMISSION_GROUP = "authorization_identity"

#: صلاحيةٌ بالمسار مهما قالت القائمة (ج): سجلُّ القدرات ولقطةُ اختباره والمنح وسياساتُ RLS.
PERMISSION_PATHS = (
    "core/capabilities/registry.py",
    "core/capabilities/**",
    "**/capability_grants*.py",
    "**/rls.py",
    "**/rls_*.py",
    "**/*_rls.py",
    "**/*_rls_*.py",
    "**/*rls*.sql",
    "**/rls/**",
)

#: ملفٌّ حاكمٌ (د) في المنصّة ثمّ في مستودع المايسترو.
GOVERNING_PATHS = (
    "CLAUDE.md",
    ".claude/**",
    "docs/governance/**",
    ".github/workflows/**",
    "scripts/deploy_window.py",
    "scripts/auto_merge_gate.py",
    "scripts/ci_*.py",
    "security/sensitive_paths.json",
    # مستودع المايسترو
    "tabs.json",
    "role_cards/**",
    "decisions.md",
)

#: أمنٌ بالمسار فوق القائمة (أ): حارسُ البيانات الشخصيّة وقاعدةُ الأسرار والاعتماديّات وإعدادُ نشر Railway (`.railway/**` غائبٌ عن
#: القائمة الأمنيّة نفسِها فكان #1223 يمرّ MERGE_OK — فجوةٌ أبلغتُ بها 0301).
SECURITY_EXTRA_PATHS = (
    "**/check_personal_data*",
    ".secrets.baseline",
    "**/detect_secrets*",
    ".railway/**",
    "requirements*.txt",
    "requirements/**",
    "**/requirements*.txt",
)

#: هجرةٌ (ب): ملفُّ هجرة، أو أمرُ إدارةٍ (قد يعدّل بيانات) — الاحتياطُ نحو الإيقاف.
MIGRATION_PATHS = ("**/migrations/*.py", "**/management/commands/*.py")

#: ملفُّ عاملِ الخدمة (هـ): تغييرُ منطقه بلا رفع رقم الذاكرة يُبقي نسخةً قديمةً على أجهزة المستخدمين.
SERVICE_WORKER_PATHS = ("**/sw*.js", "**/service-worker*.js", "**/serviceworker*.js")

URGENT_LABEL = "نشر-عاجل"
UNREVIEWED_LABEL = "لم تُراجَع أمنياً"
MAX_BEHIND = 20


@dataclass
class Verdict:
    """الحكم: `value` الأعلى أولويّةً، و`reasons` كلُّ الأسباب بترتيب ظهورها (الرمز، المسار أو العلّة)."""

    reasons: list[tuple[str, str]] = field(default_factory=list)

    @property
    def value(self) -> str:
        found = {code for code, _ in self.reasons}
        for code in PRIORITY:
            if code in found:
                return code
        return "MERGE_OK"

    def add(self, code: str, why: str) -> None:
        self.reasons.append((code, why))


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**` يعبر المجلّدات (ويطابق صفراً منها)، و`*` داخل مقطعٍ واحدٍ، و`?` حرفاً واحداً."""
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(_glob_to_regex(p).match(path) for p in patterns)


def _sensitive_groups(sensitive: dict) -> dict[str, list[str]]:
    groups = sensitive.get("mandatory_review_when_diff_touches")
    if not isinstance(groups, dict) or not groups:
        raise ValueError("القائمة الأمنيّة بلا mandatory_review_when_diff_touches")
    return {name: list(paths) for name, paths in groups.items()}


def _content_rules(sensitive: dict) -> list[tuple[str, re.Pattern[str]]]:
    """أنماطُ المحتوى: قائمةٌ مسطّحة تُطابَق على كلّ الفرق، وقاموسٌ `files`+`patterns` يُطابَق على ملفّاته وحدَها."""
    rules = sensitive.get("mandatory_review_when_diff_content_matches") or {}
    flat: list[tuple[str, re.Pattern[str]]] = []
    for name, spec in rules.items():
        if isinstance(spec, list):
            flat.extend((name, re.compile(p)) for p in spec)
    return flat


def _scoped_content_rules(
    sensitive: dict,
) -> list[tuple[str, list[str], re.Pattern[str]]]:
    rules = sensitive.get("mandatory_review_when_diff_content_matches") or {}
    scoped = []
    for name, spec in rules.items():
        if isinstance(spec, dict):
            scoped.extend(
                (name, list(spec.get("files", [])), re.compile(p, re.M))
                for p in spec.get("patterns", [])
            )
    return scoped


def _added_lines_by_file(diff_text: str) -> dict[str, list[str]]:
    """السطورُ المضافة لكلّ ملفٍّ من فرقٍ موحَّد (`+` دون ترويسة `+++`)."""
    per_file: dict[str, list[str]] = {}
    current = ""
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            per_file.setdefault(current, [])
        elif line.startswith("+") and not line.startswith("+++") and current:
            per_file[current].append(line[1:])
    return per_file


def classify(
    files: list[str],
    labels: list[str],
    sensitive: dict | None,
    *,
    diff_text: str = "",
    behind: int = 0,
) -> Verdict:
    """الحكمُ من المدخلات وحدها (دون شبكة): ملفّاتُ الفرق ووسومُ الطلب والقائمةُ الأمنيّةُ من الأساس ونصُّ الفرق وتأخّرُ الرأس."""
    v = Verdict()
    if not files:
        v.add("STOP_GENERAL", "فرقٌ بلا ملفّات أو غيرُ مقروء — الفشل آمن")
        return v

    # (أ) و(ج) من القائمة الأمنيّة المقروءة من الأساس؛ غيابُها أو تلفُها ⇒ أمن (لا نجزم أنّه ليس حسّاساً)
    groups: dict[str, list[str]] = {}
    if sensitive is None:
        v.add("STOP_SECURITY", f"تعذّرت قراءة {SENSITIVE_LIST} من فرع الأساس")
    else:
        try:
            groups = _sensitive_groups(sensitive)
        except (ValueError, AttributeError) as exc:
            v.add("STOP_SECURITY", f"{SENSITIVE_LIST} تالفة: {exc}")

    for path in files:
        for name, patterns in groups.items():
            if matches(path, patterns):
                if name == PERMISSION_GROUP:
                    v.add("STOP_PERMISSION", f"{path} ({name})")
                else:
                    v.add("STOP_SECURITY", f"{path} ({name})")
        if matches(path, SECURITY_EXTRA_PATHS):
            v.add("STOP_SECURITY", f"{path} (اعتماديّات/أسرار/بيانات شخصيّة)")
        if matches(path, PERMISSION_PATHS):
            v.add("STOP_PERMISSION", f"{path} (قدرات/منح/RLS)")
        if matches(path, MIGRATION_PATHS):
            v.add("STOP_MIGRATION", f"{path} (هجرة/أمر إدارة)")
        if matches(path, GOVERNING_PATHS):
            v.add("STOP_GOVERNING", f"{path} (ملفّ حاكم)")

    # (أ) محتوى الفرق: أنماطُ القائمة، و`RunPython` (ب)
    added = _added_lines_by_file(diff_text)
    if sensitive is not None:
        for name, rx in _content_rules(sensitive):
            for path, lines in added.items():
                if any(rx.search("+" + line) for line in lines):
                    v.add("STOP_SECURITY", f"{path} (نمط محتوى: {name})")
        for name, scope, rx in _scoped_content_rules(sensitive):
            for path, lines in added.items():
                if matches(path, scope) and any(
                    rx.search("+" + line) for line in lines
                ):
                    v.add("STOP_SECURITY", f"{path} (نمط محتوى: {name})")
    for path, lines in added.items():
        if any("RunPython" in line for line in lines):
            v.add("STOP_MIGRATION", f"{path} (RunPython)")

    # (هـ) شروطٌ عامّة
    if URGENT_LABEL in labels:
        v.add("STOP_GENERAL", f"وسمُ «{URGENT_LABEL}» يخصّ المالك")
    if UNREVIEWED_LABEL in labels:
        v.add("STOP_SECURITY", f"وسمُ «{UNREVIEWED_LABEL}»")
    for path in files:
        if matches(path, SERVICE_WORKER_PATHS):
            bumped = any("CACHE_NAME" in line for line in added.get(path, []))
            if not bumped:
                v.add("STOP_GENERAL", f"{path} (عاملُ خدمةٍ بلا رفع CACHE_NAME)")
    if behind > MAX_BEHIND:
        v.add(
            "STOP_GENERAL", f"الرأس متأخّرٌ {behind} إيداعاً عن الأساس (الحدّ {MAX_BEHIND})"
        )

    # إزالة التكرار مع حفظ الترتيب
    seen: set[tuple[str, str]] = set()
    v.reasons = [r for r in v.reasons if not (r in seen or seen.add(r))]
    return v


# ── الجلب (gh) — كلُّ إخفاقٍ هنا يُترجَم إلى توقّف، لا إلى MERGE_OK ─────────────────────────────


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout  # noqa: S603,S607


def fetch_inputs(
    pr: str, repo: str, base: str
) -> tuple[list[str], list[str], dict | None, str, int]:
    info = json.loads(
        _gh("pr", "view", pr, "--repo", repo, "--json", "files,labels,headRefOid")
    )
    files = [f["path"] for f in info["files"]]
    labels = [lab["name"] for lab in info["labels"]]
    head = info["headRefOid"]
    diff_text = _gh("pr", "diff", pr, "--repo", repo)
    try:
        raw = json.loads(
            _gh("api", f"repos/{repo}/contents/{SENSITIVE_LIST}?ref={base}")
        )
        sensitive = json.loads(base64.b64decode(raw["content"]).decode("utf-8"))
    except (subprocess.CalledProcessError, KeyError, ValueError):
        sensitive = None
    cmp_ = json.loads(_gh("api", f"repos/{repo}/compare/{head}...{base}"))
    return files, labels, sensitive, diff_text, int(cmp_.get("ahead_by", 0))


def render(v: Verdict) -> str:
    lines = [v.value]
    lines.extend(f"  {code} ← {why}" for code, why in v.reasons)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pr")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--base", default="main")
    a = ap.parse_args(argv)
    try:
        files, labels, sensitive, diff_text, behind = fetch_inputs(a.pr, a.repo, a.base)
        verdict = classify(files, labels, sensitive, diff_text=diff_text, behind=behind)
    except Exception as exc:  # noqa: BLE001 — الفشل آمن: أيُّ خطأ ⇒ توقّف
        verdict = Verdict(
            [("STOP_GENERAL", f"تعذّر التصنيف: {type(exc).__name__}: {exc}")]
        )
    print(render(verdict))
    return 0 if verdict.value == "MERGE_OK" else 1


if __name__ == "__main__":
    sys.exit(main())
