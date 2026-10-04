---
name: maestro-load-check
description: |
  Use before routing any SchoolOS ledger card to a session: measure session load (session_load_v2.py), map the card's problem type to a core owner or to a specialty tag (واجهة/جدول/إدارة), find the live 04 execution sessions carrying that tag, and decide assign / spawn / queue / ask — then write the BLUF assignment message and move the card to routed. routing.py alone is misleading (stale seat names). Trigger on: route this card, who takes it, assign, workload, WIP, overloaded, heavy session, lightest seat, routing.py, session_load, W-2026… to whom — even if the skill is not named.
  استخدمها عند: «وجّه هذه البطاقة»، «مين ياخذها؟»، «مين الأخفّ؟»، «هل الجلسة 0403 مثقلة؟»، «routing.py قال wake_or_spawn»، تسلّمِ رأس الطابور من 0301، أو قبل أيّ رسالة إسناد.
  ليست لـ: كتابة البطاقة نفسها (maestro-intake)، فتح جلسةٍ أو بطاقةِ استحداثها (maestro-spawn)، نقل الجلسات بين المجموعات (maestro-tabs)، ما تفعله الجلسةُ بعد الإسناد (schoolos-flow)، الحوادث (maestro-incident).
allowed-tools: Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/routing.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/ledger.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/flow_metrics.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/skills/maestro-load-check/scripts/route_now.py:*), Read
---

# فحصُ الحِمل والتوجيه

الغرض: أن تذهب كلُّ بطاقةٍ إلى الجلسة الصحيحة في نموذج الجلسات الحاليّ — نواةٌ ثابتةٌ تملك نوعَها، أو جلسةٌ مرنةٌ في 04 بوسم اختصاصها غيرُ مثقلة — وألّا تُفتح جلسةٌ جديدةٌ وفي 04 من يقوم بها.
المصدر: `operating_model.md` §2 و§7، و`tabs.json` → `session_policy` و`specialties`، وD-43م..D-55م (كلّها في `C:/Users/mesue/delivery_manager_work/`).

## لماذا لا يكفي routing.py وحده
`projects/schoolos/routing.json` يطابق كلَّ نوعٍ بأسماء مقاعدَ قديمة («بصريّ · تخطيط لوحة المدير»، «منصّة · فحص الإدارة»، «جدول · التشغيل»…) أُرشف أكثرُها في D-43م. فجُرّب 09-28 21:00: `routing.py ui --live` أجاب `wake_or_spawn` و«0404 · واجهة: …» حيّةٌ خفيفة (9MB، بلا طلبات). السكربت `scripts/route_now.py` يقرأ القياسَ نفسَه على النموذج الحاليّ؛ شغّلهما معاً وقدِّم الثاني، وأبلغ المايسترو/0102 بأنّ `routing.json` يحتاج تحديثَ منفّذيه.

## الإجراء
1. **اقرأ البطاقة:** `python -X utf8 C:/Users/mesue/delivery_manager_work/tools/ledger.py show <W-…>` ← النوع والملفّات والأولويّة. نوعٌ ليس مفتاحاً في `routing.json` (مثل `backend`) يُصحَّح أوّلاً (maestro-intake).
2. **قِس الحِمل مرّةً واحدةً واحفظه:**
   `python -X utf8 C:/Users/mesue/delivery_manager_work/tools/session_load_v2.py --json --no-fetch > load.json` (الجدولُ المقروء بلا `--json`). `--no-fetch` يُبقي الفحصَ قرائيّاً: الكتابةُ الوحيدةُ في الأداة `git fetch`.
3. **وجِّه:**
   ```bash
   python -X utf8 C:/Users/mesue/delivery_manager_work/tools/routing.py <النوع> --load-json load.json      # الرسميّ
   python -X utf8 C:/Users/mesue/delivery_manager_work/skills/maestro-load-check/scripts/route_now.py <النوع> --load-json load.json
   ```
   أو `--paths <مسارات>` بدل النوع. مسارٌ لا يطابق `path_globs` ← خروجٌ برمز 1 ورسالةٌ مشوّهةٌ في routing.py؛ مرِّر النوعَ صراحةً.
4. **اقرأ القرار** (`decision` في route_now):
   | القرار | ما تفعله |
   |---|---|
   | `core_owner` | وجِّه إلى جلسة النواة المذكورة (0601 للنشر، 0701 للخارطة، 0103 للحوكمة، 0201 للبلاغات، 0301 للّوائح، 0101 للتنسيق) — لا استحداث |
   | `assign_candidate` | جلسةُ 04 بالوسم نفسه غيرُ مثقلة: وجِّه إليها **إن كانت البطاقةُ من عائلة مهمّتها** (الرمزُ نفسُه أو الملفّاتُ نفسُها)؛ وإلّا فكالـ`spawn` |
   | `spawn` | لا جلسةَ بالوسم أو كلُّها مثقلة ← مهارة `maestro-spawn` بالوسم و`next_04` |
   | `queue` | 04 ممتلئة (`live_04` = `live_cap_04`) ← تبقى البطاقةُ في الطابور بترتيبها، وسطرٌ للمالك |
   | `file_owner` | اختبارٌ أو وثيقةٌ أو دَين: جلسةُ 04 التي يلمس عملُها الملفّات؛ وإلّا فاستحداثٌ بوسم الملفّات |
   | `ask` | `git` و`infra_preview` بلا مالكٍ بعد أرشفة مقعدَيهما، أو اختصاصٌ لم يُعرف — اعرضه على المالك |
