#!/bin/sh
# نسخةٌ من الشجرة المركّبة للقراءة إلى قرص الحاوية (أسرع من الربط على ويندوز، وتسمح بكتابة الذاكرات المؤقتة)، ثمّ prepush.
# مصدرُ git: مجلّد .git الرئيس مركّبٌ للقراءة فقط عند /gitmain؛ ولا يُكتب شيءٌ في المستودع أو الشجرة الأصلية.
set -e
mkdir /tmp/work
cd /src
tar --exclude=./.git --exclude=./.venv --exclude=./node_modules --exclude=./.mypy_cache --exclude=./.ruff_cache \
    --exclude=./.pytest_cache -cf - . | tar -xf - -C /tmp/work
cd /tmp/work
# شجرةُ منصّةٍ أقدمُ من أداة prepush (W-20261028-022): سكربتاتُ الجذر تُنسخ بلا استبدال لما في الشجرة نفسها
if [ -n "$PREPUSH_ROOT_SCRIPTS" ] && [ ! -f scripts/prepush_check.py ]; then mkdir -p scripts && cp -rn "$PREPUSH_ROOT_SCRIPTS"/. scripts/; fi
exec python /runner/run_prepush.py "$@"
