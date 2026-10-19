# فرز الـ97 إيداعاً غير المدفوعة على main المحلي — W-20261019-004 (0103، 2026-10-19)

تقريرٌ فقط: لا حذف ولا reset ولا لمس لـmain المحلي. المقاس: `git log origin/main..HEAD` في delivery_manager_work (قاعدة الانفراع 1c4f2e7e). الـ97 إيداعاً لمست 122 ملفاً؛ صُنّفت بمقارنة محتوى HEAD المحلي بـorigin/main لكل ملف.
الاحتياط قائم أصلاً: فرع claude/preserve-local-main-2026-10-19 يحمل الـ97 كلها (دُفع 2026-10-19).

## المجموعات
| المجموعة | العدد | الملفات | القرار | السبب |
|---|---|---|---|---|
| أ. مطابقة لما في origin | 86 | بطاقات الأدوار role_cards/*، وثائق docs/ لـ0102 و0403 (العصف والهوية والتوكنات وSWOT)، ملفات handover_notes/msg_*، أدوات branch_name_check وcleanup_guard وfloor_decomp وledger_stale وmemory_index_guard وmessage_length_guard وmy_state وprune_workspace وrecord_owner_confirmation وrender_role_cards وtoken_measure وurgent_ratio واختباراتها | يُهمل | محتواها في origin بالبايت نفسه (وصلت بطلبات أخرى)، فالإيداعات تاريخٌ فقط |
| ب. وثائق جديدة لـ0102 | 14 | docs/ (brainstorm_master_table وflex_sessions_lifecycle وflow_automation_audit_full وflow_bottleneck_* وflow_codified_swot وpreview_8500_bottleneck_report وrisk_tiers_policy_draft وswot_0502_snapshots_identity وswot_all_sessions_flow وurgent_bottleneck_brainstorm) + handover_notes (flow_automation_audit وledger_improvement_brainstorm وsession_reduction_brainstorm) | يُدفع كطلب وثائق واحد (خطورة منخفضة) | ليست في origin ولا طلب لها؛ وثائقُ قرارٍ ومرجعٌ يحتاجها 0101 |
| ج. أدوات جديدة | 5 | tools/lang_guard.py وtest_lang_guard.py وlang_guard.mode، tools/unblock_request.py، tools/test_ledger_origin_guard.py | يُدفع كطلب أدوات منفصل بعد تشغيل اختباراتها (يلزمها اعتماد رأس) | أدواتٌ لم تدخل origin؛ lang_guard.mode يغيّر سلوك حارس اللغة فيُراجع قبل التفعيل |
| د. تعديلات محلية على ملفات عدّلها origin أيضاً | 5 | tools/approval_check.py، ledger.py، pr_watch.py، session_identity.py، test_approval_head_binding.py | تُراجع واحداً واحداً (دمج ثلاثي) | الغالب أنّ أثرها دخل مع H1/H2/H3/H5 (#53) فتُهمل، وما بقي يُدمج يدوياً |
| هـ. تعديلات محلية فقط (origin لم يمسّها) | 7 | flow_changelog.md، role_cards/COMMON.md، tools/identity_ack.py وidentity_guard.py وtest_identity_guard.py وwatch_once.py، violations.md | يُدفع كطلب (الأدوات والبطاقات) بعد اعتماد رأس | عملٌ فعليّ لم يُدفع؛ violations.md الحيّ يُحدَّث من النسخة المرجعية لا من الإيداع |
| و. ملفات حُذفت محلياً | 2 | publish_digest/331f3ae6.md وlatest.md | يُهمل | موجودة في origin وتُولَّد آلياً؛ الحذف المحلي عارض |
| ز. تغييرات في origin فقط | 3 | tools/pr_open_prep.py وpublish_sync.py وtest_publish_sync.py | لا إجراء | المحلي كالقاعدة؛ origin أحدث |

## النتيجة
المطلوب فعلاً أن يصل إلى origin: المجموعة ب (طلب وثائق) والمجموعتان ج وهـ (طلبا أدوات/بطاقات بعد اعتماد) وما يبقى من د بعد المراجعة. الباقي (أ وو وز) 91 ملفاً من أصل 122 لا يحتاج شيئاً.
فرع 0502 القديم claude/0502-admin-shell-baseline المبنيّ على main المحلي يبقى بلا طلب (بتعليمة 0101).

## ما ينتظر قرار المالك بعد التقرير
1. دفع المجموعات ب وج وهـ كطلبات (بالترتيب أعلاه).
2. إعادة main المحلي إلى origin/main: لا تتمّ إلا بعد دفع ما يستحق الدفع، وهي reset تحتاج إذنه الصريح (GUARD_GIT_ALLOW).
