"""فحصُ تصادم أرقام الهجرات بلا gh (W-20261026-014): صورةُ maestro-prepush بلا gh فكان الفحصُ «غير مقيس» فيسقط الإيصالُ كلُّه.

«الطلباتُ المفتوحة» هنا فروعُ origin/* غيرُ المدموجة في origin/main، تُقرأ من مجلّد .git الرئيس المركَّب للقراءة (يلزم أن يكون
المضيفُ قد جلب origin حديثاً). هي مجموعةٌ فوقيّةٌ من الطلبات المفتوحة (فرعٌ بلا طلب أو دُمج بـsquash ولم يُحذف يدخلها)،
فالخطأ المحتمل إنذارٌ زائد لا نجاحٌ زائف؛ والملفُّ ذاتُه بالمسار نفسِه ليس تصادماً في حارس المنصّة.
"""

from __future__ import annotations

import os


def open_pull_requests(run, base: str = "origin/main", not_measured=RuntimeError) -> dict[str, dict]:
    """بصيغة scripts/check_migration_collisions.open_pull_requests: التسمية ← {head, branch, files}. `run` أمرٌ → CompletedProcess."""
    refs = run(["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/remotes/origin"])
    if refs.returncode != 0:
        raise not_measured("تعذّر قراءة فروع origin")
    out: dict[str, dict] = {}
    for line in refs.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        name, sha = parts
        branch = name.removeprefix("origin/")
        if branch in ("HEAD", "main") or name == "origin":
            continue
        if run(["git", "merge-base", "--is-ancestor", sha, base]).returncode == 0:
            continue  # مدموجٌ في main: ليس مفتوحاً
        mb = run(["git", "merge-base", base, sha])
        if mb.returncode != 0 or not mb.stdout.strip():
            continue
        diff = run(["git", "diff", "--name-only", "--diff-filter=A", mb.stdout.strip(), sha])
        if diff.returncode != 0:
            raise not_measured(f"تعذّر git diff للفرع {branch}")
        out[f"{branch} (فرع بعيد)"] = {"head": sha, "branch": branch, "files": diff.stdout.splitlines()}
    return out


def check(pc, cmc):
    """بديلُ pc.check_migration_collisions داخل الحاوية: يستعمل منطقَ المنصّة نفسَه (cmc.run) ويستبدل مصدرَ الطلبات بفروع git."""
    git_dir = os.environ.get("PREPUSH_GIT_DIR")
    saved = {k: os.environ.get(k) for k in ("GIT_DIR", "GIT_WORK_TREE")}
    if git_dir:
        os.environ["GIT_DIR"], os.environ["GIT_WORK_TREE"] = git_dir, os.getcwd()
    cmc.open_pull_requests = lambda: open_pull_requests(cmc._run, not_measured=cmc.NotMeasuredError)
    try:
        code, message = cmc.run()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return {cmc.OK: pc.OK, cmc.COLLISION: pc.FAIL, cmc.MISSING: pc.MISSING}.get(code, pc.FAIL), message
