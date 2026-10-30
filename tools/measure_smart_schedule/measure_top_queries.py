
import os,re,collections,django
os.environ["DJANGO_SETTINGS_MODULE"]="shschool.settings.development"
django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS=["*"]
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from django.urls import reverse
u=get_user_model().objects.filter(is_superuser=True,is_active=True).first()
c=Client(); c.force_login(u); c.get(reverse("smart_schedule"))
with CaptureQueriesContext(connection) as q: c.get(reverse("smart_schedule"))
cnt=collections.Counter(); tm=collections.Counter()
for x in q.captured_queries:
    t=re.sub(r"\s+"," ",x["sql"]); m=re.search(r'FROM "(\w+)"',t); k=m.group(1) if m else t[:40]
    cnt[k]+=1; tm[k]+=float(x["time"])
for k,v in cnt.most_common(6): print(k,v,round(tm[k]*1000),"ms")
print("total db ms",round(sum(tm.values())*1000))
r=c.post(reverse("smart_generate"),{},follow=True)
print([str(m) for m in r.context["messages"]] if r.context else "")
