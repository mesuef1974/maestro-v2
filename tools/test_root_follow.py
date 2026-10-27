"""W-20261027-003: المضخّةُ تقدّم الجذرَ الحيّ إلى main ff-only بعد الدمج، أو تُنذر بسببٍ واحد؛ ولا تلمس شيئاً إن كان على main."""
import flow_pump as fp


class Sh:
    """مشغّلُ أوامرٍ مزيّف: يجيب بحسب الأمر ويسجّل ما طُلب."""

    def __init__(self, behind="0", ahead="0", dirty="", fetch_rc=0, merge_rc=0):
        self.behind, self.ahead, self.dirty, self.fetch_rc, self.merge_rc = behind, ahead, dirty, fetch_rc, merge_rc
        self.calls = []

    def __call__(self, cmd, cwd=None):
        self.calls.append(cmd[1:3])
        if cmd[1] == "fetch":
            return self.fetch_rc, "خطأ شبكة" if self.fetch_rc else ""
        if cmd[1] == "rev-list":
            return 0, self.behind if cmd[-1] == "HEAD..origin/main" else self.ahead
        if cmd[1] == "status":
            return 0, self.dirty
        if cmd[1] == "merge":
            return self.merge_rc, "غير ممكن" if self.merge_rc else "Fast-forward"
        raise AssertionError(cmd)


def test_root_on_main_is_silent_and_never_merges():
    sh = Sh()
    assert fp.root_follow_pass(True, sh, "/r") == []
    assert ["merge", "--ff-only"] not in sh.calls


def test_behind_clean_root_fast_forwards_on_apply_only():
    sh = Sh(behind="3")
    assert "عرض" in fp.root_follow_pass(False, sh, "/r")[0] and ["merge", "--ff-only"] not in sh.calls
    sh = Sh(behind="3")
    out = fp.root_follow_pass(True, sh, "/r")
    assert "تقدّم ff-only بـ3" in out[0] and ["merge", "--ff-only"] in sh.calls


def test_diverged_root_warns_and_does_not_touch():
    sh = Sh(behind="96", ahead="22")
    out = fp.root_follow_pass(True, sh, "/r")
    assert "متباعد" in out[0] and "96" in out[0] and "22" in out[0] and ["merge", "--ff-only"] not in sh.calls


def test_dirty_tracked_files_block_the_advance_with_a_count():
    sh = Sh(behind="2", dirty=" M tools/a.py\n M tools/b.py\n")
    out = fp.root_follow_pass(True, sh, "/r")
    assert "2 ملفٍّ" in out[0] and ["merge", "--ff-only"] not in sh.calls


def test_fetch_failure_is_unmeasured_not_a_guess():
    sh = Sh(behind="5", fetch_rc=1)
    out = fp.root_follow_pass(True, sh, "/r")
    assert "غير مقيس" in out[0] and ["merge", "--ff-only"] not in sh.calls


def test_refused_fast_forward_is_reported():
    out = fp.root_follow_pass(True, Sh(behind="1", merge_rc=1), "/r")
    assert "رُفض" in out[0]
