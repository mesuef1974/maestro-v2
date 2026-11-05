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


def test_second_card_starts_while_first_waits_and_third_does_not(env):
    lp, lock = env
    for n in (901, 902, 903):
        _card(lp, f"W-20261104-{n}")
    fx = Fake()
    fx.ci = "pending"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 1
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 2
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci" and fx.runs == 2  # السقف بطاقتان
    assert _state(lp, "W-20261104-903")["state"] == "routed"


def test_second_card_does_not_merge_until_first_is_published(env):
    lp, lock = env
    _card(lp, "W-20261104-901")
    _card(lp, "W-20261104-902")
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
    _card(lp)
    fx = Fake()
    fx.review_q = [["حذف الخطّاف"], []]
    assert runner.run_cycle(CFG, fx, lp, lock) == "published" and fx.runs == 2 and fx.reviews == 2


def test_review_gap_that_never_closes_is_closed_without_a_pr(env):
    lp, lock = env
    _card(lp)
    fx = Fake()
    fx.review_q = [["حذف الخطّاف"]]
    assert runner.run_cycle(CFG, fx, lp, lock) == "referred" and not fx.merged
    assert "حذف الخطّاف" in runner.OWNER_QUEUE.read_text(encoding="utf-8")


def test_unreadable_review_never_opens_a_pr(env):
    lp, lock = env
    _card(lp)
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
    assert runner.prepush_env([]) == ["-e", "PREPUSH_STRUCTURE_NESTED=1"]
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
    _card(lp, "W-20261104-901")
    fx = TurnsGreen()
    fx.run_model = lambda *a: Fake.run_model(fx, *a)
    fx.ci = "pending"
    assert runner.run_cycle(CFG, fx, lp, lock) == "waiting_ci"
    _card(lp, "W-20261104-902")
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

