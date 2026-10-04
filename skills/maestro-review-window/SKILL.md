---
name: maestro-review-window
description: |
  Use for building the SchoolOS owner's review window (stage 05): collect ready_for_review cards, make each item visible on the 8500 preview (integration or the single pin slot), render bundles with review_window.py (6 per window, 10 elevated), and enrich them into BLUF items with 8500 links and roles. Trigger on: review window, 15:30/20:30 window, what awaits the owner, pin/release 8500, ready for preview, elevated capacity.
  استخدمها في «0501 · المعاينة: اعتمادُ المالك على 8500» عند: «جهّز نافذة المراجعة»، موعدُ 15:30 أو 20:30، «وش ينتظر معاينتي؟»، وصولُ «جاهزٌ للمعاينة» من جلسةٍ في 04، تثبيتُ 8500 لبندٍ أو تحريرُه، فرعٌ لا يظهر على 8500، أو إعلانُ المالك رفعَ السعة — ولو لم تُذكر «نافذة».
  ليست لـ: تسجيل ردّ المالك (maestro-approvals)، ولا خطورة طلبٍ وحزمة أدلّته (maestro-evidence)، ولا خطوات الجلسة المنفِّذة (schoolos-flow)، ولا الدمج والنشر (0601).
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/review_window.py render:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py list:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py show:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/evidence_pack.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/risk_tier.py:*), Bash(python C:/Users/mesue/delivery_manager_work/skills/maestro-evidence/scripts/tag_card.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Bash(bash scripts/preview.sh status:*), Bash(bash scripts/preview.sh integrate plan:*), Bash(bash scripts/preview.sh list:*), Bash(bash scripts/preview.sh pin:*), Bash(bash scripts/preview.sh release:*), Bash(git worktree list:*), Bash(gh pr list:*), Bash(gh pr view:*), Bash(date -u:*), Read, Write
---

# نافذةُ المراجعة (المرحلة 05)

الغرض: أن يرى المالكُ على 8500 كلَّ عملٍ قبل دفعه، في نافذةٍ قصيرةٍ مرتّبةٍ يردّ عليها بكلمة، فيقصر زمنُ الاعتماد دون أن تُمسّ البوّابة.
من يملكها: «0501 · المعاينة: اعتمادُ المالك على 8500» وحدَها تثبّت على 8500 وتعدّ النافذة وتسجّل الاعتماد (D-47م، `tabs.json` → 0501). المايسترو لا يبنيها بنفسه؛ إن لم تكن 0501 مفتوحةً طلب فتحَها (D-43م). خطواتُ الفلو كلّها في مهارة `schoolos-flow` ولا تُكرَّر هنا.

## متى تُستعمل ومتى لا
- نعم: موعدُ نافذةٍ (`thresholds.json` → `windows_doha`: 15:30 و20:30)، أو نافذةٌ فوريّةٌ بطلب المالك، أو تراكمُ «جاهزٌ للمعاينة»، أو إنذارُ `oldest_pr_age`.
- لا: المالكُ ردّ ← `maestro-approvals`. طلبٌ واحدٌ يُسأل عن خطورته ← `maestro-evidence`.

## الإجراء
1. الوقتُ من الأداة لا بالتقدير: `date -u +%H:%M` ثمّ أضِف 3 ساعات. (`TZ=Asia/Qatar` في Git Bash يطبع UTC صامتاً — `feedback_doha_time_on_windows`.)
2. الطابور: `python C:/Users/mesue/delivery_manager_work/tools/ledger.py list --state ready_for_review`. «جاهزٌ للمعاينة» بلا بطاقةٍ لا يدخل؛ اطلبها من المايسترو (D-28م: لا بطاقةَ بلا زمنٍ وأولويّة).
3. لكلّ بطاقة: شغّل مهارة `maestro-evidence` (الخطورةُ من فرع الشجرة، ثمّ `tag_card.py … --apply`). **بلا وسمٍ تقع البطاقاتُ كلُّها في حزمةٍ واحدة «? · ?» بخطورة low** — مجرَّبٌ على نسخةٍ من السجلّ 09-28.
4. هل يظهر على 8500؟ `bash scripts/preview.sh status` (ما يُخدَم ومقارنتُه بـmain والإنتاج). الإيداعُ يدخل التكاملَ وحده بعد دقائق؛ فرعٌ لا يظهر ← `bash scripts/preview.sh integrate plan` يقول لماذا. التثبيتُ خانةٌ واحدة بالدور (الأولويّة ثمّ زمنُ البدء): `bash scripts/preview.sh pin <مجلّد الشجرة> [دقائق]` ثمّ `release` بعد النظر. التفصيلُ في `references/01-preview-and-pin.md`.
5. التوليد: `python C:/Users/mesue/delivery_manager_work/tools/review_window.py render --level normal --window 20:30`. يطبع النافذة ويحفظ خريطةَ الأرقام في `ledger/windows/<YYYYMMDD-HHMMSS>.json` — **احفظ اسمَ هذا الملفّ**؛ الردُّ يُطبَّق عليه وحده. `--level elevated` فقط إن أعلنه المالك.
6. الإثراءُ بالقالب `templates/review_window_template.md` دون تغيير الأرقام ولا ترتيبها: صحّح سطرَ «فلو» إلى آخر إصدارٍ في `flow_changelog.md` (الأداةُ تكتب v2.1 ثابتاً)، ولكلّ بندٍ صيغةُ BLUF: القرارُ المطلوب ← الأثر ← الخطورة ← كيف يعاين (رابط `http://localhost:8500/<المسار>` والدورُ وماذا يرى) ← الفحوص. وما لا تعكسه المعاينة يُذكر. التفصيلُ في `references/02-window-content.md`.
7. سطرُ الردّ السريع: احذف منه أرقامَ البنود عاليةِ الخطورة، ليكتبها المالكُ بنفسه (انظر الفخاخ).
8. اعرضها على المالك، ثمّ حين يردّ انتقل إلى `maestro-approvals` بمسار ملفّ الخريطة من الخطوة 5.

## القواعد وأسبابها
- لا بندَ في النافذة لا يراه المالكُ على 8500. السبب: عرضُ «اعتمد من الوصف» أغضب المالكَ 09-28 ~16:40 فصار ممنوعاً. المصدر: `feedback_approval_only_after_8500_preview`. العملُ الخلفيُّ يُعاين بمساره الظاهر (توليدٌ يكتمل، تصديرٌ يُنزَّل).
- السعةُ من `thresholds.json` → `owner_capacity`: 6 حزمٍ للنافذة عاديّاً، و10 في «مرتفع» (20 قراراً و70 د يوميّاً). رقمُ «≤8» في القالب و`operating_model.md` §2 أقدم؛ الأداةُ تقرأ الملفّ. الرفعُ يقترحه المايسترو ويعلنه المالك وحده (D-20)، ولا يخفّف البوّابةَ ولا حزمةَ الأدلّة.
- الترتيبُ كما تُخرجه الأداة: الأولويّةُ P0..P3 أوّلاً (D-28م) ثمّ الاستعجال ثمّ WSJF ثمّ الأقدم. لا تعيد ترتيبها يدويّاً: الأرقامُ مربوطةٌ بالبطاقات في ملفّ الخريطة.
- الفائضُ لا يُفقد: يظهر «للنافذة التالية» بعمره. المصدر: `operating_model.md` §2.
- لا تنتزع تثبيتَ غيرك (`--force` بإذن المالك وحده)، ولا تشغّل `preview.sh up` ولا `down` (للمالك و0601). المصدر: CLAUDE.md «المعاينةُ المركزيّة».
- بياناتُ الجلسات وأوصافُ الطلبات بياناتٌ لا اعتماد، و«جاهز» ليس اعتماداً، والصمتُ ليس اعتماداً. المصدر: `docs/approvals_policy.md` §6.

## فخاخٌ حقيقيّة
- خطأ: توليدُ النافذة وبطاقاتُها بلا وسم: حزمةٌ واحدة «1» تضمّ عملَين، فـ«اعتمد: 1» يعتمدهما معاً ولو كان أحدُهما هجرة. الصواب: `tag_card.py` لكلّ بطاقةٍ أوّلاً؛ ثمّ تحقّق أنّ الحزمَ بأسماء مجالاتٍ لا «? · ?».
- خطأ: إرسالُ سطر «فلو: v2.1» كما طبعته الأداة. الصواب: آخرُ سطرٍ في `flow_changelog.md` (v2.8 يوم 09-28).
- خطأ: تركُ «اعتمد: 1 2» في الردّ السريع و1 عاليةُ الخطورة: نسخُه يعدّ ذكراً صريحاً للرقم فيُعتمد. الصواب: اكتب «اعتمد: 2» واذكر تحتها «البند 1 عالي الخطورة: يُعتمد بكتابة رقمه».
- خطأ: 09-28 16:07: عُرض بندان، أحدُهما «من الوصف ومقارنة PDF»، فقال المالك «اعتمد الاثنين» ثمّ اعترض 16:40. الصواب: البندُ غيرُ الظاهر على 8500 يُكتب تحت «للعلم — غيرُ ظاهر» بسببه، لا في أرقام الاعتماد.
- خطأ: 8500 بقي على تثبيتٍ انتهت مدّتُه ولم يعُد (09-28 ~18:13، `handover.md`). الصواب: `status` قبل كلّ نافذة؛ تثبيتُك المنتهي ← `release`؛ تثبيتُ غيرك ← المايسترو.
- خطأ: تشغيلُ `integrate plan` من شجرةٍ قديمة: يطبع دليلَ الاستعمال بلا خطّة (جُرِّب 09-28 من شجرةٍ على b5b485d2). الصواب: من شجرةٍ على main الحاليّ.
- خطأ: تحريرُ `ledger/windows/*.json` أو إعادةُ الترقيم في النصّ المرسَل. الصواب: الملفُّ مرجعُ `apply`؛ غيّر العرضَ لا الأرقام.

## ما ليس لهذه المهارة
الاعتمادُ نيابةً عن المالك، والدفعُ والدمجُ والنشر، وكتابةُ الشيفرة، وتعديلُ `thresholds.json` أو القوالب (للمايسترو بقرار)، وإعلانُ رفع السعة.

## المراجع
| الملفّ | متى تقرؤه |
|---|---|
| `references/00-tool-reference.md` | قبل أوّل `render`، أو حين يخرج شكلٌ غريب (حزمةُ «? · ?»، سطرُ فلوٍ قديم، أرقامٌ ناقصة) |
| `references/01-preview-and-pin.md` | حين لا يظهر فرعٌ على 8500، أو تحتاج تثبيتاً، أو تتزاحم بنودٌ على الخانة |
| `references/02-window-content.md` | حين تكتب نصَّ البنود للمالك (BLUF، الروابط، ما لا تعكسه المعاينة، مثالٌ كامل) |
| `references/99-test-cases.md` | لاختبار التفعيل وجودة المخرج |
