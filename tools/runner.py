#!/usr/bin/env python3
"""المشغّل: بطاقةٌ من «جاهزة» إلى «منشورة» بلا جلسة (D-519م، docs/runner_spec_2026-11-04.md).

النموذج يكتب الشيفرة فقط (`claude -p`)؛ كلُّ ما عداه سكربتٌ بصفر توكنز. تُجدول ويندوز هذا الملفَّ كلَّ 5 دقائق:

    python tools/runner.py            دورةٌ واحدة (قفلُ ملفٍّ يمنع دورتين، وبطاقةٌ واحدةٌ في كلّ مرّة)
    python tools/runner.py --dry      يطبع البطاقةَ المختارةَ وإعدادَها فقط

التحقّق من النسخة المثبّتة (2.1.312): `--model` و`--output-format json` و`--allowedTools` و`--max-budget-usd` موجودة،
و`--max-turns` غائب؛ فسقفُ الأدوار يُفرَض بعد التشغيل من `num_turns` في المخرجات (تجاوزه ← إحالةٌ) وسقفُ الكلفة بالعلم نفسه.
الكلفةُ في `total_cost_usd` وعددُ الأدوار في `num_turns`.

الحدودُ الصريحة: فحصُ الصحّة وأمرُ التراجع قابلان للضبط في runner_config.json؛ بلا `rollback_cmd` يُحال الفشلُ للمالك
بدل ادّعاء تراجعٍ لم يحدث.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ledger  # noqa: E402

CONFIG = ROOT / "runner_config.json"
LOCK = ROOT / "ledger" / "runner.lock"
OWNER_QUEUE = ROOT / "owner_queue.md"
REQUESTS = ROOT / "requests"
BY = "runner"
MAX_FIX_RUNS = 2
LOCK_STALE_S = 3 * 3600
MAX_INFLIGHT = 2  # بطاقتان معاً في أقصى حدّ؛ الدمجُ والنشرُ واحدةٌ تلو الأخرى (deploy_busy)
POLL_S = 60  # الدورةُ تُعاد كلَّ دقيقةٍ داخل تشغيل المهمّة المجدولة
POLL_WINDOW_S = 270  # أقلُّ من 5 دقائق حتى ينتهي التشغيلُ قبل موعد المهمّة التالي
POLL_AGAIN = ("idle", "published", "referred")  # مع waiting_*؛ غيرُها (env_down وlocked) يُنهي التشغيل
IMAGE_DIR = HERE / "prepush_image"  # Dockerfile صورة الفحص؛ يبنيها المشغّل نفسُه حين تغيب
DEFAULT_CONFIG = {
    "repo": "D:/shschool_mvp",
    "base": "origin/main",
    "sizes": {  # الوسم: (النموذج، سقف الأدوار، سقف الكلفة بالدولار)
        "صغير": ["haiku", 15, 0.5],
        "متوسط": ["sonnet", 40, 2.0],
        "كبير": ["sonnet", 80, 4.0],
        "تصميم": ["opus", 80, 6.0],
    },
    "allowed_tools": ["Read", "Edit", "Write", "Glob", "Grep", "Bash(pytest:*)", "Bash(python -m pytest:*)", "Bash(ruff:*)"],
    "health_url": "https://shschoolmvp-production.up.railway.app/health/",
    "rollback_cmd": [],  # الافتراضيّ: gh workflow run rollback.yml (runbook §4)
    "worktrees": "C:/Users/mesue/delivery_manager_work_wt",
}


class RunnerError(Exception):
    """فشلٌ يُحال للمالك بسطرٍ في owner_queue.md."""


class Transient(RunnerError):
    """عابر (تغيّر الرأس، تعذّر الدفع أو فتح الطلب أو الدمج): إعادةٌ واحدة من main المحدَّث قبل الإغلاق بتقرير (D-521م)."""


class EnvDown(Exception):
    """عطلُ البيئة (docker): يوقف الدورة ولا يُحسب على البطاقة ولا يستهلك محاولاتها (D-521م)."""


TOTAL_CAP_USD = 3.0  # السقفُ الكلّيّ للبطاقة عبر كلّ التشغيلات (D-521م)
ESCALATE = {"haiku": "sonnet"}  # الأعلى لا يُستعمل آليّاً أبداً


@dataclass
class Result:
    ok: bool
    out: str = ""
    cost: float = 0.0
    turns: int = 0
    raw: dict = field(default_factory=dict)


def load_config(path: Path = CONFIG) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.is_file():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))
    return cfg


def norm_size(label: str) -> str:
    return (label or "").replace("ّ", "").replace("ـ", "").replace("أ", "ا").strip()


def size_row(cfg: dict, label: str):
    for k, v in cfg["sizes"].items():
        if norm_size(k) == norm_size(label):
            return v
    return None


# ───────────────────────── القفل ─────────────────────────
def acquire_lock(path: Path = LOCK, now=time.time) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if now() - path.stat().st_mtime < LOCK_STALE_S:
            return False
        path.unlink()  # قفلٌ ميّت (انقطع المشغّل)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def release_lock(path: Path = LOCK) -> None:
    path.unlink(missing_ok=True)


# ───────────────────────── الاختيار ─────────────────────────
def pick_card(items: dict[str, dict], cfg: dict) -> dict | None:
    """أوّلُ بطاقةٍ موجَّهةٍ لها مواصفةٌ كاملة ومعايير قبول ووسمُ حجمٍ معروف، بالأولويّة ثمّ العمر."""
    ready = [
        i for i in items.values()
        if i.get("state") == "routed" and i.get("runner_size") and size_row(cfg, i["runner_size"])
        and i.get("accept") and i.get("spec_tier", i.get("tier")) in ("full", None, "") and not i.get("runner_hold")
    ]
    ready.sort(key=lambda i: (ledger.PRIORITIES.index(i.get("priority", "P3")) if i.get("priority") in ledger.PRIORITIES else 9, i.get("created", "")))
    return ready[0] if ready else None


def referenced_tests(tree: str, changed: list[str]) -> list[str]:
    """اختباراتٌ تذكر وحدةً معدَّلة (`quality.presentation` أو `quality/presentation.py`) أو اسمَ قالبٍ/أصلٍ معدَّل، مع ملفّات
    الاختبار المعدَّلة نفسِها: تُشغَّل في الحاوية بعد prepush.

    prepush ثابتٌ لا يختار بحسب التعديل، فكسرُ مستعمِلٍ لم يلمسه النموذج (ثلاثةُ اختباراتٍ في ملفّين لم يُفتحا) اجتاز
    الحاويةَ وظهر في CI وحده فأُغلقت البطاقة بتقرير (#1338، 2026-11-05). المطابقةُ نصّيّةٌ على مستوى الملفّ: أوسع
    من اللازم أحياناً، ولا تفوّت مستعمِلاً.
    """
    keys: set[str] = set()
    direct: list[str] = []
    for f in changed:
        p = Path(f)
        if f.startswith("tests/") and p.suffix == ".py":
            direct.append(f)
        elif p.suffix == ".py":
            keys.add(".".join(p.with_suffix("").parts))
            keys.add(f)
        elif p.suffix in (".html", ".js", ".css", ".txt", ".json", ".yml", ".yaml"):
            keys.add(p.name)
    hits = []
    if keys:
        for t in sorted((Path(tree) / "tests").rglob("test_*.py")):
            txt = t.read_text(encoding="utf-8", errors="replace")
            if any(k in txt for k in keys):
                hits.append(t.relative_to(tree).as_posix())
    return sorted(set(direct) | set(hits))


def brief(card: dict, rules: list[str], fail_log: str = "", diff: str = "") -> str:
    """موجزٌ من قالب: المواصفةُ والمعايير والقواعدُ ذات الصلة فقط، لا تاريخ ولا رسائل."""
    acc = card.get("accept")
    acc_txt = "\n".join(f"- {a}" for a in acc) if isinstance(acc, list) else str(acc)
    parts = [
        f"البطاقة {card['id']}: {card.get('problem', '')}",
        f"المطلوب (الأثر): {card.get('impact', '')}",
        f"الملفّات المسموحة: {', '.join(card.get('files_allowed') or []) or 'بحسب الحاجة'}",
        f"الملفّات الممنوعة: {', '.join(card.get('files_forbidden') or []) or 'لا شيء'}",
        f"معايير القبول:\n{acc_txt}",
        "قواعد: عدّل الملفّات واكتب الاختبارات وشغّلها فقط. لا git ولا دفع ولا نشر. التعليقات بالعربيّة.",
        "قبل أن تنتهي: `ruff format <الملفّات المعدَّلة>` ثمّ `ruff check <الملفّات المعدَّلة>`؛ فحصُ الدمج يرفض ملفّاً غيرَ منسَّق.",
        "غيّرتَ سلوكَ دالّةٍ أو قالب؟ ابحث (Grep) في tests/ عن كلّ مستعمِلٍ له وحدّث اختباراته وشغّلها؛ اختبارٌ لم تفتحه يكسر CI.",
    ]
    parts += rules
    if fail_log:
        parts += ["فشلت الفحوص؛ أصلح السبب فقط:", fail_log[-4000:], "الفرق الحاليّ:", diff[-4000:]]
    return "\n\n".join(p for p in parts if p)


# ───────────────────────── التأثيرات (قابلة للحقن) ─────────────────────────
def sh(cmd: list[str], cwd: str | None = None, timeout: int = 1800, inp: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}  # عمليةُ البوّابة تقرأ وصف الطلب بـcp1256 على ويندوز فلا يطابق سطرُ الاعتماد
    return subprocess.run(cmd, cwd=cwd, input=inp, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout, check=False, env=env)  # noqa: S603


def _git(tree: str, *args: str) -> tuple[int, str]:
    p = sh(["git", *args], tree)
    return p.returncode, p.stdout.strip()


class Effects:
    """كلُّ ما يلمس العالمَ: git وclaude وgh والفحوص؛ تُستبدل في الاختبارات."""

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def prepare_tree(self, card_id: str, round_no: int = 1) -> tuple[str, str]:
        repo, wt = self.cfg["repo"], self.cfg["worktrees"]
        suffix = f"-{time.strftime('%m%d%H%M%S')}-r{round_no}"  # فريدٌ لكلّ محاولة: لا يصطدم بفرعٍ باقٍ من محاولة سابقة
        branch = f"claude/runner-{card_id.lower()}{suffix}"
        tree = f"{wt}/runner-{card_id}{suffix}"
        sh(["git", "fetch", "origin", "main"], repo)
        p = sh(["git", "worktree", "add", "-B", branch, tree, self.cfg["base"]], repo)
        if p.returncode:
            raise RunnerError(f"تعذّر إنشاءُ الشجرة: {p.stderr.strip()[:200]}")
        return tree, branch

    def isolation_args(self, tree: str) -> list[str]:
        """تشغيلٌ بلا خطّافات المشروع والمستخدم (فخطّاف SessionStart session-start-prod.sh يحرّك رأس فرعٍ نظيف إلى إيداع الإنتاج لا main)،
        ويبقى حارسُ git وحده بإعداداتٍ خاصّةٍ بالتشغيل."""
        guard = Path(tree) / ".claude" / "hooks" / "guard_git.sh"
        hooks = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": f'bash "{guard.as_posix()}"', "timeout": 10}]}]}} if guard.is_file() else {}
        return ["--setting-sources", "local", "--settings", json.dumps(hooks)]

    def run_model(self, tree: str, prompt: str, model: str, budget: float) -> Result:
        cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--max-budget-usd", str(budget),
               "--allowedTools", *self.cfg["allowed_tools"], "--permission-mode", "acceptEdits",
               *self.isolation_args(tree)]
        p = sh(cmd, tree, 3600, prompt)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            return Result(False, (p.stdout + p.stderr)[-500:])
        return Result(not data.get("is_error"), str(data.get("result", ""))[-500:], float(data.get("total_cost_usd") or 0),
                      int(data.get("num_turns") or 0), data)

    @staticmethod
    def docker_up(docker) -> bool:
        """docker يستجيب (المحرّك لا الصورة): التمييزُ بين «المحرّك متوقّف» و«الصورة غائبة» شرطُ العلاج الصحيح لكلٍّ."""
        rc, _ = docker(["info", "--format", "ok"], 60)
        return rc == 0

    def build_image(self, docker=None) -> None:
        """الصورةُ غائبةٌ والمحرّكُ يعمل: تُبنى من Dockerfile المرفق (IMAGE_DIR) بلا انتظار يدٍ تبنيها.

        قبل 2026-11-05 كان المشغّل ينتظر عشر دقائق «حتى تعود الصورة» ثمّ يبلّغ EnvDown كلَّ دورة، فعلقت البطاقةُ
        الأولى (W-20261105-001) في الطابور مع أنّ docker يعمل. الفشلُ في البناء EnvDown: علّةُ بيئةٍ لا تُحسب على البطاقة.
        """
        import flow_pump as fp  # noqa: PLC0415

        docker = docker or fp._docker
        if not (IMAGE_DIR / "Dockerfile").is_file():
            raise EnvDown(f"صورة {fp.PREPUSH_IMAGE} غائبة ولا Dockerfile في {IMAGE_DIR}")
        rc, out = docker(["build", "-t", fp.PREPUSH_IMAGE, str(IMAGE_DIR)], 1800)
        if rc:
            raise EnvDown(f"تعذّر بناءُ صورة {fp.PREPUSH_IMAGE}: {out.strip()[-200:]}")

    def preflight(self, sleep=time.sleep, wait_s: int = 600, docker=None) -> None:
        """المحرّكُ متوقّف: يشغّل Docker Desktop وينتظر حتى 10 دقائق ثمّ EnvDown. المحرّكُ يعمل والصورةُ غائبة: تُبنى الآن.

        لا تُحسب أيٌّ من الحالتين على البطاقة (D-521م).
        """
        import flow_pump as fp  # noqa: PLC0415

        docker = docker or fp._docker
        if fp._image_present(docker):
            return
        if not self.docker_up(docker):
            exe = self.cfg.get("docker_desktop", "C:/Program Files/Docker/Docker/Docker Desktop.exe")
            if Path(exe).is_file():
                subprocess.Popen([exe], close_fds=True)  # noqa: S603
            end = time.time() + wait_s
            while not self.docker_up(docker):
                if time.time() >= end:
                    raise EnvDown(f"docker متوقّف ولم يعد خلال {wait_s // 60} دقائق")
                sleep(15)
        if not fp._image_present(docker):
            self.build_image(docker)

    def autoformat(self, tree: str) -> list[str]:
        """تنسيقُ ما عدّله النموذج من بايثون بـruff قبل الفحص: حتميٌّ وبصفر توكنز.

        قبل 2026-11-05 أنفق المشغّل ثلاثةَ تشغيلاتٍ ونحو عشرين دقيقةً من فحوص الحاوية على بطاقةٍ لم يكن ينقصها إلّا
        `ruff format`؛ فما تصلحه أداةٌ لا يُعاد إلى النموذج. غيابُ ruff لا يُكتم: يُرفع RunnerError كعلّة بيئة.
        """
        files = [f for f in self.changed(tree) if f.endswith(".py") and (Path(tree) / f).is_file()]
        if not files:
            return []
        p = sh([sys.executable, "-m", "ruff", "format", "--", *files], tree, 300)
        if p.returncode:
            raise RunnerError(f"بيئةٌ: تعذّر ruff format — {(p.stdout + p.stderr).strip()[-200:]}")
        return files

    def quick_check(self, tree: str) -> tuple[bool, str]:
        """فحصٌ بالثواني قبل الحاوية: أخطاءُ الصياغة والأسماءُ غير المعرَّفة فقط، لأنّ ruff الجهاز أحدثُ من نسخة CI
        فلا تُطبَّق قواعدُ المستودع هنا. خروجٌ غيرُ 1 (أداةٌ غائبة أو علّةُ تشغيل) لا يُسقط شيئاً: الحكمُ لـprepush."""
        files = [f for f in self.changed(tree) if f.endswith(".py") and (Path(tree) / f).is_file()]
        if not files:
            return True, ""
        p = sh([sys.executable, "-m", "ruff", "check", "--isolated", "--select", "E9,F821,F822,F823", "--", *files], tree, 120)
        return p.returncode != 1, (p.stdout + p.stderr)[-4000:]

    def verify(self, tree: str) -> tuple[bool, str]:
        """prepush داخل الحاوية كما تفعل المضخّة (صورةٌ وقاعدةُ اختبارٍ مؤقّتة)؛ علّةُ البيئة (docker/الصورة/غير مقيس) تُحال فوراً بلا تشغيل إصلاح."""
        import flow_pump as fp  # noqa: PLC0415

        quick_ok, quick_log = self.quick_check(tree)
        if not quick_ok:  # لا تُهدر سبعُ دقائق حاويةٍ على خطأٍ يُرى في ثوانٍ
            return False, quick_log
        if not fp._image_present(fp._docker):
            raise RunnerError(f"بيئةٌ: صورة {fp.PREPUSH_IMAGE} غائبة أو docker متوقّف — لا يُصلحه النموذج")
        rc, gitdir = _git(tree, "rev-parse", "--absolute-git-dir")
        rc2, common = _git(tree, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if rc or rc2:
            raise RunnerError("بيئةٌ: تعذّرت قراءةُ مجلّد git للشجرة")
        name = f"runner-{Path(tree).name.lower()}"
        extra = referenced_tests(tree, self.changed(tree))

        def cmd_for(net: str) -> list[str]:
            cmd = fp.prepush_command(tree, gitdir, common, name, net, fp.root_prepush_scripts(tree))
            if extra:  # تُشغَّل في الحاوية نفسها بعد prepush (run_prepush.py يقرأ المتغيّر)
                i = cmd.index(fp.PREPUSH_IMAGE)
                cmd[i:i] = ["-e", "PREPUSH_EXTRA_TESTS=" + " ".join(extra)]
            return cmd

        code, log = fp.run_with_db(fp._docker, cmd_for, name, 3600)
        if "غير مقيس" in log or "تعذّر إنشاء" in log or "تعذّر" in log[:200]:
            raise RunnerError("بيئةٌ: الفحص غير مقيس في الحاوية — " + log.strip()[-160:])
        return code == 0 and fp.PREPUSH_OK_LINE in log, log[-4000:]

    def changed(self, tree: str) -> list[str]:
        p = sh(["git", "status", "--porcelain"], tree)
        return [ln[3:].strip().strip('"') for ln in p.stdout.splitlines() if ln.strip()]

    def diff(self, tree: str) -> str:
        return sh(["git", "diff", "HEAD"], tree).stdout

    def commit_push(self, tree: str, branch: str, files: list[str], msg: str) -> str:
        sh(["git", "add", "--", *files], tree)
        p = sh(["git", "commit", "-m", msg], tree)
        if p.returncode:
            raise RunnerError(f"تعذّر الإيداع: {(p.stdout + p.stderr)[-200:]}")
        head = sh(["git", "rev-parse", "HEAD"], tree).stdout.strip()
        p = sh(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], tree)
        if p.returncode:
            raise Transient(f"تعذّر الدفع: {p.stderr.strip()[-200:]}")
        return head

    def open_pr(self, tree: str, branch: str, title: str, body: str) -> int:
        p = sh(["gh", "pr", "create", "--head", branch, "--title", title, "--body", body], tree)
        if p.returncode:
            raise Transient(f"تعذّر فتحُ الطلب: {p.stderr.strip()[-200:]}")
        return int(p.stdout.strip().rstrip("/").rsplit("/", 1)[-1])

    def set_pr_body(self, tree: str, pr: int, body: str) -> None:
        p = sh(["gh", "pr", "edit", str(pr), "--body", body], tree)
        if p.returncode:
            raise Transient(f"تعذّر تحديثُ وصف الطلب: {p.stderr.strip()[-200:]}")

    def close_old_prs(self, tree: str, card_id: str, new_pr: int) -> list[int]:
        """طلباتٌ مفتوحةٌ سابقةٌ للبطاقة نفسها: تُغلق بتعليق «حلّ محلّه #جديد» ويُحذف فرعُها."""
        p = sh(["gh", "pr", "list", "--state", "open", "--search", f"{card_id} in:title", "--json", "number,headRefName"], tree)
        try:
            rows = json.loads(p.stdout or "[]")
        except ValueError:
            return []
        closed = []
        for r in rows:
            if r["number"] != new_pr and sh(["gh", "pr", "close", str(r["number"]), "--delete-branch", "--comment", f"حلّ محلّه #{new_pr}"], tree).returncode == 0:
                closed.append(r["number"])
        return closed

    def checks_state(self, tree: str, pr: int) -> str:
        """pending | green | red من `gh pr checks`."""
        out = sh(["gh", "pr", "checks", str(pr)], tree).stdout.lower()
        if not out.strip() or any(w in out for w in ("pending", "queued", "in_progress", "waiting")):
            return "pending"
        return "red" if "fail" in out else "green"

    def failed_names(self, tree: str, pr: int) -> list[str]:
        out = sh(["gh", "pr", "checks", str(pr)], tree).stdout
        return [ln.split("\t")[0] for ln in out.splitlines() if "\tfail" in ln]

    def failed_checks(self, tree: str, pr: int) -> str:
        return "، ".join(self.failed_names(tree, pr))[:300] or "؟"

    def pr_body_of(self, tree: str, pr: int) -> str:
        return sh(["gh", "pr", "view", str(pr), "--json", "body", "-q", ".body"], tree).stdout

    def gate_script(self, tree: str) -> str:
        """بوّابةُ الدمج بنسخة main لا بنسخة فرع الطلب (2026-11-05).

        قبلها كانت تُشغَّل من الشجرة، ففرعٌ يعدّل `scripts/auto_merge_gate.py` في ملفّه يقبل نفسَه ويدمجه المشغّل (ثغرة)؛
        وبطاقةٌ على فرعٍ أقدمَ من إصلاحٍ في البوّابة تُرفض بنسخةٍ عفا عنها main (#1338). الحَكَمُ main؛ وإن خلت منها
        البوّابةُ فنسخةُ الشجرة. تُكتب إلى ملفٍّ مؤقّتٍ خارجَ الشجرة وتعمل بـcwd الشجرة ليجد gh المستودع.
        """
        repo, base = self.cfg["repo"], self.cfg["base"]
        sh(["git", "fetch", "-q", "origin", "main"], repo)
        p = sh(["git", "show", f"{base}:scripts/auto_merge_gate.py"], repo)
        if p.returncode or not p.stdout.strip():
            return "scripts/auto_merge_gate.py"
        out = Path(tempfile.gettempdir()) / f"auto_merge_gate_main_{os.getpid()}.py"
        out.write_text(p.stdout, encoding="utf-8")
        return str(out)

    def gate_reasons(self, tree: str, pr: int) -> str:
        p = sh([sys.executable, self.gate_script(tree), str(pr)], tree)
        return " | ".join(ln.strip(" -") for ln in p.stdout.splitlines()[1:6])[:300] or "؟"

    def gate_allows(self, tree: str, pr: int) -> bool:
        return sh([sys.executable, self.gate_script(tree), str(pr)], tree).returncode == 0

    def remote_head(self, branch: str) -> str:
        out = sh(["git", "ls-remote", "origin", f"refs/heads/{branch}"], self.cfg["repo"]).stdout.split()
        return out[0] if out else ""

    def merge(self, tree: str, pr: int) -> bool:
        return sh(["gh", "pr", "merge", str(pr), "--auto"], tree).returncode == 0  # كما تفعل البوّابة: الطابورُ يفرض استراتيجيّته

    def in_deploy_window(self, tree: str) -> bool:
        return sh([sys.executable, "scripts/deploy_window.py"], tree).returncode == 0

    def pr_state(self, tree: str, pr: int) -> tuple[str, str]:
        p = sh(["gh", "pr", "view", str(pr), "--json", "state,mergeCommit"], tree)
        try:
            d = json.loads(p.stdout)
        except ValueError:
            return "UNKNOWN", ""
        return d.get("state", "UNKNOWN"), (d.get("mergeCommit") or {}).get("oid", "")

    def prod_status(self) -> tuple[str, bool]:
        """(commit الإنتاج من /health/، وهل status=ok وكلّ checks=ok)."""
        url = self.cfg.get("health_url")
        if not url:
            return "", False
        import urllib.request  # noqa: PLC0415

        try:
            with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
                d = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError):
            return "", False
        return str(d.get("commit") or ""), d.get("status") == "ok" and all(v == "ok" for v in (d.get("checks") or {}).values())

    def contains(self, tree: str, oid: str, prod: str) -> bool:
        """commit الإنتاج هو oid أو من سلالته (compare: identical|ahead)."""
        p = sh(["gh", "api", f"repos/sh-school/shschool_mvp/compare/{oid}...{prod}", "--jq", ".status"], tree)
        return p.stdout.strip() in ("identical", "ahead")

    def healthy(self) -> bool:
        url = self.cfg.get("health_url")
        if not url:
            return False  # بلا عنوانٍ لا ادّعاءَ صحّة
        import urllib.request  # noqa: PLC0415

        try:
            with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
                return r.status == 200
        except OSError:
            return False

    def main_sha(self) -> str:
        out = sh(["git", "ls-remote", "origin", "refs/heads/main"], self.cfg["repo"]).stdout.split()
        return out[0] if out else ""

    def rollback(self, good_sha: str, reason: str) -> bool:
        """runbook §4 الخيار أ: يُطلق rollback.yml فيفتح طلبَ دمجٍ يعيد شجرةَ main إلى آخر نشرٍ سليم؛ التراجعُ لا يقع قبل دمج ذلك الطلب."""
        if not good_sha:
            return False
        cmd = self.cfg.get("rollback_cmd") or ["gh", "workflow", "run", "rollback.yml", "-f", "commit_sha={sha}", "-f", "reason={reason}"]
        return sh([c.format(sha=good_sha, reason=reason) for c in cmd], self.cfg["repo"]).returncode == 0

    def remove_tree(self, tree: str) -> None:
        if not Path(tree).resolve().is_relative_to(Path(self.cfg["worktrees"]).resolve()):
            return  # لا يُزال إلا ما أنشأه المشغّل تحت مجلّد أشجاره (الشجرة الرئيسة لا تُمسّ أبداً)
        sh(["git", "worktree", "remove", "--force", tree], self.cfg["repo"])


