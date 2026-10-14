# تسجيلُ تقليمٍ أسبوعيّ لمخلّفات العمل وقواعدِ الجلسات (W-20261014-028) — يعمل بلا Claude فلا توكنز.
# التشغيلُ مرّةً واحدة من PowerShell بيد المالك:  powershell -ExecutionPolicy Bypass -File scripts_for_owner\register_weekly_prune.ps1
# الإزالة: Unregister-ScheduledTask -TaskName SchoolOS-WeeklyPrune -Confirm:$false
$root = Split-Path -Parent $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "python" -Argument "-X utf8 tools\prune_workspace.py --apply" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At "06:00"
Register-ScheduledTask -TaskName "SchoolOS-WeeklyPrune" -Action $action -Trigger $trigger -Description "تقليم evidence وtmp_reports وقواعد الجلسات اليتيمة (prune_workspace.py --apply)"