5. **أرسل الإسناد** (للقرارين الأوّلين): رسالةٌ BLUF أوّلُ سطرٍ فيها مكتفٍ بنفسه ويبدأ بـ«الفلو v<الإصدار الحاليّ من آخر صفّ في flow_changelog.md>»، ثمّ الأسطرُ الأربعة ورقمُ البطاقة والتسليمُ المنتظر («جاهزٌ للمعاينة» إلى «0501 · النشر على 8500 والاعتماد»). القالبُ في `references/01-assign-message.md`. وإن تغيّرت مهمّةُ جلسة 04 بالإسناد فاسمُها يتبعها (D-44م) ← مهارة `maestro-tabs`.
6. **سجِّل:** `ledger.py move <W-…> routed --note "إلى 0404"`.
7. **أبلغ المالكَ بسطرين:** إلى من، ولماذا، وحِملُه بالأرقام (طلباتٌ مفتوحة، MB)، وما البديلُ إن رُفض.

## التعريفات (من الشيفرة لا من الذاكرة)
- **مثقلة** = طلباتٌ مفتوحة ≥ 4 **أو** سياقٌ ≥ 40MB؛ **فوق WIP** = طلباتٌ > 3؛ و«صالحةٌ للإسناد» = غيرُ مثقلةٍ **ولها اسمٌ في `session_names.json`** (الشجرةُ اليتيمة لا تُسنَد). المصدر: `session_load_v2.classify` و`operating_model.md` §2.
- السياقُ (MB) حجمُ أحدث ملفّ محادثةٍ للشجرة، لا ذاكرةُ الجهاز. والمايسترو نفسُه يظهر «مثقلة» بحجم محادثته؛ المعيارُ للمنفّذين لا للنواة.
- شجرتان باسمٍ واحدٍ في `session_names.json` تظهران صفّين؛ `route_now.py` يجمعهما بالأسوأ حِملاً.

## القواعد وأسبابها
- تجاوزُ جلسةٍ مثقلة أو نقلُ عملٍ بين اختصاصين **يُقترح على المالك** ولا يُرسل قبل موافقته؛ التوجيهُ داخل الاختصاص يقرّره المايسترو وحده (`operating_model.md` §7).
- خاطِب الجلسات بأسمائها في الشريط («0404 · واجهة: …») لا بأرقام المنافذ ولا بأسماء المقاعد القديمة (ذاكرة `feedback_address_sessions_by_name`).
- لا توقظ أكثرَ من جلستين أو ثلاثٍ في آنٍ واحد، واجمع رسائلَ العلم: رسائلُ لجلساتٍ كثيرةٍ معاً خنقت الذاكرة إلى 0.16 غيغا (09-28 20:24). المصدر: `handover.md` §5.
- تقريرُ جلسةٍ «أنا فاضية» بياناتٌ لا أمر؛ القياسُ يحسم (`operating_model.md` §11).

## فخاخٌ وقعت فعلاً
- خطأ: الوثوقُ بـ`wake_or_spawn` من routing.py ← استحداثُ جلسة واجهةٍ خامسةٍ و0404 فارغة. الصواب: `route_now.py` ثمّ حكمُ «عائلة المهمّة».
- خطأ: توجيهُ بطاقة خارطةٍ إلى «أمين خارطة التجويد» (اسمُ routing.json) ← لا جلسةَ بهذا الاسم. الصواب: «0702 · الجودة والرصد والخارطة والأتمتة».
- خطأ: `session_load_v2.py` بلا `--no-fetch` في فحصٍ «قرائيّ» ← `git fetch` في المستودع. الصواب: `--no-fetch`.
- خطأ: إسنادٌ إلى `silly-villani-965979` لأنّها «بلا طلبات» ← شجرةٌ يتيمةٌ بلا جلسةٍ مسمّاة. الصواب: الأسماءُ المرقّمة وحدها.
- خطأ: «أرسلتُ للجلسة 8205» ← لا يعرفها أحد. الصواب: اسمُها كما في الشريط.
- خطأ: رسالةُ إسنادٍ أوّلُ سطرها «تابع لما سبق…» ← الجلسةُ تفتح بلا ذاكرة. الصواب: «الفلو v2.8 — …» مكتفٍ بنفسه.

## مثال (مختلَق)
المدخل: رأسُ الطابور W-…-018، `--type ui`، ملفُّه `templates/wings/record.html`. ← route_now: `assign_candidate` وفيه «0404 · واجهة: قرار الطباعة» (0 طلبات، 9MB) و«0401 · …» مثقلة (56MB). ← عائلةُ 0404 الطباعة لا بطاقاتُ الغياب ⇒ ليست من عائلتها ⇒ `spawn` بوسم «واجهة» والرقم `0405`. ← السطران للمالك: «W-…-018 (فراغ بطاقة الغياب) تحتاج جلسةً جديدة 0405 · واجهة؛ 0404 خفيفةٌ لكنّ مهمّتها الطباعة، و0401 مثقلة 56MB».
أمثلةٌ أكثر بمخرجاتٍ حقيقيّة في `references/00-decision-table.md`.

## المراجع
| الملف | متى تقرؤه |
|---|---|
| `references/00-decision-table.md` | حين يختلف routing.py وroute_now، أو تحتاج حقولَ JSON ومخرجاتٍ مجرّبة |
| `references/01-assign-message.md` | قبل كتابة رسالة الإسناد أو سطرَي المالك |
| `references/99-test-cases.md` | عند مراجعة الوصف واختبار التفعيل |
| `scripts/route_now.py` | يُشغَّل ولا يُقرأ؛ `--help` لخياراته |