# ───────────────────────── الإحالة والتسجيل ─────────────────────────
def refer(card_id: str, reason: str, queue: Path | None = None) -> None:
    queue = queue or OWNER_QUEUE
    line = f"- {time.strftime('%Y-%m-%d %H:%M')} {card_id}: {reason}\n"
    with queue.open("a", encoding="utf-8") as f:
        f.write(line)


def record_run(card_id: str, label: str, res: Result, path=None) -> None:
    ledger.append_event("note", card_id, {"text": f"[مشغّل] {label}: كلفة={res.cost:.4f}$ أدوار={res.turns}", "by": BY}, path)


# ───────────────────────── الدورة ─────────────────────────
def pr_body(card: dict, head: str = "") -> str:
    """وصفُ الطلب؛ لبطاقاتٍ source=owner سطرُ اعتماد المالك بصيغة D-520م (طلبُه في الخطوة الأولى هو الاعتماد)."""
    body = f"البطاقة {card['id']} — المشغّل."
    if card.get("source") == "owner" and card.get("approval") != "معاينة":
        body += f"\n\nاعتُمد من المالك مباشرةً بلا معاينة 8500 — {time.strftime('%Y-%m-%d')}{(' — الرأس ' + head[:8]) if head else ''} (D-520م، {card['id']})"
    if card.get("source") == "owner" and card.get("approval") == "معاينة" and card.get("preview_approved"):
        body += f"\n\nاعتُمد من المالك على 8500 — {time.strftime('%Y-%m-%d')}{(' — الرأس ' + head[:8]) if head else ''} (D-528م، {card['id']})"
    return body


