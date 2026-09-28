#!/usr/bin/env python3
"""تصنيفُ الخطورة من المسارات — حتميٌّ، بلا شبكةٍ ولا نموذج. أساسُ حزمة الأدلّة وحزمِ المراجعة وسعةِ المالك.

    python risk_tier.py path1 path2 ...
"""

from __future__ import annotations

import re
import sys

RANK = ["migration", "security", "visible_ui", "backend", "infra", "roadmap_data", "tests_only", "docs_only"]
TIER = {
    "migration": "high", "security": "high",
    "visible_ui": "medium", "backend": "medium",
    "infra": "low",
    "roadmap_data": "light", "tests_only": "light", "docs_only": "light",
}
TIER_ORDER = ["light", "low", "medium", "high"]
HOT_FILES = ("docs/governance/regression_guards.md", "tests/mypy_ratchet_baseline.json")


def classify_file(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("roadmap/migrations/"):
        return "roadmap_data"
    if re.search(r"/migrations/[^/]+\.py$", p):
        return "migration"
    if re.search(r"(^|/)(permissions|rls|crypto|consent|erasure)[^/]*\.py$|/auth/", p):
        return "security"
    if p.startswith(("templates/", "static/")) or p.endswith((".html", ".css", ".js")):
        return "visible_ui"
    if p.startswith("tests/"):
        return "tests_only"
    if p.startswith((".github/", "scripts/", ".claude/", "docker", "requirements", "Makefile")) or "docker-compose" in p:
        return "infra"
    if p.endswith(".md") or p.startswith(("docs/", "AAdocs/")):
        return "docs_only"
    if p.endswith(".py"):
        return "backend"
    return "infra"


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
    if any(p in ("templates/base.html", "templates/login.html") for p in norm):
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
