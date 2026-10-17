"""تقريرُ قبل/بعد (المرحلة 1 من W-20261017-022): يقارن لقطتين من snapshot.take. نصٌّ عربيٌّ بلا أسماء مستخدمين ولا مسارات."""

from __future__ import annotations

from .snapshot import UNMEASURED


def _fmt(v, unit: str = "") -> str:
    return UNMEASURED if v is None else f"{v}{unit}"


def _delta(a, b, unit: str = "") -> str:
    if a is None or b is None:
        return UNMEASURED
    d = round(b - a, 2)
    return f"{d:+g}{unit}"


def _counts(snap: dict) -> dict[str, int] | None:
    cs = snap.get("containers")
    if cs is None:
        return None
    out = {"حيّة": 0, "خاملة": 0, "متوقّفة": 0, "محمية": 0}
    for c in cs:
        out[c["kind"]] += 1
    return out


def render(before: dict, after: dict) -> str:
    bh, ah = before.get("host", {}), after.get("host", {})
    lines = [f"# تقرير الجهاز قبل/بعد — {before.get('label', 'قبل')} ← {after.get('label', 'بعد')}", ""]
    lines += ["| المقياس | قبل | بعد | الفرق |", "|---|---|---|---|"]
    rows = [
        ("التزام الذاكرة %", "commit_pct", "%"),
        ("استخدام الذاكرة %", "ram_pct", "%"),
        ("المتاح GB", "avail_gb", ""),
        ("قرص C الحرّ GB", "disk_free_gb", ""),
        ("عمليّات claude", "claude_procs", ""),
        ("عمليّات الصدفة", "shell_procs", ""),
    ]
    for title, key, unit in rows:
        a, b = bh.get(key), ah.get(key)
        lines.append(f"| {title} | {_fmt(a, unit)} | {_fmt(b, unit)} | {_delta(a, b, unit)} |")
    wa, wb = before.get("wsl_memory_gb"), after.get("wsl_memory_gb")
    lines.append(f"| ذاكرة WSL GB | {_fmt(wa)} | {_fmt(wb)} | {_delta(wa, wb)} |")
    ca, cb = _counts(before), _counts(after)
    for kind in ("حيّة", "خاملة", "متوقّفة", "محمية"):
        a, b = (ca or {}).get(kind), (cb or {}).get(kind)
        lines.append(f"| حاويات {kind} | {_fmt(a)} | {_fmt(b)} | {_delta(a, b)} |")
    miss = sorted(set(before.get("unmeasured", [])) | set(after.get("unmeasured", [])))
    lines += ["", f"{UNMEASURED}: {'، '.join(miss)}" if miss else "كلُّ المقاييس قيست.", ""]
    return "\n".join(lines)