def finish(card: dict, cfg: dict, fx: Effects, lpath, tree: str, branch: str, head: str, pr: int) -> str:
    """ما بعد فتح الطلب: انتظار CI (معلَّقة = تبقى للدورة التالية)، البوّابة، الرأس، النافذة، الدمج، النشر، الصحّة، الإغلاق."""
    st = fx.checks_state(tree, pr)
    if st == "pending":
        return "waiting_ci"
    preview = card.get("approval") == "معاينة"
    failed = fx.failed_names(tree, pr) if st != "green" else []
    # بطاقةُ المعاينة: فحصُ «سطر الاعتماد» أحمرُ بطبيعته حتى يُكتب السطرُ بعد اعتماد المالك، فليس فشلاً. قبل 2026-11-05 كان
    # يُعدّ فشلَ CI فتُغلق كلُّ بطاقة معاينةٍ بتقرير قبل أن تبلغ المعاينةَ أصلاً (W-20261105-001 مرّتين).
    real = [f for f in failed if not (preview and APPROVAL_CHECK in f)]
    if real:
        raise RunnerError(f"فحوصُ CI حمراء على الطلب {pr}: {'، '.join(real)[:300]}")
    if preview:
        if not card.get("preview_approved"):
            if not card.get("preview_noted"):  # سطرٌ واحد في طابور المالك لا كلَّ دورة
                refer(card["id"], f"جاهز للمعاينة على 8500: الطلب #{pr} — بعد اعتمادك يُدمج (preview_approved)", None)
                ledger.append_event("update", card["id"], {"preview_noted": True}, lpath)
            return "waiting_preview"
        body = pr_body(card, head)
        if fx.pr_body_of(tree, pr).strip() != body.strip():  # يُكتب مرّةً؛ فحصُ السطر يُعاد عند edited فيخضرّ في الدورة التالية
            fx.set_pr_body(tree, pr, body)
            return "waiting_ci"
        if failed:  # السطرُ مكتوبٌ وفحصُه لم يُعَد بعد
            return "waiting_ci"
    if not fx.gate_allows(tree, pr):
        raise RunnerError(f"بوّابةُ الدمج الآليّ رفضت الطلب {pr}: {fx.gate_reasons(tree, pr)}")
    if fx.remote_head(branch) != head:
        raise Transient("الرأسُ تغيّر بعد الفحص")
    if not fx.in_deploy_window(tree):  # الدمجُ نشرٌ فوريّ: خارجَ النافذة لا دمج، ويبقى الطلبُ مفتوحاً
        return "waiting_window"
    if deploy_busy(card["id"], lpath):  # نشرٌ واحدٌ في الطريق فقط، فيبقى هدفُ التراجع عند فشل الصحّة واضحاً
        return "waiting_turn"
    return merge_and_publish(card, fx, lpath, tree, pr, r_stage="merge")


