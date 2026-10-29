"""قياس GET smart-schedule/ بأربع حالات (بلا CaptureQueriesContext لأنه يضخّم الزمن) — قراءةٌ فقط، على نسخةٍ مؤقتة.

الحالات: كاملة، فحصُ الجدوى معطَّل (يُرجع التقريرَ المحسوبَ مسبقاً)، حلقةُ ScheduleLab معطَّلة، كلاهما معطَّل.
ثم متوسّطُ زمن الاستعلام الواحد محلياً (من connection.queries مع DEBUG).
"""

import os
import statistics as st
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shschool.settings.development")
django.setup()
from django.conf import settings

settings.ALLOWED_HOSTS = ["*"]
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import Client
from django.urls import reverse

from operations import schedule_feasibility as F
from operations.schedule_lab import ScheduleLab

user = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
c = Client()
c.force_login(user)
URL = reverse("smart_schedule")


def timed(k=9):
    c.get(URL)  # تسخين
    xs = []
    for _ in range(k):
        a = time.perf_counter()
        r = c.get(URL)
        xs.append((time.perf_counter() - a) * 1000)
        assert r.status_code == 200
    xs.sort()
    return round(st.median(xs), 1), round(xs[int(0.95 * (len(xs) - 1))], 1)


class _Stub:
    def compute(self, *a, **k):
        return {}


real_check = F.check
school = None
from operations.models import ScheduleGeneration

g = ScheduleGeneration.objects.first()
precomputed = real_check(g.school, g.academic_year)
print("db", connection.settings_dict["NAME"])
print("1 كاملة                      ms p50/p95:", timed())
with mock.patch.object(F, "check", lambda *a, **k: precomputed):
    print("2 فحص الجدوى معطَّل           ms p50/p95:", timed())
with mock.patch.object(ScheduleLab, "for_generation", classmethod(lambda cls, g: _Stub())):
    print("3 حلقة ScheduleLab معطَّلة    ms p50/p95:", timed())
    with mock.patch.object(F, "check", lambda *a, **k: precomputed):
        print("4 كلاهما معطَّل               ms p50/p95:", timed())

settings.DEBUG = True
reset_queries()
c.get(URL)
qs = connection.queries
tot = sum(float(q["time"]) for q in qs) * 1000
print("متوسط زمن الاستعلام الواحد محلياً ms:", round(tot / len(qs), 3), "عدد", len(qs), "مجموع", round(tot, 1))
