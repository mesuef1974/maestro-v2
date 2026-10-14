#!/usr/bin/env python3
"""تقليمُ مخلّفات العمل (W-20261014-001، أمر المالك 2026-10-14) — عرضٌ افتراضيّاً و`--apply` للحذف.

    python prune_workspace.py                    عرضٌ بالأحجام لكلّ فئة (لا يحذف)
    python prune_workspace.py --apply            يحذف ما يحقّق الشروط (فئاتُ evidence وtmp_reports فقط)
    python prune_workspace.py --json             إخراج آليّ

الفئات:
  evidence  لقطات/مرفقات رأسٍ قديمٍ لبطاقةٍ منشورة؛ يُبقى manifest.json وكلُّ ملفٍّ نصّيّ (md/txt/json).
  tmp       مجلّد tmp_reports.
  worktrees (عرضٌ فقط) شجراتُ العمل الخالية من تعديلاتٍ وفرعُها مدموجٌ في main — يُحذف بـ`git worktree remove` يدويّاً.
  containers(عرضٌ فقط) حاوياتُ جلساتٍ متوقّفة (Exited).
  session_dbs قواعدُ Postgres للجلسات (ss_<slug> وtest_ss_<slug>) التي لا شجرةَ عملٍ لها ولا اتصالَ بها — تُحذف بـ`--apply`
             (W-20261014-028). لا تُمسّ: قاعدةُ شجرةٍ حيّة، قاعدةٌ بها اتصال، ss_main_preview وss_integration_preview
             وأجيالُها ss_main_preview_g<N> وss_base_*؛ وأجيالُ المعاينة تُعرض عدداً وحجماً فقط (قرارُها لـ0501).

الأمان: داخل الجذر فقط؛ لا روابطَ رمزيّة؛ لا يمسّ رأساً معتمداً لم يُنشر؛ ترفض ما حالتُه مجهولةٌ في الدفتر؛
سماحُ الرأس الأخير ثلاثةُ أيّام؛ سجلٌّ بالأحجام في prune_log.jsonl.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
TMP = ROOT / "tmp_reports"
LOG = ROOT / "prune_log.jsonl"
GRACE_DAYS = 3
#: يجوز تقليمُ مرفقات البطاقة بعد تأكّد النشر فقط (published: دُمجت ونُشرت وتُحقّق من الإنتاج) — أمر المالك 2026-10-14.
PRUNABLE_STATES = {"published"}
#: ملفّاتٌ تبقى دائماً.
KEEP_NAMES = {"manifest.json"}
KEEP_SUFFIX = {".md", ".txt", ".json"}


def _size(path: Path) -> int:
    try:
        return path.lstat().st_size
    except OSError:
        return 0


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return not path.is_symlink()
    except (ValueError, OSError):
        return False


def card_states() -> dict[str, str]:
    """حالةُ كلّ بطاقةٍ من الدفتر؛ فشلُ القراءة = قاموسٌ فارغٌ فتُرفض كلُّ البطاقات (مجهولة)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import ledger

        return {k: v.get("state", "") for k, v in ledger.reduce_state(ledger.load_events()).items()}
    except Exception:  # noqa: BLE001 — الدفترُ غائب ⇒ لا حذف
        return {}


def scan_evidence(states: dict[str, str], now: float | None = None, root: Path = EVIDENCE) -> dict:
    now = now or time.time()
    cut = now - GRACE_DAYS * 86400
    out = {"files": [], "bytes": 0, "skipped_unknown": [], "skipped_state": []}
    if not root.exists():
        return out
    for card in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        state = states.get(card.name)
        if state is None:
            out["skipped_unknown"].append(card.name)
            continue
        if state not in PRUNABLE_STATES:
            out["skipped_state"].append(f"{card.name}:{state}")
            continue
        heads = sorted((h for h in card.iterdir() if h.is_dir() and not h.is_symlink()), key=lambda h: h.stat().st_mtime)
        for i, head in enumerate(heads):
            newest = i == len(heads) - 1
            if newest and head.stat().st_mtime > cut:
                continue  # سماحُ الرأس الأخير
            for f in head.rglob("*"):
                if not f.is_file() or f.is_symlink() or not _inside(f, root):
                    continue
                if f.name in KEEP_NAMES or f.suffix.lower() in KEEP_SUFFIX:
                    continue
                out["files"].append(str(f))
                out["bytes"] += _size(f)
    return out


def scan_tmp(root: Path = TMP) -> dict:
    files, total = [], 0
    if root.exists() and not root.is_symlink():
        for f in root.rglob("*"):
            if f.is_file() and not f.is_symlink() and _inside(f, root):
                files.append(str(f))
                total += _size(f)
    return {"files": files, "bytes": total}


