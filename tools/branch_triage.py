#!/usr/bin/env python3
"""تصنيفٌ آليٌّ للفروع المحلية في أربع قوائم — W-20261020-002 (بديل W-20261001-050). قراءةٌ فقط: لا حذفَ ولا كتابةَ في git.

يبني على `branch_status.classify_tree` (حكمٌ نقيّ بمطابقة المحتوى للسحق، W-20260928-027):
  (أ) مدموجٌ بطلبه        ← MERGED
  (ب) مدموجٌ بالسلف       ← MERGED_ELSEWHERE (رأسُه داخل طلبٍ مدموجٍ من فرعٍ آخر)
  (ج) بلا طلب             ← NO_PR (إيداعاتٌ خارج main بلا أيّ طلب)
  (د) طلبُه مغلقٌ بلا دمج ← CLOSED_UNMERGED
وما سواها يُعدّ «أخرى» (طلبٌ مفتوح، عملٌ بعد الدمج، نظيف) ولا يدخل قائمةَ الحذف المقترحة.

الحذف لا يُنفَّذ هنا ولا بغير أمر المالك الصريح على القائمة الدقيقة بدفعةٍ واحدة (قاعدةُ المستودع 6 وحارسُ غيت).

    python tools/branch_triage.py --repo D:/shschool_mvp [--out ملفّ.md] [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from collections.abc import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import branch_status as bs  # noqa: E402

LISTS = (
    ("merged_pr", "(أ) مدموجٌ بطلبه", {bs.MERGED, bs.MERGED_DIRTY}),
    ("merged_ancestor", "(ب) مدموجٌ بالسلف", {bs.MERGED_ELSEWHERE}),
    ("no_pr", "(ج) بلا طلب", {bs.NO_PR}),
    ("closed_unmerged", "(د) طلبُه مغلقٌ بلا دمج", {bs.CLOSED_UNMERGED}),
)
PROTECTED = {"main", "master"}


def triage(
    branches: dict[str, str],
    ahead: Callable[[str], int],
    prs: dict[str, list[dict]],
    contains: Callable[[str, str], bool],
    content_merged: Callable[[str, str], bool] | None = None,
    elsewhere: Callable[[str], list[int]] | None = None,
    checked_out: frozenset[str] = frozenset(),
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, list[dict]]:
    """حكمٌ نقيٌّ على {اسمُ الفرع: رأسُه}. `elsewhere(head)` مكلفةٌ فلا تُستدعى إلّا لما لا طلبَ له وفيه إيداعات.
    فرعٌ مفتوحٌ في شجرة عملٍ حيّة يُعلَّم `checked_out` ويُستبعد من قائمة الحذف المقترحة."""
    out: dict[str, list[dict]] = {key: [] for key, _label, _st in LISTS}
    out["other"] = []
    names = sorted(branches)
    for i, name in enumerate(names, 1):
        if progress:
            progress(i, len(names), name)
        if name in PROTECTED:
            continue
        head = branches[name]
        n_ahead = ahead(name)
        own = prs.get(name, [])
        extra = elsewhere(head) if (elsewhere and not own and n_ahead) else None
        res = bs.classify_tree(head, name, n_ahead, 0, own, contains, extra, content_merged)
        row = {
            "branch": name,
            "head": head[:8],
            "status": res["status"],
            "prs": res["prs"],
            "ahead": n_ahead,
            "checked_out": name in checked_out,
        }
        key = next((k for k, _l, st in LISTS if res["status"] in st), "other")
        out[key].append(row)
    return out


def deletion_candidates(result: dict[str, list[dict]]) -> list[dict]:
    """(أ)+(ب) بلا ما هو مفتوحٌ في شجرة عمل؛ تُعرض على المالك ولا تُنفَّذ."""
    rows = result["merged_pr"] + result["merged_ancestor"]
    return [r for r in rows if not r["checked_out"]]


def render(result: dict[str, list[dict]], repo: str) -> str:
    total = sum(len(v) for v in result.values())
    lines = [f"# تصنيف الفروع المحلية — {repo}", "", f"المجموع {total} فرعاً (بلا main). قراءةٌ فقط؛ لا حذفَ قبل أمر المالك على القائمة الدقيقة.", ""]
    lines += ["| القائمة | العدد |", "|---|---|"]
    for key, label, _st in LISTS:
        lines.append(f"| {label} | {len(result[key])} |")
    lines.append(f"| أخرى (طلبٌ مفتوح/بعد الدمج/نظيف) | {len(result['other'])} |")
    cand = deletion_candidates(result)
    lines += ["", f"قائمةُ الحذف المقترحة (أ)+(ب) بلا ما هو في شجرةٍ حيّة: **{len(cand)}** (للعرض على المالك فقط).", ""]
    for key, label, _st in LISTS + (("other", "أخرى", set()),):
        lines += [f"## {label} ({len(result[key])})", ""]
        lines += [f"- `{r['branch']}` @{r['head']}" + (f" #{', #'.join(map(str, r['prs']))}" if r["prs"] else "")
                  + (f" — {r['ahead']} إيداعاً خارج main" if r["ahead"] else "") + (" — في شجرة عمل" if r["checked_out"] else "")
                  for r in result[key]] or ["- (لا شيء)"]
        lines.append("")
    return "\n".join(lines)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, encoding="utf-8", errors="replace", check=False).stdout  # noqa: S603, S607


def local_branches(repo: Path) -> dict[str, str]:
    rows = _git(repo, "for-each-ref", "--format=%(refname:short)\t%(objectname)", "refs/heads").splitlines()
    return dict(r.split("\t", 1) for r in rows if "\t" in r)


def worktree_branches(repo: Path) -> frozenset[str]:
    names = set()
    for ln in _git(repo, "worktree", "list", "--porcelain").splitlines():
        if ln.startswith("branch "):
            names.add(ln.removeprefix("branch refs/heads/"))
    return frozenset(names)


def ancestor_index(repo: Path, merged: list[dict], branches: dict[str, str]) -> dict[str, list[int]]:
    """{رأسُ الفرع: طلباتٌ مدموجةٌ رأسُها يحوي رأسَ الفرع} بنداءٍ واحدٍ لكل طلب (`for-each-ref --merged`) بدل merge-base لكل فرعٍ وطلب."""
    by_head: dict[str, list[str]] = {}
    for name, head in branches.items():
        by_head.setdefault(head, []).append(name)
    out: dict[str, list[int]] = {}
    for p in merged:
        oid = p.get("headRefOid") or ""
        names = _git(repo, "for-each-ref", f"--merged={oid}", "--format=%(objectname)", "refs/heads").split()
        for head in set(names):
            out.setdefault(head, []).append(p["number"])
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--out", help="ملفٌّ يُكتب فيه التقرير (Markdown)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    warn: list[str] = []
    prs = bs.prs_by_branch(repo, warn)
    if prs is None:
        print("✘ تعذّر gh pr list: " + "; ".join(warn), file=sys.stderr)
        return 3
    merged = [p for plist in prs.values() for p in plist if p["state"] == "MERGED"]
    contains, cm = bs.git_contains(repo), bs.git_content_merged(repo)

    def ahead(name: str) -> int:
        out = _git(repo, "rev-list", "--count", f"{a.base}..{name}").strip()
        return int(out) if out.isdigit() else 0

    branches = local_branches(repo)
    index = ancestor_index(repo, merged, branches)
    result = triage(
        branches, ahead, prs, contains, cm,
        lambda head: sorted(index.get(head, [])), worktree_branches(repo),
        lambda i, n, name: print(f"[{i}/{n}] {name}", file=sys.stderr, flush=True) if i % 10 == 0 or i == n else None,
    )
    text = json.dumps(result, ensure_ascii=False, indent=1) if a.json else render(result, str(repo))
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"كُتب {a.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