def deploy_busy(card_id: str, lpath=None) -> bool:
    """هل بطاقةٌ أخرى دخلت الدمجَ ولم تُنشر بعد؟"""
    items = ledger.reduce_state(ledger.load_events(lpath))
    return any(i["id"] != card_id and (i.get("runner_resume") or {}).get("stage") in ("merged_wait", "deploy_wait") for i in items.values())


def inflight(items: dict[str, dict]) -> list[dict]:
    """بطاقاتٌ فتحت طلبها ولم تنتهِ، الأقدمُ أوّلاً فهي الأسبقُ إلى الدمج."""
    cards = [i for i in items.values() if i.get("state") in ("in_progress", "merged") and i.get("runner_resume")]
    return sorted(cards, key=lambda i: i.get("created", ""))


APPROVAL_CHECK = "سطرُ الاعتماد مطابقٌ للرأس"  # اسمُ فحص CI (pr-approval-head.yml) الذي يحمرّ حتى يُكتب السطر
MERGE_WAIT_S = 60 * 60
DEPLOY_WAIT_S = 120 * 60


def _since(card: dict, stage: str, now) -> float:
    """بدءُ انتظار المرحلة: يُخزَّن في runner_resume فلا يُصفَّر بين الدورات."""
    r = card.get("runner_resume") or {}
    return float(r.get(f"{stage}_since") or now())