def _git(*args: str, cwd: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60).stdout


def scan_worktrees(repo: str = "D:/shschool_mvp") -> dict:
    """عرضٌ فقط: شجراتٌ نظيفةٌ فرعُها مدموجٌ في origin/main."""
    out = {"candidates": [], "bytes": 0}
    try:
        merged = {b.strip().lstrip("*+ ") for b in _git("branch", "--merged", "origin/main", cwd=repo).splitlines()}
        cur, branch = None, None
        for line in _git("worktree", "list", "--porcelain", cwd=repo).splitlines() + [""]:
            if line.startswith("worktree "):
                cur = line[9:]
            elif line.startswith("branch "):
                branch = line[7:].removeprefix("refs/heads/")
            elif not line and cur:
                if branch and branch in merged and ".claude/worktrees" in cur.replace("\\", "/"):
                    if not _git("status", "--porcelain", cwd=cur).strip():
                        size = sum(_size(Path(r) / f) for r, _d, fs in os.walk(cur) for f in fs)
                        out["candidates"].append({"path": cur, "branch": branch, "bytes": size})
                        out["bytes"] += size
                cur, branch = None, None
    except Exception:  # noqa: BLE001 — فئةُ عرضٍ فقط
        pass
    return out


def scan_containers() -> dict:
    try:
        r = subprocess.run(["docker", "ps", "-a", "--filter", "status=exited", "--format", "{{.Names}}"],
                           capture_output=True, text=True, timeout=30)
        names = [n for n in r.stdout.split() if n.startswith("schoolos-")]
    except Exception:  # noqa: BLE001
        names = []
    return {"names": names}


DB_CONTAINER = "shschool-dev-db"
REPO = "D:/shschool_mvp"
#: لا تُحذف قطّ: المعاينةُ المركزيّة وأجيالُها والقواعدُ الأساس والنظام.
PROTECTED_DB = re.compile(r"^(ss_main_preview(_g\d+)?|ss_integration_preview|ss_base_.*|postgres|shschool_db|template[01])$")
PREVIEW_GEN_DB = re.compile(r"^ss_main_preview_g\d+$")
SESSION_DB = re.compile(r"^(test_)?ss_[a-z0-9_]+$")


def tree_slug(path: str) -> str:
    """اسمُ القاعدة من اسم الشجرة كما يشتقّه scripts/session-db.sh (حروفٌ وأرقام، 40 محرفاً، دون شرطةٍ سفليّةٍ أخيرة)."""
    slug = (re.sub(r"[^a-z0-9]", "_", Path(path).name.lower()) + "_")[:40]
    return slug[:-1] if slug.endswith("_") else slug


