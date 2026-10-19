"""اختباراتُ red_notify — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_red_notify"""

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import red_notify as rn

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
DIR = {
    "0101": {"id": "local_0101"},
    "0702": {"id": "local_0702"},
    "0402": {"id": "local_0402"},
}


def check(name, conclusion="FAILURE", at="2026-10-19T11:00:00Z"):
    return {
        "name": name,
        "conclusion": conclusion,
        "status": "COMPLETED",
        "completedAt": at,
        "startedAt": at,
    }


def pr(
    n=7,
    head="a" * 40,
    checks=(),
    title="W-20261019-001: عمل",
    body="",
    state="OPEN",
    draft=False,
):
    return {
        "number": n,
        "title": title,
        "body": body,
        "isDraft": draft,
        "state": state,
        "headRefName": "claude/x",
        "headRefOid": head,
        "statusCheckRollup": list(checks),
    }


ITEMS = {"W-20261019-001": {"held_by": "0402"}}


class Red(unittest.TestCase):
    def test_a_new_failed_check_goes_to_the_holder_and_to_0101_with_check_and_head(
        self,
    ):
        fresh = rn.fresh_failures([pr(checks=[check("ruff")])], {}, NOW)
        msgs = rn.messages(fresh, ITEMS, DIR)
        self.assertEqual([m[0] for m in msgs], ["0402", "0101"])
        self.assertEqual(msgs[0][1], "local_0402")
        self.assertIn("«ruff»", msgs[0][2])
        self.assertIn("aaaaaaaa", msgs[0][2])
        self.assertIn("#7", msgs[0][2])

    def test_when_the_holder_is_0101_one_message_only(self):
        msgs = rn.messages(
            rn.fresh_failures([pr(checks=[check("x")])], {}, NOW),
            {"W-20261019-001": {"held_by": "0101"}},
            DIR,
        )
        self.assertEqual([m[0] for m in msgs], ["0101"])

    def test_an_unknown_holder_still_reaches_0101_and_says_so(self):
        msgs = rn.messages(
            rn.fresh_failures([pr(checks=[check("x")], title="بلا بطاقة")], {}, NOW),
            {},
            DIR,
        )
        self.assertEqual([m[0] for m in msgs], ["0101"])
        self.assertIn("غيرُ معروف", msgs[0][2])

    def test_a_pr_without_a_card_is_never_sent_to_anyone(self):
        fresh = rn.fresh_failures(
            [pr(checks=[check("x")], title="chore(deps): bump")], {}, NOW
        )
        self.assertEqual(rn.messages(fresh, ITEMS, DIR), [])

    def test_the_same_check_on_the_same_head_is_not_repeated(self):
        state = {}
        p = [pr(checks=[check("ruff")])]
        self.assertEqual(len(rn.fresh_failures(p, state, NOW)), 1)
        self.assertEqual(rn.fresh_failures(p, state, NOW + timedelta(minutes=60)), [])

    def test_a_new_head_within_the_window_is_held_then_announced(self):
        state = {}
        rn.fresh_failures([pr(head="a" * 40, checks=[check("ruff")])], state, NOW)
        again = [pr(head="b" * 40, checks=[check("ruff")])]
        self.assertEqual(
            rn.fresh_failures(again, state, NOW + timedelta(minutes=5)), []
        )
        self.assertEqual(
            len(rn.fresh_failures(again, state, NOW + timedelta(minutes=16))), 1
        )

    def test_a_cancelled_or_superseded_check_is_not_red(self):
        old_fail = check("pytest", "FAILURE", "2026-10-19T10:00:00Z")
        new_ok = check("pytest", "SUCCESS", "2026-10-19T11:00:00Z")
        self.assertEqual(
            rn.fresh_failures(
                [pr(checks=[old_fail, new_ok, check("slow", "CANCELLED")])], {}, NOW
            ),
            [],
        )

    def test_drafts_and_closed_prs_are_skipped(self):
        c = [check("ruff")]
        self.assertEqual(
            rn.fresh_failures(
                [pr(checks=c, draft=True), pr(n=8, checks=c, state="MERGED")], {}, NOW
            ),
            [],
        )

    def test_two_failed_checks_make_two_alerts_and_old_state_is_forgotten(self):
        state = {"1|old": {"head": "x", "at": (NOW - timedelta(hours=30)).isoformat()}}
        fresh = rn.fresh_failures([pr(checks=[check("a"), check("b")])], state, NOW)
        self.assertEqual({f["check"] for f in fresh}, {"a", "b"})
        self.assertNotIn("1|old", state)

    def test_the_log_line_is_added_when_available_and_never_breaks_the_message(self):
        fresh = rn.fresh_failures([pr(checks=[check("ruff")])], {}, NOW)
        self.assertIn(
            "E501", rn.messages(fresh, ITEMS, DIR, err=lambda c: "E501")[0][2]
        )

        def boom(_c):
            raise RuntimeError

        self.assertNotIn("—  —", rn.messages(fresh, ITEMS, DIR, err=boom)[0][2])

    def test_a_cycle_is_unmeasured_when_gh_fails_and_dry_run_writes_nothing(self):
        tmp = Path(tempfile.mkdtemp()) / "s.json"
        rn.STATE_FILE = tmp
        rn.COUNTER = Path(tempfile.mkdtemp()) / "لا_عدّاد.py"  # لا يمسّ العدّادَ الحقيقيّ
        rn.fetch_open = lambda: None
        self.assertIsNone(rn.cycle(NOW))
        msgs = rn.cycle(
            NOW,
            dry_run=True,
            prs=[pr(checks=[check("ruff")])],
            items=ITEMS,
            directory=DIR,
            err=None,
        )
        self.assertEqual(len(msgs), 2)
        self.assertFalse(tmp.exists())
        rn.cycle(
            NOW,
            dry_run=False,
            prs=[pr(checks=[check("ruff")])],
            items=ITEMS,
            directory=DIR,
            err=None,
        )
        self.assertTrue(tmp.exists())
        self.assertEqual(
            rn.cycle(
                NOW + timedelta(minutes=1),
                prs=[pr(checks=[check("ruff")])],
                items=ITEMS,
                directory=DIR,
                err=None,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
