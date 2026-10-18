#!/usr/bin/env python3
"""طابورُ الجلسات الموقوفة الإرسال (قرار المالك 2026-10-18): تسجّل الجلسةُ توقّفَها فيراه المايسترو والمالك.

  python unblock_request.py add <رقم الجلسة> --waiting "ما تنتظر إرساله"
  python unblock_request.py list
  python unblock_request.py clear <رقم الجلسة>

الملف: ../unblock_queue.json. الكتابةُ ذرّيّة. لا يرسل رسائلَ ولا يغيّر إعداداتٍ.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "unblock_queue.json"


def load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(PATH.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, PATH)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("session")
    a.add_argument("--waiting", required=True)
    sub.add_parser("list")
    c = sub.add_parser("clear")
    c.add_argument("session")
    args = ap.parse_args(argv)
    data = load()
    if args.cmd == "add":
        data[args.session] = {"waiting": args.waiting, "since": datetime.now().isoformat(timespec="minutes")}
        save(data)
        print(f"سُجّل: {args.session} موقوفة الإرسال — ينتظر المالكُ كلمة «تابع» في محادثتها")
    elif args.cmd == "clear":
        data.pop(args.session, None)
        save(data)
        print(f"أُزيلت {args.session} من الطابور")
    else:
        if not data:
            print("لا جلسةَ موقوفةَ الإرسال")
        for k, v in sorted(data.items()):
            print(f"{k}: منذ {v['since']} — تنتظر: {v['waiting']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
