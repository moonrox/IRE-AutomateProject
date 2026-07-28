<#
run_weekly.ps1 - Scheduled-task wrapper for the automated IRE weekly report.

Runs the multi-source weekly generator with the project's virtual-env Python,
logging output to weekly_reports\logs. Intended to be launched by the
"IRE-WeeklyStatus" scheduled task every Wednesday at 17:00.

Usage:
    .\run_weekly.ps1                 # current work week, upload + email
    .\run_weekly.ps1 -WW WW30        # specific work week
    .\run_weekly.ps1 -DryRun         # build only, no SharePoint/email
#>
param(
    [string]$WW,
    [switch]$DryRun,
    [switch]$NoUpload,
    [switch]$NoEmail
)

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$logDir = Join-Path $root "weekly_reports\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("run_weekly_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

$argsList = @((Join-Path $root "run_weekly.py"))
if ($WW)       { $argsList += @("--ww", $WW) }
if ($DryRun)   { $argsList += "--dry-run" }
if ($NoUpload) { $argsList += "--no-upload" }
if ($NoEmail)  { $argsList += "--no-email" }

$env:PYTHONIOENCODING = "utf-8"
Write-Host "Running weekly report -> $log"
& $python @argsList *>&1 | Tee-Object -FilePath $log
exit $LASTEXITCODE
