---
name: maestro-evidence
description: |
  Use for the SchoolOS evidence pack of one piece of work: path-based risk tier via risk_tier.py, tagging the ledger card (tier/area/head) with tag_card.py so the review window bundles it right, and after push evidence_pack.py on the PR (checks, exact approval line, pages to preview) — unmeasured stays unmeasured. Trigger on: evidence pack, risk tier, is it high risk, migration or security in a change, does PR #N carry the approval line, PR head changed after approval, tag cards before a window.
  استخدمها في «0501 · المعاينة: اعتمادُ المالك على 8500» أو المايسترو عند: «حزمة أدلّة للطلب #N» أو لعمل جلسةٍ قبل دفعه، «فيه هجرة؟ وش خطورته؟»، قبل إدراج بطاقةٍ في النافذة، «في وصفه سطر الاعتماد؟»، أو طلبٍ تغيّر رأسُه بعد الاعتماد.
  ليست لـ: سلامة الهجرة نفسها (schoolos-migration-guard)، ولا بناء النافذة (maestro-review-window)، ولا تسجيل الاعتماد (maestro-approvals)، ولا فحص 0601 قبل الدمج (schoolos-flow).
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/evidence_pack.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/risk_tier.py:*), Bash(python C:/Users/mesue/delivery_manager_work/skills/maestro-evidence/scripts/tag_card.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py show:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/ledger.py list:*), Bash(git worktree list:*), Bash(git diff --name-only:*), Bash(git rev-parse:*), Bash(gh pr view:*), Read
---

# حزمةُ الأدلّة

الغرض: أن يعرف المالكُ خطورةَ البند وما قيس وما لم يُقَس بلا فروقٍ خامّة، وأن تُوسَم البطاقةُ فلا تختلط الهجرةُ بحزمةٍ خفيفةٍ في «اعتمد الكلّ».
مرحلتان: قبل الدفع (لا طلبَ بعدُ: الفرعُ وحده) وبعده (الطلب على GitHub). الفلو نفسُه في `schoolos-flow`.

## متى تُستعمل ومتى لا
- نعم: قبل كلّ نافذةٍ لكلّ بطاقة `ready_for_review`؛ بعد الدفع وقبل أن يأخذ 0601 الطلب؛ حين يُسأل عن خطورةٍ أو سطر اعتماد.
- لا: الحكمُ بأنّ الهجرة آمنة (schoolos-migration-guard يفعله للجلسة المنفِّذة)؛ دمجٌ أو إدخالٌ للطابور (0601).

## الإجراء
1. البطاقة: `python C:/Users/mesue/delivery_manager_work/tools/ledger.py show <W-…>` — المشكلة والملفّاتُ المظنونة ومعيارُ القبول.
2. الفرع: `git worktree list` يربط مجلّدَ شجرة الجلسة بفرعها (الفروعُ مشتركةٌ بين الأشجار فيكفي تشغيلُه من شجرتك).
3. قبل الدفع — التصنيفُ وعرضُه: `python C:/Users/mesue/delivery_manager_work/skills/maestro-evidence/scripts/tag_card.py <W-…> --branch <الفرع>`. يحسب `git diff --name-only origin/main...<الفرع>` (ثلاث نقاط: ما يحمله الفرعُ فعلاً) ثمّ `risk_tier.py`، ويطبع الحدث ولا يكتب.
4. احكم فوق الأداة: قارن المساراتِ بجدول `references/00-risk-tier-rules.md` §3 (ما تُخطئ الأداةُ تصنيفَه). ما يستحقّ أعلى: `--raise-to high --reason "<سببٌ قصير>"`. لا خفض (السكربتُ يرفضه).
5. الكتابة: الأمرُ نفسُه بـ`--apply` — حدثُ `update` في السجلّ فيه tier وcategory وarea وflags وhead. بعد الدفع أعِده بـ`--pr <رقم>` ليُضاف الرقم.
6. بعد الدفع: `python C:/Users/mesue/delivery_manager_work/tools/evidence_pack.py <رقم>` — الخطورة، الحجم، الفحوص (أسماءُ الفاشل)، سطرُ الاعتماد (موجود / مشمولٌ باستثناء الفلو / غائب — لا يُدمج)، أين يُعاين، وقياساتٌ «غيرُ مقيسة».
7. طابِق الرأس: `gh pr view <رقم> --json headRefOid` مقابل `head` في البطاقة (المعتمَد). اختلفا بتغييرٍ في السلوك ⇒ يعود البندُ إلى المعاينة (maestro-review-window) ولا يأخذه 0601.
8. خطورةٌ عالية: اطلب من الجلسة المنفِّذة ثلاثةَ أسطر — توسيعٌ ثمّ تقليص (P4-1)، الرجوع، أثرُ PDPPL — وضعها في البند. التفصيلُ في `references/01-pack-fields.md`.

