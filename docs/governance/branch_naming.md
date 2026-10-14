# تسمية الفروع برمز البطاقة (R5، W-20261014-008)

- النمط: `claude/W-YYYYMMDD-NNN` أو `claude/W-YYYYMMDD-NNN-<وصف قصير>`.
- التحذير: غير حاجب حتى 2026-10-28 (قرار المالك 10-14)؛ ثم الإلزام بحارس منفصل بعمل 0103. هذه الأداة لا تحذف ولا تعيد تسمية ولا تحجب دفعاً.
- الدفع الصحيح بلا تحريك الرأس: `git push origin HEAD:refs/heads/claude/W-YYYYMMDD-NNN-<وصف>`.
- القياس: `python tools/branch_name_check.py --repo D:/shschool_mvp` (أو `--json`). الهدف: 95% من الفروع غير المستثناة لبطاقة حيّة قبل الإلزام.
- «حيّة» = بطاقة حالتها captured/verified/routed/in_progress/ready_for_review/notes/approved/pushed (يؤكد 0103). المستثنى: main وbackup* وrebuild/*.
- لا تنظيف آلي: الفروع غير المطابقة تُعرض فقط؛ التنظيف بقرار المالك وأداة R1 عند 0103.
