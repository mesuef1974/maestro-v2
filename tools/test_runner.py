"""اختباراتُ المشغّل (D-519م): الاختيار، القفل، الإصلاح مرّتين، الإحالة، التراجع الآليّ، وتسجيل الكلفة."""
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
    def prod_status(self): return self.prod, self.is_healthy
    def contains(self, tree, oid, prod): return prod == "oid1"
    def main_sha(self): return "good1234abcd"
    def rollback(self, sha, reason):
        self.rolled_to = sha
        return self.can_rollback
    def remove_tree(self, tree): self.removed = True


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "OWNER_QUEUE", tmp_path / "owner_queue.md")
    monkeypatch.setattr(runner, "REQUESTS", tmp_path / "requests")
    return tmp_path / "e.jsonl", tmp_path / "lock"


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
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and fx.runs == 6 and not fx.merged
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
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged


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


def test_autoformat_formats_only_changed_python_files(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.py").write_text("x = [1,2,\n  3]\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x = [1,2]\n", encoding="utf-8")
    assert runner.Effects(CFG).autoformat(str(tmp_path)) == ["a.py"]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "x = [1, 2, 3]\n"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "x = [1,2]\n"


def test_brief_tells_the_model_to_format():
    assert "ruff format" in runner.brief({"id": "W-1", "accept": ["x"]}, [])


def test_referenced_tests_find_users_of_changed_modules_and_templates(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_uses_module.py").write_text("from quality.presentation import signature_stamps\n", encoding="utf-8")
    (tmp_path / "tests" / "test_uses_template.py").write_text("html = render('quality/_pdf_e_sign.html')\n", encoding="utf-8")
    (tmp_path / "tests" / "test_unrelated.py").write_text("assert 1\n", encoding="utf-8")
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
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred"
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
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged
