"""لقطةُ الجهاز (المرحلة 1 من W-20261017-022): ذاكرةٌ وعمليّاتٌ وحاويات — قراءةً فقط، بلا أسماء مستخدمين ولا مساراتٍ شخصيّة.

مصدرُ المنطق: native_metrics في MonitorWidget (نُسخ المنطقُ لا الملفّ؛ الأصلُ لا يُمَسّ). كلُّ أمرٍ خارجيّ من قائمةٍ بيضاء مغلقة
وقراءةٌ محضة؛ أداةٌ غائبة (docker/tasklist) تُسجَّل «غير مقيس» ولا تُعدّ سليمة.
"""

from __future__ import annotations

import collections
import csv
import ctypes
import io
import json
import shutil
import subprocess
import time
from ctypes import wintypes

UNMEASURED = "غير مقيس"
#: الأوامرُ الخارجيّةُ الوحيدةُ المسموحة (قراءةٌ فقط). أيُّ أمرٍ آخر يُرفض قبل التشغيل.
ALLOWED_COMMANDS = (
    ("docker", "ps", "-a", "--format", "{{.Names}}|{{.State}}|{{.Status}}"),
    ("docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"),
    ("tasklist", "/FI", "IMAGENAME eq vmmemWSL.exe", "/FO", "CSV", "/NH"),
    ("tasklist", "/FI", "IMAGENAME eq vmmem.exe", "/FO", "CSV", "/NH"),
)
#: حاوياتٌ لا تدخل أيَّ فعلٍ لاحق (المرحلة 2): تُعلَّم «محمية» في التقرير.
PROTECTED_PREFIXES = ("shschool-dev-db", "shschool-dev-redis", "schoolos-main-preview-")
IDLE_CPU_PCT = 0.5  # افتراضٌ معلَن: حاويةٌ تعمل ومعالجها دون هذه النسبة وقتَ القياس «خاملة»


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("load", wintypes.DWORD),
        ("tp", ctypes.c_ulonglong),
        ("ap", ctypes.c_ulonglong),
        ("tpf", ctypes.c_ulonglong),
        ("apf", ctypes.c_ulonglong),
        ("tv", ctypes.c_ulonglong),
        ("av", ctypes.c_ulonglong),
        ("ae", ctypes.c_ulonglong),
    ]


class _Proc32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("usage", wintypes.DWORD),
        ("pid", wintypes.DWORD),
        ("heap", ctypes.c_void_p),
        ("module", wintypes.DWORD),
        ("threads", wintypes.DWORD),
        ("parent", wintypes.DWORD),
        ("pri", ctypes.c_long),
        ("flags", wintypes.DWORD),
        ("exe", ctypes.c_wchar * 260),
    ]


def run_allowed(cmd: tuple[str, ...], timeout: int = 30) -> str | None:
    """يشغّل أمراً من القائمة البيضاء فقط؛ يعيد None إن غاب أو فشل."""
    if cmd not in ALLOWED_COMMANDS:
        raise PermissionError(f"أمرٌ خارج القائمة البيضاء: {cmd[:2]}")
    if shutil.which(cmd[0]) is None:
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def native_metrics() -> dict:
    """ذاكرةُ ويندوز والالتزام وأعدادُ عمليّاتٍ بعينها (claude.exe وpwsh.exe) — منطقُ MonitorWidget بنسخةٍ معزولة."""
    ms = _MemStatus()
    ms.dwLength = ctypes.sizeof(ms)
    k = ctypes.windll.kernel32
    k.GlobalMemoryStatusEx(ctypes.byref(ms))
    gb = 1024**3
    commit_used, limit = (ms.tpf - ms.apf) / gb, ms.tpf / gb
    total, avail = ms.tp / gb, ms.ap / gb
    k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    counts: collections.Counter = collections.Counter()
    snap = k.CreateToolhelp32Snapshot(0x2, 0)
    if snap and snap != ctypes.c_void_p(-1).value:
        pe = _Proc32()
        pe.dwSize = ctypes.sizeof(pe)
        ok = k.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            counts[pe.exe.lower()] += 1
            ok = k.Process32NextW(snap, ctypes.byref(pe))
        k.CloseHandle(snap)
    du = shutil.disk_usage("C:\\")
    return {
        "commit_pct": round(100 * commit_used / limit, 1),
        "ram_pct": round(100 * (total - avail) / total, 1),
        "total_gb": round(total, 1),
        "avail_gb": round(avail, 2),
        "disk_free_gb": round(du.free / gb, 1),
        "claude_procs": counts["claude.exe"],
        "shell_procs": counts["pwsh.exe"] + counts["powershell.exe"],
    }