def _psql(sql: str, container: str = DB_CONTAINER) -> list[str]:
    r = subprocess.run(
        ["docker", "exec", container, "sh", "-c", 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -tAF "|" -c "$0"', sql],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "psql failed")
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def live_tree_slugs(repo: str = REPO) -> set[str]:
    """أسماءُ كلّ الأشجار المسجَّلة (الرئيسةُ وشجراتُ العمل)؛ فشلُ القراءة يرفع خطأً فلا حذفَ على أساس قائمةٍ فارغة."""
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=60)
    if out.returncode != 0:
        raise RuntimeError("git worktree list failed")
    slugs = {tree_slug(ln[9:]) for ln in out.stdout.splitlines() if ln.startswith("worktree ")}
    if not slugs:
        raise RuntimeError("no worktrees listed")
    return slugs


def classify_session_dbs(rows: list[tuple[str, int, int]], slugs: set[str]) -> dict:
    """rows = (اسم، حجم بالبايت، عددُ الاتصالات). نقيّ بلا دخولٍ ولا خروج فيُختبر."""
    out = {"orphans": [], "kept_live": 0, "kept_connected": [], "preview_gens": {"count": 0, "bytes": 0}, "bytes": 0}
    for name, size, conns in rows:
        if PREVIEW_GEN_DB.match(name):
            out["preview_gens"]["count"] += 1
            out["preview_gens"]["bytes"] += size
            continue
        if PROTECTED_DB.match(name) or not SESSION_DB.match(name):
            continue
        slug = name.removeprefix("test_").removeprefix("ss_")
        if slug in slugs:
            out["kept_live"] += 1
        elif conns > 0:
            out["kept_connected"].append(name)
        else:
            out["orphans"].append({"name": name, "bytes": size})
            out["bytes"] += size
    return out


def scan_session_dbs(repo: str = REPO, container: str = DB_CONTAINER) -> dict:
    """عرضٌ: قواعدُ جلساتٍ بلا شجرةٍ ولا اتصال. فشلُ docker/git ⇒ خطأٌ مسجَّلٌ بلا حذف."""
    try:
        rows = [
            (n, int(sz), int(c))
            for n, sz, c in (
                ln.split("|")
                for ln in _psql(
                    "select d.datname, pg_database_size(d.datname), "
                    "(select count(*) from pg_stat_activity a where a.datname=d.datname) from pg_database d",
                    container,
                )
            )
        ]
        res = classify_session_dbs(rows, live_tree_slugs(repo))
        res["error"] = None
        return res
    except Exception as e:  # noqa: BLE001 — الحاويةُ غائبةٌ أو git فاشل ⇒ لا حذف
        return {"orphans": [], "kept_live": 0, "kept_connected": [], "preview_gens": {"count": 0, "bytes": 0}, "bytes": 0, "error": str(e)}


def drop_session_dbs(orphans: list[dict], container: str = DB_CONTAINER) -> int:
    freed = 0
    for o in orphans:
        name = o["name"]
        if not SESSION_DB.match(name) or PROTECTED_DB.match(name):
            continue
        try:
            _psql(f'DROP DATABASE "{name}"', container)  # بلا FORCE: ترفضه بوستغريس إن اتّصل أحدٌ بعد الفحص
            freed += o["bytes"]
        except RuntimeError:
            pass
    return freed


def apply_files(files: list[str], roots: list[Path]) -> int:
    freed = 0
    for f in files:
        p = Path(f)
        if p.is_symlink() or not any(_inside(p, r) for r in roots):
            continue
        try:
            n = _size(p)
            p.unlink()
            freed += n
        except OSError:
            pass
    return freed


def run(apply: bool = False, evidence: Path = EVIDENCE, tmp: Path = TMP, states: dict | None = None,
        worktrees: bool = True, containers: bool = True, session_dbs: bool = True) -> dict:
    states = card_states() if states is None else states
    ev, tm = scan_evidence(states, root=evidence), scan_tmp(tmp)
    res = {
        "mode": "apply" if apply else "dry-run",
        "evidence": {"files": len(ev["files"]), "bytes": ev["bytes"], "skipped_unknown": ev["skipped_unknown"],
                     "skipped_state": len(ev["skipped_state"])},
        "tmp": {"files": len(tm["files"]), "bytes": tm["bytes"]},
        "worktrees": scan_worktrees() if worktrees else {"candidates": [], "bytes": 0},
        "containers": scan_containers() if containers else {"names": []},
        "session_dbs": scan_session_dbs() if session_dbs else classify_session_dbs([], set()) | {"error": None},
    }
    if apply:
        res["freed_bytes"] = apply_files(ev["files"], [evidence]) + apply_files(tm["files"], [tmp])
        res["freed_db_bytes"] = drop_session_dbs(res["session_dbs"]["orphans"])
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **{k: res[k] for k in ("evidence", "tmp", "freed_bytes", "freed_db_bytes")}, "session_dbs_dropped": len(res["session_dbs"]["orphans"])}, ensure_ascii=False) + chr(10))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = run(a.apply)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    mb = lambda b: f"{b / 1e6:.0f} م"  # noqa: E731
    print(f"الوضع: {res['mode']}")
    print(f"evidence: {res['evidence']['files']} ملفاً قابلاً للتقليم ({mb(res['evidence']['bytes'])})؛ تخطّي مجهول الحالة: {len(res['evidence']['skipped_unknown'])}")
    print(f"tmp_reports: {res['tmp']['files']} ملفاً ({mb(res['tmp']['bytes'])})")
    print(f"شجراتُ عملٍ مدموجةٌ نظيفة (عرضٌ فقط): {len(res['worktrees']['candidates'])} ({res['worktrees']['bytes'] / 1e9:.2f} غ)")
    print(f"حاوياتٌ متوقّفة (عرضٌ فقط): {len(res['containers']['names'])}")
    sd = res["session_dbs"]
    if sd["error"]:
        print(f"قواعدُ الجلسات: لم تُفحص ({sd['error']}) — لا حذف")
    else:
        print(f"قواعدُ جلساتٍ بلا شجرةٍ ولا اتصال: {len(sd['orphans'])} ({sd['bytes'] / 1e9:.2f} غ)؛ حيّةٌ محفوظة: {sd['kept_live']}؛ متّصلةٌ بلا شجرة (محفوظة): {len(sd['kept_connected'])}")
        print(f"أجيالُ المعاينة ss_main_preview_g<N> (عرضٌ فقط، قرارُها لـ0501): {sd['preview_gens']['count']} ({sd['preview_gens']['bytes'] / 1e9:.2f} غ)")
    if a.apply:
        print(f"المحرَّر فعلاً من القواعد: {res['freed_db_bytes'] / 1e6:.0f} م")
        print(f"المحرَّر فعلاً: {mb(res['freed_bytes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