def merge_and_publish(card: dict, fx: Effects, lpath, tree: str, pr: int, r_stage: str = "merge", now=None) -> str:
    """الدمج ثم انتظار MERGED ثم انتظار ظهور commit الدمج في /health/؛ «منشورة» لا تُكتب قبله (ثغرة 19:00، D-521م)."""
    cid = card["id"]
    now = now or (lambda: time.time())  # يُقرأ وقتَ الاستدعاء لا وقتَ التعريف
    resume_ = dict(card.get("runner_resume") or {})
    stage = resume_.get("stage", r_stage)
    if stage == "merge":
        resume_["good"] = fx.main_sha()  # آخرُ نشرٍ سليم قبل هذا الدمج
        if not fx.merge(tree, pr):
            raise Transient(f"تعذّر دمجُ الطلب {pr}")
        resume_.update(stage="merged_wait", merged_wait_since=now())
        ledger.append_event("update", cid, {"runner_resume": resume_}, lpath)
        stage = "merged_wait"
    if stage == "merged_wait":
        state, oid = fx.pr_state(tree, pr)
        if state != "MERGED":
            if state == "CLOSED" or now() - _since(card, "merged_wait", now) > MERGE_WAIT_S:
                raise RunnerError(f"الطلب {pr} لم يُدمج ({state}) — أُخرج من الطابور أو انقضت مهلة 60 دقيقة")
            if state == "OPEN":
                fx.merge(tree, pr)  # لا يزال مفتوحاً بلا طابور: يُعاد طلب الدمج (idempotent)
            ledger.append_event("update", cid, {"runner_resume": resume_}, lpath)
            return "waiting_merge"
        ledger.append_event("state", cid, {"state": "merged", "by": BY, "merge_commit": oid}, lpath)
        resume_.update(stage="deploy_wait", oid=oid, deploy_wait_since=now())
        ledger.append_event("update", cid, {"runner_resume": resume_}, lpath)
        stage = "deploy_wait"
    oid = resume_.get("oid", "")
    prod, healthy = fx.prod_status()
    if prod and oid and fx.contains(tree, oid, prod):
        if healthy:
            ledger.append_event("state", cid, {"state": "published", "by": BY}, lpath)
            return "published"
        if fx.rollback(resume_.get("good", ""), f"فشل فحص الصحة بعد {cid}"):
            raise RunnerError(f"فشل فحصُ الصحّة بعد النشر فأُطلق التراجعُ الآليّ إلى {resume_.get('good', '')[:8]} (الطلب {pr})")
        raise RunnerError(f"فشل فحصُ الصحّة بعد النشر ولا تراجعَ آليّ مضبوط (الطلب {pr})")
    if now() - _since(card, "deploy_wait", now) > DEPLOY_WAIT_S:
        refer(cid, f"دُمجت (الطلب {pr}) ولم تُنشر خلال 120 دقيقة؛ الإنتاج على {prod[:8] or '؟'}")  # تقريرٌ فقط: لا تراجع ولا إغلاق
        ledger.append_event("update", cid, {"runner_resume": None}, lpath)
        return "merged"
    ledger.append_event("update", cid, {"runner_resume": resume_}, lpath)
    return "waiting_deploy"


