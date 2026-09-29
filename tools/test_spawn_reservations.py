"""اختباراتُ حجز أرقام بطاقات spawn_task — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_spawn_reservations"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "skills" / "maestro-spawn" / "scripts"))
import spawn_preflight as sp  # noqa: E402

TABS = json.loads((ROOT / "projects/schoolos/tabs.json").read_text(encoding="utf-8"))
TH = json.loads((ROOT / "projects/schoolos/thresholds.json").read_text(encoding="utf-8"))
NXT = TABS["session_policy"]["serial"]["per_tab_next"]["04"]
TAG = TABS["specialties"][0]["name_tag"]


def pre(**kw):
    return sp.preflight(None, TAG, "مهمّة", "W-1", "", TABS, TH, 8.0, **kw)


class Reservations(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "spawn_reservations.json"
        self.now = datetime(2026, 9, 29, 20, 0)

    def test_without_reservation_next_is_per_tab_next(self):
        self.assertEqual(pre()["next_serial_04"], f"04{NXT:02d}")

    def test_reserved_number_pushes_next_so_two_cards_do_not_collide(self):
        first = pre()["title"]
        sp.reserve(NXT, first, self.path, self.now)
        reserved = {r["number"]: r["title"] for r in sp.active_reservations(NXT, self.path, self.now)}
        second = pre(reserved=reserved)
        self.assertEqual(second["next_serial_04"], f"04{NXT + 1:02d}")
        self.assertNotEqual(second["title"][:4], first[:4])

    def test_same_cards_own_title_is_not_blocked(self):
        title = pre()["title"]
        result = sp.preflight(title, None, None, None, "", TABS, TH, 8.0, {NXT: title})
        self.assertFalse([b for b in result["blockers"] if "أُعطي" in b])

    def test_another_cards_reserved_number_is_blocked(self):
        result = sp.preflight(f"04{NXT:02d} · {TAG}: أخرى (W-2)", None, None, None, "", TABS, TH, 8.0, {NXT: "عنوانٌ آخر"})
        self.assertTrue([b for b in result["blockers"] if "أُعطي" in b])

    def test_opened_or_expired_reservations_drop(self):
        sp.reserve(NXT, "a", self.path, self.now)
        sp.reserve(NXT + 1, "b", self.path, self.now)
        self.assertEqual(len(sp.active_reservations(NXT, self.path, self.now)), 2)
        self.assertEqual([r["number"] for r in sp.active_reservations(NXT + 1, self.path, self.now)], [NXT + 1])
        later = self.now + timedelta(hours=sp.RESERVATION_HOURS + 1)
        self.assertEqual(sp.active_reservations(NXT, self.path, later), [])


if __name__ == "__main__":
    unittest.main()
