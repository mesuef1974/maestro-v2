<#
  حارسُ ذاكرة الجهاز — يفحص كلَّ 5 دقائق ولا يتصرّف إلا حين ينخفض «المتاح» تحت العتبة.
  الأصلُ: عرضٌ فقط (DryRun). التنفيذُ بـ -Apply. لا يمسّ claude ولا code ولا docker ولا postgres ولا svchost ولا MsMpEng.
  ويسجّل **نسبةَ الالتزام (Commit%)** أيضاً: هي الخطرُ الحقيقيّ (فوق ~95% تفشل التخصيصاتُ) ولا يخفضها تقليصُ الذاكرة.
  (مراجعةُ 0105 الأمنيّة 2026-10-03 طُبّقت: المتاحُ لا FreePhysicalMemory، عيّنتان للخمول، قائمةُ حاوياتٍ ضيّقة، conhost بإذنٍ صريح، تدويرُ السجلّ.)

  الإجراءاتُ حين Available < Threshold (GB):
    1) docker stop لحاويات خوادم الجلسات الخاملة فقط (لا حذف؛ يُعاد تشغيلُها بـ docker start):
       الاسمُ ^schoolos-(?!main-preview)[a-z0-9]+-(web|worker)-1$ وخاملةٌ CPU ≤ 1% في **عيّنتين بينهما 10 ثوانٍ معاً**.
    2) إنهاءُ conhost يتيمٍ — **معطَّلٌ إلا بـ -KillOrphanConhost** (قد يقطع عمليّةً طويلةً متّصلةً به؛ شغّلِ DryRun أياماً وراجع السجلّ أوّلاً):
       أبوه ميّتٌ، وعمرُه > 10 دقائق، ولا عمليّةَ حيّةً أبوها هو.
  لا تقليصَ لـWorkingSet. السجلّ: $env:USERPROFILE\.claude\logs\memory_guard.log (يُدوَّر عند 1MB).

  التركيب (بإذن المالك وحدَه — لا يُركَّب تلقائيّاً)، بحسب مراجعة 0105:
    1) انسخ الملفَّ إلى مجلّدٍ لا تكتب فيه جلسةٌ: C:\ProgramData\SchoolOS\ (كتابةٌ للمدير فقط، قراءةٌ وتنفيذٌ للمستخدم).
    2) سجّل SHA256 (Get-FileHash) في ملاحظةٍ عند المالك؛ والتجزئةُ المخزَّنةُ بجواره بلا فائدة.
    3) مهمّةٌ بحساب المالك LIMITED (لا SYSTEM ولا Highest) ومسارٍ كاملٍ لـpwsh:
       schtasks /Create /SC MINUTE /MO 5 /TN "SchoolOS-MemoryGuard" /RL LIMITED /TR "\"C:\Program Files\PowerShell\7\pwsh.exe\" -NoProfile -File C:\ProgramData\SchoolOS\device_memory_guard.ps1"
       (بلا -Apply أسبوعاً أوّلاً؛ ثمّ يُقرَّر التطبيقُ من السجلّ)
    الإزالة: schtasks /Delete /TN "SchoolOS-MemoryGuard" /F
#>
param(
  [double]$Threshold = 2.5,        # GB «متاحة» (Available MBytes)؛ تحتها يتصرّف
  [switch]$Apply,
  [switch]$KillOrphanConhost
)

$ErrorActionPreference = "Continue"
$log = Join-Path $env:USERPROFILE ".claude\logs\memory_guard.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 1MB)) { Move-Item $log "$log.1" -Force }
$stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

function Get-CommitPct { $m = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory; [math]::Round(100 * $m.CommittedBytes / $m.CommitLimit, 1) }
function Get-AvailGB { [math]::Round((Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory).AvailableMBytes / 1024, 2) }
$availGB = Get-AvailGB
$actions = @()

if ($availGB -lt $Threshold) {
  # (1) حاويات خوادم جلساتٍ خاملة — عيّنتان بينهما 10 ث
  $pattern = '^schoolos-(?!main-preview)[a-z0-9]+-(web|worker)-1$'
  $s1 = docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}" 2>$null
  Start-Sleep -Seconds 10
  $s2 = docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}" 2>$null
  $cpu2 = @{}; foreach ($r in $s2) { $n, $c = $r -split "\|"; $cpu2[$n] = [double]($c -replace '%','') }
  foreach ($r in $s1) {
    $n, $c = $r -split "\|"
    if ($n -match $pattern -and ([double]($c -replace '%','')) -le 1.0 -and $cpu2.ContainsKey($n) -and $cpu2[$n] -le 1.0) {
      $actions += "docker stop $n"
      if ($Apply) { docker stop $n 2>$null | Out-Null }
    }
  }
  # (2) conhost يتيم — معطَّلٌ افتراضيّاً
  if ($KillOrphanConhost) {
    $alive = @{}; Get-Process | ForEach-Object { $alive[$_.Id] = $true }
    $all = Get-CimInstance Win32_Process
    $hasChild = @{}; $all | ForEach-Object { $hasChild[[int]$_.ParentProcessId] = $true }
    $orphans = $all | Where-Object { $_.Name -eq 'conhost.exe' -and -not $alive.ContainsKey([int]$_.ParentProcessId) -and
      ((Get-Date) - $_.CreationDate).TotalMinutes -gt 10 -and -not $hasChild.ContainsKey([int]$_.ProcessId) }
    foreach ($p in $orphans) {
      $actions += "conhost يتيم PID=$($p.ProcessId)"
      if ($Apply) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    }
  }
}

$mode = if ($Apply) { "APPLY" } else { "DRYRUN" }
$line = "$stamp [$mode] commit=$(Get-CommitPct)% available=${availGB}GB threshold=${Threshold}GB actions=$($actions.Count) after=$(Get-AvailGB)GB :: " + ($actions -join "; ")
Add-Content -Path $log -Value $line -Encoding UTF8
Write-Output $line
