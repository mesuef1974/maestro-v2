"""machine_ops — قياسُ الجهاز قبل/بعد (W-20261017-022، المرحلة 1: قراءةٌ فقط).

نسخةٌ معزولة من منطق القياس في MonitorWidget؛ لا تكتب في مجلّد الأصل ولا في monitor.db، ولا تشغّل فعلاً مغيِّراً.
الأوامر (من مجلّد tools):
    python -m machine_ops snapshot --label قبل --out ../docs/machine_ops/before.json
    python -m machine_ops snapshot --label بعد --out ../docs/machine_ops/after.json
    python -m machine_ops report ../docs/machine_ops/before.json ../docs/machine_ops/after.json
    python -m machine_ops history --db <monitor.db> --hours 24
المرحلة 2 (أفعالٌ منعكسة بقائمةٍ بيضاء) لا تبدأ إلا بعد اعتماد المالك لهذه المرحلة.
"""