def _tiers(cfg: dict, card: dict) -> list[tuple[str, int, float]]:
    """سلّم النماذج للبطاقة: نموذجُ وسمها ثمّ (هايكو فقط) سونيت؛ الأعلى لا يُستعمل آليّاً."""
    model, max_turns, budget = size_row(cfg, card["runner_size"])
    tiers = [(model, max_turns, budget)]
    if model in ESCALATE:
        up = ESCALATE[model]
        row = next((v for v in cfg["sizes"].values() if v[0] == up), None)
        if row:
            tiers.append((up, row[1], row[2]))
    return tiers


def process(card: dict, cfg: dict, fx: Effects, lpath=None) -> str:
    """بطاقةٌ واحدة من أوّلها إلى آخرها؛ عابرٌ يُعاد مرّة، وفشلُ النموذج يتصاعد هايكو←سونيت بسقف كلّيّ 3$ ثمّ يُغلق بتقرير (D-521م)."""
    cid = card["id"]
    fx.preflight()  # EnvDown تخرج قبل أيّ تغيير للبطاقة فلا تُحسب عليها
    ledger.append_event("state", cid, {"state": "in_progress", "by": BY, "held_by": BY}, lpath)
    spent = 0.0
    for round_no in (1, 2):  # الجولة الثانية للعابر فقط
        tree, keep = "", False
        try:
            tree, branch = fx.prepare_tree(cid, round_no)
            rules = [Path(p).read_text(encoding="utf-8")[:3000] for p in card.get("rules") or [] if Path(p).is_file()]
            prompt, ok = brief(card, rules), False
            for model, max_turns, budget in _tiers(cfg, card):
                for attempt in range(MAX_FIX_RUNS + 1):
                    res = fx.run_model(tree, prompt, model, min(budget, TOTAL_CAP_USD - spent))
                    record_run(cid, f"{model} تشغيل {attempt + 1}", res, lpath)
                    spent += res.cost
                    if not res.ok or spent >= TOTAL_CAP_USD:  # سقفُ الأدوار لا يحكم؛ الفحصُ والميزانيةُ هما الحماية
                        break  # فشل النموذج: التصعيد إلى الأعلى مسموحُ السلّم
                    fx.autoformat(tree)  # ما تصلحه الأداةُ لا يُعاد إلى النموذج
                    ok, log = fx.verify(tree)
                    if ok and not fx.changed(tree):
                        ok = False  # لم يُحدث تغييراً: يصعد إلى السلّم التالي (D-522م)
                        break
                    if ok:
                        break
                    prompt = brief(card, rules, log, fx.diff(tree))
                if ok or spent >= TOTAL_CAP_USD:
                    break
            if not ok:
                raise RunnerError(f"فشل النموذج بعد السلّم الكامل (كلفة={spent:.2f}$ من {TOTAL_CAP_USD}$)")
            files = fx.changed(tree)
            if not files:
                raise RunnerError("لم يُحدث النموذجُ أيَّ تغيير")
            head = fx.commit_push(tree, branch, files, f"{cid}: {card.get('problem', '')[:60]}")
            pr = fx.open_pr(tree, branch, f"{cid}: {card.get('problem', '')[:60]}", pr_body(card, head))
            for old_pr in fx.close_old_prs(tree, cid, pr):
                ledger.append_event("note", cid, {"text": f"[مشغّل] أُغلق الطلب القديم #{old_pr}: حلّ محلّه #{pr}", "by": BY}, lpath)
            card["runner_resume"] = {"pr": pr, "branch": branch, "head": head, "tree": tree}
            ledger.append_event("update", cid, {"pr": pr, "runner_resume": card["runner_resume"]}, lpath)
            out = finish(card, cfg, fx, lpath, tree, branch, head, pr)
            keep = out.startswith("waiting")
            return out
        except Transient as exc:
            ledger.append_event("note", cid, {"text": f"[مشغّل] عابر في الجولة {round_no}: {exc}"[:400], "by": BY}, lpath)
            if round_no == 2:
                return fail(card, exc, fx, lpath)
        except RunnerError as exc:
            return fail(card, exc, fx, lpath)
        finally:
            if tree and not keep:
                fx.remove_tree(tree)
    return "referred"


