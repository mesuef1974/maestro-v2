#!/usr/bin/env python3
"""يزامن `preview_accounts_registry.json` مع `EMPLOYEE_NUMBERS` في origin/main:core/preview_accounts.py.

الأرقامُ تُقرأ من القاموس بـ`ast` (لا تُكتب يدويّاً ولا يُنفَّذ كودُ المستودع). لا كلمةَ مرورٍ هنا ولا في الملف.
    python sync_preview_registry.py [--repo <شجرة>] [--ref origin/main] [--check]
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REGISTRY = Path(__file__).resolve().parent / "preview_accounts_registry.json"
SOURCE = "core/preview_accounts.py"


def employee_numbers(repo: str, ref: str) -> dict[str, str]:
    text = subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{SOURCE}"], capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    for node in ast.parse(text).body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if getattr(target, "id", "") == "EMPLOYEE_NUMBERS":
            return ast.literal_eval(node.value)
    raise SystemExit("EMPLOYEE_NUMBERS غير موجود في المصدر")


def build(numbers: dict[str, str], opened_at: str | None = None) -> list[dict[str, str]]:
    stamp = opened_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    return [{"role": role, "national_id": number, "opened_at": stamp} for role, number in numbers.items()]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap =argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--check", action="store_true", help="يفحص المطابقة فقط")
    args = ap.parse_args()
    numbers = employee_numbers(args.repo, args.ref)
    current = {r["role"]: r["national_id"] for r in json.loads(REGISTRY.read_text(encoding="utf-8"))}
    if args.check:
        print("مطابق" if current == numbers else "غير مطابق")
        return 0 if current == numbers else 1
    REGISTRY.write_text(json.dumps(build(numbers), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"كُتب {len(numbers)} صفوف")
    return 0


if __name__ == "__main__":
    sys.exit(main())
