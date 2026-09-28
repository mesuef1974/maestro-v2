---
name: maestro-intake
description: |
  يحوّل أيَّ مدخلٍ (كلامُ المالك، بلاغ، بندُ خارطة، تنبيه، اكتشافٌ من جلسة) إلى بطاقةٍ في السجلّ بمواصفةٍ من أربعة أسطر، مع إلغاء التكرار وتصنيف الاستعجال.
  استخدمها عند: كلّ طلبٍ جديدٍ من المالك، أو «سجّل هذه»، أو حين تبلغ جلسةٌ باكتشاف. Trigger on: new task, intake, discovery, expedite.
allowed-tools: Bash(python C:/Users/mesue/delivery_manager_v2_work/tools/ledger.py:*), Bash(python C:/Users/mesue/delivery_manager_v2_work/tools/routing.py:*), Bash(gh pr list:*), Read
---

# الالتقاط
1. المرجعُ: `C:/Users/mesue/delivery_manager_v2_work/docs/intake_and_discovery.md`.
2. **إلغاءُ التكرار:** `gh pr list --state open` وبنودُ الخارطة وبطاقاتُ `ledger.py list`؛ التطابقُ ← ضمٌّ لا بطاقةٌ جديدة.
3. اكتب أسطرَه الأربعة (مشكلة، أثر، ملفّاتٌ مظنونة، معيارُ قبول) ≤240 حرفاً لكلّ سطر، **بلا نصٍّ خامٍّ لرسالة مستخدمٍ ولا أسماءَ ولا أرقامَ شخصيّة** (الأداةُ ترفضها).
4. `python C:/Users/mesue/delivery_manager_v2_work/tools/ledger.py add --source <owner|intake|roadmap|kpi_guard|alert|advisor|repo_keeper|discovery> --type <نوعُ المشكلة> --problem … --impact … --accept … [--files …] [--urgent]`.
5. **اكتشاف:** من يجد عيباً أثناء عمله لا يصلحه خارج نطاقه — يسجّل بطاقةَ `discovery`. S1/S2 ← استعجالٌ (واحدٌ في وقتٍ واحد)؛ غيرُه ← الطابورُ العاديّ.
6. بلّغ المالكَ بسطرٍ: الرقمُ، الأثرُ، الجلسةُ المقترحة.

**حدود:** الاستعجالُ يتجاوز الدورَ لا بوّابةَ الاعتماد. بطاقةٌ ناقصةٌ تعود لمصدرها.
