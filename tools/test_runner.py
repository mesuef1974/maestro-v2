"""اختباراتُ المشغّل (D-519م): الاختيار، القفل، الإصلاح مرّتين، الإحالة، التراجع الآليّ، وتسجيل الكلفة."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import runner  # noqa: E402

CFG = runner.load_config(Path("/nonexistent"))
CFG["health_url"] = "x"


def _card(lp, cid="W-20261104-901", size="صغير", state="routed", **extra):
    ledger.append_event("created", cid, {"problem": "مشكلة", "impact": "أثر", "accept": ["يمرّ الاختبار"], "priority": "P2",
                                         "runner_size": size, **extra}, lp)
    ledger.append_event("state", cid, {"state": state, "by": "t"}, lp)


class Fake(runner.Effects):
    def __init__(self, verify=(True,), healthy=True, rollback=True, gate=True, window=True, turns=3, cost=0.1, files=("a.py",)):
        super().__init__(CFG)
        self.verify_q, self.is_healthy, self.can_rollback, self.gate, self.window = list(verify), healthy, rollback, gate, window
        self.turns, self.cost, self.files = turns, cost, list(files)
        self.runs = 0
        self.ci = "green"
        self.merge_state = "MERGED"
        self.prod = "oid1"
        self.old_prs = []
        self.removed = False
        self.merged = False

    def preflight(self): pass
    def prepare_tree(self, cid, round_no=1): return "/t", "claude/runner-x"
    def run_model(self, tree, prompt, model, budget):
        self.runs += 1
        return runner.Result(True, "تم", self.cost, self.turns)
    def verify(self, tree):
        self.calls = getattr(self, "calls", []) + ["verify"]
        return (self.verify_q.pop(0) if len(self.verify_q) > 1 else self.verify_q[0]), "سجلّ الفشل"
    def autoformat(self, tree):
        self.calls = getattr(self, "calls", []) + ["autoformat"]
        return []
    def changed(self, tree): return self.files
    def diff(self, tree): return "diff"
    def commit_push(self, tree, branch, files, msg): return "h1"
    def open_pr(self, tree, branch, title, body): return 7
    def set_pr_body(self, tree, pr, body): self.pr_bodies = getattr(self, 'pr_bodies', []) + [body]
    def close_old_prs(self, tree, cid, new): return self.old_prs
    def checks_state(self, tree, pr): return self.ci
    def failed_checks(self, tree, pr): return "Ruff"
    def failed_names(self, tree, pr): return list(getattr(self, "failed", ["Ruff"])) if self.ci == "red" else []
    def infra_runs(self, tree, pr): return dict(getattr(self, "cancelled", {})) if self.ci == "red" else {}
    def seed_script(self, tree, prompt):
        self.seed_prompts = getattr(self, "seed_prompts", []) + [prompt]
        q = getattr(self, "seed_q", ["```python" + chr(10) + "print(1)" + chr(10) + "```"])
        return runner.Result(True, q.pop(0) if len(q) > 1 else q[0], 0.05, 3)

    def run_seed(self, script):
        q = getattr(self, "seed_runs", [(True, "PREVIEW_PATH=/quality/observations/1/pdf/view/")])
        return q.pop(0) if len(q) > 1 else q[0]

    def map_rls(self, account):
        self.mapped = account
        return getattr(self, "map_result", (True, ""))

    def pdf_fallback_fonts(self, path, account):
        return list(getattr(self, "fallback", []))

    def check_seed(self, path, account):
        q = getattr(self, "seed_checks", [(True, "PREVIEW_STATUS=200")])
        return q.pop(0) if len(q) > 1 else q[0]

    def slot_up(self, tree, port):
        self.slots = getattr(self, "slots", []) + [port]
        return getattr(self, "slot_ok", True), "log"

    def menu_gap(self, tree, card): return getattr(self, "menu", [])
    def slot_serves(self, port, head): return getattr(self, "slot_live", True)
    def slot_down(self, port): self.downs = getattr(self, "downs", []) + [port]
    def slot_projects(self): return list(getattr(self, "projects", []))
    def containers(self): return list(getattr(self, "boxes", []))
    def container_rm(self, name): self.rm_boxes = getattr(self, "rm_boxes", []) + [name]
    def project_down(self, project): self.downed = getattr(self, "downed", []) + [project]
    def preview_tick(self): self.ticks = getattr(self, "ticks", 0) + 1
    def preview_release(self): self.releases = getattr(self, "releases", 0) + 1
    def close_pr(self, tree, pr): self.closed_pr = pr

    def preview_state(self):
        if not getattr(self, "pinned", ""):
            return {}
        return {"mode": "pin", "pin_tree": self.pinned, "pin_until": str(int(runner.time.time()) + 600)}

    def preview_pin(self, tree):
        self.pins = getattr(self, "pins", []) + [tree]
        self.pinned = tree


    def rerun_failed(self, tree, run_id):
        self.reruns = getattr(self, "reruns", []) + [run_id]
        return True

    def pr_body_of(self, tree, pr): return (getattr(self, "pr_bodies", None) or [""])[-1]
    def gate_reasons(self, tree, pr): return "سبب"
    def gate_allows(self, tree, pr): return self.gate
    def remote_head(self, branch): return "h1"
    def merge(self, tree, pr):
        self.merged = True
        return True
    def in_deploy_window(self, tree): return self.window
    def healthy(self): return self.is_healthy
    def pr_state(self, tree, pr): return self.merge_state, "oid1"
    def pr_conflicted(self, tree, pr): return getattr(self, "conflicted", False)
    def prod_status(self): return self.prod, self.is_healthy
    def contains(self, tree, oid, prod): return prod == "oid1"
    def main_sha(self): return "good1234abcd"
    def rollback(self, sha, reason):
        self.rolled_to = sha
        return self.can_rollback
    def remove_tree(self, tree): self.removed = True
    def review_diff(self, tree): return "الفرق الكامل"
    def branch_diff(self, tree): return "فرق الفرع"
    def ci_log(self, tree, pr): return "FAILED tests/test_y.py"
    def review(self, tree, card, budget):
        self.reviews = getattr(self, "reviews", 0) + 1
        q = getattr(self, "review_q", [[]])
        missing = q.pop(0) if len(q) > 1 else q[0]
        if missing is None:
            return runner.Result(False, "جواب غير مقروء"), []
        return runner.Result(True, "", 0.02, 1), missing


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OWNER_QUEUE", tmp_path / "owner_queue.md")
    monkeypatch.setattr(runner, "REQUESTS", tmp_path / "requests")
    monkeypatch.setattr(runner, "FAIL_DIFFS", tmp_path / "fail_diffs")
    return tmp_path / "e.jsonl", tmp_path / "lock"


def _until_closed(fx, lp, lock):
    """أحمرُ CI يأخذ جولاتِ إصلاحٍ قبل الإغلاق."""
    for _ in range(runner.CI_FIX_MAX):
        assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    return runner.run_cycle(CFG, fx, lp, lock)


def _state(lp, cid="W-20261104-901"):
    return ledger.reduce_state(ledger.load_events(lp))[cid]


def test_pick_requires_size_accept_and_routed(env):
    lp, _ = env
    _card(lp, "W-20261104-901", size="مجهول")
    _card(lp, "W-20261104-902", state="captured")
    _card(lp, "W-20261104-903")
    items = ledger.reduce_state(ledger.load_events(lp))
    assert runner.pick_card(items, CFG)["id"] == "W-20261104-903"


def test_size_label_tolerates_diacritics_and_hamza():
    assert runner.size_row(CFG, "متوسّط") == runner.size_row(CFG, "متوسط")


def test_lock_blocks_second_cycle_and_stale_lock_is_reclaimed(tmp_path):
    p = tmp_path / "l"
    assert runner.acquire_lock(p) and not runner.acquire_lock(p)
    assert runner.acquire_lock(p, now=lambda: p.stat().st_mtime + runner.LOCK_STALE_S + 1)
    runner.release_lock(p)
    assert not p.exists()


def test_green_path_publishes_and_records_cost(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    assert runner.run_cycle(CFG, fx, lp, lock) == "published"
    st = _state(lp)
    assert st["state"] == "published" and fx.merged and fx.removed
    assert any("كلفة=0.1000$ أدوار=3" in n.get("text", "") for n in st["notes"]) or "كلفة=0.1000" in str(ledger.load_events(lp))
    assert not lock.exists()


def test_red_checks_are_fixed_within_two_runs(env):
    lp, lock = env
    _card(lp)
    fx = Fake(verify=(False, False, True))
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 3


def test_red_checks_escalate_haiku_to_sonnet_then_close_with_report(env):
    lp, lock = env
    _card(lp)
    fx = Fake(verify=(False,))
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == runner.MAX_ROUNDS and not fx.merged
    assert _state(lp)["state"] == "closed"
    assert "W-20261104-901" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_turn_count_does_not_escalate_when_checks_pass(env):
    lp, lock = env
    _card(lp)
    fx = Fake(turns=99)
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 1


def test_gate_refusal_refers_and_does_not_merge(env):
    lp, lock = env
    _card(lp)
    fx = Fake(gate=False)
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged and fx.removed


def test_outside_deploy_window_does_not_merge(env):
    lp, lock = env
    _card(lp)
    fx = Fake(window=False)
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_window" and not fx.merged


def test_failed_health_check_rolls_back_automatically_and_refers(env):
    lp, lock = env
    _card(lp)
    fx = Fake(healthy=False, rollback=True)
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred"
    assert fx.rolled_to == "good1234abcd" and "التراجعُ الآليّ" in runner.OWNER_QUEUE.read_text(encoding="utf-8")
    assert _state(lp)["state"] != "published"


def test_failed_health_check_without_rollback_is_reported_honestly(env):
    lp, lock = env
    _card(lp)
    runner.run_cycle(CFG, Fake(healthy=False, rollback=False), lp, lock)
    assert "ولا تراجعَ آليّ" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_idle_when_no_ready_card(env):
    lp, lock = env
    lp.write_text("", encoding="utf-8")
    assert runner.run_cycle(CFG, Fake(), lp, lock) == "idle"


def test_request_file_becomes_a_routed_card_without_a_model(env):
    lp, _ = env
    runner.REQUESTS.mkdir()
    (runner.REQUESTS / "r1.md").write_text("العنوان: ن\nالمطلوب: م\nمعايير القبول: ق\nالوسم: صغير\n", encoding="utf-8")
    (runner.REQUESTS / "r2.md").write_text("العنوان: ناقص\n", encoding="utf-8")
    assert runner.intake_requests(CFG, lp) == 1
    assert (runner.REQUESTS / "r2.rejected").exists()
    assert [i for i in ledger.reduce_state(ledger.load_events(lp)).values() if i["state"] == "routed"]


def test_environment_failure_refers_immediately_without_a_fix_run(env):
    lp, lock = env
    _card(lp)

    class Env(Fake):
        def verify(self, tree):
            raise runner.RunnerError("بيئةٌ: docker متوقّف")

    fx = Env()
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 1 and not fx.merged


def test_referred_card_is_held_and_not_picked_again(env):
    lp, lock = env
    _card(lp)
    runner.run_cycle(CFG, Fake(gate=False), lp, lock)
    assert runner.run_cycle(CFG, Fake(), lp, lock) == "idle"


def test_env_down_does_not_touch_the_card_and_reports_once_a_day(env):
    lp, lock = env
    _card(lp)

    class Down(Fake):
        def preflight(self):
            raise runner.EnvDown("docker متوقّف")

    fx = Down()
    assert runner.run_cycle(CFG, fx, lp, lock) == "env_down" and fx.runs == 0
    assert runner.run_cycle(CFG, Down(), lp, lock) == "env_down"
    assert _state(lp)["state"] == "routed" and runner.OWNER_QUEUE.read_text(encoding="utf-8").count("بيئة") == 1


def test_transient_failure_is_retried_once_from_a_fresh_tree(env):
    lp, lock = env
    _card(lp)

    class Flaky(Fake):
        n = 0

        def commit_push(self, tree, branch, files, msg):
            Flaky.n += 1
            if Flaky.n == 1:
                raise runner.Transient("تعذّر الدفع")
            return "h1"

    assert runner.run_cycle(CFG, Flaky(), lp, lock) == "published"


def test_transient_failure_twice_closes_with_report(env):
    lp, lock = env
    _card(lp)

    class Broken(Fake):
        def commit_push(self, tree, branch, files, msg):
            raise runner.Transient("تعذّر الدفع")

    assert runner.run_cycle(CFG, Broken(), lp, lock) == "referred" and _state(lp)["state"] == "closed"


def test_incomplete_request_is_rejected_naming_the_missing_field(env):
    lp, _ = env
    runner.REQUESTS.mkdir()
    (runner.REQUESTS / "r.md").write_text("العنوان: ن\nالوسم: صغير\n", encoding="utf-8")
    runner.intake_requests(CFG, lp)
    assert "المطلوب" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_pending_ci_keeps_the_card_open_and_resumes_next_cycle(env):
    lp, lock = env
    _card(lp, source="owner")
    fx = Fake()
    fx.ci = "pending"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and not fx.removed and not fx.merged
    assert _state(lp)["state"] == "in_progress"
    fx.ci = "green"
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.removed and fx.merged


def test_red_ci_refers(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.ci = "red"
    assert _until_closed(fx, lp, lock) == "referred" and not fx.merged


def test_owner_cards_get_the_d520_approval_line_others_do_not():
    import re
    line = re.compile(r"اعتُمد من المالك (?:على 8500|مباشرةً بلا معاينة 8500) — [0-9]{4}-[0-9]{2}-[0-9]{2}")
    assert line.search(runner.pr_body({"id": "W-1", "source": "owner"}))
    assert not line.search(runner.pr_body({"id": "W-1", "source": "intake"}))


def test_request_priority_and_touches_are_carried_into_the_card(env):
    lp, _ = env
    runner.REQUESTS.mkdir()
    (runner.REQUESTS / "r.md").write_text("العنوان: ن\nالمطلوب: م\nمعايير القبول: ق\nالوسم: صغير\nالأولوية: P1\nيمسّ: الأمن، الهجرات\n", encoding="utf-8")
    runner.intake_requests(CFG, lp)
    card = next(iter(ledger.reduce_state(ledger.load_events(lp)).values()))
    assert card["priority"] == "P1" and card["touches"] == ["الأمن", "الهجرات"]


def test_pr_body_binds_the_approval_line_to_the_head():
    import re
    body = runner.pr_body({"id": "W-1", "source": "owner"}, "0123456789abcdef")
    assert re.search("8500 — [0-9]{4}-[0-9]{2}-[0-9]{2} — الرأس 01234567", body)


def test_old_prs_of_the_card_are_closed_and_noted(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.old_prs = [1334]
    assert runner.run_cycle(CFG, fx, lp, lock) == "published"
    assert "1334" in str(ledger.load_events(lp)) and "حلّ محلّه" in str(ledger.load_events(lp))


def test_no_change_after_green_checks_escalates_instead_of_publishing(env):
    lp, lock = env
    _card(lp)
    fx = Fake(files=())
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 2


def test_haiku_over_turn_cap_with_green_checks_never_runs_sonnet(env):
    lp, lock = env
    _card(lp)
    fx = Fake(turns=99)
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 1


def test_sh_forces_utf8_for_child_processes():
    out = runner.sh([sys.executable, "-c", "import os,sys;print(os.environ.get('PYTHONUTF8'), sys.flags.utf8_mode)"]).stdout.split()
    assert out == ["1", "1"]


def test_sh_child_round_trips_arabic_text_in_utf8():
    code = "import sys;sys.stdout.write('اعتُمد من المالك')"
    assert runner.sh([sys.executable, "-c", code]).stdout == "اعتُمد من المالك"


def test_merge_without_deploy_stays_merged_and_waits(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.prod = "old0000"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_deploy"
    assert _state(lp)["state"] == "merged"
    fx.prod = "oid1"
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and _state(lp)["state"] == "published"


def test_pr_in_merge_queue_waits_then_continues(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.merge_state = "OPEN"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_merge" and _state(lp)["state"] == "in_progress"
    fx.merge_state = "MERGED"
    assert runner.run_cycle(CFG, fx, lp, lock) == "published"


def test_pr_closed_out_of_queue_closes_with_report(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.merge_state = "CLOSED"
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and _state(lp)["state"] == "closed"


def test_deploy_timeout_reports_merged_not_deployed_without_rollback(env, monkeypatch):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.prod = "old0000"
    rolled = []
    fx.rollback = lambda sha, reason: rolled.append(sha) or True
    runner.run_cycle(CFG, fx, lp, lock)
    real = runner.time.time
    monkeypatch.setattr(runner.time, "time", lambda: real() + runner.DEPLOY_WAIT_S + 5)
    assert runner.run_cycle(CFG, fx, lp, lock) == "merged" and not rolled
    assert "ولم تُنشر" in runner.OWNER_QUEUE.read_text(encoding="utf-8") and _state(lp)["state"] == "merged"


def test_unhealthy_new_commit_rolls_back_but_old_commit_does_not(env):
    lp, lock = env
    _card(lp)
    fx = Fake(healthy=False)
    fx.prod = "old0000"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_deploy" and not hasattr(fx, "rolled_to")
    fx.prod = "oid1"
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.rolled_to == "good1234abcd"


def _write_req(env, **kw):
    d = runner.REQUESTS
    d.mkdir(exist_ok=True)
    base = {"العنوان": "ع", "المطلوب": "م", "معايير القبول": "أ ؛ ب", "الوسم": "صغير"}
    base.update(kw)
    (d / "web-1.md").write_text("\n".join(f"{k}: {v}" for k, v in base.items()), encoding="utf-8")


def test_intake_splits_accept_and_defaults_approval(env):
    lp, _ = env
    _write_req(env)
    runner.intake_requests(CFG, lp)
    c = list(ledger.reduce_state(ledger.load_events(lp)).values())[0]
    assert c["accept"] == ["أ", "ب"] and c["approval"] == "مباشر"


def test_intake_design_size_defaults_to_preview(env):
    lp, _ = env
    _write_req(env, **{"الوسم": "تصميم"})
    runner.intake_requests(CFG, lp)
    assert list(ledger.reduce_state(ledger.load_events(lp)).values())[0]["approval"] == "معاينة"


def test_intake_forbidden_touch_is_held_early_and_referred(env):
    lp, _ = env
    _write_req(env, **{"يمسّ": "الهجرات"})
    runner.intake_requests(CFG, lp)
    c = list(ledger.reduce_state(ledger.load_events(lp)).values())[0]
    assert c["runner_hold"] and runner.pick_card({c["id"]: c}, CFG) is None
    assert "الهجرات" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_preview_card_waits_then_gets_the_8500_line_after_approval(env):
    lp, lock = env
    _card(lp, approval="معاينة", source="owner")
    f = Fake()
    assert runner.run_cycle(CFG, f, lp, lock) == "waiting_preview"
    runner.run_cycle(CFG, f, lp, lock)
    assert "جاهز للمعاينة" in runner.OWNER_QUEUE.read_text(encoding="utf-8")
    ledger.append_event("update", "W-20261104-901", {"preview_approved": True}, lp)
    runner.run_cycle(CFG, f, lp, lock)
    assert any("اعتُمد من المالك على 8500" in b for b in f.pr_bodies)


def test_direct_card_has_no_preview_stop(env):
    lp, lock = env
    _card(lp, approval="مباشر", source="owner")
    assert not runner.run_cycle(CFG, Fake(), lp, lock).startswith("waiting_preview")


# ───────────────────────── علاجُ 2026-11-05: الصورةُ تُبنى والتنسيقُ قبل الفحص ─────────────────────────
class _Docker:
    """محاكي docker: يسجّل الأوامر؛ `up` للمحرّك و`image` للصورة، والبناءُ يجعل الصورةَ موجودة."""

    def __init__(self, up=True, image=False, build_rc=0):
        self.up, self.image, self.build_rc, self.cmds = up, image, build_rc, []

    def __call__(self, cmd, timeout):
        self.cmds.append(cmd[0])
        if cmd[0] == "info":
            return (0 if self.up else 1), ""
        if cmd[0] == "image":
            return (0 if self.image else 1), ""
        if cmd[0] == "build":
            if self.build_rc == 0:
                self.image = True
            return self.build_rc, "سجلّ البناء"
        raise AssertionError(cmd)


@pytest.fixture()
def image_dir(tmp_path, monkeypatch):
    d = tmp_path / "prepush_image"
    d.mkdir()
    (d / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    monkeypatch.setattr(runner, "IMAGE_DIR", d)
    return d


def test_preflight_builds_missing_image_when_docker_is_up(image_dir):
    dk = _Docker(up=True, image=False)
    runner.Effects(CFG).preflight(sleep=lambda s: None, wait_s=0, docker=dk)
    assert "build" in dk.cmds and dk.image


def test_preflight_does_not_build_when_image_exists():
    dk = _Docker(up=True, image=True)
    runner.Effects(CFG).preflight(sleep=lambda s: None, wait_s=0, docker=dk)
    assert "build" not in dk.cmds


def test_preflight_env_down_when_docker_never_returns(image_dir):
    dk = _Docker(up=False, image=False)
    with pytest.raises(runner.EnvDown, match="docker متوقّف"):
        runner.Effects(CFG).preflight(sleep=lambda s: None, wait_s=0, docker=dk)
    assert "build" not in dk.cmds


def test_preflight_build_failure_is_env_down_not_card_failure(image_dir):
    dk = _Docker(up=True, image=False, build_rc=1)
    with pytest.raises(runner.EnvDown, match="تعذّر بناءُ صورة"):
        runner.Effects(CFG).preflight(sleep=lambda s: None, wait_s=0, docker=dk)


def test_preflight_missing_dockerfile_is_env_down(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "IMAGE_DIR", tmp_path / "none")
    with pytest.raises(runner.EnvDown, match="لا Dockerfile"):
        runner.Effects(CFG).preflight(sleep=lambda s: None, wait_s=0, docker=_Docker(up=True, image=False))


def test_autoformat_runs_before_every_verify(env):
    lp, lock = env
    _card(lp)
    fx = Fake(verify=(False, True))
    assert runner.run_cycle(CFG, fx, lp, lock) == "published"
    assert fx.calls == ["autoformat", "verify", "autoformat", "verify"]


def test_autoformat_uses_the_image_ruff_on_changed_python_only(tmp_path, monkeypatch):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.py").write_text("x = [1,2,\n  3]\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x = [1,2]\n", encoding="utf-8")
    real, seen = runner.sh, []

    def spy(cmd, cwd=None, timeout=None, *rest):
        if cmd[0] == "docker":
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real(cmd, cwd, timeout, *rest) if timeout else real(cmd, cwd)

    monkeypatch.setattr(runner, "sh", spy)
    monkeypatch.setattr(runner.Effects, "preflight", lambda self, *a, **k: None)  # لا محرّك حاويات في CI (windows-latest)
    assert runner.Effects(CFG).autoformat(str(tmp_path)) == ["a.py"]
    assert seen[0][-1] == "a.py" and "--network" in seen[0] and "ruff" in seen[0]  # لا ruff الجهاز ولا b.txt


def test_brief_tells_the_model_to_format():
    assert "ruff format" in runner.brief({"id": "W-1", "accept": ["x"]}, [])


def test_referenced_tests_find_users_of_changed_modules_and_templates(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_uses_module.py").write_text("from quality.presentation import signature_stamps\n", encoding="utf-8")
    (tmp_path / "tests" / "test_uses_template.py").write_text("html = render('quality/_pdf_e_sign.html')\n", encoding="utf-8")
    (tmp_path / "tests" / "test_unrelated.py").write_text("assert 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_changed_itself.py").write_text("", encoding="utf-8")
    changed = ["quality/presentation.py", "templates/quality/_pdf_e_sign.html", "tests/test_changed_itself.py"]
    assert runner.referenced_tests(str(tmp_path), changed) == [
        "tests/test_changed_itself.py", "tests/test_uses_module.py", "tests/test_uses_template.py",
    ]
    assert runner.referenced_tests(str(tmp_path), ["docs/x.md"]) == []


def test_brief_tells_the_model_to_hunt_other_users_in_tests():
    assert "tests/" in runner.brief({"id": "W-1", "accept": ["x"]}, [])


# ───────────────────────── علاجُ 2026-11-05: بطاقةُ المعاينة وفحصُ «سطر الاعتماد» ─────────────────────────
def _preview_card(lp):
    _card(lp, approval="معاينة", source="owner")


def test_preview_card_waits_for_owner_when_only_the_approval_check_is_red(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    fx.ci, fx.failed = "red", [runner.APPROVAL_CHECK]
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_preview"
    assert _state(lp)["state"] == "in_progress" and not fx.removed and not fx.merged


def test_preview_card_with_a_real_red_check_still_closes(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    fx.ci, fx.failed = "red", [runner.APPROVAL_CHECK, "pytest shard 1/4"]
    assert _until_closed(fx, lp, lock) == "referred"
    assert "pytest shard 1/4" in runner.OWNER_QUEUE.read_text(encoding="utf-8")
    assert runner.APPROVAL_CHECK not in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_approved_preview_card_writes_the_line_once_then_waits_for_its_check_then_merges(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    fx.ci, fx.failed = "red", [runner.APPROVAL_CHECK]
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_preview"
    ledger.append_event("update", "W-20261104-901", {"preview_approved": True}, lp)
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    assert "اعتُمد من المالك على 8500" in fx.pr_bodies[-1] and "الرأس h1" in fx.pr_bodies[-1]
    n = len(fx.pr_bodies)
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and len(fx.pr_bodies) == n  # لا يُكتب ثانيةً
    fx.ci, fx.failed = "green", []
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.merged


def test_direct_card_treats_a_red_approval_check_as_a_real_failure(env):
    lp, lock = env
    _card(lp, source="owner")
    fx = Fake()
    fx.ci, fx.failed = "red", [runner.APPROVAL_CHECK]
    assert _until_closed(fx, lp, lock) == "referred" and not fx.merged


def test_gate_script_comes_from_main_not_from_the_branch(tmp_path):
    """فرعٌ يعدّل البوّابةَ في ملفّه لا يحكم نفسَه: تُقرأ نسخةُ main (cfg['base'])، وإن خلت main منها فنسخةُ الشجرة."""
    import subprocess
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "auto_merge_gate.py").write_text("print('main-gate')\n", encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True, env={**__import__("os").environ, **env})
    cfg = {**CFG, "repo": str(repo), "base": "main"}
    path = runner.Effects(cfg).gate_script(str(tmp_path))
    assert path != "scripts/auto_merge_gate.py" and Path(path).read_text(encoding="utf-8") == "print('main-gate')\n"
    cfg_none = {**CFG, "repo": str(repo), "base": "main~0:nonexistent"}
    assert runner.Effects(cfg_none).gate_script(str(tmp_path)) == "scripts/auto_merge_gate.py"


def test_cards_start_up_to_the_ceiling_and_the_next_does_not(env):
    lp, lock = env
    for n in range(901, 901 + runner.MAX_INFLIGHT + 1):
        _card(lp, f"W-20261104-{n}", scope_files=[f"{n}.py"])
    fx = Fake()
    fx.ci = "pending"
    for started in range(1, runner.MAX_INFLIGHT + 1):
        assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == started
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == runner.MAX_INFLIGHT
    assert _state(lp, f"W-20261104-{901 + runner.MAX_INFLIGHT}")["state"] == "routed"


def test_card_sharing_a_file_waits_for_the_running_one(env):
    lp, lock = env
    _card(lp, "W-20261104-901", scope_files=["a.py"])
    _card(lp, "W-20261104-902", scope_files=["a.py"])
    fx = Fake()
    fx.ci = "pending"
    runner.run_cycle(CFG, fx, lp, lock)
    runner.run_cycle(CFG, fx, lp, lock)
    assert fx.runs == 1 and _state(lp, "W-20261104-902")["state"] == "routed"


def test_second_card_does_not_merge_until_first_is_published(env):
    lp, lock = env
    _card(lp, "W-20261104-901", scope_files=["a.py"])
    _card(lp, "W-20261104-902", scope_files=["b.py"])
    fx = Fake()
    fx.prod = "old0000"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_deploy"  # الأولى دُمجت ولم تُنشر
    fx.merged = False
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_turn" and not fx.merged
    assert _state(lp, "W-20261104-902")["state"] == "in_progress"
    fx.prod = "oid1"
    runner.run_cycle(CFG, fx, lp, lock)
    assert _state(lp, "W-20261104-901")["state"] == "published" and _state(lp, "W-20261104-902")["state"] == "published"


def _poll_with(outs):
    t = {"now": 0.0}
    calls = []

    def cycle(cfg):
        calls.append(1)
        return outs[min(len(calls) - 1, len(outs) - 1)]

    def sleep(s):
        t["now"] += s

    runner.poll(CFG, cycle, sleep, lambda: t["now"])
    return len(calls)


def test_poll_repeats_every_minute_and_ends_before_the_next_task():
    assert _poll_with(["waiting_ci"]) == 5  # 0 و60 و120 و180 و240 ثانية


def test_poll_stops_on_env_down_and_locked():
    assert _poll_with(["idle", "env_down"]) == 2
    assert _poll_with(["locked"]) == 1


def test_quick_check_fails_only_on_exit_one(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = y", encoding="utf-8")
    fx = runner.Effects(CFG)
    monkeypatch.setattr(fx, "changed", lambda tree: ["a.py", "docs/b.md", "gone.py"])
    seen = []

    def fake(code):
        def run(cmd, cwd=None, timeout=None):
            seen.append(cmd)
            return runner.subprocess.CompletedProcess(cmd, code, "F821 undefined", "")
        return run

    monkeypatch.setattr(runner, "sh", fake(1))
    assert fx.quick_check(str(tmp_path)) == (False, "F821 undefined")
    assert seen[0][-1] == "a.py" and "gone.py" not in seen[0]
    monkeypatch.setattr(runner, "sh", fake(2))
    assert fx.quick_check(str(tmp_path))[0] is True  # علّةُ أداة: الحكمُ لـprepush


def test_note_timing_keeps_only_timing_lines(tmp_path):
    out = tmp_path / "t.log"
    runner.note_timing("runner-x", 400.4, "ضجيج\n[timing] ruff 3s\n[timing] check_types 120s\n", out)
    line = out.read_text(encoding="utf-8")
    assert "total=400s" in line and "ruff 3s | check_types 120s" in line and "ضجيج" not in line



# ───────── المرحلة 2 من استمارة ميزان: النوع والمعايير المرقّمة والنطاق وفحوص بلا توكنز ─────────
def test_intake_reads_phase2_fields(env):
    lp, _ = env
    _write_req(env, **{"النوع": "خلل", "معايير مرقّمة": "1، 2، 4", "فحوص المشغّل": "tests_in_diff، no_migrations، مجهول",
                       "الصفحة": "/attendance/", "الملفات": "attendance/views.py، attendance/forms.py", "خارج النطاق": "التقارير"})
    runner.intake_requests(CFG, lp)
    c = list(ledger.reduce_state(ledger.load_events(lp)).values())[0]
    assert c["req_type"] == "خلل" and c["criteria_ids"] == [1, 2, 4]
    assert c["runner_checks"] == ["tests_in_diff", "no_migrations"]  # فحصٌ مجهول يُتجاهَل
    assert c["scope_files"] == ["attendance/views.py", "attendance/forms.py"] and c["out_of_scope"] == "التقارير"
    assert runner.pick_card({c["id"]: c}, CFG)  # الحقول الجديدة لا تمنع الالتقاط


def test_intake_without_phase2_fields_is_unchanged(env):
    lp, _ = env
    _write_req(env)
    runner.intake_requests(CFG, lp)
    c = list(ledger.reduce_state(ledger.load_events(lp)).values())[0]
    assert not any(k in c for k in ("req_type", "runner_checks", "scope_files"))


def test_brief_carries_type_and_scope():
    card = {"id": "W-1", "problem": "م", "impact": "أ", "accept": ["x"], "req_type": "خلل", "scope_page": "/a/",
            "scope_files": ["a.py"], "out_of_scope": "ب", "runner_checks": ["scope_only"]}
    b = runner.brief(card, [])
    assert "نوع الطلب: خلل" in b and "الصفحة المعنيّة: /a/" in b and "خارج النطاق (لا تمسّه): ب" in b
    assert "لا تعدّل غيرها" in b and "a.py" in b


def test_criteria_checks():
    card = {"runner_checks": ["tests_in_diff", "scope_only", "no_migrations"], "scope_files": ["app/views.py"]}
    assert runner.criteria_failures(card, ["app/views.py", "tests/test_views.py"]) == []
    miss = runner.criteria_failures(card, ["app/views.py", "app/models.py", "app/migrations/0002.py"])
    assert len(miss) == 3 and "app/models.py" in miss[1] and "0002" in miss[2]
    assert runner.criteria_failures({"runner_checks": ["scope_only"]}, ["x.py"]) == []  # لا نطاق معلن: لا مقارنة


def test_failed_criterion_goes_back_to_the_model_then_passes(env):
    lp, lock = env
    _card(lp, runner_checks=["tests_in_diff"], source="owner")
    fx = Fake(files=("a.py",))
    orig = fx.run_model

    def run_model(tree, prompt, model, budget):
        if fx.runs == 1:  # المحاولة الثانية تضيف الاختبار
            assert "اختبار" in prompt
            fx.files = ["a.py", "tests/test_a.py"]
        return orig(tree, prompt, model, budget)
    fx.run_model = run_model
    out = runner.run_cycle(CFG, fx, lp, lock)
    assert fx.runs == 2 and out != "referred"
    assert "✔ اختبار يغطّي الحالة" in fx.pr_bodies[-1] if hasattr(fx, "pr_bodies") else True
    c = list(ledger.reduce_state(ledger.load_events(lp)).values())[0]
    assert "✔ اختبار يغطّي الحالة" in c["criteria_line"]


def test_pr_body_keeps_criteria_line_after_preview_rewrite():
    card = {"id": "W-1", "source": "owner", "approval": "معاينة", "preview_approved": True, "criteria_line": "معايير آليّة: ✔ لا هجرات"}
    assert "✔ لا هجرات" in runner.pr_body(card, "abcdef123")


def test_review_gap_sends_the_model_back_and_passes_after_fix(env):
    lp, lock = env
    _card(lp, size="متوسط")
    fx = Fake()
    fx.review_q = [["حذف الخطّاف"], []]
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 2 and fx.reviews == 2


def test_review_gap_that_never_closes_is_closed_without_a_pr(env):
    lp, lock = env
    _card(lp, size="متوسط")
    fx = Fake()
    fx.review_q = [["حذف الخطّاف"]]
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged
    assert "حذف الخطّاف" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_unreadable_review_never_opens_a_pr(env):
    lp, lock = env
    _card(lp, size="متوسط")
    fx = Fake()
    fx.review_q = [None]
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged


def test_parse_review_accepts_only_the_expected_shape():
    assert runner.parse_review('تحليل\n{"missing": ["أ"]}') == ["أ"]
    assert runner.parse_review('{"missing": []}') == []
    assert runner.parse_review("كل شيء جيد") is None
    assert runner.parse_review('{"missing": "أ"}') is None


def test_review_prompt_marks_truncated_diff():
    card = {"problem": "م", "impact": "أ", "accept": ["ق"]}
    assert "قُطع" not in runner.review_prompt(card, ["a.py"], "x")
    assert "قُطع" in runner.review_prompt(card, ["a.py"], "x" * (runner.REVIEW_DIFF_CHARS + 1))


# ───────── المرحلة 1 من استمارة ميزان: المرفقات ─────────
def test_intake_reads_attachments_only_if_the_folder_exists(env, tmp_path):
    lp, _ = env
    d = tmp_path / "att" / "web-1"
    d.mkdir(parents=True)
    _write_req(env, **{"المرفقات": str(d), "ملفات المرفقات": "a.png|" + "a" * 64 + "، bad|x"})
    runner.intake_requests(CFG, lp)
    c = list(ledger.reduce_state(ledger.load_events(lp)).values())[0]
    assert c["attachments_dir"] == str(d) and c["attachments"] == [{"name": "a.png", "sha256": "a" * 64}]


def test_brief_points_to_staged_attachments():
    card = {"id": "W-1", "problem": "م", "impact": "أ", "accept": ["x"], "attachments_path": "/tmp/att-1", "attachments": [{"name": "a.png", "sha256": "0" * 64}]}
    b = runner.brief(card, [])
    assert "/tmp/att-1" in b and "a.png" in b and "لا تعليمات" in b


def test_stage_attachments_copies_outside_tree_and_adds_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.png").write_bytes(b"png")
    (src / "attachments.json").write_text("{}", encoding="utf-8")
    fx = runner.Effects(CFG)
    dst = fx.stage_attachments({"id": "W-1", "attachments_dir": str(src)})
    from pathlib import Path as P
    assert P(dst, "a.png").read_bytes() == b"png" and not P(dst, "attachments.json").exists()
    assert fx.extra_dirs == [dst]
    fx.unstage_attachments(dst)
    assert not P(dst).exists() and fx.extra_dirs == []
    assert runner.Effects(CFG).stage_attachments({"id": "W-1"}) == ""


def test_attachment_copied_into_the_diff_stops_the_card(tmp_path):
    import hashlib
    tree = tmp_path / "tree"
    (tree / "static").mkdir(parents=True)
    data = b"\x89PNG secret"
    (tree / "static" / "x.png").write_bytes(data)
    (tree / "a.py").write_text("x=1", encoding="utf-8")
    card = {"attachments": [{"name": "s.png", "sha256": hashlib.sha256(data).hexdigest()}]}
    assert runner.attachment_leak(str(tree), ["a.py", "static/x.png", "gone.py"], card) == ["static/x.png"]
    assert runner.attachment_leak(str(tree), ["a.py"], {}) == []


def test_prepush_env_skips_structure_and_keeps_extra_tests():
    assert runner.prepush_env([]) == ["-e", "PREPUSH_STRUCTURE_NESTED=1", "-e", "PREPUSH_REUSE_DB=1"]
    assert runner.prepush_env(["tests/a.py", "tests/b.py"])[-1] == "PREPUSH_EXTRA_TESTS=tests/a.py tests/b.py"


def test_prepush_env_adds_light_guards_once_when_present(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_layering.py").write_text("", encoding="utf-8")
    out = runner.prepush_env(["tests/test_layering.py", "tests/a.py"], str(tmp_path))
    assert out[-1] == "PREPUSH_EXTRA_TESTS=tests/test_layering.py tests/a.py"  # بلا تكرار، والغائبُ لا يُضاف
    assert runner.prepush_env([], str(tmp_path))[-1] == "PREPUSH_EXTRA_TESTS=tests/test_layering.py"


class TurnsGreen(Fake):
    def run_model(self, tree, prompt, model, budget):
        self.ci = "green"
        return super().run_model(tree, prompt, model, budget)


def test_waiting_card_is_published_between_rounds_of_the_other(env):
    lp, lock = env
    _card(lp, "W-20261104-901", scope_files=["a.py"])
    fx = TurnsGreen()
    fx.run_model = lambda *a: Fake.run_model(fx, *a)
    fx.ci = "pending"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    _card(lp, "W-20261104-902", scope_files=["b.py"])
    fx.run_model = lambda *a: TurnsGreen.run_model(fx, *a)
    fx.ci = "pending"
    runner.run_cycle(CFG, fx, lp, lock)
    assert _state(lp, "W-20261104-901")["state"] == "published"


def test_a_broken_follow_up_does_not_fail_the_running_card(env, monkeypatch):
    lp, lock = env
    _card(lp, "W-20261104-901")
    fx = Fake()
    fx.ci = "pending"
    runner.run_cycle(CFG, fx, lp, lock)
    calls = []

    def boom(card, cfg, fx_, lpath=None):
        calls.append(card["id"])
        raise ValueError("عطل")

    monkeypatch.setattr(runner, "resume", boom)
    runner.advance_others("W-20261104-902", CFG, fx, lp)
    assert calls == ["W-20261104-901"]
    notes = [e for e in ledger.load_events(lp) if e["kind"] == "note" and "تعذّرت المتابعة" in e["data"].get("text", "")]
    assert len(notes) == 1


class FailsWith(Fake):
    def __init__(self, log):
        super().__init__(verify=(False,))
        self.log = log

    def verify(self, tree):
        return False, self.log


def test_last_failure_reason_reaches_owner_queue_and_ledger(env):
    lp, lock = env
    _card(lp)
    log = "ضجيج " * 900 + "FAILED tests/test_x.py السبب الأخير"
    assert runner.run_cycle(CFG, FailsWith(log), lp, lock) == "referred"
    queue = runner.OWNER_QUEUE.read_text(encoding="utf-8")
    assert "فشل النموذج بعد السلّم الكامل" in queue and "السبب الأخير" in queue
    assert len(queue.splitlines()) == 1
    note = next(e["data"]["text"] for e in ledger.load_events(lp) if "آخر سجلّ فشل" in e["data"].get("text", ""))
    assert note.endswith("السبب الأخير") and len(note) <= runner.FAIL_NOTE_CHARS + 40


def test_failure_log_is_masked_and_newlines_stay_out_of_the_report(env):
    lp, lock = env
    _card(lp)
    runner.run_cycle(CFG, FailsWith("سطر\nuser@example.com رقم 123456789"), lp, lock)
    queue = runner.OWNER_QUEUE.read_text(encoding="utf-8")
    assert "example.com" not in queue and "123456789" not in queue and "[محجوب]" in queue
    assert len(queue.splitlines()) == 1
    assert "example.com" not in lp.read_text(encoding="utf-8")


def test_model_failure_without_verify_still_reports_its_reason(env):
    lp, lock = env
    _card(lp)

    class ModelDown(Fake):
        def run_model(self, tree, prompt, model, budget):
            return runner.Result(False, "رصيد غير كاف")

    assert runner.run_cycle(CFG, ModelDown(), lp, lock) == "referred"
    assert "رصيد غير كاف" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_failure_summary_shows_what_failed_not_what_passed():
    log = "✔ ruff check: نجح\n✘ ruff format --check: فشل\n    Would reformat: tests/a.py\n✔ mypy: نجح\nلا تدفع"
    assert runner.failure_summary(log) == "✘ ruff format --check: فشل Would reformat: tests/a.py"
    assert runner.failure_summary("بلا علامات") == "بلا علامات"
    assert runner.failure_summary("✔ ok" + chr(10) + "    FAILED tests/a.py::t - x") == "FAILED tests/a.py::t - x"


class Dock:
    """دوكر مزيّف: يسجّل الأوامر ويفشل فيما يحوي fail، و`cp` إلى المضيف ينشئ الملف."""

    def __init__(self, fail=()):
        self.cmds, self.fail = [], fail

    def __call__(self, cmd, timeout):
        self.cmds.append(cmd)
        if any(f in " ".join(cmd) for f in self.fail):
            return 1, ""
        if cmd[0] == "cp" and cmd[1].startswith("pg:"):
            Path(cmd[2]).write_bytes(b"dump")
        return 0, ""

    def ran(self, word):
        return any(word in " ".join(c) for c in self.cmds)


def test_cached_db_is_restored_without_building(tmp_path):
    (tmp_path / "prepush_testdb_k.dump").write_bytes(b"d")
    dock = Dock()
    assert runner.prepare_test_db(dock, "pg", "k", ["build"], tmp_path) == "hit"
    assert dock.ran("pg_restore") and not dock.ran("build")


def test_missing_cache_builds_and_saves(tmp_path):
    dock = Dock()
    assert runner.prepare_test_db(dock, "pg", "k", ["build"], tmp_path) == "built"
    assert (tmp_path / "prepush_testdb_k.dump").is_file()


def test_bad_cache_is_dropped_and_rebuilt(tmp_path):
    (tmp_path / "prepush_testdb_k.dump").write_bytes(b"d")
    dock = Dock(fail=("pg_restore",))
    assert runner.prepare_test_db(dock, "pg", "k", ["build"], tmp_path) == "built"
    assert dock.ran("drop database") and dock.ran("build")


def test_failed_build_leaves_no_partial_db(tmp_path):
    dock = Dock(fail=("build",))
    assert runner.prepare_test_db(dock, "pg", "k", ["build"], tmp_path) == "none"
    assert dock.ran("drop database") and not (tmp_path / "prepush_testdb_k.dump").exists()


def test_old_dumps_are_pruned(tmp_path):
    for n in range(runner.DB_CACHE_KEEP + 2):
        f = tmp_path / f"prepush_testdb_{n}.dump"
        f.write_bytes(b"d")
        os.utime(f, (n, n))
    runner.prepare_test_db(Dock(), "pg", "new", ["build"], tmp_path)
    assert len(list(tmp_path.glob("*.dump"))) == runner.DB_CACHE_KEEP


def test_any_migration_change_changes_the_key(tmp_path):
    m = tmp_path / "app" / "migrations"
    m.mkdir(parents=True)
    (m / "0001_a.py").write_text("a", encoding="utf-8")
    first = runner.migrations_key(str(tmp_path), "pg16")
    assert first == runner.migrations_key(str(tmp_path), "pg16")
    (m / "0002_b.py").write_text("b", encoding="utf-8")
    second = runner.migrations_key(str(tmp_path), "pg16")
    (m / "0001_a.py").write_text("changed", encoding="utf-8")
    assert len({first, second, runner.migrations_key(str(tmp_path), "pg16"), runner.migrations_key(str(tmp_path), "pg17")}) == 4


def test_red_ci_goes_back_to_the_model_on_the_same_pr(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.ci = "red"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 2 and not fx.merged
    assert "اعتُمد من المالك" in fx.pr_bodies[-1] or fx.pr_bodies[-1].startswith("البطاقة")
    fx.ci = "green"
    assert runner.run_cycle(CFG, fx, lp, lock) == "published"


def test_red_ci_closes_after_the_repair_limit_and_keeps_the_diff(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.ci = "red"
    for _ in range(runner.CI_FIX_MAX):
        assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged
    assert (runner.FAIL_DIFFS / "W-20261104-901.diff").read_text(encoding="utf-8") == "فرق الفرع"


def test_ci_repair_voids_a_preview_approval(env):
    lp, lock = env
    _card(lp, approval="معاينة", source="owner", preview_approved=True)
    fx = Fake()
    fx.ci = "red"
    runner.run_cycle(CFG, fx, lp, lock)
    assert not _state(lp).get("preview_approved")


def test_rounds_stop_at_five_across_the_whole_ladder(env):
    lp, lock = env
    _card(lp, size="متوسط")
    fx = Fake(verify=(False,))
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == runner.MAX_ROUNDS


def test_review_gets_a_round_after_a_late_gap(env):
    lp, lock = env
    _card(lp, size="متوسط")
    fx = Fake(verify=(False, False, True))
    fx.review_q = [["ناقص"], []]
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 4


def test_every_failed_round_is_noted_and_the_diff_is_kept(env):
    lp, lock = env
    _card(lp, size="متوسط")
    assert runner.run_cycle(CFG, Fake(verify=(False,)), lp, lock) == "referred"
    notes = [e for e in ledger.load_events(lp) if "جولة" in e["data"].get("text", "")]
    assert len(notes) == runner.MAX_ROUNDS
    assert (runner.FAIL_DIFFS / "W-20261104-901.diff").read_text(encoding="utf-8") == "الفرق الكامل"


def test_ci_guards_run_in_the_container():
    assert {"tests/test_file_size.py", "tests/test_layering.py", "tests/test_page_layouts.py"} <= set(runner.LIGHT_GUARDS)


NL = chr(10)


class Logs(Fake):
    """verify فاشل بسجلّات متتالية."""

    def __init__(self, *logs):
        super().__init__(verify=(False,))
        self.logs = list(logs)
        self.verifies = 0

    def verify(self, tree):
        self.verifies += 1
        log = self.logs.pop(0) if len(self.logs) > 1 else self.logs[0]
        return (log == "ok"), log


def test_same_failure_twice_closes_after_two_model_runs_without_escalating(env):
    lp, lock = env
    _card(lp)
    fx = Logs("    FAILED tests/a.py::t - سبب أول", "    FAILED tests/a.py::t - سبب آخر")
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 2
    queue = runner.OWNER_QUEUE.read_text(encoding="utf-8")
    assert queue.count("الفشل نفسه مرتين") == 1 and "tests/a.py::t" in queue


def test_fingerprint_survives_the_ladder_step(env):
    lp, lock = env
    _card(lp)
    fx = Logs("FAILED a", "", "", "FAILED b", "FAILED b")
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 5


def test_empty_fingerprint_never_closes(env):
    lp, lock = env
    _card(lp)
    fx = Logs("سجل بلا فحوص")
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == runner.MAX_ROUNDS


def test_fingerprint_reads_names_and_test_ids_only():
    log = "✘ التعقيد الحلقي (CC ≥ 31): فشل" + NL + "    تفصيل" + NL + "FAILED tests/a.py::t - سبب" + NL + "✔ ruff: نجح"
    assert runner.failure_fingerprint(log) == ("tests/a.py::t", "التعقيد الحلقي (CC ≥ 31)")
    assert runner.failure_fingerprint("لا شيء") == ()


class NewHeads(Fake):
    heads = 0

    def commit_push(self, tree, branch, files, msg):
        self.heads += 1
        return f"h{self.heads}"


def test_same_red_ci_after_a_pushed_fix_closes(env):
    lp, lock = env
    _card(lp)
    fx = NewHeads()
    fx.ci, fx.failed = "red", ["pytest shard 1/8"]
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 2
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 2
    assert "الفشل نفسه مرتين" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_new_red_checks_after_a_fix_get_another_repair(env):
    lp, lock = env
    _card(lp)
    fx = NewHeads()
    fx.ci, fx.failed = "red", ["pytest shard 1/8"]
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    fx.failed = ["pytest shard 2/8"]
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 3


def test_usage_limit_during_ci_repair_keeps_the_open_pr_in_flight(env):
    lp, lock = env
    _card(lp)

    class QuotaOnRepair(Fake):
        def run_model(self, tree, prompt, model, budget):
            if self.runs:
                runner.check_quota("Usage limit reached")
            return super().run_model(tree, prompt, model, budget)

    fx = QuotaOnRepair()
    fx.ci, fx.failed = "red", ["pytest shard 1/8"]
    assert runner.run_cycle(CFG, fx, lp, lock) == "env_down"
    card = _state(lp)
    assert card["state"] == "in_progress" and card["runner_resume"]["pr"] and not fx.removed


def test_small_card_is_not_reviewed(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and not getattr(fx, "reviews", 0)
    assert not any("مراجعة القبول" in e["data"].get("text", "") for e in ledger.load_events(lp))


def _spent(lp, cid, cost, ts=None, label="[مشغّل] sonnet تشغيل 1"):
    ev = ledger.append_event("note", cid, {"text": f"{label}: كلفة={cost:.4f}$ أدوار=1", "by": "runner"}, lp)
    if ts:
        raw = lp.read_text(encoding="utf-8").replace(ev["ts"], ts)
        lp.write_text(raw, encoding="utf-8")


def test_usage_limit_returns_the_card_to_the_queue(env):
    lp, lock = env
    _card(lp)

    class Quota(Fake):
        def run_model(self, tree, prompt, model, budget):
            runner.check_quota("You've hit your session limit · resets 9pm")
            return super().run_model(tree, prompt, model, budget)

    assert runner.run_cycle(CFG, Quota(), lp, lock) == "env_down"
    assert _state(lp)["state"] == "routed"
    queue = runner.OWNER_QUEUE.read_text(encoding="utf-8")
    assert "نفدت حصّة الاشتراك" in queue and "W-20261104-901" not in queue


def test_quota_text_does_not_match_the_run_budget():
    runner.check_quota("Budget limit reached")
    with pytest.raises(runner.EnvDown):
        runner.check_quota("Usage limit reached")


def test_record_run_keeps_tokens_beside_the_unchanged_text(env):
    lp, _ = env
    runner.record_run("W-1", "haiku تشغيل 1", runner.Result(True, "", 0.5, 2, {"usage": {"input_tokens": 3, "output_tokens": 4, "x": {}}}), lp)
    data = ledger.load_events(lp)[-1]["data"]
    assert data["text"] == "[مشغّل] haiku تشغيل 1: كلفة=0.5000$ أدوار=2" and data["usage"] == {"input_tokens": 3, "output_tokens": 4}


def test_format_only_failure_is_fixed_without_a_model_run(env):
    lp, lock = env
    _card(lp)
    fx = Logs("✘ ruff format --check: فشل" + NL + "    Would reformat: a.py", "ok")
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 1 and fx.verifies == 2


def test_autoformat_and_prepush_use_the_same_image(tmp_path, monkeypatch):
    import flow_pump as fp
    seen = []
    fx = runner.Effects(CFG)
    (tmp_path / "a.py").write_text("x=1", encoding="utf-8")
    monkeypatch.setattr(fx, "changed", lambda tree: ["a.py"])
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: seen.append(cmd) or runner.subprocess.CompletedProcess(cmd, 0, "", ""))
    fx.autoformat(str(tmp_path))
    assert fp.PREPUSH_IMAGE in seen[0] and fp.PREPUSH_IMAGE in fp.prepush_command("t", "g", "g", "n", "net")


def test_changed_lists_files_inside_a_new_folder(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "pkg" / "sub").mkdir(parents=True)
    (tmp_path / "pkg" / "sub" / "a.py").write_text("x = 1", encoding="utf-8")
    assert runner.Effects(CFG).changed(str(tmp_path)) == ["pkg/sub/a.py"]


GOOD = "العنوان: ع" + NL + "المطلوب: م" + NL + "معايير القبول: ق" + NL + "الوسم: صغير" + NL


def test_request_that_vanishes_after_glob_makes_no_card(env, monkeypatch):
    lp, _ = env
    runner.REQUESTS.mkdir()
    gone = runner.REQUESTS / "web-1.md"
    gone.write_text(GOOD, encoding="utf-8")
    real = Path.rename

    def lost(self, target):
        if self.name == "web-1.md":
            self.unlink()
            raise FileNotFoundError
        return real(self, target)

    monkeypatch.setattr(Path, "rename", lost)
    assert runner.intake_requests(CFG, lp) == 0 and not ledger.load_events(lp)


def test_request_deleted_before_read_is_skipped(env, monkeypatch):
    lp, _ = env
    runner.REQUESTS.mkdir()
    ghost = runner.REQUESTS / "web-2.md"
    monkeypatch.setattr(Path, "glob", lambda self, pat: [ghost])
    assert runner.intake_requests(CFG, lp) == 0 and not ledger.load_events(lp)


def test_card_links_back_to_its_request_and_retry(env):
    lp, _ = env
    runner.REQUESTS.mkdir()
    (runner.REQUESTS / "web-20261105-164506.md").write_text(GOOD + "إعادة لـ: R-7" + NL, encoding="utf-8")
    assert runner.intake_requests(CFG, lp) == 1
    created = next(e for e in ledger.load_events(lp) if e["kind"] == "created")["data"]
    assert created["request_file"] == "web-20261105-164506" and created["retry_of"] == "R-7"
    assert (runner.REQUESTS / "web-20261105-164506.done").is_file()


E2E = "Playwright — e2e"


def _cancelled(fx):
    fx.ci, fx.failed, fx.cancelled = "red", [E2E, runner.GATE_SUMMARY], {E2E: "42"}
    return fx


def test_cancelled_check_is_rerun_without_the_model(env):
    lp, lock = env
    _card(lp)
    fx = _cancelled(Fake())
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    assert fx.reruns == ["42"] and fx.runs == 1
    fx.ci = "green"
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 1


def test_cancelled_shown_without_a_failed_name_still_never_passes_as_green(env):
    lp, lock = env
    _card(lp)
    fx = _cancelled(Fake())
    fx.failed = []
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and not fx.merged and fx.reruns == ["42"]


def test_repeated_cancel_closes_as_a_ci_fault_with_no_model_run(env):
    lp, lock = env
    _card(lp)
    fx = _cancelled(Fake())
    for _ in range(runner.CI_RERUN_MAX):
        assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 1 and not fx.merged
    assert "عطل بنية في CI" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_a_real_failure_beside_a_cancel_goes_to_the_model(env):
    lp, lock = env
    _card(lp)
    fx = _cancelled(Fake())
    fx.failed = [E2E, "pytest shard 1/8", runner.GATE_SUMMARY]
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 2 and not getattr(fx, "reruns", [])


def test_infra_runs_reads_state_and_run_id(monkeypatch):
    rows = [{"name": "e2e", "state": "CANCELLED", "link": "https://x/actions/runs/42/job/7"},
            {"name": "ok", "state": "SUCCESS", "link": "https://x/actions/runs/43/job/8"}]
    out = runner.json.dumps(rows)
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: runner.subprocess.CompletedProcess(cmd, 0, out, ""))
    assert runner.Effects(CFG).infra_runs(".", 1) == {"e2e": "42"}


def test_checks_state_treats_cancel_as_red(monkeypatch):
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: runner.subprocess.CompletedProcess(cmd, 0, "e2e" + chr(9) + "cancel" + chr(9) + "5m", ""))
    assert runner.Effects(CFG).checks_state(".", 1) == "red"


def _preview_card(lp, cid="W-20261104-901"):
    _card(lp, cid, approval="معاينة")
    ledger.append_event("update", cid, {"source": "owner", "scope_page": "/quality/", "accept": ["make prepush ينجح", "علامة صح في PDF"]}, lp)


def _queue():
    return runner.OWNER_QUEUE.read_text(encoding="utf-8") if runner.OWNER_QUEUE.is_file() else ""


def test_preview_is_requested_only_after_8500_serves_the_card(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_preview"
    assert len(fx.pins) == 1 and "جاهز للمعاينة" not in _queue()
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_preview"
    line = _queue()
    assert line.count("جاهز للمعاينة") == 1 and "http://localhost:8500/quality/" in line and "99900001" in line
    assert "علامة صح في PDF" in line and "make prepush" not in line and "--approve W-20261104-901" in line
    runner.run_cycle(CFG, fx, lp, lock)
    assert _queue().count("جاهز للمعاينة") == 1 and len(fx.pins) == 1


def test_password_value_is_never_in_the_message():
    info = runner.preview_info({"id": "W", "accept": []}, 1)
    assert info["password_at"] == "tools/.preview_accounts.env" and "password" not in info


def test_approval_is_refused_until_the_head_was_served(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    runner.run_cycle(CFG, fx, lp, lock)
    ok, text = runner.decide_preview("W-20261104-901", True, lpath=lp)
    assert not ok and "لم يُعرض" in text
    runner.run_cycle(CFG, fx, lp, lock)
    assert runner.decide_preview("W-20261104-901", True, lpath=lp)[0]
    assert _state(lp)["preview_approved"] is True


def test_approved_card_merges_and_its_pin_is_released(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    runner.run_cycle(CFG, fx, lp, lock)
    runner.run_cycle(CFG, fx, lp, lock)
    runner.decide_preview("W-20261104-901", True, lpath=lp)
    for _ in range(3):
        runner.run_cycle(CFG, fx, lp, lock)
    assert fx.merged


def test_reject_needs_a_reason_then_closes_card_and_pr(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    runner.run_cycle(CFG, fx, lp, lock)
    assert not runner.decide_preview("W-20261104-901", False, " ", lp)[0]
    assert runner.decide_preview("W-20261104-901", False, "العلامة مائلة", lp)[0]
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.closed_pr and not fx.merged
    assert "العلامة مائلة" in _queue()


def test_expired_pin_voids_the_shown_head_and_pins_again(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    runner.run_cycle(CFG, fx, lp, lock)
    runner.run_cycle(CFG, fx, lp, lock)
    fx.pinned = ""
    runner.run_cycle(CFG, fx, lp, lock)
    assert len(fx.pins) == 2 and not _state(lp)["preview_seen"]


def test_second_card_is_shown_on_a_slot_beside_8500(env):
    lp, lock = env
    _preview_card(lp, "W-20261104-901")
    _preview_card(lp, "W-20261104-902")

    class Trees(Fake):
        def prepare_tree(self, card_id, round_no=1):
            return f"/t/{card_id}", "b"

    fx = Trees()
    fx.ci = "green"
    for _ in range(3):
        runner.run_cycle(CFG, fx, lp, lock)
    assert len(fx.pins) == 1 and fx.slots == [8601] and _queue().count("جاهز للمعاينة") == 2


class Pinned(Fake):
    def __init__(self, tree, beat=""):
        super().__init__()
        self.tree, self.beat = tree, beat

    def preview_state(self):
        return {"mode": "pin", "pin_tree": self.tree, "pin_until": "9999999999", "watch_hb": self.beat}


WT = {"worktrees": "C:/wt"}


def test_runner_pin_with_no_waiting_card_is_released(env):
    lp, _ = env
    fx = Pinned("C:/wt/runner-W-1-r1")
    runner.preview_cycle(WT, fx, lp)
    assert fx.releases == 1 and not getattr(fx, "ticks", 0)


def test_someone_elses_pin_is_left_alone(env):
    lp, _ = env
    fx = Pinned("D:/x/session-tree")
    runner.preview_cycle(WT, fx, lp)
    assert not getattr(fx, "releases", 0) and fx.ticks == 1


def test_dead_watch_is_reported_once_a_day_while_previews_wait(env):
    lp, lock = env
    _preview_card(lp)
    fx = Fake()
    runner.run_cycle(CFG, fx, lp, lock)
    fx.preview_state = lambda: {"watch_hb": "1000"}
    runner.preview_cycle(WT, fx, lp)
    runner.preview_cycle(WT, fx, lp)
    assert _queue().count("خادم المعاينة متوقّف") == 1


def test_preview_state_reads_the_state_files(tmp_path, monkeypatch):
    base = tmp_path / "preview-state"
    base.mkdir()
    (base / "mode").write_text("pin" + chr(10), encoding="utf-8")
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: runner.subprocess.CompletedProcess(cmd, 0, str(tmp_path) + chr(10), ""))
    st = runner.Effects({**CFG, "repo": "R"}).preview_state()
    assert st["mode"] == "pin" and st["pin_tree"] == ""


def test_pin_command_lifts_the_limit_for_this_call_only(monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: seen.append(cmd) or runner.subprocess.CompletedProcess(cmd, 0, "", ""))
    runner.Effects({**CFG, "repo": "R"}).preview_pin("C:/wt/t")
    assert seen[0][0] == runner.GIT_BASH and "PREVIEW_PIN_MAX_MINUTES=720" in seen[0][2] and 'pin "C:/wt/t" 720' in seen[0][2]


def _shown(lp, lock, fx):
    _preview_card(lp)
    runner.run_cycle(CFG, fx, lp, lock)
    runner.run_cycle(CFG, fx, lp, lock)
    return _queue()


def test_seeded_record_link_reaches_the_owner_and_its_cost_counts(env):
    lp, lock = env
    line = _shown(lp, lock, Fake())
    assert "http://localhost:8500/quality/observations/1/pdf/view/" in line and "لم تُبذر" not in line
    assert runner.COST_NOTE.match("[مشغّل] بذر المعاينة: كلفة=0.0500$ أدوار=3")


def test_seed_error_goes_back_to_the_model_once(env):
    lp, lock = env
    fx = Fake()
    fx.seed_runs = [(False, "NameError: Foo"), (True, "PREVIEW_PATH=/x/")]
    assert "http://localhost:8500/x/" in _shown(lp, lock, fx)
    assert len(fx.seed_prompts) == 2 and "NameError: Foo" in fx.seed_prompts[1]


def test_failed_seed_blocks_ready_and_approval_and_is_not_retried_each_cycle(env):
    lp, lock = env
    fx = Fake()
    fx.seed_runs = [(False, "NameError: Foo")]
    line = _shown(lp, lock, fx)
    assert "تعذّرت المعاينة" in line and "جاهز للمعاينة" not in line and "--reseed" in line
    assert len(fx.seed_prompts) == runner.SEED_ATTEMPTS
    runner.run_cycle(CFG, fx, lp, lock)
    assert len(fx.seed_prompts) == runner.SEED_ATTEMPTS and _queue().count("تعذّرت المعاينة") == 1
    assert not runner.decide_preview("W-20261104-901", True, lpath=lp)[0]


def test_reseed_tries_again(env, monkeypatch):
    lp, lock = env
    fx = Fake()
    fx.seed_runs = [(False, "x")]
    _shown(lp, lock, fx)
    monkeypatch.setattr(runner.ledger, "append_event", lambda *a, _f=runner.ledger.append_event: _f(*a, lp) if len(a) == 3 else _f(*a))
    assert runner.main(["--reseed", "W-20261104-901"]) == 0
    fx.seed_runs = [(True, "PREVIEW_PATH=/ok/")]
    runner.run_cycle(CFG, fx, lp, lock)
    assert "http://localhost:8500/ok/" in _queue()


def test_link_that_the_account_cannot_open_goes_back_to_the_model(env):
    lp, lock = env
    fx = Fake()
    fx.seed_checks = [(False, "PREVIEW_STATUS=403"), (True, "PREVIEW_STATUS=200")]
    assert "جاهز للمعاينة" in _shown(lp, lock, fx)
    assert len(fx.seed_prompts) == 2 and "PREVIEW_STATUS=403" in fx.seed_prompts[1] and "99900001" in fx.seed_prompts[1]


def test_no_script_in_the_answer_never_runs_anything(env):
    lp, lock = env
    fx = Fake()
    fx.seed_q = ["لا أستطيع"]
    fx.run_seed = lambda s: pytest.fail("شُغّل نصٌّ ليس سكربتاً")
    assert "تعذّرت المعاينة" in _shown(lp, lock, fx)


def test_check_goes_through_the_real_server_and_needs_200(monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "open_as", lambda account, path, base="": seen.append((account, path)) or 404)
    ok, log = runner.Effects(CFG).check_seed("/a/", "99900001")
    assert not ok and "404" in log and seen == [("99900001", "/a/")]


def test_rls_mapping_failure_stops_before_any_model_cost(env):
    lp, lock = env
    fx = Fake()
    fx.map_result = (False, "لا مدرسة")
    assert "تعذّرت المعاينة" in _shown(lp, lock, fx) and not getattr(fx, "seed_prompts", [])


def test_rls_is_mapped_for_the_preview_account_first(env):
    lp, lock = env
    fx = Fake()
    _shown(lp, lock, fx)
    assert fx.mapped == "99900001"


def test_rls_statement_runs_behind_the_pin_guard(monkeypatch):
    fx = runner.Effects(CFG)
    seen = []
    monkeypatch.setattr(fx, "run_seed", lambda s: seen.append(s) or (True, ""))
    fx.map_rls("99900001")
    assert "app_rls_role_school" in seen[0] and "employee_number='99900001'" in seen[0]


def test_seed_guard_runs_first_and_accepts_only_a_pin_copy(monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "sh", lambda cmd, cwd, t=0, stdin=None: seen.append((cmd, stdin)) or runner.subprocess.CompletedProcess(cmd, 0, "", ""))
    fx = runner.Effects({**CFG, "repo": "R"})
    monkeypatch.setattr(fx, "preview_slot", lambda: "b")
    fx.run_seed("print(1)")
    cmd, stdin = seen[0]
    assert "schoolos-main-preview-b-web-1" in cmd and stdin.startswith(runner.SEED_GUARD) and stdin.endswith("print(1)")
    pattern = runner.re.search(r"r'(.+?)'", runner.SEED_GUARD).group(1)
    assert runner.re.fullmatch(pattern, "ss_runner_w_preview") and not runner.re.fullmatch(pattern, "ss_main_preview_g73")
    assert not runner.re.fullmatch(pattern, "shschool_db")


def test_seed_body_takes_the_fenced_script_only():
    assert runner.seed_body("شرح" + chr(10) + "```python" + chr(10) + "a=1" + chr(10) + "```") == "a=1" + chr(10)
    assert runner.seed_body("a=1") == ""


def test_visible_change_turns_a_direct_card_into_preview_before_the_pr(env):
    lp, lock = env
    _card(lp, approval="مباشر", source="owner")
    bodies = []

    class Opens(Fake):
        def open_pr(self, tree, branch, title, body):
            bodies.append(body)
            return super().open_pr(tree, branch, title, body)

    fx = Opens(files=("templates/quality/a.html", "tests/test_a.py"))
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_preview" and not fx.merged
    assert _state(lp)["approval"] == "معاينة"
    assert bodies and not any("مباشرةً" in b for b in bodies)


def test_static_change_counts_and_backend_change_stays_direct(env):
    lp, lock = env
    card = {"id": "W-1", "approval": "مباشر"}
    runner.require_preview(card, ["core/a.py", "tests/test_a.py"], lp)
    assert card["approval"] == "مباشر"
    runner.require_preview(card, ["static/css/a.css"], lp)
    assert card["approval"] == "معاينة"


def test_ci_repair_that_touches_a_template_requires_preview(env):
    lp, lock = env
    _card(lp, approval="مباشر", source="owner")
    fx = Fake()
    fx.ci = "red"
    runner.run_cycle(CFG, fx, lp, lock)
    fx.files = ["templates/a.html"]
    runner.run_cycle(CFG, fx, lp, lock)
    assert _state(lp)["approval"] == "معاينة"


def test_coverage_fallen_with_a_cancelled_shard_is_rerun_not_sent_to_the_model(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.ci, fx.failed, fx.cancelled = "red", ["pytest shard 3/8", "pytest — تغطية", runner.GATE_SUMMARY], {"pytest shard 3/8": "42"}
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.reruns == ["42"] and fx.runs == 1


def _checks(monkeypatch, rows):
    out = runner.json.dumps(rows)
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: runner.subprocess.CompletedProcess(cmd, 0, out, ""))


def test_failure_in_an_infra_step_counts_as_infra(monkeypatch):
    _checks(monkeypatch, [{"name": "shard", "state": "FAILURE", "link": "https://x/actions/runs/42/job/7"},
                          {"name": "ruff", "state": "FAILURE", "link": "https://x/actions/runs/42/job/8"}])
    fx = runner.Effects(CFG)
    monkeypatch.setattr(fx, "infra_jobs", lambda tree, run: ["shard"])
    assert fx.infra_runs(".", 1) == {"shard": "42"}


def test_infra_jobs_uses_the_main_copy_of_the_judge(monkeypatch, tmp_path):
    f = tmp_path / "ci_needs_gate.py"
    f.write_text("def infra_failures(jobs):" + chr(10) + "    return [jobs]" + chr(10), encoding="utf-8")
    _checks(monkeypatch, [])
    fx = runner.Effects(CFG)
    monkeypatch.setattr(fx, "main_file", lambda rel: str(f))
    assert fx.infra_jobs(".", "42") == ["[]"]


def test_unreadable_judge_leaves_the_failure_as_code(monkeypatch):
    _checks(monkeypatch, [])
    fx = runner.Effects(CFG)
    monkeypatch.setattr(fx, "main_file", lambda rel: "")
    assert fx.infra_jobs(".", "42") == []


def test_failed_names_include_cancelled(monkeypatch):
    t = chr(9)
    out = chr(10).join([f"shard{t}cancel{t}5m", f"cov{t}fail{t}1m", f"ok{t}pass{t}1m"])
    monkeypatch.setattr(runner, "sh", lambda cmd, *a: runner.subprocess.CompletedProcess(cmd, 0, out, ""))
    assert runner.Effects(CFG).failed_names(".", 1) == ["shard", "cov"]


def test_no_change_in_ci_repair_closes_at_once_with_no_second_round(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.ci = "red"
    runner.run_cycle(CFG, fx, lp, lock)
    fx.files, runs = [], fx.runs
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == runs + 1 and not fx.merged
    assert "لم يُحدث" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_affected_env_joins_branch_and_uncommitted_files(monkeypatch, tmp_path):
    fx = runner.Effects(CFG)
    tool = tmp_path / "affected_tests.py"
    monkeypatch.setattr(fx, "main_file", lambda rel: str(tool))
    monkeypatch.setattr(fx, "changed", lambda tree: ["b.py", "c.py"])
    monkeypatch.setattr(runner, "_git", lambda tree, *a: (0, "a.py" + chr(0) + "b.py"))
    env = fx.affected_env(".")
    assert env[1] == f"{tmp_path}:/affected:ro" and "PREPUSH_AFFECTED=/affected/affected_tests.py" in env
    assert env[-1] == "PREPUSH_AFFECTED_FILES=" + chr(10).join(["a.py", "b.py", "c.py"])


def test_affected_env_is_empty_without_the_main_tool(monkeypatch):
    fx = runner.Effects(CFG)
    monkeypatch.setattr(fx, "main_file", lambda rel: "")
    monkeypatch.setattr(fx, "changed", lambda tree: ["b.py"])
    monkeypatch.setattr(runner, "_git", lambda tree, *a: (0, ""))
    assert fx.affected_env(".") == []


def _held(lp, lock, fx):
    _card(lp, merge_hold=True)
    return runner.run_cycle(CFG, fx, lp, lock)


def test_held_card_waits_green_and_reports_once(env):
    lp, lock = env
    fx = Fake()
    assert _held(lp, lock, fx) == "waiting_owner" and not fx.merged
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_owner"
    assert runner.OWNER_QUEUE.read_text(encoding="utf-8").count("--release") == 1


def test_release_merges_the_head_that_was_read(env):
    lp, lock = env
    fx = Fake()
    _held(lp, lock, fx)
    assert runner.release_merge("W-20261104-901", lp)[0]
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.merged


def test_release_does_not_cover_a_later_head(env):
    lp, lock = env
    fx = Fake()
    _held(lp, lock, fx)
    runner.release_merge("W-20261104-901", lp)
    card = _state(lp)
    r = {**card["runner_resume"], "head": "other"}
    ledger.append_event("update", card["id"], {"runner_resume": r}, lp)
    assert runner.hold_for_owner(_state(lp), lp, 1, "other") == "waiting_owner"
    assert _state(lp)["merge_released"] != "other"


def test_release_refuses_a_card_that_is_not_held(env):
    lp, lock = env
    _card(lp)
    assert not runner.release_merge("W-20261104-901", lp)[0]


def test_a_card_past_three_dollars_is_not_closed_for_cost(env):
    lp, lock = env
    _card(lp)
    fx = Fake(verify=(False, True), cost=4.0)
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 2


def test_ci_repair_past_three_dollars_still_runs_the_model(env):
    lp, lock = env
    _card(lp)
    fx = Fake(cost=4.0)
    fx.ci = "red"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 2


def test_a_heavy_day_does_not_stop_new_cards(env):
    lp, lock = env
    _spent(lp, "W-1", 500.0)
    _card(lp)
    assert runner.run_cycle(CFG, Fake(), lp, lock) == "published"


def test_the_single_run_cap_stays(env):
    lp, lock = env
    _card(lp)
    seen = []
    fx = Fake()
    real = fx.run_model
    fx.run_model = lambda tree, prompt, model, budget: seen.append(budget) or real(tree, prompt, model, budget)
    runner.run_cycle(CFG, fx, lp, lock)
    assert seen and seen[0] == runner._tiers(CFG, _state(lp))[0][2]


def test_a_deleted_test_is_not_handed_to_pytest(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_kept.py").write_text("", encoding="utf-8")
    assert runner.referenced_tests(str(tmp_path), ["tests/test_kept.py", "tests/test_gone.py"]) == ["tests/test_kept.py"]


def _commits(monkeypatch, outs):
    calls = []

    def sh(cmd, *a, **k):
        calls.append(cmd)
        if cmd[:2] == ["git", "commit"]:
            rc, out = outs.pop(0)
            return runner.subprocess.CompletedProcess(cmd, rc, out, "")
        return runner.subprocess.CompletedProcess(cmd, 0, "h1", "")
    monkeypatch.setattr(runner, "sh", sh)
    return calls


def test_baseline_refresh_by_the_hook_is_added_and_committed_again(monkeypatch):
    calls = _commits(monkeypatch, [(1, runner.BASELINE_UPDATED), (0, "")])
    assert runner.Effects(CFG).commit_push(".", "b", ["a.yml"], "m") == "h1"
    assert ["git", "add", "--", runner.SECRETS_BASELINE] in calls


def test_a_new_secret_still_stops_the_commit_on_the_second_pass(monkeypatch):
    _commits(monkeypatch, [(1, runner.BASELINE_UPDATED), (1, "Potential secrets")])
    with pytest.raises(runner.RunnerError, match="تعذّر الإيداع"):
        runner.Effects(CFG).commit_push(".", "b", ["a.yml"], "m")


def test_any_other_hook_failure_does_not_touch_the_baseline(monkeypatch):
    calls = _commits(monkeypatch, [(1, "ruff failed")])
    with pytest.raises(runner.RunnerError):
        runner.Effects(CFG).commit_push(".", "b", ["a.yml"], "m")
    assert ["git", "add", "--", runner.SECRETS_BASELINE] not in calls


def test_security_summary_fallen_with_a_cancelled_audit_is_not_sent_to_the_model(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.ci, fx.failed = "red", ["pip-audit", "Security Summary", "pytest shard 6/8", "pytest — تغطية", runner.GATE_SUMMARY]
    fx.cancelled = {"pip-audit": "41", "pytest shard 6/8": "42"}
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and sorted(fx.reruns) == ["41", "42"] and fx.runs == 1


def test_parallel_hook_passes_need_several_baseline_retries(monkeypatch):
    _commits(monkeypatch, [(1, runner.BASELINE_UPDATED)] * 3 + [(0, "")])
    assert runner.Effects(CFG).commit_push(".", "b", ["a.yml"], "m") == "h1"


def test_baseline_retries_stop_at_the_limit(monkeypatch):
    _commits(monkeypatch, [(1, runner.BASELINE_UPDATED)] * (runner.BASELINE_TRIES + 1))
    with pytest.raises(runner.RunnerError, match="تعذّر الإيداع"):
        runner.Effects(CFG).commit_push(".", "b", ["a.yml"], "m")


def test_a_pdf_with_fallback_fonts_never_reaches_the_owner(env):
    lp, lock = env
    fx = Fake()
    fx.fallback = ["DejaVu-Sans"]
    text = _shown(lp, lock, fx)
    assert "خطوط احتياطية" in text and "جاهز للمعاينة" not in text
    assert not _state(lp).get("preview_seen")


def test_only_pdf_pages_are_checked_and_view_is_stripped(monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "fetch_as", lambda a, p, base="": seen.append(p) or (404, b""))
    fx = runner.Effects(CFG)
    assert fx.pdf_fallback_fonts("/students/", "1") == [] and not seen
    assert fx.pdf_fallback_fonts("/q/1/pdf/view/", "1") == ["لم يُفحص: HTTP 404"] and seen == ["/q/1/pdf/"]


def test_unreadable_pdf_is_reported_not_passed(monkeypatch):
    monkeypatch.setattr(runner, "fetch_as", lambda a, p, base="": (200, b"not a pdf"))
    assert runner.Effects(CFG).pdf_fallback_fonts("/q/1/pdf/", "1")[0].startswith("لم يُفحص")


def test_real_owner_file_fonts_are_named_by_the_check(monkeypatch):
    import fitz
    doc = fitz.open()
    doc.new_page()
    monkeypatch.setattr(runner, "fetch_as", lambda a, p, base="": (200, doc.tobytes()))
    assert runner.Effects(CFG).pdf_fallback_fonts("/q/1/pdf/", "1") == []


def test_a_conflicted_pr_stops_waiting_for_the_queue_and_frees_its_slot(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.merge_state, fx.conflicted = "OPEN", True
    closed = []
    fx.close_pr = lambda tree, pr: closed.append(pr)
    runner.run_cycle(CFG, fx, lp, lock)
    runner.run_cycle(CFG, fx, lp, lock)
    assert closed and _state(lp)["state"] == "closed" and "تعارض دمج" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def _attempt(cid, request, retry_of, lp):
    ledger.append_event("created", cid, {"problem": "x", "request_file": request, "retry_of": retry_of}, lp)


def test_a_retry_finds_every_earlier_attempt(env):
    lp, _ = env
    _attempt("W-1", "web-1", "", lp)
    _attempt("W-2", "web-2", "web-1", lp)
    assert runner.earlier_attempts({"id": "W-3", "retry_of": "web-2"}, lp) == ["W-2", "W-1"]


def test_a_card_without_retry_has_no_earlier_attempt(env):
    lp, _ = env
    _attempt("W-1", "web-1", "", lp)
    assert runner.earlier_attempts({"id": "W-2", "retry_of": ""}, lp) == []


def test_a_retry_loop_in_the_ledger_ends(env):
    lp, _ = env
    _attempt("W-1", "web-1", "web-2", lp)
    _attempt("W-2", "web-2", "web-1", lp)
    assert runner.earlier_attempts({"id": "W-3", "retry_of": "web-1"}, lp) == ["W-1", "W-2"]


def _running(cid, files=(), **extra):
    return {"id": cid, "state": "in_progress", "scope_files": list(files), "runner_resume": {"head": "h1"}, **extra}


def test_card_shown_to_owner_does_not_hold_a_slot():
    assert runner.awaiting_owner(_running("a", approval="معاينة", preview_seen="h1"))
    assert not runner.awaiting_owner(_running("a", approval="معاينة", preview_seen="old"))
    assert not runner.awaiting_owner(_running("a", approval="معاينة", preview_seen="h1", preview_approved=True))
    assert not runner.awaiting_owner(_running("a", approval="مباشر"))


def test_card_held_for_diff_reading_does_not_hold_a_slot():
    assert runner.awaiting_owner(_running("a", merge_hold_told="h1"))
    assert not runner.awaiting_owner(_running("a", merge_hold_told="h1", merge_released="h1"))


def test_shared_file_clashes_even_with_a_card_awaiting_owner():
    waiting = _running("a", ["x.py"], approval="معاينة", preview_seen="h1")
    assert runner.clashes({"scope_files": ["x.py"]}, [waiting])
    assert not runner.clashes({"scope_files": ["y.py"]}, [waiting])


def test_unknown_scope_runs_alone_among_working_cards():
    working = _running("a", ["x.py"])
    assert runner.clashes({"scope_files": []}, [working])
    assert runner.clashes({"scope_files": ["y.py"]}, [_running("b")])
    assert not runner.clashes({"scope_files": []}, [])


def test_unknown_scope_card_awaiting_owner_blocks_nothing():
    waiting = _running("a", approval="معاينة", preview_seen="h1")
    assert not runner.clashes({"scope_files": ["y.py"]}, [waiting])
    assert not runner.clashes({"scope_files": []}, [waiting])


class VisualRed(Fake):
    """فحصُ اللقطات أحمرُ بفرق صفحات؛ وبعد الوسم يخضرّ."""

    def __init__(self, log="E   mobile/light/a--b.png: 0.838%\nE   desktop/light/a--b.png: 0.317%"):
        super().__init__()
        self.ci, self.log, self.marked = "red", log, 0

    def failed_names(self, tree, pr): return ["لقطات الهويّة — حتميّةٌ ومقارنة"]
    def infra_runs(self, tree, pr): return {}
    def ci_log(self, tree, pr): return self.log
    def mark_visual(self, tree, pr): self.marked += 1


def test_visual_diff_on_a_preview_card_is_labelled_and_named_not_repaired(env):
    lp, lock = env
    _preview_card(lp)
    fx = VisualRed()
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    assert fx.marked == 1 and fx.runs == 1
    assert "mobile/light/a--b.png" in fx.pr_bodies[-1] and "mobile/light/a--b.png" in _queue()


def test_visual_diff_is_marked_once_per_head_then_goes_to_the_model(env):
    lp, lock = env
    _preview_card(lp)
    fx = VisualRed()
    runner.run_cycle(CFG, fx, lp, lock)
    runner.run_cycle(CFG, fx, lp, lock)
    assert fx.marked == 1 and fx.runs >= 2


def test_a_failure_without_page_diffs_is_not_labelled(env):
    lp, lock = env
    _preview_card(lp)
    fx = VisualRed(log="E   determinism failed")
    runner.run_cycle(CFG, fx, lp, lock)
    assert fx.marked == 0 and fx.runs >= 2


def test_a_direct_card_is_never_labelled(env):
    lp, lock = env
    _card(lp)
    fx = VisualRed()
    runner.run_cycle(CFG, fx, lp, lock)
    assert fx.marked == 0


def test_added_lines_reads_zero_context_hunks():
    assert runner.added_lines("@@ -3,0 +4,2 @@ x" + chr(10) + "@@ -9 +12 @@") == {4, 5, 12}


def test_new_mypy_errors_prefers_added_lines_then_the_whole_file():
    out = chr(10).join(["a/b.py:4: error: new  [x]", "a/b.py:9: error: old  [x]", "c.py:4: error: other  [x]"])
    assert runner.new_mypy_errors(out, {"a/b.py": {4}}) == ["a/b.py:4: error: new  [x]"]
    assert len(runner.new_mypy_errors(out, {"a/b.py": {50}})) == 2


def test_fewer_mypy_errors_is_not_the_same_failure_twice():
    one = runner.failure_fingerprint("✘ mypy ratchet: فشل" + chr(10) + "    زاد: b/s.py: 17 → 19")
    two = runner.failure_fingerprint("✘ mypy ratchet: فشل" + chr(10) + "    زاد: b/s.py: 17 → 18")
    assert one != two and one == runner.failure_fingerprint("✘ mypy ratchet: فشل" + chr(10) + "    زاد: b/s.py: 17 → 19")


def _on_preview(lp, cid, tree="/t"):
    _preview_card(lp, cid)
    ledger.append_event("update", cid, {"runner_resume": {"pr": 1, "branch": "b", "head": "h1", "tree": tree, "spent": 0}}, lp)
    return ledger.reduce_state(ledger.load_events(lp))[cid]


def test_busy_8500_gives_the_card_a_slot_and_shows_it_there(env):
    lp, _ = env
    card = _on_preview(lp, "W-20261104-902")
    fx = Fake()
    fx.pinned = "/other"
    assert runner.preview_step(card, fx, lp, "/t", "h1", 1) == "waiting_preview"
    got = ledger.reduce_state(ledger.load_events(lp))["W-20261104-902"]
    assert fx.slots == [8601] and got["preview_slot_port"] == 8601 and got["preview_seen"] == "h1"
    assert got["preview_info"]["url"].startswith("http://localhost:8601/") and fx.target == 0


def test_free_8500_is_used_before_any_slot(env):
    lp, _ = env
    card = _on_preview(lp, "W-20261104-902")
    fx = Fake()
    runner.preview_step(card, fx, lp, "/t", "h1", 1)
    assert fx.pins == ["/t"] and not getattr(fx, "slots", [])


def test_all_slots_busy_keeps_the_card_waiting(env):
    lp, _ = env
    for n, port in (("903", 8601), ("904", 8602)):
        _preview_card(lp, "W-20261104-" + n)
        ledger.append_event("update", "W-20261104-" + n, {"preview_slot_port": port}, lp)
    card = _on_preview(lp, "W-20261104-902")
    fx = Fake()
    fx.pinned = "/other"
    assert runner.preview_step(card, fx, lp, "/t", "h1", 1) == "waiting_preview"
    assert not getattr(fx, "slots", [])


def test_failed_slot_is_reported_once_per_head(env):
    lp, _ = env
    card = _on_preview(lp, "W-20261104-902")
    fx = Fake()
    fx.pinned, fx.slot_ok = "/other", False
    runner.preview_step(card, fx, lp, "/t", "h1", 1)
    card = ledger.reduce_state(ledger.load_events(lp))["W-20261104-902"]
    runner.preview_step(card, fx, lp, "/t", "h1", 1)
    assert len(fx.slots) == 1


def test_a_decided_card_frees_its_slot(env):
    lp, _ = env
    _on_preview(lp, "W-20261104-902")
    ledger.append_event("update", "W-20261104-902", {"preview_slot_port": 8601, "preview_approved": True}, lp)
    fx = Fake()
    runner.preview_cycle(CFG, fx, lp)
    assert fx.downs == [8601] and ledger.reduce_state(ledger.load_events(lp))["W-20261104-902"]["preview_slot_port"] == 0
    assert runner.free_slot(lp) == 8601


def test_a_slot_that_fell_is_claimed_again_and_reseeded(env):
    lp, _ = env
    _on_preview(lp, "W-20261104-902")
    ledger.append_event("update", "W-20261104-902", {"preview_slot_port": 8601, "preview_seen": "h1"}, lp)
    card = ledger.reduce_state(ledger.load_events(lp))["W-20261104-902"]
    fx = Fake()
    fx.pinned, fx.slot_live = "/other", False
    runner.preview_step(card, fx, lp, "/t", "h1", 1)
    got = ledger.reduce_state(ledger.load_events(lp))["W-20261104-902"]
    assert fx.slots == [8601] and got["preview_slot_port"] == 8601 and got["preview_seen"] == "h1"


def test_a_different_mypy_error_with_the_same_count_is_not_a_repeat():
    head = "✘ mypy ratchet: فشل" + chr(10) + "    زاد: b/s.py: 0 → 1" + chr(10)
    one = runner.failure_fingerprint(head + 'b/s.py:166: error: Argument 1 has incompatible type "F"  [arg-type]')
    two = runner.failure_fingerprint(head + 'b/s.py:166: error: Argument 1 has incompatible type "str"  [arg-type]')
    moved = runner.failure_fingerprint(head + 'b/s.py:170: error: Argument 1 has incompatible type "F"  [arg-type]')
    assert one != two and one == moved


URLS_DIFF = """+++ b/behavior/urls.py
+    path("daily/", views_daily.daily_report, name="daily"),
+    path(
+        "daily/export/pdf/",
+        views_daily.export_pdf,
+        name="daily_pdf",
+    ),
"""


def test_a_new_page_without_a_menu_link_goes_back_to_the_model():
    gap = runner.menu_gap("behavior/daily/?date=2026-11-07", URLS_DIFF, "{% url 'behavior:statistics' %}")
    assert len(gap) == 1 and runner.MENU_FILE in gap[0]
    assert runner.menu_gap("/behavior/daily/", URLS_DIFF, "{% url 'behavior:daily' %}") == []


def test_only_the_cards_own_new_page_needs_a_link():
    assert runner.menu_gap("behavior/statistics/", URLS_DIFF, "") == []  # صفحة قائمة: لا مسار مضاف لها
    detail = '+    path("student/<uuid:pk>/", v, name="student"),'
    assert runner.menu_gap("behavior/student/1/", detail, "") == []
    assert runner.menu_gap("", URLS_DIFF, "") == []


def test_the_menu_file_is_inside_any_declared_scope():
    card = {"runner_checks": ["scope_only"], "scope_files": ["app/views.py"]}
    assert runner.criteria_failures(card, ["app/views.py", runner.MENU_FILE]) == []


def test_an_advisory_red_alone_does_not_send_the_card_to_repair(env):
    lp, _ = env
    card = _on_preview(lp, "W-20261104-902")
    fx = Fake()
    fx.ci, fx.failed = "red", ["روابطُ المسارات الجديدة — استشاري", runner.APPROVAL_CHECK]
    assert runner.finish(card, CFG, fx, lp, "/t", "b", "h1", 1) == "waiting_preview"


def test_brief_names_the_synthetic_number_ranges():
    assert "2900000000x" in runner.brief({"id": "W-1", "accept": ["x"]}, [])


def test_new_files_are_visible_and_formatted_before_the_checks(monkeypatch):
    import flow_pump as fp

    calls, docker = [], []
    monkeypatch.setattr(runner, "sh", lambda cmd, cwd=None, *a: calls.append(cmd) or __import__("types").SimpleNamespace(stdout=" A new.py" + chr(10), stderr="", returncode=0))
    monkeypatch.setattr(fp, "_image_present", lambda d: True)
    monkeypatch.setattr(fp, "_docker", lambda cmd, t: docker.append(cmd) or (0, ""))
    monkeypatch.setattr(runner.Path, "is_file", lambda self: True)
    runner.Effects(CFG).prepare_for_checks("/t")
    assert calls[0] == ["git", "add", "-N", "--", "."]
    assert [c[c.index("ruff") + 1] for c in docker] == ["check", "format"] and all(c[-1] == "new.py" for c in docker)


def test_an_advisory_red_does_not_hold_an_approved_card_from_merging(env, monkeypatch):
    lp, _ = env
    card = _on_preview(lp, "W-20261104-902")
    card["preview_approved"] = True
    fx = Fake()
    fx.ci, fx.failed = "red", ["روابطُ المسارات الجديدة — استشاري"]
    monkeypatch.setattr(runner, "pr_body", lambda c, h: fx.pr_body_of("/t", 1))
    assert runner.finish(card, CFG, fx, lp, "/t", "b", "h1", 1) != "waiting_ci"


def test_scope_covers_the_declared_app_but_not_shared_code():
    card = {"runner_checks": ["scope_only"], "scope_files": ["behavior/views.py", "templates/behavior/s.html", "core/print_policy.py"]}
    ok = ["behavior/selectors.py", "behavior/urls.py", "templates/behavior/partials/rows.html"]
    assert runner.criteria_failures(card, ok) == []
    for bad in ("behavior/models.py", "behavior/migrations/0002_x.py", "core/permissions.py", "clinic/views.py", "templates/clinic/a.html", "scripts/x.py"):
        assert bad in runner.criteria_failures(card, [bad])[0], bad


def test_mypy_drops_are_recorded_without_a_model_round(tmp_path):
    (tmp_path / "tests").mkdir()
    base = tmp_path / "tests" / "mypy_ratchet_baseline.json"
    base.write_text('{"files": {"a/x.py": 3, "b/y.py": 2, "c/z.py": 5}, "total": 10}', encoding="utf-8")
    log = "✘ mypy ratchet: فشل" + chr(10) + "    نقص ولم يُسجَّل (python -m tests.mypy_ratchet --update): a/x.py: 3 → 2" + chr(10)
    log += "    نقص ولم يُسجَّل (python -m tests.mypy_ratchet --update): b/y.py: 2 → 0" + chr(10)
    assert runner.record_mypy_drops(str(tmp_path), log)
    got = __import__("json").loads(base.read_text(encoding="utf-8"))
    assert got == {"files": {"a/x.py": 2, "c/z.py": 5}, "total": 7}
    assert not runner.record_mypy_drops(str(tmp_path), "لا شيء")


BEHAVIOR_URLS = """app_name = "behavior"
urlpatterns = [
    path("statistics/", views.behavior_statistics, name="statistics"),
    path("daily/", views_daily.daily_report, name="daily_report"),
    path("student/<uuid:pk>/", views.student, name="student"),
]
"""
MENUS = """<div class="sd-menu" id="m-sa"><a href="{% url 'behavior:daily_report' %}">x</a></div>
<div class="sd-menu" id="m-sw"><a href="{% url 'behavior:statistics' %}">x</a></div>
<div class="sd-menu" id="m-staff"><a href="{% url 'staff_list' %}">x</a></div>
"""


def test_an_existing_page_is_linked_in_every_menu_of_its_app():
    gap = runner.menu_sibling_gap("behavior/statistics/?month=2026-10", BEHAVIOR_URLS, MENUS)
    assert len(gap) == 1 and "m-sa" in gap[0] and "m-sw" not in gap[0] and "m-staff" not in gap[0]
    fixed = MENUS.replace("behavior:daily_report' %}\">x</a>", "behavior:daily_report' %}\">x</a>{% url 'behavior:statistics' %}")
    assert runner.menu_sibling_gap("behavior/statistics/", BEHAVIOR_URLS, fixed) == []


def test_sibling_rule_skips_detail_pages_and_unknown_apps():
    assert runner.menu_sibling_gap("behavior/student/1/", BEHAVIOR_URLS, MENUS) == []
    assert runner.menu_sibling_gap("behavior/statistics/", "", MENUS) == []
    assert runner.menu_sibling_gap("", BEHAVIOR_URLS, MENUS) == []


def test_docker_down_mid_card_requeues_instead_of_closing(monkeypatch):
    fx = runner.Effects(CFG)
    monkeypatch.setattr(fx, "changed", lambda tree: ["a.py"])
    monkeypatch.setattr(runner.Path, "is_file", lambda self: True)

    def down(*a, **k):
        raise runner.EnvDown("docker متوقّف")

    monkeypatch.setattr(fx, "preflight", down)
    with pytest.raises(runner.EnvDown):
        fx.autoformat("/t")


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path):
    lock = tmp_path / "runner.lock"
    lock.write_text("21892", encoding="utf-8")
    assert not runner.acquire_lock(lock, alive=lambda pid: True)  # صاحبُه حيّ: يُنتظر
    assert runner.acquire_lock(lock, alive=lambda pid: False)  # صاحبُه ميّت: يؤخذ فورًا
    assert lock.read_text(encoding="utf-8") == str(runner.os.getpid())


def test_an_orphaned_build_goes_back_to_the_queue_but_an_open_request_does_not(env):
    lp, _ = env
    for cid in ("W-20261107-990", "W-20261107-991"):
        ledger.append_event("created", cid, {"problem": "x"}, lp)
        ledger.append_event("state", cid, {"state": "in_progress", "by": "runner", "held_by": "runner"}, lp)
    ledger.append_event("update", "W-20261107-991", {"runner_resume": {"pr": 1, "tree": "/t"}}, lp)
    assert runner.requeue_orphans(lp) == ["W-20261107-990"]
    assert _state(lp, "W-20261107-990")["state"] == "routed"
    assert _state(lp, "W-20261107-991")["state"] == "in_progress"


def test_brief_warns_about_the_guards_that_keep_failing_cards(monkeypatch):
    import types

    src = "MAX_LINES = 60" + chr(10) + "MAX_ORM = 5" + chr(10)
    monkeypatch.setattr(runner, "sh", lambda *a, **k: types.SimpleNamespace(stdout=src, stderr="", returncode=0))
    text = runner.brief({"id": "W-1", "accept": ["x"]}, [])
    assert "≤ 60 سطرًا" in text and "pin_clock" in text and "mypy" in text


def _slot_card(lp, cid, port, since):
    ledger.append_event("created", cid, {"problem": "x"}, lp)
    ledger.append_event("state", cid, {"state": "in_progress", "by": "runner"}, lp)
    ledger.append_event("update", cid, {"preview_slot_port": port, "preview_slot_since": since, "runner_resume": {"head": "h1", "tree": "/t"}}, lp)


def test_sweep_closes_orphan_slots_and_idle_ones_but_keeps_a_fresh_one(env):
    lp, _ = env
    now = 1_000_000
    _slot_card(lp, "W-20261107-980", 8601, now - 60)  # حيّة وحديثة
    _slot_card(lp, "W-20261107-981", 8602, now - runner.PREVIEW_PIN_MINUTES * 60 - 1)  # خاملة
    fx = Fake()
    fx.projects = [8601, 8602, 8603]  # 8603 بلا بطاقة: يتيمة
    items = ledger.reduce_state(ledger.load_events(lp))
    assert runner.sweep_slots(fx, items, lp, now=now) == [8602, 8603]
    assert sorted(fx.downs) == [8602, 8603]
    idle = ledger.reduce_state(ledger.load_events(lp))["W-20261107-981"]
    assert idle["preview_slot_port"] == 0 and idle["preview_idle_closed"] == "h1"


def test_a_slot_that_failed_to_start_is_torn_down(env):
    lp, _ = env
    card = _on_preview(lp, "W-20261104-903")
    fx = Fake()
    fx.slot_ok = False
    assert runner.claim_slot(card, fx, lp, "/t", "h1") == 0
    assert fx.downs == [runner.PREVIEW_SLOTS[0]]



def test_sweep_containers_closes_finished_old_and_idle_stacks_but_keeps_resident(env):
    lp, _ = env
    ledger.append_event("created", "W-20261107-022", {"problem": "x"}, lp)
    ledger.append_event("state", "W-20261107-022", {"state": "closed", "by": "runner"}, lp)
    ledger.append_event("created", "W-20261107-023", {"problem": "x"}, lp)
    ledger.append_event("state", "W-20261107-023", {"state": "in_progress", "by": "runner"}, lp)
    fx = Fake()
    fx.boxes = [
        {"name": "runner-runner-w-20261107-022-x-pg", "project": "", "age": 60},  # بطاقتُها أُغلقت
        {"name": "runner-runner-w-20261107-023-x", "project": "", "age": 60},  # حيّة وحديثة
        {"name": "runner-runner-w-20261107-024-x", "project": "", "age": runner.RUNNER_CONTAINER_TTL_S + 1},  # قديمة
        {"name": "schoolos-t1-web-1", "project": "schoolos-t1", "age": runner.SESSION_STACK_TTL_S + 1},
        {"name": "schoolos-t1-worker-1", "project": "schoolos-t1", "age": runner.SESSION_STACK_TTL_S + 1},
        {"name": "schoolos-t2-web-1", "project": "schoolos-t2", "age": 60},  # جلسةٌ حديثة
        {"name": "schoolos-main-preview-a-web-1", "project": "schoolos-main-preview-a", "age": 10**7},  # مقيمة
        {"name": "shschool-dev-web", "project": "shschool-dev", "age": 10**7},  # ليست لنا
    ]
    items = ledger.reduce_state(ledger.load_events(lp))
    closed = runner.sweep_containers(fx, items)
    assert fx.rm_boxes == ["runner-runner-w-20261107-022-x-pg", "runner-runner-w-20261107-024-x"]
    assert fx.downed == ["schoolos-t1"]
    assert closed == [*fx.rm_boxes, "schoolos-t1"]



def test_legal_flag_from_field_check_or_regulatory_words():
    assert runner.legal_flagged({"legal": True})
    assert runner.legal_flagged({"runner_checks": ["legal_source"]})
    assert runner.legal_flagged({"problem": "إجراء المخالفة بحسب سلّم المخالفات"})
    assert not runner.legal_flagged({"problem": "لون زر الحفظ", "impact": "تحسين", "accept": ["الاتجاه سليم"]})


def test_legal_gap_requires_marker_and_a_citation_that_exists_in_the_source(tmp_path):
    src = tmp_path / "AAdocs" / "x.md"
    src.parent.mkdir()
    src.write_text("مادة 5.3 منسق شؤون الطلبة", encoding="utf-8")
    ok = '"""[LEGAL] عتبة الإحالة.\nالمصدر: AAdocs/x.md م5.3"""'
    assert runner.legal_gap(ok, str(tmp_path)) == []
    assert "[LEGAL]" in runner.legal_gap("def f(): pass", str(tmp_path))[0]
    assert "لا إسناد" in runner.legal_gap("[LEGAL] بلا مصدر", str(tmp_path))[0]
    assert "غير موجود" in runner.legal_gap("[LEGAL]\nالمصدر: AAdocs/none.md م1", str(tmp_path))[0]
    assert "غير وارد" in runner.legal_gap("[LEGAL]\nالمصدر: AAdocs/x.md م9.9", str(tmp_path))[0]


def test_brief_asks_to_read_the_source_for_a_legal_card():
    card = {"id": "W-1", "problem": "سلّم المخالفات", "req_type": "", "accept": ["a"]}
    assert "مصدر الحقيقة" in runner.brief(card, [])
    assert "مصدر الحقيقة" not in runner.brief({"id": "W-2", "problem": "لون زر", "req_type": "", "accept": ["a"]}, [])
