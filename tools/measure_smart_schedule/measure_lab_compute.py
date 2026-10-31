import os, time, statistics as st, django
os.environ["DJANGO_SETTINGS_MODULE"] = "shschool.settings.development"
django.setup()
from django.db import connection
from django.test.utils import CaptureQueriesContext
from operations.models import ScheduleGeneration, ScheduleSlot
from operations import schedule_lab as L
from operations.schedule_lab import ScheduleLab, load_slots, load_context

print("db", connection.settings_dict["NAME"], connection.settings_dict["PORT"])
gens = list(ScheduleGeneration.objects.all().order_by("-generated_at")[:5])
print("gens", [(str(g.id)[:6], g.status, ScheduleSlot.objects.filter(generation=g).count()) for g in gens])
g = max(gens, key=lambda g: ScheduleSlot.objects.filter(generation=g).count())
n = ScheduleSlot.objects.filter(generation=g).count()
print("chosen slots", n)


def t(f, k=15):
    xs = []
    for _ in range(k):
        a = time.perf_counter()
        f()
        xs.append((time.perf_counter() - a) * 1000)
    xs.sort()
    return round(st.median(xs), 1), round(xs[int(0.95 * (len(xs) - 1))], 1)


ctx = load_context(g.school, g.academic_year)
slots = load_slots(ScheduleSlot.objects.filter(generation=g))
print("load_slots ms p50/p95", t(lambda: load_slots(ScheduleSlot.objects.filter(generation=g))))
print("load_context ms p50/p95", t(lambda: load_context(g.school, g.academic_year)))
print("compute only ms p50/p95", t(lambda: ScheduleLab(slots, ctx).compute()))
print("for_generation+compute ms p50/p95", t(lambda: ScheduleLab.for_generation(g).compute()))
with CaptureQueriesContext(connection) as c:
    ScheduleLab.for_generation(g).compute()
print("queries per generation compute", len(c))
calls = [0]
orig = ScheduleLab.compute


def w(self, *a, **k):
    calls[0] += 1
    return orig(self, *a, **k)


ScheduleLab.compute = w
base = L.latest_baseline(g.school, g.academic_year)
with CaptureQueriesContext(connection) as c:
    a = time.perf_counter()
    for x in gens:
        placed = ScheduleSlot.objects.filter(generation=x).exists() or x.total_slots_created
        lab = ScheduleLab.for_generation(x).compute() if placed else (x.metrics or {})
        if lab:
            L.compare(lab, base.metrics if base else None)
            L.overall_score(lab)
            if base:
                L.relative_score(lab, base.metrics)
    el = (time.perf_counter() - a) * 1000
print("page loop: generations", len(gens), "compute calls", calls[0], "ms", round(el, 1), "queries", len(c))
from operations import schedule_feasibility as F

print("feasibility.check ms p50/p95", t(lambda: F.check(g.school, g.academic_year), 8))
