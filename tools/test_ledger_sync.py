"""اختباراتُ ledger_sync (W-20261019-018) — بلا شبكةٍ ولا دفتر حقيقيّ:  python -m pytest test_ledger_sync.py"""

from datetime import datetime, timedelta, timezone

import ledger
import ledger_sync as ls

TZ = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 19, 20, 0, tzinfo=TZ)
SHS, MV2 = "sh-school/shschool_mvp", "mesuef1974/maestro-v2"


def st(state, head="aaaaaaaa", **kw):
    return {"state": state, "approved_head": head, **kw}


def pr(n=7, merge="b" * 40):
    return {"number": n, "merge": merge, "at": "2026-10-19T10:00:00Z"}


def always(merge, prod):
    return True


def never(merge, prod):
    return False


def live(merge):
    return True


def not_live(merge):
    return False


def test_maestro_v2_merged_pr_goes_to_published_only_when_live_in_root():
    """W-20261027-003: published في maestro-v2 يعني حيّاً في الجذر (سلفاً لرأسه) لا مجرّد مدموج في GitHub."""
    rows = ls.plan({"W-1": st("approved")}, {MV2: {"aaaaaaaa": pr()}}, None, live=live)
    assert [(r["target"], r["slug"]) for r in rows] == [("published", MV2)]
    assert ls.steps(rows[0]) == ["pushed", "merged", "published"]
    rows = ls.plan({"W-1": st("approved")}, {MV2: {"aaaaaaaa": pr()}}, None, live=not_live)
    assert rows[0]["target"] == "merged" and ls.steps(rows[0]) == ["pushed", "merged"]
    rows = ls.plan({"W-1": st("approved")}, {MV2: {"aaaaaaaa": pr()}}, None)  # بلا فاحصٍ حيّ: لا ادّعاء
    assert rows[0]["target"] == "merged"


def test_merged_card_is_promoted_to_published_once_root_catches_up():
    assert ls.plan({"W-1": st("merged")}, {MV2: {"aaaaaaaa": pr()}}, None, live=not_live) == []
    rows = ls.plan({"W-1": st("merged")}, {MV2: {"aaaaaaaa": pr()}}, None, live=live)
    assert ls.steps(rows[0]) == ["published"]


def test_pushed_card_skips_nothing_and_does_not_repeat_steps():
    rows = ls.plan({"W-1": st("pushed")}, {MV2: {"aaaaaaaa": pr()}}, None, live=live)
    assert ls.steps(rows[0]) == ["merged", "published"]


def test_root_live_uses_merge_base_ancestry_and_unknown_commit_is_not_live():
    seen = []
    assert ls.root_live("a" * 40, "/r", run=lambda cmd, cwd: seen.append((cmd, cwd)) or 0) is True
    assert seen == [(["git", "merge-base", "--is-ancestor", "a" * 40, "HEAD"], "/r")]
    assert ls.root_live("a" * 40, "/r", run=lambda cmd, cwd: 1) is False  # ليس سلفاً
    assert ls.root_live("a" * 40, "/r", run=lambda cmd, cwd: 128) is False  # commit مجهول محلّياً
    assert ls.root_live("", "/r", run=lambda cmd, cwd: 0) is False


def test_shschool_merged_but_not_in_production_stops_at_merged():
    rows = ls.plan(
        {"W-1": st("pushed")}, {SHS: {"aaaaaaaa": pr()}}, "c" * 40, check=never
    )
    assert rows[0]["target"] == "merged" and ls.steps(rows[0]) == ["merged"]


def test_shschool_in_production_goes_to_published():
    rows = ls.plan(
        {"W-1": st("merged")}, {SHS: {"aaaaaaaa": pr()}}, "c" * 40, check=always
    )
    assert ls.steps(rows[0]) == ["published"]


def test_unknown_production_never_publishes_shschool():
    rows = ls.plan({"W-1": st("pushed")}, {SHS: {"aaaaaaaa": pr()}}, None, check=always)
    assert rows[0]["target"] == "merged"


