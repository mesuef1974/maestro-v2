# خطة مزامنة الشجرة المشتركة مع origin — 2026-10-21

أُعدّت قراءةً فقط: لا دمج ولا دفع ولا checkout ولا reset ولا حذف، ولم يُمسّ ledger/flow_pump.off. التنفيذ ينتظر اعتماد 0101 والمالك.

## ملخص للمالك (قصير)

1. الوضع: الشجرة متقدمة 21 إيداعاً ومتأخرة 22 عن origin/main. نقطة الانفصال b55d5c4 (2026-10-19).
2. التعارضات النصيّة ثلاثة فقط، وكلها صغيرة وحلّها معروف (انظر القسم 3). لا يضيع شيء من أيّ الجهتين.
3. ترقيم القرارات: لا تعارض فعليّاً. decisions.md في origin وفي الإيداع المحلي كلاهما ينتهي عند D-332م، وorigin لم يلمسه منذ 2026-10-10. القرارات D-333م…D-453م (141 سطراً) موجودة فقط في نسخة العمل غير المودَعة، وأكواد origin تشير إليها أصلاً (D-446م وD-450م وD-451م وD-452م). فالعلاج إيداعُها كما هي بلا إعادة ترقيم.
4. الخطر الأكبر: هذه النسخة غير المودَعة هي النسخة الوحيدة لسجلّ القرارات (11 يوماً من قرارات المالك) ولسجلّ owner_confirmations.md (+1143 سطراً). يُنصح بنسخة أمان خارج المستودع قبل أيّ خطوة.
5. نحو نصف «الأتساخ» نسخٌ مطابقة لما في origin (7 ملفات معدَّلة و7 غير متتبَّعة) فلا تُودَع؛ تُستبدل بنسخة origin بلا فقد.
6. الشجرة نشطة الآن: جلسة مرتبطة تعمل فيها. لا يُنفَّذ شيء قبل هدوئها.

## 1. الحالة والتصنيف

أ) الملفات المتتبَّعة المعدَّلة (44: 38 معدَّلاً و6 محذوفة)

| الفئة | الملفات | ملاحظة |
|---|---|---|
| قرارات وسجلّات | decisions.md (+141)، ledger/decisions_meta.jsonl (+126)، owner_confirmations.md (+1143)، owner_orders_auto.md، board_state.md، violations.md | origin لم يلمس أيّاً منها: إيداعها بلا تعارض |
| مذكرات | handover_notes: 0414-w016-w001-handover، peaceful-zhukovsky-b848aa، scheduler-quality-wave1؛ docs/intake_and_discovery.md | لا تعارض |
| لقطات | projects/schoolos/sessions_snapshot.json | حالة آلية؛ تُودَع أو تُهمل بقرار 0101 |
| مهارات | skills/maestro-intake وmaestro-load-check وmaestro-spawn (SKILL.md) | لا تعارض |
| أدوات تتمة دمج 01 (حقيقية) | archive_sweep، decision_add، decisions_lint، gate_check، identity_ack، open_gate، post_merge_checklist، flow_watch، my_state، wake_monitor، test_decisions_lint، test_flow_watch، test_open_gate_archive، test_package، test_wake_monitor | flow_watch وmy_state وwake_monitor وtest_* مشتركة مع origin (القسم 2.ب) |
| أدوات نسخٌ مطابقة لـorigin (7) | branch_status، ledger_sync، release_follow.sh، watch_once، test_ledger_gates، test_ledger_sync، test_remote_push_held_by | محتواها = origin/main حرفياً (بعد تطبيع CRLF): لا تُودَع |
| أدوات سلَف قديم لما في origin (2) | record_owner_confirmation.py، test_record_owner_confirmation.py | origin يحوي نفس الميزة (--window-order) وزيادة (--delegation، D-443م): يؤخذ origin كاملاً |
| محذوفة (6) | docs/machine_ops/after.json وbefore.json وreport.md، docs/railway_rollback_trial.md، docs/triage_local_main_2026-10-19.md، handover_notes/ready_mark_hook_settings_snippet.md | كلها موجودة في origin أيضاً. لا تُودَع كحذف؛ تُستعاد (حذفٌ غير مبرَّر) ما لم يؤكد 0101 قصده |

ب) غير المتتبَّعة (410)

