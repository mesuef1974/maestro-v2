"""نسخةٌ خارج الجهاز من تاريخ الأتمتة (قرار المالك 2026-11-06): دفعةٌ يوميّة إلى فرع في مستودع خاصّ.

الفرعُ مستقلّ (بلا تاريخ مشترك مع main) ونسختُه في مجلّد خاصّ، فلا يمسّ D:\\shschool-docs ولا فروعه. الدفعُ بلا force.
كلُّ ما يخرج يُفحص بقواعد daily_push، وأيُّ إصابة توقف الدفع بسطرٍ في طابور المالك. فشلُ هذه الأداة لا يمسّ البطاقات.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import daily_push  # noqa: E402

ROOT = TOOLS.parent
REMOTE = os.environ.get("OFFSITE_REMOTE") or "https://github.com/mesuef1974/shschool-docs.git"
BRANCH = "automation-archive"
HOME = Path(os.environ.get("OFFSITE_HOME") or Path.home() / ".maestro")
CLONE = HOME / "offsite_docs"
STATE = HOME / "offsite_state.json"
SOURCES = (("ledger/events.jsonl", "ledger/events.jsonl"), ("requests", "requests"), ("archive_local/fail_diffs", "fail_diffs"))
SKIP_SUFFIXES = (".md",)  # طلبٌ لم يُنفَّذ بعد قد يتغيّر؛ ما انتهى وحده يُحفظ
README = """# أرشيف الأتمتة

