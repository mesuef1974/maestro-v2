---
name: maestro-evidence
description: |
  يولّد حزمةَ الأدلّة لطلبٍ (خطورةٌ من المسارات، فحوصٌ، سطرُ الاعتماد، أين يُعاين) ويحدّد ما لم يُقَس بعد بلا اختلاق أرقام.
  استخدمها عند: «حزمة أدلّة للطلب #N»، قبل إدراج طلبٍ في نافذة المراجعة، أو حين يسأل المالكُ «ما خطورتُه؟». Trigger on: evidence pack, risk tier, PR readiness.
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_work/tools/evidence_pack.py:*), Bash(python C:/Users/mesue/delivery_manager_work/tools/risk_tier.py:*), Bash(gh pr view:*), Read
---

# حزمةُ الأدلّة
1. `python C:/Users/mesue/delivery_manager_work/tools/evidence_pack.py <رقم>` — قراءةٌ فقط.
2. المراجعةُ: الخطورةُ (light/low/medium/high) والعلامات؛ الفحوصُ؛ سطرُ الاعتماد (غائبٌ ← **لا يدخل نافذةَ المراجعة كمعتمَد**).
3. ما يظهر «غيرُ مقيس» يبقى كذلك — **لا تُخترع أرقامٌ**؛ يُذكر في نافذة المراجعة أنّه غيرُ مقيسٍ آليّاً بعد (المرجع `docs/evidence_pack_spec.md`).
4. خطورةٌ عالية: اطلب من الجلسة المنفّذة ملخّصَ الهجرة (توسيع ثمّ تقليص، الرجوع، أثر PDPPL).
5. سجّل النتيجةَ في بطاقة السجلّ: `ledger.py move <id> ready_for_review`.

**حدود:** الأداةُ تصنّف بالمسارات فقط؛ التصنيفُ تقريبيّ ولا يغني عن حكم المنفّذ.