def fail(card: dict, exc: Exception, fx: Effects, lpath=None) -> str:
    """إغلاقٌ بتقرير: لا يُنتظر ردٌّ من المالك (D-521م)؛ سطرُ تقرير وملاحظةٌ في الدفتر وحالةُ closed."""
    cid = card["id"]
    ledger.append_event("note", cid, {"text": f"[مشغّل] أُغلقت بتقرير: {exc}"[:400], "by": BY}, lpath)
    ledger.append_event("update", cid, {"runner_hold": True, "runner_resume": None}, lpath)
    ledger.append_event("state", cid, {"state": "closed", "by": BY, "held_by": ""}, lpath)
    refer(cid, str(exc)[:300])
    return "referred"


def resume(card: dict, cfg: dict, fx: Effects, lpath=None) -> str:
    """بطاقةٌ فتحت طلبها وتنتظر الفحوص أو النافذة: تُكمَل من البوّابة بلا تشغيل نموذج."""
    r = card["runner_resume"]
    try:
        if r.get("stage") in ("merged_wait", "deploy_wait"):  # بعد الدمج: لا إعادةَ فحوصٍ ولا بوّابة
            out = merge_and_publish(card, fx, lpath, r["tree"], r["pr"])
        else:
            out = finish(card, cfg, fx, lpath, r["tree"], r["branch"], r["head"], r["pr"])
    except RunnerError as exc:
        out = fail(card, exc, fx, lpath)
    if not out.startswith("waiting"):
        ledger.append_event("update", card["id"], {"runner_resume": None}, lpath)
        fx.remove_tree(r["tree"])
    return out


