#!/usr/bin/env bash
# PreToolUse (Bash|PowerShell) — نفسُ احتياط guard_git.sh (D:/shschool_mvp/.claude/hooks/guard_git.sh):
# مُشغِّلُ متجر ويندوز يخدع (python3 موجودٌ ولا يعمل)، فيُجرَّب أكثرُ من مُشغِّل قبل التسليم.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for py in python3 python "py -3"; do
  # shellcheck disable=SC2086
  if $py -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    exec $py "$here/maestro_git_scope.py"
  fi
done
echo "maestro_git_scope: لا بايثون 3.9+ يعمل — الخطّافُ غيرُ فعّالٍ في هذه الجلسة" >&2
exit 1