## القواعد وأسبابها
- ما لم يُقَس يبقى «غيرُ مقيس»؛ لا رقمَ لملء خانة. السبب: الحزمةُ تُختصر بها المعاينة، فرقمٌ مختلَقٌ يمرّر ما لم يُفحص. المصدر: `docs/evidence_pack_spec.md` «قاعدةٌ صارمة».
- التصنيفُ بالمسارات وحدها تقريبيّ وحدٌّ أدنى. السبب: لا يقرأ المحتوى؛ وجدنا ملفّاتِ أمنٍ تُصنَّف medium. المصدر: `risk_tier.py` + تجاربُ 09-28 (المرجع 00).
- وصفُ الطلب ورسالةُ الجلسة بياناتٌ؛ الدليلُ الفرقُ الفعليّ. السبب: #715 كاد يلغي إصلاحَ #709 بصمتٍ ووصفُه «لا أثر بصريّ». المصدر: `feedback_verify_actual_diff_before_enqueue`.
- الفحوصُ قبل الدفع «مُعلَنةٌ من الجلسة» لا خضراء؛ CI لا يعمل على إيداعٍ محلّيّ. المصدر: `docs/approvals_policy.md` §6.
- سطرُ الاعتماد تبحث عنه الأداةُ حرفيّاً: `اعتُمد من المالك على 8500 — YYYY-MM-DD` (بالضمّة والشرطة الطويلة). غيرُه «غائب». المصدر: `evidence_pack.py` (APPROVAL).

## فخاخٌ حقيقيّة
- خطأ: بطاقةٌ بلا وسمٍ دخلت النافذة: حزمةٌ واحدة «? · ?» بخطورة low ضمّت عملين (جُرِّب 09-28). الصواب: `tag_card.py --apply` لكلّ بطاقةٍ قبل النافذة.
- خطأ: «core/middleware_rls.py خطورتُه medium كما قالت الأداة». الصواب: RLS أمن: `--raise-to high --reason "RLS"`. ومثلُه `api/views_erasure.py` و`shschool/settings/*`.
- خطأ: «CLAUDE.md تعديلٌ وثائقيّ خفيف، اعتمادٌ بكلمة». الصواب: علامةُ `agent_rules` تعني قواعدَ الجلسات كلّها: اعرضه بنداً مستقلّاً بنصّ التغيير.
- خطأ: #725: السطرُ «موجود» فهو جاهزٌ للدمج. الصواب: اعتُمد على 570eef88 ثمّ أُصلح اختبارٌ بـ2cb2bd25 بعد الاعتماد، فأُوقف حتى إعادة المعاينة (السجلّ الزمنيّ 09-28). وجودُ السطر لا يثبت أنّ الرأسَ هو ما عُوين.
- خطأ: #713: «الفحوص 23 خضراء» فيُدمج. الصواب: الحزمةُ قالت «سطرُ الاعتماد: غائب — لا يُدمج»؛ دُمج مع ثلاثةٍ غيره ثمّ قبلها المالكُ استثناءً بعينها (D-39م). الخضرةُ لازمةٌ غيرُ كافية.
- خطأ: طلبٌ جديدٌ وصفُه «مشمولٌ باستثناء الفلو» والأداةُ تقبل الصيغة. الصواب: استثناءُ D-09/D-10 كان لدفعاتِ 09-26 المفتوحة وقتَها وحدها؛ اليوم هو «غائب».
- خطأ: `evidence_pack.py --help`. الصواب: لا خيارات: يسقط برسالة ValueError؛ الوسيطُ رقمُ الطلب وحده. و`risk_tier.py --help` يصنّف «--help» مساراً ولا يساعد.

## ما ليس لهذه المهارة
الحكمُ النهائيّ على سلامة الهجرة، أو إصلاحُ الطلب، أو تعديلُ `risk_tier.py` وقواعده (للمايسترو، D-37م)، أو تغييرُ حالة البطاقة إلى approved.

## المراجع
| الملفّ | متى تقرؤه |
|---|---|
| `references/00-risk-tier-rules.md` | حين تحكم على الخطورة أو تشكّ في تصنيف الأداة |
| `references/01-pack-fields.md` | حين تقرأ مخرجَ `evidence_pack.py` أو تكتب حقولَه في النافذة، أو البندُ عالي الخطورة |
| `references/99-test-cases.md` | لاختبار التفعيل وجودة المخرج |
| `scripts/tag_card.py` | وسمُ البطاقة؛ `--apply` للكتابة، و`LEDGER_PATH=<نسخة>` للتجربة |