- handover_notes/ ‏227 ملفاً، docs/ ‏87 (43 html و14 md و14 py و10 txt ومجلدات)، جذر المستودع 54، tools/ ‏32، ledger/ ‏4، و6 مجلدات صغيرة (tmp، skills_drafts، security، research_skill_sources، reports، digest).
- tools/ ‏32: سبعة مطابقة لـorigin (batch_approve، ready_to_approval_metric، test_backup_stale_marker، test_batch_approve، test_ledger_sot_gate، test_ready_to_approval_metric، test_waive_reviewed_diff) وستقف عائقاً أمام الدمج لأن git يرفض الكتابة فوق غير متتبَّع؛ وعشرة ملفات مؤقتة (_c5.txt، _o3..9.txt، _open_cards*.txt، _captured.txt وledger.py.bak_2026-10-02)؛ والباقي أدوات حقيقية غير مودَعة يشير إليها الكود: msg_counter.py (يحمل حدّ D-447م=300 وتذكره بطاقات COMMON)، doha_time.py، ledger_at_github.py، baseline_refresh.py ومعهما اختباراتهما، وأدوات preview.
- ledger/: flow_pump.off وflow_pump.out وflow_pump.stamp وpr_watch_state.json — حالة تشغيل؛ لا تُودَع ولا تُلمس (flow_pump.off يُبقي المضخّة متوقفة، ويجب أن يبقى كذلك طوال المزامنة).
- الجذر (54): مخلّفات عمل مؤقتة (a1_*، v2_*، prod_assign_*، *_latest.txt، wake_log.jsonl، msg_counter.json…) وبعض المذكرات (approval_naming_addendum…، brainstorm_v2_constraints…). تُصنَّف بيد 0101: أرشفة خارج المستودع أو .gitignore. لا حذف.

ج) الإيداعات المحلية الـ21 (b55d5c4..HEAD)

- 17 إيداعاً لوثائق 0102 (تقييم الفلو والأتمتة، SWOT، عصف العيادة والجدول، قراري الغياب…) — كل منها ملف واحد أو اثنان تحت docs/ وhandover_notes/؛ لا تتقاطع مع شيء في origin.
- 2 نسختان من PR‏ #91 وPR‏ #92 (92f1de8 وصنوه 05734e6): flow_pump.py وflow_pump_hook.py واختبارهما مطابقة لـorigin حرفياً (مفحوصة). هما سبب «التقدّم 21» الظاهر، ومحتواهما موجود في origin أصلاً؛ فتدخل الدمج بلا أثر.
- 1 إيداع ضخم bff6eba (44 ملفاً): دمج المواثيق المرحلة 2 وترقيم المجموعة 01 (role_cards ‏21 ملفاً، tools ‏32، tabs.json وsession_names.json). هذا هو المحتوى المحلي الحقيقي الوحيد في الكود.
- 1 إيداع 6dc9bac للمرحلة 2 (مذكرة + HTML).

د) الإيداعات البعيدة الـ22 (HEAD..origin/main)

PR‏ #71–#92 (2026-10-19→21): ‏machine_ops (#71)، ledger sot-stamp (#72)، classify_tree (#73)، تقرير الإيداعات (#74)، flow-eval (#75)، قياس جاهز←اعتماد (#76)، waive reviewed-diff (#77)، wake_monitor (#78 و#82)، مذكرة المراجعة الرجعية (#79)، BACKUP_FAILED (#80)، my_state (#81)، قاعدة COMMON السؤال المشترك (#83)، قائمة ما قبل جاهز وapproval_check ready (#84)، إنذار pr_watch (#85)، بوّابات الجاهزية (#86)، record_owner_confirmation --delegation (#87)، مضخّة التدفق (#88 و#89)، branch_triage (#90)، flow_pump_hook (#91)، flow_pump الدفع الآلي (#92). كلها أدوات واختبارات وبطاقتا 0301 و0501 وCOMMON.md؛ لا تلمس decisions.md ولا السجلّات.

## 2. التعارضات

أ) الثلاثة النصيّة (git merge-tree، قراءة فقط)

