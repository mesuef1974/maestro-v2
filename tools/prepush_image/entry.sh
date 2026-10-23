#!/bin/sh
# نسخةٌ من الشجرة المركّبة للقراءة إلى قرص الحاوية (أسرع من الربط على ويندوز، وتسمح بكتابة الذاكرات المؤقتة)، ثمّ prepush.
# مصدرُ git: مجلّد .git الرئيس مركّبٌ للقراءة فقط عند /gitmain؛ ولا يُكتب شيءٌ في المستودع أو الشجرة الأصلية.
set -e
mkdir /tmp/work
cd /src
tar --exclude=./.git --exclude=./.venv --exclude=./node_modules --exclude=./.mypy_cache --exclude=./.ruff_cache \
    --exclude=./.pytest_cache -cf - . | tar -xf - -C /tmp/work
cd /tmp/work
exec python /runner/run_prepush.py "$@"