def intake_requests(cfg: dict, lpath=None) -> int:
    """ملفّاتُ requests/*.md ← بطاقاتٌ بلا نموذج؛ القالب: عنوان/مطلوب/معايير/وسم، سطرٌ لكلّ مفتاح."""
    n = 0
    if not REQUESTS.is_dir():
        return 0
    for f in sorted(REQUESTS.glob("*.md")):
        fields = {}
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ":" in ln:
                k, v = ln.split(":", 1)
                fields[k.strip()] = v.strip()
        missing = [k for k in ("العنوان", "المطلوب", "معايير القبول", "الوسم") if not fields.get(k)]
        if missing or not size_row(cfg, fields.get("الوسم", "")):
            refer(f.stem, "رُفض الطلب " + f.name + " — " + (f"الحقل الناقص: {'، '.join(missing)}" if missing else "وسمٌ مجهول"))
            f.rename(f.with_suffix(".rejected"))
            continue
        cid = ledger.new_id(ledger.load_events(lpath))
        touches = [t.strip() for t in fields.get("يمسّ", "").split("،") if t.strip()]
        approval = "معاينة" if fields.get("الاعتماد") == "معاينة" or (not fields.get("الاعتماد") and fields["الوسم"] == "تصميم") else "مباشر"
        ledger.append_event("created", cid, {"problem": fields["العنوان"], "impact": fields["المطلوب"],
                                              "accept": [a.strip() for a in fields["معايير القبول"].split("؛") if a.strip()],
                                              "approval": approval,
                                              "priority": fields.get("الأولوية") if fields.get("الأولوية") in ledger.PRIORITIES else "P2",
                                              "runner_size": fields["الوسم"], "source": "owner",
                                              "touches": touches}, lpath)
        ledger.append_event("state", cid, {"state": "routed", "by": BY}, lpath)
        if touches:  # الأمن والصلاحيات والأدوار والهجرات تردّها البوّابة: لا نبني ثم نُرَدّ
            ledger.append_event("update", cid, {"runner_hold": True}, lpath)
            refer(cid, "يمسّ " + "، ".join(touches) + " فلن يُدمج آليًّا — يلزم قرارك")
        f.rename(f.with_suffix(".done"))
        n += 1
    return n


def report_env(msg: str, queue: Path | None = None) -> str:
    """تقريرٌ واحدٌ فقط لعطل البيئة في اليوم؛ لا يمسّ البطاقة."""
    queue = queue or OWNER_QUEUE
    mark = f"بيئة {time.strftime('%Y-%m-%d')}"
    if not (queue.is_file() and mark in queue.read_text(encoding="utf-8")):
        refer("RUNNER", f"{mark}: {msg}", queue)
    return "env_down"


def run_cycle(cfg: dict | None = None, fx: Effects | None = None, lpath=None, lock: Path = LOCK) -> str:
    cfg = cfg or load_config()
    if not acquire_lock(lock):
        return "locked"
    try:
        intake_requests(cfg, lpath)
        fx = fx or Effects(cfg)
        out = "idle"
        for waiting in inflight(ledger.reduce_state(ledger.load_events(lpath))):
            out = resume(waiting, cfg, fx, lpath)
        items = ledger.reduce_state(ledger.load_events(lpath))
        if len(inflight(items)) >= MAX_INFLIGHT:
            return out
        card = pick_card(items, cfg)
        if not card:
            return out
        try:
            return process(card, cfg, fx, lpath)
        except EnvDown as exc:
            return report_env(str(exc))
    finally:
        release_lock(lock)


def poll(cfg: dict, cycle=run_cycle, sleep=time.sleep, clock=time.monotonic) -> None:
    """دوراتٌ كلَّ دقيقةٍ داخل تشغيل المهمّة: مهمّةُ الخمس دقائق تبقى كما هي ويقصر الانتظار بين مراحل البطاقة."""
    end = clock() + POLL_WINDOW_S
    while True:
        out = cycle(cfg)
        print(out)
        if not (out in POLL_AGAIN or out.startswith("waiting")) or clock() + POLL_S > end:
            return
        sleep(POLL_S)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="مشغّل البطاقات بلا جلسة")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    if a.dry:
        card = pick_card(ledger.reduce_state(ledger.load_events()), cfg)
        print(card["id"] if card else "idle")
        return 0
    poll(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