def test_card_at_target_or_without_merged_pr_is_untouched():
    states = {
        "W-1": st("published"),
        "W-2": st("merged"),
        "W-3": st("approved", head="dddddddd"),
    }
    rows = ls.plan(states, {SHS: {"aaaaaaaa": pr()}}, "c" * 40, check=never)
    assert rows == []


def test_apply_walks_chain_without_claiming_0601_and_waives_only_pushed():
    calls = []
    rows = ls.plan({"W-1": st("approved")}, {MV2: {"aaaaaaaa": pr()}}, None, live=live)
    done = ls.apply_rows(
        rows, None, move=lambda cid, step, **kw: calls.append((step, kw))
    )
    assert [c[0] for c in calls] == ["pushed", "merged", "published"]
    assert (
        "waive_remote_check" in calls[0][1] and "waive_remote_check" not in calls[1][1]
    )
    assert all("by" not in c[1] for c in calls)
    assert "ledger_sync" in calls[-1][1]["note"]
    assert done == ["W-1 ← published (#7)"]


def test_note_carries_the_real_github_merge_time_not_the_registration_time():
    """أمر المالك 10-20 بند 2: وقتُ الدمج الحقيقيّ يُدوَّن، فلا ينتظر الدفترُ حذفَ الفرع ولا يُنسب الدمجُ إلى وقت التسجيل."""
    calls = []
    rows = ls.plan({"W-1": st("pushed")}, {MV2: {"aaaaaaaa": pr()}}, None)
    ls.apply_rows(rows, None, move=lambda cid, step, **kw: calls.append((step, kw)))
    assert "2026-10-19T10:00:00Z" in calls[-1][1]["note"]


def test_a_failing_card_does_not_stop_the_rest():
    def move(cid, step, **kw):
        if cid == "W-1":
            raise ledger.LedgerError("مرفوض")

    states = {"W-1": st("approved"), "W-2": st("approved", head="eeeeeeee")}
    rows = ls.plan(states, {MV2: {"aaaaaaaa": pr(1), "eeeeeeee": pr(2)}}, None)
    done = ls.apply_rows(rows, None, move=move)
    assert done[0].startswith("W-1 ✘") and done[1].startswith("W-2 ←")


def events(cid, hours_ago):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat()
    return [{"ts": ts, "id": cid, "kind": "state", "data": {"state": "pushed"}}]


def test_pushed_without_any_pr_is_reported_not_converted():
    states = {"W-1": st("pushed", held_by="0702")}
    out = ls.orphans(states, events("W-1", 5), {}, {}, NOW)
    assert [(o["id"], o["hours"], o["held_by"]) for o in out] == [("W-1", 5, "0702")]
    assert ls.plan(states, {}, None) == []
    assert "pushed بلا طلب" in ls.report([], out)[0]


def test_recent_pushed_or_with_open_pr_is_not_orphan():
    states = {"W-1": st("pushed")}
    assert ls.orphans(states, events("W-1", 1), {}, {}, NOW) == []
    assert (
        ls.orphans(states, events("W-1", 9), {MV2: {"aaaaaaaa": pr()}}, {}, NOW) == []
    )


def test_fetch_prs_parses_gh_json():
    out = '[{"number": 9, "headRefOid": "abcdef1234", "mergeCommit": {"oid": "f00"}, "mergedAt": "2026-10-19T01:00:00Z"}]'
    got = ls.fetch_prs(MV2, "merged", 5, gh=lambda args: out)
    assert got == {
        "abcdef12": {"number": 9, "merge": "f00", "at": "2026-10-19T01:00:00Z"}
    }


def test_the_auto_note_never_exceeds_the_ledger_field_limit():
    """ملاحظةٌ تتجاوز 240 حرفاً ترفضها الدفتر فتبقى البطاقة pushed ولا تُنقل إلى merged (واقعة 10-29)."""
    calls = []
    rows = ls.plan({"W-1": st("pushed")}, {MV2: {"aaaaaaaa": pr()}}, None)
    rows[0]["at"] = "2026-10-19T10:00:00Z" + "x" * 400
    ls.apply_rows(rows, None, move=lambda cid, step, **kw: calls.append((step, kw)))
    assert all(len(v) <= 240 for _, kw in calls for v in kw.values() if isinstance(v, str))
