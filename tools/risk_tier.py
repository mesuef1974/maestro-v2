#!/usr/bin/env python3
"""تصنيفُ الخطورة من المسارات — حتميٌّ، بلا شبكةٍ ولا نموذج. أساسُ حزمة الأدلّة وحزمِ المراجعة وسعةِ المالك.

    python risk_tier.py path1 path2 ...
"""

from __future__ import annotations

import re
import sys

RANK = ["migration", "security", "unknown", "visible_ui", "backend", "infra", "roadmap_data", "tests_only", "docs_only"]
TIER = {
    "migration": "high", "security": "high", "unknown": "high",
    "visible_ui": "medium", "backend": "medium",
    "infra": "low",
    "roadmap_data": "light", "tests_only": "light", "docs_only": "light",
}
TIER_ORDER = ["light", "low", "medium", "high"]
HOT_FILES = ("docs/governance/regression_guards.md", "tests/mypy_ratchet_baseline.json")
# القوالبُ الأساسيّة في المنصّة: base في templates/base/ وصفحةُ الدخول في templates/auth/؛ والقديمان يبقيان احتياطاً
BASE_TEMPLATES = ("templates/base/base.html", "templates/auth/login.html", "templates/base.html", "templates/login.html")
# أسماءُ ملفّاتٍ حسّاسةٌ تُقرأ بمقاطعها المفصولة بـ«_»: صلاحيّاتٌ وأمنُ الصفوف وتشفيرٌ وموافقاتٌ ومحوٌ واحتفاظٌ وتطهير
SECURITY_TOKENS = {"permission", "permissions", "rls", "crypto", "consent", "consents", "erasure", "retention", "purge"}
# إعداداتُ الإنتاج وأساسُها وما بينهما تغيّر الأمنَ (CSP، DEBUG، الأسرار)؛ وإعداداتُ التطوير والاختبار لا
SECURITY_SETTINGS = re.compile(r"(^|/)settings/(__init__|base|production|staging)\.py$")


# امتداداتٌ قد تحمل بياناتٍ حقيقيّةً أو أسراراً (قوائمُ طلبة، نسخُ قواعد، مفاتيح) فخطورتُها عاليةٌ أينما وُجدت
SENSITIVE_EXT = (".csv", ".xlsx", ".xls", ".zip", ".sqlite", ".sqlite3", ".db", ".dump", ".bak", ".sql", ".pem", ".key", ".p12", ".pfx")
# ما يُعرف أنّه بنيةٌ منخفضةُ الخطورة؛ وما سواه مجهولٌ فيُرفَع إلى «عالية» (يفشل المجهولُ مغلقاً — Zero-Trust)
INFRA_EXT = (".txt", ".cfg", ".ini", ".toml", ".yml", ".yaml", ".json", ".lock", ".conf", ".sh", ".ps1", ".bat", ".gitkeep")
UI_ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".ttf", ".map")
INFRA_NAMES = {"Dockerfile", "Makefile", "Procfile", "LICENSE", "Pipfile", ".gitignore", ".gitattributes", ".editorconfig", ".dockerignore"}


def _security_name(p: str) -> bool:
    """ملفُّ بايثون اسمُه (أو أحدُ مقاطعه) من الحسّاسات: core/middleware_rls.py وgovernance/retention.py وpurge_parent_consents.py."""
    if not p.endswith(".py"):
        return False
    stem = p.rsplit("/", 1)[-1][:-3]
    return any(tok in SECURITY_TOKENS for tok in stem.split("_"))


def classify_file(path: str) -> str:
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if base.startswith(".env") or base.lower().endswith(SENSITIVE_EXT):
        return "security"
    if p.startswith("roadmap/migrations/"):
        return "roadmap_data"
    if re.search(r"/migrations/[^/]+\.py$", p):
        return "migration"
    if SECURITY_SETTINGS.search(p) or re.search(r"/auth/", p) or _security_name(p):
        return "security"
    if p.startswith("tests/"):
        return "tests_only"
    if p.startswith((".github/", "scripts/", ".claude/", "docker", "requirements", "Makefile")) or "docker-compose" in p:
        return "infra"
    # امتدادُ html/css/js وحدَه لا يكفي: سكربتُ مهارةٍ في .claude/skills/*/scripts/*.js صار يُحسَب
    # «واجهةً مرئيّة» قبل هذا الإصلاح لأنّ الفحص بالامتداد يسبق فحصَ .claude/ — اكتُشف بتشغيل
    # evidence_pack.py فعلاً على طلب الدمج #730 (خطورةٌ متوسّطة بدل الصحيح: منخفضة)
    if p.startswith(("templates/", "static/")) or p.endswith((".html", ".css", ".js")):
        return "visible_ui"
    if p.endswith(".md") or p.startswith(("docs/", "AAdocs/")):
        return "docs_only"
    if p.endswith(".py"):
        return "backend"
    if base in INFRA_NAMES or base.lower().endswith(INFRA_EXT):
        return "infra"
    if base.lower().endswith(UI_ASSET_EXT):
        return "visible_ui"
    return "unknown"


def classify_paths(paths: list[str]) -> dict:
    """يُرجع أعلى فئةٍ وأعلى خطورةٍ وعلاماتٍ (أثرٌ واسع، ملفٌّ ساخن) ومجالَ الحزمة."""
    cats = {classify_file(p) for p in paths}
    if not cats:
        return {"category": "infra", "tier": "low", "area": "-", "flags": [], "categories": []}
    top = next(c for c in RANK if c in cats)
    tier = TIER[top]
    flags = []
    norm = [p.replace("\\", "/") for p in paths]
    if any(p.startswith("static/css/custom/") for p in norm):
        flags.append("global_css")
    if any(p in BASE_TEMPLATES for p in norm):
        flags.append("base_template")
    if any(p in HOT_FILES for p in norm):
        flags.append("hot_file")
    if any(p == "CLAUDE.md" or p.startswith(".claude/") for p in norm):
        flags.append("agent_rules")
    if ("global_css" in flags or "base_template" in flags) and TIER_ORDER.index(tier) < TIER_ORDER.index("medium"):
        tier = "medium"
    first = next(p for p in norm if classify_file(p) == top)
    area = first.split("/")[0] if "/" in first else first
    return {"category": top, "tier": tier, "area": area, "flags": flags, "categories": [c for c in RANK if c in cats]}


def bundle_key(paths: list[str]) -> tuple[str, str]:
    info = classify_paths(paths)
    return info["category"], info["area"]


if __name__ == "__main__":
    import json

    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(classify_paths(sys.argv[1:]), ensure_ascii=False, indent=2))
