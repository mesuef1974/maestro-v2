import unittest

from preview_alert import parse_status

HEALTHY = """الوضع:        follow
الخادم:       running (healthy) — http://localhost:8500 — يعلن commit=6e32825
المعروض:      main@6e32825
"""


class PreviewAlert(unittest.TestCase):
    def test_healthy_has_no_alerts(self):
        self.assertEqual(parse_status(HEALTHY), [])

    def test_docker_down_is_high(self):
        a = parse_status("", docker_ok=False)
        self.assertEqual(a[0]["code"], "docker_down")
        self.assertEqual(a[0]["level"], "high")

    def test_stalled_watch_over_15_minutes(self):
        t = HEALTHY + "! تنبيه لـ0101: لا نبضَ لـwatch منذ 166 دقيقة — الحلقةُ متوقّفة؟\n"
        self.assertEqual([x["code"] for x in parse_status(t)], ["watch_stalled"])

    def test_short_gap_is_not_an_alert(self):
        t = HEALTHY + "! تنبيه لـ0101: لا نبضَ لـwatch منذ 5 دقيقة\n"
        self.assertEqual(parse_status(t), [])

    def test_expired_pin_and_boot_failure(self):
        t = (
            HEALTHY
            + "! تنبيه لـ0101: تثبيتٌ منتهٍ لم يُفكّ (w0701-dec — منذ 58 دقيقة)\n"
            + "! آخرُ خطأ (2026-10-18 16:57): main@352ae17 لم يُقلع\n"
        )
        self.assertEqual({x["code"] for x in parse_status(t)}, {"pin_expired", "boot_failed"})

    def test_unhealthy_server(self):
        t = "الخادم:       غيرُ موجود — http://localhost:8500\n"
        self.assertEqual(parse_status(t)[0]["code"], "server_not_healthy")


if __name__ == "__main__":
    unittest.main()