def parse_wsl_memory(tasklist_csv: str | None) -> float | None:
    """ذاكرةُ vmmem بالجيجابايت من مخرج tasklist /FO CSV /NH؛ None إن لم تكن العمليّة قائمة."""
    if not tasklist_csv:
        return None
    for row in csv.reader(io.StringIO(tasklist_csv)):
        if len(row) >= 5 and row[0].lower().startswith("vmmem"):
            digits = "".join(ch for ch in row[4] if ch.isdigit())
            if digits:
                return round(int(digits) / 1024 / 1024, 2)  # KB → GB
    return None


def _mem_to_mb(text: str) -> float | None:
    """«123.4MiB / 4GiB» ← 123.4 (الجزءُ الأوّل فقط، بالميغابايت)."""
    first = text.split("/")[0].strip()
    for unit, mult in (("GiB", 1024.0), ("MiB", 1.0), ("KiB", 1 / 1024), ("B", 1 / 1024 / 1024)):
        if first.endswith(unit):
            try:
                return round(float(first[: -len(unit)]) * mult, 1)
            except ValueError:
                return None
    return None


def parse_containers(ps_out: str | None, stats_out: str | None) -> list[dict] | None:
    """قائمةُ الحاويات: الاسم والحالة والمعالج والذاكرة بالميغابايت وتصنيفها (محميّة/خاملة/حيّة/متوقّفة)."""
    if ps_out is None:
        return None
    usage: dict[str, tuple[float | None, float | None]] = {}
    for line in (stats_out or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3:
            try:
                cpu = float(parts[1].rstrip("%"))
            except ValueError:
                cpu = None
            usage[parts[0]] = (cpu, _mem_to_mb(parts[2]))
    out = []
    for line in ps_out.splitlines():
        parts = line.strip().split("|")
        if len(parts) < 2 or not parts[0]:
            continue
        name, state = parts[0], parts[1]
        cpu, mem = usage.get(name, (None, None))
        if name.startswith(PROTECTED_PREFIXES):
            kind = "محمية"
        elif state != "running":
            kind = "متوقّفة"
        elif cpu is not None and cpu < IDLE_CPU_PCT:
            kind = "خاملة"
        else:
            kind = "حيّة"
        out.append({"name": name, "state": state, "cpu_pct": cpu, "mem_mb": mem, "kind": kind})
    return out


def take(label: str) -> dict:
    """لقطةٌ كاملة. كلُّ حقلٍ لم يُقَس يحمل None ويُدرَج في unmeasured."""
    unmeasured: list[str] = []
    try:
        host = native_metrics()
    except (OSError, AttributeError, ValueError):
        host = {}
        unmeasured.append("host")
    wsl_raw = run_allowed(ALLOWED_COMMANDS[2]) or run_allowed(ALLOWED_COMMANDS[3])
    wsl_gb = parse_wsl_memory(wsl_raw)
    if wsl_gb is None:
        unmeasured.append("wsl_memory")
    containers = parse_containers(run_allowed(ALLOWED_COMMANDS[0]), run_allowed(ALLOWED_COMMANDS[1]))
    if containers is None:
        unmeasured.append("containers")
    return {
        "label": label,
        "ts": int(time.time()),
        "host": host,
        "wsl_memory_gb": wsl_gb,
        "containers": containers,
        "unmeasured": unmeasured,
    }


def dumps(snap: dict) -> str:
    return json.dumps(snap, ensure_ascii=False, indent=2) + "\n"