نسخة يوميّة آليّة من دفتر المشغّل وطلباته المنتهية وفروق الفشل. المصدر هو الجهاز، وهذا الفرع نسخة استعادة.
لا يُعدَّل يدويًّا. `MANIFEST.json` يحمل بصمة كلّ ملفّ في آخر دفعة.
"""
# اسمٌ كامل: اسمٌ شائع يتبعه اسمٌ شائع أو نسب ثم كلمة. الاسم الأول وحده لا يُعدّ، فـ«عمر آخر حركة» كلامٌ عاديّ.
FIRST_NAMES = ("محمد|أحمد|احمد|علي|خالد|عبدالله|عبدالرحمن|يوسف|إبراهيم|ابراهيم|حسن|حسين|سعيد|عمر|مصطفى|محمود|سالم|ناصر|فهد|جاسم|"
               "حمد|راشد|سلطان|طارق|سفيان|فاطمة|مريم|عائشة|نورة")
FULL_NAME = re.compile(rf"(?<![\u0621-\u064a])(?:{FIRST_NAMES})\s+(?:بن|بنت|ابن|عبد\s?[\u0621-\u064a]+|{FIRST_NAMES})\s+[\u0621-\u064a]{{2,}}")
GIT_TIMEOUT = 300
RETRY_S = 3600  # الدورة كلّ 5 دقائق؛ بعد فشلٍ لا يُطرق البعيد إلّا كلّ ساعة


def git(*args: str) -> subprocess.CompletedProcess:
    identity = ("-c", "user.name=schoolos-runner", "-c", "user.email=schoolos-runner@users.noreply.github.com")
    return subprocess.run(  # noqa: S603
        ["git", *identity, *args], cwd=CLONE, capture_output=True, text=True, encoding="utf-8",  # noqa: S607
        errors="replace", timeout=GIT_TIMEOUT, check=False)


def must(*args: str) -> str:
    out = git(*args)
    if out.returncode:
        raise RuntimeError(f"git {args[0]}: {(out.stderr or out.stdout).strip()[:300]}")
    return out.stdout


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(**fields) -> None:
    state = read_state() | fields | {"checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def due() -> bool:
    state = read_state()
    if today() in (state.get("ok_day"), state.get("stop_day")):
        return False
    checked = state.get("checked_at")
    return not checked or (datetime.now(UTC) - datetime.fromisoformat(checked.replace("Z", "+00:00"))).total_seconds() >= RETRY_S


def prepare_clone() -> None:
    """نسخةٌ على الفرع وحده: تُنشأ أوّل مرّة، وتتبع البعيد بتقديمٍ سريع بعد ذلك."""
    CLONE.mkdir(parents=True, exist_ok=True)
    if not (CLONE / ".git").is_dir():
        must("init", "-q")
        must("remote", "add", "origin", REMOTE)
    if must("ls-remote", "--heads", "origin", BRANCH).strip():
        must("fetch", "-q", "origin", BRANCH)
        if git("rev-parse", "--verify", "-q", "HEAD").returncode:
            must("checkout", "-q", "-B", BRANCH, "FETCH_HEAD")
        else:
            must("merge", "-q", "--ff-only", "FETCH_HEAD")
    elif git("rev-parse", "--verify", "-q", "HEAD").returncode:
        must("checkout", "-q", "--orphan", BRANCH)


def copy_sources(root: Path) -> list[Path]:
    """يعكس المصادر في النسخة (ما حُذف من المصدر لا يُحذف من الأرشيف) ويعيد الملفّات الموجودة في المصادر."""
    copied = []
    for src, dst in SOURCES:
        path = root / src
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else []
        for f in files:
            if f.suffix in SKIP_SUFFIXES and path.is_dir():
                continue
            target = CLONE / dst if path.is_file() else CLONE / dst / f.relative_to(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, target)
            copied.append(target)
    return copied


def scan(files: list[Path]) -> list[str]:
    """أسماء القواعد والملفّات لا القيم."""
    found = set()
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as lines:
            for line in lines:
                found.update(f"{name}: {f.relative_to(CLONE).as_posix()}" for name in daily_push.scan_line(line))
                if FULL_NAME.search(line):
                    found.add(f"اسم شخص كامل: {f.relative_to(CLONE).as_posix()}")
    return sorted(found)


def manifest(files: list[Path]) -> dict:
    return {"files": {f.relative_to(CLONE).as_posix(): {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "bytes": f.stat().st_size}
                      for f in sorted(files)}}


def refer(message: str) -> None:
    import runner  # noqa: PLC0415 — المشغّل ثقيل، ويلزم هنا وحدها

    runner.refer("OFFSITE", message[:600])


def run(root: Path = ROOT) -> int:
    prepare_clone()
    files = copy_sources(root)
    hits = scan(files)
    if hits:
        # ما نُسخ يبقى محلّيًّا بلا إيداع، ويُعاد الفحص غدًا فلا يتكرّر السطر في الطابور كلّ دورة
        write_state(ok=False, stop_day=today(), error="إصابة في الفحص", hits=len(hits))
        refer("لم تُدفع نسخة الأتمتة الخارجية: " + "، ".join(hits[:8]))
        return 2
    (CLONE / "README.md").write_text(README, encoding="utf-8")
    table = manifest(files)
    (CLONE / "MANIFEST.json").write_text(json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    must("add", "--", "README.md", "MANIFEST.json", *[dst for _src, dst in SOURCES if (CLONE / dst).exists()])
    changed = git("diff", "--cached", "--quiet").returncode != 0
    if changed:
        must("commit", "-q", "-m", f"أرشيف الأتمتة {today()}")
        must("push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}")
    head = must("rev-parse", "HEAD").strip()
    ledger_sha = table["files"].get("ledger/events.jsonl", {}).get("sha256")
    write_state(ok=True, ok_day=today(), head=head, ledger_sha256=ledger_sha, files=len(files), error=None, hits=0)
    print(f"{'دُفعت' if changed else 'لا جديد'}: {head[:10]}، {len(files)} ملفًّا")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="نسخة يوميّة من تاريخ الأتمتة إلى المستودع الخاصّ")
    ap.add_argument("--force", action="store_true", help="الآن ولو دُفعت اليوم")
    args = ap.parse_args(argv)
    if not args.force and not due():
        return 0
    try:
        return run()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        write_state(ok=False, error=str(exc)[:300])
        print(f"تعذّرت النسخة الخارجية: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
