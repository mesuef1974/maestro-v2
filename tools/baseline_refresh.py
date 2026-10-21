#!/usr/bin/env python3
"""تحديثُ خطوط الأساس تلقائياً عند النقصان فقط (أمر المالك «باشر» D-429م، البند 4).

    python baseline_refresh.py --repo D:/shschool_mvp/.claude/worktrees/<شجرتك>            # يطبّق
    python baseline_refresh.py --repo <شجرتك> --check                                       # يقرأ ولا يكتب

ثلاثةُ خطوط: `tests/file_size_baseline.json` و`tests/mypy_ratchet_baseline.json` و`.secrets.baseline`. القاعدةُ في كلٍّ منها واحدة:
  • **زيادة أو جديد** (ملفٌّ كبُر، خطأُ نوعٍ زاد، سرٌّ جديدٌ لم يكن) = ترفضه الأداةُ ولا تكتب شيئاً — ذلك عيبٌ يُصلَح لا أساسٌ يُرفع؛
  • **نقص فقط** (ملفٌّ صغُر أو نزل تحت الحدّ، أخطاءُ أنواعٍ قلّت، سرٌّ زال أو تحرّك سطرُه) = تُسجَّله بأمر الأساس نفسِه (`--update`/`scan --baseline`)
    فيبقى التحسّنُ مثبَّتاً ولا يُنفَق ثانيةً.
لا تُودِع الأداةُ ولا تدفع: تترك الملفّاتِ معدَّلةً في الشجرة وتطبع ما تغيّر، والإيداعُ بمسارات صريحةٍ بيد صاحب الشجرة.

mypy: أمرُ `--update` يرفض تلقائياً إن اختلفت إصداراتُ الفاحص المثبَّتةُ عن requirements-mypy.txt (ما تحكم به البوّابة)؛ فتقول الأداةُ ذلك
وتتركه (تثبيتُ الإصدارات ثمّ إعادةُ التشغيل). رموز الخروج: 0 لا شيءَ أو حُدِّث، 1 زيادةٌ تُرفض، 3 خطٌّ لم يُقَس (أداةٌ غائبة أو إصدارٌ مخالف).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

OK, WORSE, UNMEASURED = 0, 1, 3


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def ratchet(repo: Path, module: str, apply: bool, label: str) -> tuple[int, str]:
    """سقّاطتا الأحجام وmypy تطبعان `WORSE`/`زاد` للزيادة و`STALE`/`نقص` للنقص؛ والتحديثُ بـ`--update`."""
    code, out = run([sys.executable, "-m", module], repo)
    worse = [ln for ln in out.splitlines() if ln.startswith(("WORSE", "زاد:"))]
    stale = [ln for ln in out.splitlines() if ln.startswith(("STALE", "نقص ولم يُسجَّل"))]
    if worse:
        return WORSE, f"{label}: زيادةٌ تُرفض ولا يُكتب شيء:\n  " + "\n  ".join(worse[:10])
    if not stale:
        if code not in (0, 1):  # لم يُقس (أداةٌ أو استيرادٌ مفقود)
            return UNMEASURED, f"{label}: لم يُقَس (رمز {code}): {out.strip().splitlines()[-1] if out.strip() else ''}"
        return OK, f"{label}: لا نقصَ لتسجيله."
    if not apply:
        return OK, f"{label}: {len(stale)} نقصٌ يُسجَّل بلا --check:\n  " + "\n  ".join(stale[:10])
    code, out2 = run([sys.executable, "-m", module, "--update"], repo)
    if code != 0:
        first = out2.strip().splitlines()[0] if out2.strip() else ""
        return UNMEASURED, f"{label}: رفض الأمرُ نفسُه التسجيل (رمز {code}): {first}"
    return OK, f"{label}: سُجّل {len(stale)} نقصٌ:\n  " + "\n  ".join(stale[:10])


def secret_keys(baseline: dict) -> set[tuple[str, str]]:
    return {(path, item["hashed_secret"]) for path, items in baseline.get("results", {}).items() for item in items}


def secrets_baseline(repo: Path, apply: bool) -> tuple[int, str]:
    """نفسُ أمر المولِّد (`detect-secrets scan --baseline`) لكن يُلغى الكتابُ إن ظهر سرٌّ جديد، ولا يُكتب لتغيّر `generated_at` وحدَه."""
    path = repo / ".secrets.baseline"
    exe = shutil.which("detect-secrets")
    if not exe:
        return UNMEASURED, ".secrets.baseline: detect-secrets غير مثبَّت (غيرُ مقيس)."
    original = path.read_text(encoding="utf-8")
    before = json.loads(original)
    code, out = run([exe, "scan", "--baseline", ".secrets.baseline"], repo)
    if code != 0:
        path.write_text(original, encoding="utf-8")
        return UNMEASURED, f".secrets.baseline: فشل المسح (رمز {code}): {out.strip()[-200:]}"
    after = json.loads(path.read_text(encoding="utf-8"))
    added = secret_keys(after) - secret_keys(before)
    removed = secret_keys(before) - secret_keys(after)

    def strip_time(b: dict) -> dict:
        return {k: v for k, v in b.items() if k != "generated_at"}

    changed = strip_time(after) != strip_time(before)
    if added:
        path.write_text(original, encoding="utf-8")
        names = sorted({p for p, _h in added})
        return WORSE, ".secrets.baseline: سرٌّ جديدٌ يُرفض ولا يُكتب شيء في: " + "، ".join(names[:10])
    if not changed or not apply:
        path.write_text(original, encoding="utf-8")
        if changed:
            return OK, f".secrets.baseline: {len(removed)} سرٍّ زال أو تحرّكت أسطرٌ — يُسجَّل بلا --check."
        return OK, ".secrets.baseline: لا نقصَ ولا تحرّك لتسجيله."
    return OK, f".secrets.baseline: سُجّل (زال {len(removed)} سرّاً أو تحرّكت أسطرُه)."


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", help="مجلّد شجرة العمل")
    ap.add_argument("--check", action="store_true", help="اقرأ وأبلغ دون كتابة")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    if not (repo / "tests" / "file_size_ratchet.py").is_file():
        print("✘ ليس جذرَ مستودع SchoolOS:", repo)
        return 2
    apply = not a.check
    results = [
        ratchet(repo, "tests.file_size_ratchet", apply, "file_size_baseline"),
        ratchet(repo, "tests.mypy_ratchet", apply, "mypy_ratchet_baseline"),
        secrets_baseline(repo, apply),
    ]
    for _code, msg in results:
        print(msg)
    worst = max(code for code, _ in results)
    # الزيادةُ (1) تغلب عدمَ القياس (3) في الإبلاغ: ما يُرفض أخطرُ مما لم يُقَس
    if any(code == WORSE for code, _ in results):
        return WORSE
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
