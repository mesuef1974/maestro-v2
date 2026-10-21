"""تنبيهُ المعاينة المركزية: قراءةٌ فقط (جلسة 0601، إذن المالك 2026-10-18 «جدولة قراءة وتنبيه»).

يشغّل `preview.sh status` ويقرأ Docker، ثمّ يطبع JSON بدرجاتٍ (info/warn/high) ويخرج 1 إن وُجد تنبيه.
لا up ولا down ولا pin ولا sync — لا يكتب شيئاً ولا يرسل رسائل (المهمّة المجدولة تلخّص الخرج).

    python tools/preview_alert.py [--script <preview.sh>] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_SCRIPTS = (
    os.environ.get("PREVIEW_SCRIPT", ""),
    "D:/shschool_mvp/scripts/preview.sh",
)


def parse_status(text: str, docker_ok: bool = True) -> list[dict]:
    """يحوّل مخرجَ status وحالةَ Docker إلى تنبيهاتٍ (قائمةٌ فارغةٌ = سليم)."""
    alerts: list[dict] = []
    if not docker_ok:
        alerts.append({"level": "high", "code": "docker_down", "msg": "Docker متوقف — المعاينة لا تعمل"})
    for line in text.splitlines():
        s = line.strip()
        if "لا نبضَ" in s:
            m = re.search(r"(\d+)\s*دقيقة", s)
            mins = int(m.group(1)) if m else None
            if mins is None or mins > 15:
                alerts.append({"level": "high", "code": "watch_stalled", "msg": s.lstrip("! ")})
        elif "تثبيتٌ منتهٍ لم يُفكّ" in s:
            alerts.append({"level": "warn", "code": "pin_expired", "msg": s.lstrip("! ")})
        elif "لم يُقلع" in s:
            alerts.append({"level": "high", "code": "boot_failed", "msg": s.lstrip("! ")})
        elif s.startswith("الخادم:") and "running (healthy)" not in s:
            alerts.append({"level": "high", "code": "server_not_healthy", "msg": s})
    return alerts


def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "ps"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _status(script: str) -> str:
    r = subprocess.run(
        ["bash", script, "status"], capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    return r.stdout + r.stderr


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", help="مسار preview.sh")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    script = a.script or next((p for p in DEFAULT_SCRIPTS if p and os.path.exists(p)), "")
    docker_ok = _docker_ok()
    if not script:
        alerts = [{"level": "high", "code": "no_script", "msg": "لا preview.sh (ضع PREVIEW_SCRIPT)"}]
    elif not docker_ok:
        alerts = parse_status("", docker_ok=False)
    else:
        alerts = parse_status(_status(script), docker_ok=True)
    out = {"ok": not alerts, "alerts": alerts}
    print(json.dumps(out, ensure_ascii=False, indent=None if a.json else 2))
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
