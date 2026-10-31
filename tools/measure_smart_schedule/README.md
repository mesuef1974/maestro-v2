# قياس ثقل صفحة الجدولة الذكية (W-20261010-003) — يُعاد بعد الإصلاح بلا تعديل

1) نسخةٌ مؤقتة من قاعدة المعاينة المحلية (لا إنتاج، ولا مساس بالأصل):
   psql -h localhost -p 5433 -U <DB_USER> -d postgres -c "create database ss_0701_measure template ss_main_preview"
2) من شجرة الشيفرة المراد قياسها (بعد الإصلاح) ضع في البيئة:
   DB_NAME=ss_0701_measure DB_HOST=localhost DB_PORT=5433 DB_USER=… DB_PASSWORD=… (من .env الشجرة)
   PYTHONPATH="C:/Users/mesue/scheduling_automation_work/shim;<مسار الشجرة بصيغة ويندوز>"
   ثم: /d/shschool_mvp/.venv/Scripts/python.exe manage.py migrate -v0
3) شغّل (كلٌّ بالبايثون نفسه):
   measure_page.py          # GET الصفحة/lab/status وPOST «ولّد»: p50/p95 واستعلامات وحجم
   measure_top_queries.py   # أكثر الجداول استعلاماً في GET الصفحة (يكشف N+1)
   measure_lab_compute.py   # compute للمختبر: التحميل مقابل الحساب
4) أسقط القاعدة المؤقتة: drop database ss_0701_measure.

خطّ الأساس قبل الإصلاح (2026-10-10، مقيس): GET الصفحة p50=3859ms و1078 استعلاماً، منها 1024 على operations_timeslotconfig (1517ms)؛
lab p50=190ms/19؛ status 23ms/10؛ POST «ولّد» 2983ms/1036 استعلاماً؛ compute للتوليد الواحد 140ms (الحساب الصافي 16ms).
الهدف: استعلامات الصفحة ≪ 100 وزمنها ≪ 1000ms.
