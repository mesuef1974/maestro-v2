#!/usr/bin/env python3
"""أداةُ صورٍ للنموذج بلا تشغيل Python حرّ: تصغيرٌ وتحسينٌ لملفّات PNG وJPEG داخل شجرة البطاقة وحدها.

    python tools/img_tool.py resize <مسار> <عرض> <ارتفاع>   يعيد أخذ العيّنات (LANCZOS) ويحفظ الشفافية ويحسّن الضغط
    python tools/img_tool.py optimize <مسار>                 ضغطٌ بلا فقدٍ ولا تغيير أبعاد
تُطبع الأحجامُ قبل وبعد؛ ومساراتٌ خارج المجلّد الحاليّ أو بصيغةٍ غير الصور تُرفض. بصفر توكنز.
"""
from __future__ import annotations

import sys
from pathlib import Path

EXT = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}


def _resolve(raw: str, root: Path) -> Path:
    path = (root / raw).resolve()
    if root not in path.parents or not path.is_file():
        raise SystemExit(f"مرفوض: {raw} خارج الشجرة أو غير موجود")
    if path.suffix.lower() not in EXT:
        raise SystemExit(f"مرفوض: {path.suffix} ليست صيغةَ صورةٍ مدعومة (png وjpg)")
    return path


def run(argv: list[str], root: Path | None = None) -> str:
    from PIL import Image  # noqa: PLC0415

    root = (root or Path.cwd()).resolve()
    if len(argv) < 2 or argv[0] not in ("resize", "optimize") or (argv[0] == "resize" and len(argv) != 4):
        raise SystemExit(__doc__)
    path = _resolve(argv[1], root)
    before = path.stat().st_size
    im = Image.open(path)
    fmt = EXT[path.suffix.lower()]
    if argv[0] == "resize":
        try:
            w, h = int(argv[2]), int(argv[3])
        except ValueError:
            raise SystemExit("مرفوض: العرض والارتفاع عددان صحيحان") from None
        if not (1 <= w <= 4096 and 1 <= h <= 4096):
            raise SystemExit("مرفوض: الأبعاد بين 1 و4096")
        im = im.convert("RGBA" if fmt == "PNG" else "RGB").resize((w, h), Image.LANCZOS)
    save = {"optimize": True} | ({"quality": 85} if fmt == "JPEG" else {})
    im.save(path, fmt, **save)
    return f"{argv[1]}: {before} بايت ← {path.stat().st_size} بايت ({im.size[0]}×{im.size[1]})"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    print(run(sys.argv[1:]))
