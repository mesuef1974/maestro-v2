import os, time, statistics as st, sys, django
os.environ["DJANGO_SETTINGS_MODULE"] = "shschool.settings.development"
django.setup()
from django.conf import settings
settings.ALLOWED_HOSTS = ["*"]
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model

U = get_user_model()
user = U.objects.filter(is_superuser=True, is_active=True).first() or U.objects.filter(is_active=True).first()
print("db", connection.settings_dict["NAME"], "user_is_superuser", user.is_superuser)
c = Client()
c.force_login(user)


def hit(method, url, k=7, **kw):
    ts, qs, sizes = [], [], []
    last = None
    for _ in range(k):
        with CaptureQueriesContext(connection) as q:
            a = time.perf_counter()
            r = getattr(c, method)(url, **kw)
            ts.append((time.perf_counter() - a) * 1000)
        qs.append(len(q))
        sizes.append(len(r.content))
        last = r
    ts.sort()
    return dict(status=last.status_code, p50=round(st.median(ts), 1), p95=round(ts[int(0.95 * (len(ts) - 1))], 1),
                queries=qs[-1], bytes=sizes[-1])


print("GET smart-schedule/", hit("get", "/operations/smart-schedule/" if False else None) if False else "")
from django.urls import reverse
print("GET smart_schedule", hit("get", reverse("smart_schedule")))
print("GET lab", hit("get", reverse("schedule_quality_lab")))
print("GET status", hit("get", reverse("smart_generate_status")))

# زمن الضغط على «ولّد» حتى الردّ: الطابور محجوب (لا عامل)، فيُقاس الطلب نفسه بما فيه بوّابة الجدوى.
from unittest import mock
import operations.tasks as T
with mock.patch.object(T.generate_smart_schedule_task, "delay", lambda *a, **k: None):
    from operations.models import ScheduleGeneration
    before = ScheduleGeneration.objects.count()
    with CaptureQueriesContext(connection) as q:
        a = time.perf_counter()
        r = c.post(reverse("smart_generate"), {})
        el = (time.perf_counter() - a) * 1000
    print("POST generate click->response ms", round(el, 1), "status", r.status_code, "queries", len(q),
          "new_rows", ScheduleGeneration.objects.count() - before)
    g = ScheduleGeneration.objects.order_by("-generated_at").first()
    print("new generation status", g.status)
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        a = time.perf_counter()
        T.generate_smart_schedule_task.run(str(g.id))
        print("worker task run s", round(time.perf_counter() - a, 1))
        g.refresh_from_db()
        print("final status", g.status, "slots", g.total_slots_created)
