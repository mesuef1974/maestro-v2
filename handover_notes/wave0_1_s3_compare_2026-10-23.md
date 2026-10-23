# تصحيح (07:15، 2026-10-23): النتيجة الصحيحة «مطابق»

قراءتي الأولى كانت على نسخة الشجرة (HEAD 256f9938b، 10-19) وهي أقدم من main. على origin/main (آخر تعديل لـ`.railway/railway.ts` في 4d7d00114، 10-22) توجد المتغيرات الستة AWS_ACCESS_KEY_ID وAWS_SECRET_ACCESS_KEY وAWS_STORAGE_BUCKET_NAME وAWS_S3_REGION_NAME وAWS_S3_ENDPOINT_URL وAWS_S3_CUSTOM_DOMAIN في `SHARED_VARIABLES` (الأسطر 46–51) وتُستعمل في الخدمتين (68 و95)، فلا خطر حذف عند apply. (نبّهت 0101 وأكدت 0701 منذ #1223.)
الدرس: قارن بـ`git show origin/main:` لا بالشجرة. القسم أدناه تاريخي وملغى.

---
# W-20261023-006 (الموجة 0.1): مقارنة متغيرات S3 — النتيجة: فرق

التاريخ: 2026-10-23. من 0201، قراءة فقط، أسماء بلا قيم.

## ما يشترطه الإنتاج (من الشيفرة)
- `shschool/settings/production.py` (نحو السطر 405) يستدعي `core/storage_config.py::s3_default_storage` دائماً (لا يُقرأ USE_S3).
- `core/storage_config.py` يرفع `ImproperlyConfigured` إن نقص أيٌّ من: AWS_ACCESS_KEY_ID، AWS_SECRET_ACCESS_KEY، AWS_STORAGE_BUCKET_NAME.
- اختيارية: AWS_S3_REGION_NAME (الافتراضي me-south-1)، AWS_S3_ENDPOINT_URL (فارغ)، AWS_S3_CUSTOM_DOMAIN (فارغ، يُقرأ في production.py).
- AWS_QUERYSTRING_EXPIRE ثابت 3600 في base.py وليس متغير بيئة.

## ما في ملف النشر `.railway/railway.ts`
- لا ذكر لأيٍّ من متغيرات AWS_* (فحص grep: صفر تطابق).
- رأس الملف (السطران 10–13): كل متغير غير مذكور فيه يُعدّه `railway config apply` مطلوب الحذف.

## الفرق
| المتغير | الإنتاج | railway.ts |
|---|---|---|
| AWS_ACCESS_KEY_ID | إلزامي | غائب |
| AWS_SECRET_ACCESS_KEY | إلزامي | غائب |
| AWS_STORAGE_BUCKET_NAME | إلزامي | غائب |
| AWS_S3_REGION_NAME | اختياري | غائب |
| AWS_S3_ENDPOINT_URL | اختياري | غائب |
| AWS_S3_CUSTOM_DOMAIN | اختياري | غائب |

الحكم: فرق (6 متغيرات غائبة، 3 منها إلزامية).

## الأثر والتوصية
- أول `railway config apply` يحذف المتغيرات الثلاثة الإلزامية إن كانت مضبوطة في Railway، فينهار الإقلاع.
- لا تنفيذ لـ apply قبل إضافة الأسماء الستة إلى railway.ts بصيغة `preserve()` (بلا قيم)، ومراجعة 0301، و`railway config plan` يُظهر صفر حذف.
- لم أتحقق من وجودها فعلاً على Railway (لا وصول ولا طباعة أسرار)؛ الإنتاج سليم على /health/ فهي على الأرجح مضبوطة.
- التعديل على ملف نشر: خارج صلاحيتي، يُسند لمنفّذ عبر 0101.
