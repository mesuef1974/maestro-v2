---
name: maestro-intake
description: |
  Use for turning any incoming item in the SchoolOS maestro system (owner request, approved inbox item, due roadmap item, alert, failed guard, bug discovered mid-work) into exactly ONE ledger card (ledger.py add) with a four-line spec, a real Doha start time and a P0..P3 priority, after de-duplication. Trigger on: new task, capture, intake, "log this", discovery, found work, out-of-scope bug, expedite, urgent, P0, ledger add, W-2026…, late start, 0202, 0201 — even if unnamed.
  استخدمها عند: «سجّل هذه»، «عندي طلب»، «أضفها للطابور»، «لقيت عيباً خارج مهمّتي»، «هذا عاجل»، «ما المتأخّر؟»، طلبٍ جديدٍ من المالك، بطاقةٍ من 0201 أو 0202 أو 0203 أو 0701 تصل «0201 · البوابة: البلاغاتُ والطابور»، أو قبل أيّ `ledger.py add`.
  ليست لـ: اختيار الجلسة وقياس الحِمل (maestro-load-check)، فتح جلسة (maestro-spawn)، قراءة صندوق رسائل المطوّر وتنقيحها (schoolos-feedback-intake)، خطوات الفلو بعد التنفيذ (schoolos-flow)، تسجيل اعتماد المالك (maestro-approvals)، هجرات الخارطة (0701).
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/ledger.py:*), Bash(python -X utf8 C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Bash(gh pr list:*), Bash(date -u:*), Read
---

# الالتقاط: من مدخلٍ إلى بطاقةٍ واحدة

الغرض: كلُّ عملٍ يدخل المنصّةَ يصير بطاقةً واحدةً في السجلّ (`ledger/events.jsonl`) بأربعة أسطرٍ وزمنِ بدءٍ فعليٍّ وأولويّة، بلا تكرار، ثمّ يُسلَّم مرتّباً إلى «0301 · المستشار: التصنيف والتسمية».
المصدر: `docs/intake_and_discovery.md`، وD-28م (لا مهمّةَ بلا زمنٍ وأولويّة)، وD-55م (0201 البوابةُ الموحّدة) — كلّها في `C:/Users/mesue/delivery_manager_work/`.

## من يستعمل ماذا
| الجلسة | دورُها في الالتقاط |
|---|---|
| 0101 · المايسترو | يسمع المالكَ ويحوّل طلبَه إلى 0202؛ ويستقبل P0 فوراً |
| 0202 · طلبات المالك | يحفظ نصَّ الطلب ووقتَه، ويعيد فهمَه للمالك في سطرٍ إن التبس، ويرسل مسوّدةَ الأسطر الأربعة إلى 0201 |
| 0201 · البوابة: البلاغاتُ والطابور | وحدها تدمج المصادرَ وتزيل التكرارَ وتعطي الزمنَ والأولويّةَ وتكتب `ledger.py add` وتسلّم الرأسَ إلى 0301 |
| أيُّ جلسةٍ تجد عيباً خارج مهمّتها | لا تصلحه؛ سطرٌ إلى 0201 بمصدر `discovery` |
المصدر: مواثيقُ 0202 و0201 في `tabs.json` → `session_policy.charters`؛ D-49م، D-51م، D-55م.

## الإجراء (بصيغة 0201؛ غيرُها ينفّذ الخطوات 1–4 ويرسل النتيجةَ إليها)
1. **حدّد المصدر** من ثمانية لا غير: `owner` `intake` `roadmap` `kpi_guard` `alert` `advisor` `repo_keeper` `discovery` (الأداةُ ترفض غيرَها). الجدولُ بمن يفتح كلَّ مصدرٍ في `references/00-fields-and-sources.md`.
2. **أزِل التكرار** في ثلاثة مواضع قبل أيّ بطاقة:
   - `gh pr list --state all --search "<كلمتان مميّزتان>" --limit 10 --json number,title,state` (من `D:/shschool_mvp`) — `--state all` لا `open`: المدموجُ يعني أنّ العملَ أُنجز.
   - `python -X utf8 C:/Users/mesue/delivery_manager_work/tools/ledger.py list` (البطاقاتُ كلُّها مرتّبة؛ أو `--state captured`).
   - الخارطةُ الحيّة: لا أداةَ محلّيّة لها في الحزمة — اسأل «0701 · الجودة: الرصدُ والخارطةُ والأتمتة» عن البند أو افتح `/roadmap/`.
   التطابقُ ضمٌّ لا بطاقة: أبلغ المصدرَ برقم البطاقة أو الطلب القائم؛ وإن حمل المدخلُ جديداً فأضِفه ملاحظةً: `ledger.py move <id> <حالتُها الحاليّة> --note "…"` (لا أمرَ «ضمّ» في الأداة).
3. **اكتب الأسطرَ الأربعة** (كلٌّ ≤ 240 حرفاً): المشكلة، الأثر (من يتأثّر وكم)، الملفّاتُ المظنونة (مساراتٌ فقط)، معيارُ القبول (كيف نعرف أنّها انتهت). بطاقةٌ ناقصةٌ تعود لمصدرها ولا تدخل الطابور.
4. **اختر `--type` من مفاتيح `projects/schoolos/routing.json`**: `ui` `schedule` `admin_platform` `product_features` `release` `git` `infra_preview` `qa_docs` `tech_debt` `roadmap` `governance` `intake` `regulations` `orchestration`. السبب: `routing.py` يُرجع `unknown_type` لغيرها (جُرّب 09-28 على `backend` الموجود في السجلّ فعلاً).
5. **الأولويّة:** P0 استعجال · P1 هذا الأسبوع · P2 هذا الشهر · P3 لاحقٌ مؤرَّخ (تعليقُ `PRIORITIES` في `ledger.py`). الاستعجالُ = ما يقرّره المالكُ اضطراراً، أو عطلُ إنتاجٍ/بياناتٍ/أمنٍ/PDPPL (S1)، أو معاينةٌ/طابورٌ/CI معطّلٌ يوقف الدفع (S2)؛ وبواحدٍ في وقتٍ واحد (`routing.json` → `expedite.limit = 1`)، ويُسجَّل في `decisions.md` بتاريخه وسببه. إن اختلف مصدران في الاستعجال فالمالكُ يحسم لا 0201.
6. **زمنُ البدء** = متى يجب أن يبدأ العملُ فعلاً (لا لحظةُ الالتقاط)، بتوقيت الدوحة من الساعة لا بالتقدير: `date -u -d '+3 hours' +%Y-%m-%dT%H:%M`. وP0 زمنُه الآن.
7. **اكتب البطاقة:**
   ```bash
   python -X utf8 C:/Users/mesue/delivery_manager_work/tools/ledger.py add --source owner --type ui \
     --problem "…" --impact "…" --accept "…" --files templates/x.html \
     --start 2026-09-29T08:00 --priority P2          # و--urgent مع P0 وحدها
   ```
   المخرجُ رقمُ البطاقة `W-YYYYMMDD-NNN`. `-X utf8` يجعل رسالةَ الرفض (تبدأ بـ«رُفض:») مقروءةً في Git Bash بدل رموزٍ مشوّهة.
8. **سلِّم وأبلغ:** رأسُ الطابور إلى 0301 بالترتيب (الأولويّة ← زمنُ البدء ← WSJF)؛ P0 إلى المايسترو فوراً؛ وسطرٌ واحدٌ للمالك أو المايسترو: الرقم، الأثر، المصدر، التالي («إلى 0301 للتصنيف»).
9. **يوميّاً:** المتأخّر = بطاقةٌ حالتُها `captured`/`verified`/`routed` وزمنُ بدئها مضى. يكشفه `python -X utf8 …/watch_once.py` (تنبيهُ `late_start`؛ وضعٌ حيٌّ يقرأ gh) — أرسل القائمةَ إلى المايسترو.

## القواعد وأسبابها
- لا بطاقةَ بلا `--start` و`--priority`: قرارُ المالك «لا شيءَ بدون زمن» (D-28م)، والأداةُ تفرضه بـargparse.
- لا نصَّ خامّاً لرسالة مستخدمٍ ولا اسمَ ولا رقمَ شخصيّاً في أيّ حقل: البطاقةُ تُنسخ إلى رسائل الإسناد واللوحة والخارطة، والمبدأُ PDPPL (`operating_model.md` §11؛ `ledger/events.jsonl` نفسُه متجاهَلٌ في غيت، `.gitignore` وD-56م). والحارسُ الآليُّ يمسك الأرقامَ ≥ 9 خاناتٍ والبريدَ فقط — **الأسماءُ تمرّ منه**، فالتنقيحُ مسؤوليّتُك.
- لا تُصلح خارج نطاقك؛ سجِّل: الإصلاحُ الجانبيّ يوسّع الطلبَ فيُرفض أو يتأخّر اعتمادُه، ويضيع أثرُه في الخارطة (`intake_and_discovery.md`، «مسارُ الاكتشاف»).
- الاستعجالُ يتجاوز الدورَ لا بوّابةَ الاعتماد ولا حزمةَ الأدلّة (`routing.json` → `expedite.note`).
- جوابٌ ملتبسٌ من المالك لا يُحوَّل إلى مواصفة: يُسأل عنه بسطر. السابقة: D-18 (بُنيت ثلاثةُ نماذج على فرضيّةٍ فأُلغيت).

## فخاخٌ وقعت فعلاً
- خطأ: نسخُ مثال `docs/intake_and_discovery.md` كما هو ← «the following arguments are required: --start, --priority». الصواب: المثالُ هناك أقدمُ من D-28م؛ أضِف الحقلين دائماً.
- خطأ: `TZ=Asia/Qatar date` في Git Bash ← يطبع UTC صامتاً (سُجّل طلبٌ في الطابور وقتَ الدوام بسببه). الصواب: `date -u -d '+3 hours'` (ذاكرة `feedback_doha_time_on_windows`).
- خطأ: وقتٌ مقدَّرٌ «~18:45» ← أوقاتُ D-40م..D-49م في `decisions.md` كُتبت متقدّمةً على الساعة وصُحّحت بسطرٍ لاحق (09-28 17:40). الصواب: الوقتُ من الساعة أو من حقل `generated_doha`.
- خطأ: `--type backend` أو `security` ← البطاقةُ تُكتب لكنّ التوجيه يسقط لاحقاً. الصواب: مفتاحٌ من `routing.json`.
- خطأ: `--urgent --priority P1` ← «رُفض: الاستعجالُ أولويّتُه P0». الصواب: الاستعجالُ P0 دائماً.
- خطأ: بطاقةٌ جديدةٌ لما دُمج أمس لأنّ البحث كان `--state open`. الصواب: `--state all`.
- خطأ: «وليّ أمر الطالب فلان يشتكي أنّ…» في `--problem`. الصواب: «شكوى وليّ أمرٍ من اختفاء زرّ التصدير في صفحة الطالب».

## أمثلة (مختلَقة)
- المدخل: المالك للمايسترو «بطاقة الغياب فيها فراغ أبيض على الجوال». ← 0202 يحفظ النصَّ ووقتَه ← 0201: لا طلبَ ولا بطاقةَ مطابقة ← `add --source owner --type ui --problem "بطاقة رصد الغياب تمتدّ بفراغٍ أبيض على عرض الجوال" --impact "مشرفو الأجنحة يوميّاً" --accept "البطاقةُ بارتفاع محتواها عند 375px" --files templates/wings/record.html --start <الغد 08:00> --priority P2` ← «W-…-018 إلى 0301».
- المدخل: جلسةُ 04 تكتب «وجدتُ أنّ التصدير يكسر الترويسة وهذا خارج مهمّتي». ← `--source discovery`؛ ليس S1/S2 ← P2 مربوطٌ في `--problem` برقم البطاقة الأصل؛ والجلسةُ تكمل مهمّتها ولا تصلحه.
- المدخل: 0203 «الإنتاج يعيد 500 على صفحة الدخول». ← S1 ← `--source alert --priority P0 --urgent --start <الآن>`، وإبلاغُ المايسترو فوراً قبل أيّ ترتيب.
أمثلةٌ أكثر وحالاتُ الرفض في `references/00-fields-and-sources.md`.

## المراجع
| الملف | متى تقرؤه |
|---|---|
| `references/00-fields-and-sources.md` | حين تتردّد في المصدر أو الحالة أو قيدِ حقلٍ، أو ترى رسالةَ «رُفض:» |
| `references/99-test-cases.md` | عند مراجعة وصف المهارة أو اختبار تفعيلها |
