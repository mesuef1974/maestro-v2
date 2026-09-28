---
name: maestro-archive-check
description: |
  يفحص أهليّة أرشفة جلسةٍ (لا طلبَ مفتوح، git cherry فارغ، لا ملفّات غير مودَعة، ليست دائمة، لا تعمل الآن، مذكّرةُ تسليمٍ محفوظة، لا شجرةَ مشتركة) ويُخرج سطرَ سببٍ للموافقة.
  استخدمها قبل أيّ طلب أرشفة. Trigger on: archive session, finished session, cleanup.
disable-model-invocation: true
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/archive_check.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/watch_once.py:*), Read
---

# فحصُ الأرشفة
الأرشفةُ في التطبيق **تُزيل الشجرةَ افتراضيّاً** وتُؤرشف الجلساتِ المشتركة لها ولا تُنفَّذ على جلسةٍ عاملةٍ أو مثبَّتةٍ أو مفتوحةٍ على الشاشة؛ وكلُّ استدعاءٍ بموافقة المالك.
1. `python C:/Users/mesue/delivery_manager_work/tools/archive_check.py <مجلّدُ الشجرة> --title "<عنوان الجلسة>" [--running] [--shared N]` (عدد الجلسات المشتركة من `list_sessions` بنفس cwd).
2. `eligible: false` ← **لا تطلب الأرشفة**؛ اعرض على المالك blockers.
3. `eligible: true` ← احفظ مذكّرةَ التسليم (`handover_notes/<شجرة>.md`) إن لم تكن، ثمّ اطلب الأرشفةَ ويكون **سببُ الموافقة = حقل reason** حرفيّاً.
4. أبلغ المالكَ بالقائمة وسببِ كلٍّ وطريقةِ العودة (`unarchive_session`)؛ لا حذفَ أبداً.
5. **لا أرشفةَ لجلسةٍ دائمة** (قيادة/مدخل/تمكين) **ولا لمسارٍ انتقاليّ** قبل حارسه الآليّ وموافقةِ المالك (`tabs.json: exit_rule`).

**حدود:** ما خارجَ مشروع المدرسة لا يُؤرشف إلا بأمر المالك باسم الجلسة؛ الأشجارُ اليتيمةُ بعملٍ غيرِ مدفوعٍ تُسأل عنها أنت قبل أيّ إجراء.