1. tools/approval_check.py — الجانب المحلي يخلو من فرع `ready`، وorigin أضاف (#84) الدالة ready_problem وخيار kind=ready وسطر --repo وأربعة أسطر في main(). الفرق الكلي بين HEAD وorigin في هذا الملف 27 سطراً كلها من جهة origin. الحل: يؤخذ ملف origin كاملاً (لا محتوى محلي ضائع). التحقق: `git diff HEAD origin/main -- tools/approval_check.py` يُظهر نفس الأسطر الـ27 فقط قبل الأخذ.
2. tools/push_watch.py — الاختلاف في الافتراضي by: المحلي "0701" (0702 مدمجة في 0701 وهي «رقم ميّت» حتى في validate_registry لدى origin) مقابل "0702". والمحلي أضاف استيراد session_alias والمعامل aliases في messages. وorigin أضاف branch_re وrequire_receipt (D-450م). الحل: اتحاد يدوي: توقيع origin (branch_re، require_receipt) مع by="0701" في scan وcycle وخيار --by، مع إبقاء aliases/session_alias المحلية. بعدها: grep لأيّ استدعاء لـpush_watch من flow_pump.py يمرّر by صراحةً، وتشغيل test_push_watch.
3. tools/render_role_cards.py — مولّد COMMON.md وبطاقات الأدوار. الجانب المحلي: حدّ الرسائل 300 (D-447م) وCOMMON_EXTRA وMERGED_LABELS ودوال الميثاق المدمج. الجانب البعيد: سطر AskUserQuestion الإلزامي (#83) وكتلة READY_GATE (#84) وحدّ 150. الحل: اتحاد: يُبقى سطر AskUserQuestion، وسطر الحدّ يُكتب بـ300 (بقرار المالك D-447م الأحدث)، وتُبقى READY_GATE والإضافات المحلية. ثم إعادة توليد role_cards وCOMMON.md بالمولّد (لأن COMMON.md يندمج نصّاً بلا تعارض لكنه قد لا يطابق خرج المولّد) وتشغيل test_render_role_cards.
   - متابعة دلالية: READY_GATE في origin مفتاحاه "0501" و"0301"؛ والمحلي أعاد ترقيم 01 (0301 صارت ميثاقاً مدمجاً/أُعيد استعمالها). يقرّر 0101 لمن يُسند سطر الشرط الخاص بـ0301 قبل الإيداع.

ب) تعارضات تظهر إن أُودعت نسخة العمل غير المودَعة قبل الدمج (أربعة أخرى)

اختبرت بإنشاء إيداع مؤقت (`git stash create`، كائن فقط بلا مرجع ولا مساس بالشجرة) ودمجه تجريبياً مع origin: يرتفع العدد من 3 إلى 7.

4. tools/record_owner_confirmation.py وtest_record_owner_confirmation.py — نسخة العمل سلَفٌ قديم لما في origin (origin فيه كل أسطر الشجرة و118 سطراً زائداً، والشجرة فيها سطران فقط ليسا في origin). الحل: يؤخذ origin كاملاً.
5. tools/wake_monitor.py وtest_wake_monitor.py — العكس: نسخة العمل = origin + 23 سطراً جديداً (aliases عبر session_alias، COUNTER_GUARD=260 لـD-447م، REWAKE_MIN=10، TEST_CHANNEL={0701,0301})، واختبار العمل يزيد 58 سطراً ويفقد 8 أسطر فقط هي اختبارات القيم القديمة (130 و4 جلسات). الحل: يؤخذ ملف العمل (فوق origin)، ويُراجع أن test_wake_monitor يمرّ ويحوي اختبارات #78/#82 كلها.
6. تناقض ترقيم يستوجب حسم 0101 قبل الإيداع: flow_watch/test_flow_watch يعتبران ميثاق 0301 مدمجاً في 0101، بينما my_state (COORDINATORS تضيف 0201 و0301) وwake_monitor وtest_package يعاملان 0301 جلسة حيّة للحوكمة. أحدهما قيد التعديل. لا أقترح حلّاً هنا لأن القرار حوكميّ.

## 3. ترقيم القرارات دون فقد أيّ قرار

الوقائع:
- decisions.md المودَع (HEAD وorigin) ينتهي عند D-332م، وآخر إيداع له 84ae36a (2026-10-10). origin لم يغيّره ولا غيّر decisions_meta.jsonl.
- نسخة العمل تضيف D-333م…D-453م. decision_add.py يحسب الرقم التالي بـmax(decisions.md)+1، فالترقيم تسلسليّ واحد ولا يوجد «ترقيمان». الظاهر من «D-453م مقابل D-332» هو أن الإيداع متأخر وليس تفرّعاً.
- قرارات بصيغة قسم `## D-444م … ## D-446م` (لا `- D-…`) داخل الملف، وD-447م…D-453م بصيغة السطر. D-444م وD-445م وD-446م موجودة فعلاً (ليست ثغرة).
- تكرارات معروفة: D-291م مكرَّر في HEAD أصلاً (قبل هذه المزامنة)؛ و«D-432م (ملحق)» و«D-433م (تصحيح)» بتصميم.
- decisions_meta.jsonl يحوي أسطراً إلى D-453م لكنه يخلو من معرّفات D-412م…D-443م الموجودة في decisions.md (فجوة تغطية، لا فقد قرار).

الإجراء المقترح:
1. إيداع decisions.md وdecisions_meta.jsonl وowner_confirmations.md وowner_orders_auto.md وboard_state.md وviolations.md كما هي (إيداع «سجلّات» أول، قبل أيّ دمج) — بلا إعادة ترقيم ولا تعديل نصّ قرار. بما أن origin لم يلمسها فلا تعارض.
2. تجميد إنشاء قرارات جديدة في أيّ شجرة أخرى حتى يصل هذا الإيداع إلى origin (وإلا ستحسب شجرة طازجة من origin الرقم D-333م وتتصادم). قرار D-453م يرفع تجميد الموجة 0 فقط، فلا يُفهم منه رفع هذا التجميد.
3. بعد الدمج: تشغيل `python tools/decisions_lint.py check` (قراءة) و`decision_add` لا يُستعمل. ثم قياس: عدد معرّفات `- D-` + أقسام `## D-` في decisions.md بعد الدمج = قبله (يُسجَّل الرقم قبل وبعد) ويبقى آخر معرّف D-453م.
4. فجوة decisions_meta (D-412م…D-443م): تُملأ بأمر من 0101 بسطور type مناسب (بقراءة نوع كلٍّ من نصّه) في إيداع لاحق منفصل، لا ضمن المزامنة، حتى لا يختلط الإصلاح بالنقل.
5. D-291م المكرَّر: يُترك؛ تغييره مخالف لقاعدة «لا تعديل لقرار قديم». يُذكر للمالك فقط.

## 4. تسلسل التنفيذ المقترح (بعد الاعتماد)

0. هدوء: التأكد من توقّف الجلسات الكاتبة في الشجرة (يوجد جلسة نشطة الآن).
1. نسخة أمان خارج المستودع: نسخ الملفات الستة السجلّية + `git status --porcelain` + `git diff` كاملاً + كل المسارات غير المتتبَّعة المهمّة إلى مجلد مؤرَّخ؛ وتدوين كائنات `git stash create`.
2. إيداع 1 (سجلّات): القرارات والدفتر والمذكرات والمهارات واللقطات المعتمدة. لا push.
3. نقل جانبي لما يعيق الدمج بلا حذف: إعادة تسمية الملفات الـ7 غير المتتبَّعة المطابقة لـorigin إلى `*.bak_2026-10-21`، واستعادة الـ7 المعدَّلة المطابقة وأخذ origin لـrecord_owner_confirmation (واختباره). (استعادة ملف مطابق لـorigin لا تفقد شيئاً؛ ومع ذلك يتم بعد الخطوة 1.)
4. إيداع 2 (تتمة دمج 01): أدوات القسم 1.أ «حقيقية» + الأدوات غير المتتبَّعة المرجعية (msg_counter.py وdoha_time.py وledger_at_github.py وbaseline_refresh.py واختباراتها) بعد قرار 0101 في التناقض 6.
5. `git merge origin/main` (دمج لا إعادة تأسيس، فالإيداعات المحلية لم تُدفع). حلّ الثلاثة وفق القسم 2.
6. تحقّق: `python -m pytest tools -q` كاملة، render_role_cards ثم فرق COMMON.md فارغ، validate_registry، decisions_lint، `approval_check.py ready - --repo .` بعد إيصال prepush، وبقاء ledger/flow_pump.off.
7. التسليم لـ0101 مع نتائج الاختبار. الدفع (عبر الفلو المعتاد: فرع/طلب، لا دفع مباشر لـmain) بعد اعتماد 0101 والمالك فقط.

التراجع: كل خطوة إيداع محلية؛ العودة إلى ORIG_HEAD أو إلى bff6eba (أصل الإيداع المحلي) ومعه نسخة الأمان.

## 5. ما لم أفعله

لم أنفّذ دمجاً ولا دفعاً ولا checkout ولا reset ولا حذفاً، ولم أودع شيئاً، ولم أعدّل ledger/flow_pump.off. الأدوات المستعملة للفحص قراءة فقط (git status/log/diff/show، merge-tree، stash create لكائنٍ بلا مرجع) ونسخٌ مؤقتة في مجلد الجلسة المؤقت. الملف الوحيد المضاف في المستودع هو هذا الملف (غير متتبَّع).
