# review_window.py — ما يفعله فعلاً (مقروءٌ من الشيفرة ومجرَّبٌ 09-28)

متى تقرأ هذا الملف: قبل أوّل `render` في جلستك، أو حين تبدو النافذةُ المولَّدة غريبة، أو قبل أن تقترح إصلاحاً للأداة.

المصدر: `C:/Users/mesue/delivery_manager_work/tools/review_window.py` و`ledger.py` و`projects/schoolos/thresholds.json`. التجاربُ على نسخةٍ من السجلّ عبر `LEDGER_PATH` لا على الأصل.

## 1) الأوامر
```
python C:/Users/mesue/delivery_manager_work/tools/review_window.py render [--level normal|elevated] [--window "15:30"]
python C:/Users/mesue/delivery_manager_work/tools/review_window.py apply --window <مسارٌ كامل لملفّ الخريطة> --text "<ردّ المالك حرفيّاً>"
```
- `render` يقرأ بطاقات `ready_for_review` من `ledger/events.jsonl`، ويطبع Markdown، **ويكتب** `ledger/windows/<YYYYMMDD-HHMMSS>.json` فيه `level` و`mapping` (رقمُ الحزمة ← معرّفاتُ البطاقات) و`high` (أرقامُ الحزم عاليةِ الخطورة). أي أنّه ليس قرائيّاً بحتاً؛ لا تشغّله «للتجربة» ثمّ تنساه.
- `--window` نصٌّ يظهر في العنوان فقط؛ لا يغيّر شيئاً آخر.
- `apply` يُلحق أحداثاً بالسجلّ — لا تشغّله إلّا بنصّ المالك (مهارة `maestro-approvals`).
- `--window` في `apply` مسارٌ يُحلّ من مجلّد التشغيل الحاليّ؛ مرِّر المسارَ الكامل تحت `C:/Users/mesue/delivery_manager_work/ledger/windows/`.

## 2) كيف تُبنى الحزم
| الحقل في البطاقة | أثرُه | من أين يأتي |
|---|---|---|
| `tier` | الخفيفةُ (light) كلُّها حزمةٌ واحدة؛ وhigh تُستثنى من «اعتمد الكلّ» | `tag_card.py` (مهارة maestro-evidence) |
| `category` + `area` | مفتاحُ الحزمة: حزمةٌ لكلّ (فئة × مجال) | المصدر نفسُه |
| `pr` | يظهر في سطر «الطلبات» | `tag_card.py --pr` بعد الدفع؛ قبله «—» طبيعيّ |
| `priority`, `urgent`, `scores` | الترتيب: الأولويّة ثمّ الاستعجال ثمّ WSJF ثمّ الأقدم | `ledger.py add` |

`ledger.py` لا أمرَ فيه يكتب `tier/category/area/pr` (أوامرُه: add، move، list، show). فبلا وسمٍ: المفتاحُ («?»، «?») لكلّ البطاقات والخطورةُ low. جُرِّب 09-28: بطاقتان جاهزتان بلا وسم ← `{'1': [W-…-001, W-…-005]}`؛ وبعد الوسم ← حزمتان و`high: [1]`.

## 3) السعة
| المستوى | حزمٌ في النافذة | قراراتٌ يوميّاً | دقائق يوميّاً |
|---|---|---|---|
| normal | 6 | 12 | 40 |
| elevated | 10 | 20 | 70 (ويعود بعد 24 س: `auto_return_hours`) |
المصدر: `thresholds.json` → `owner_capacity`. الأداةُ لا تعيد المستوى وحدَها؛ «العودةُ» معناها أن تولّد التاليةَ بـnormal ما لم يُعلن المالكُ غيرَه.

## 4) عيوبٌ معروفة في الأداة (09-28) — تعامل معها ولا تصلحها هنا
| العيب | أثرُه | ما تفعله الآن |
|---|---|---|
| `flow_version="v2.1"` ثابتٌ في `render` ولا خيارَ له | عنوانٌ بإصدار فلوٍ قديم | صحّحه يدويّاً من `flow_changelog.md` |
| لا أمرَ لوسم البطاقة | «? · ?» وخطورةٌ low للكلّ | `tag_card.py` قبل `render` |
| سطرُ الردّ السريع يضمّ أرقامَ high | نسخُه يعتمدها | احذفها من السطر |
| لا رابطَ ولا دورَ ولا أثرَ في البند | النافذةُ هيكلٌ لا BLUF | الإثراءُ بالقالب (`02-window-content.md`) |
| حدثُ الاعتماد `via: "maestro"` ثابت ولا يحفظ نصَّ المالك | الأثرُ لا يُظهر الجلسةَ ولا الصيغة | مهارة maestro-approvals تحفظ النصَّ الحرفيّ في السجلّ الزمنيّ |
هذه بطاقاتٌ للمايسترو (يصون أدواتِه بنفسه، D-37م)، لا تعديلٌ من 0501.

## 5) تجربةٌ آمنةٌ بلا مساسٍ بالسجلّ
```
cp C:/Users/mesue/delivery_manager_work/ledger/events.jsonl <مجلّدك المؤقّت>/ev.jsonl
LEDGER_PATH=<مجلّدك المؤقّت>/ev.jsonl python -c "import sys; sys.path.insert(0, r'C:/Users/mesue/delivery_manager_work/tools'); import ledger, review_window as rw; it=[i for i in ledger.reduce_state(ledger.load_events()).values() if i['state']=='ready_for_review']; print(rw.render(it, 'normal', '20:30', save_dir=None)[1])"
```
`save_dir=None` لا يكتب ملفّ خريطة. استعملها لتعرف شكلَ الحزم قبل النافذة الحقيقيّة.

## أنماطٌ مضادّة
- خطأ: `render` مرّتين ثمّ تطبيقُ الردّ على الملفّ الأحدث وقد أُرسلت الأقدم. الصواب: ملفٌّ واحدٌ لكلّ نافذةٍ مُرسَلة، واسمُه في رسالتك لنفسك وفي `handover.md`.
- خطأ: «أصلح» الأداةَ من جلسة 0501. الصواب: بطاقةٌ للمايسترو بالعيب وأثره.
- خطأ: الاعتمادُ على `--window` ليحدّد النافذة. الصواب: هو عنوانٌ فقط؛ ملفُّ الخريطة هو الهويّة.
