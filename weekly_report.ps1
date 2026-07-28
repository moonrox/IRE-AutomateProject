<#
.SYNOPSIS
    Generate and optionally post an IRE weekly status report to OneNote and/or email.

.DESCRIPTION
    Wrapper around weekly_report.py. Reads from the project registry,
    tracker DB, and file system, then writes a markdown report and
    optionally appends it to the current WW page in the IRE Teams notebook
    and/or emails it via Microsoft Graph.

    Configuration is read from a .env file in the same directory as this script.
    Copy .env.example to .env and fill in your values before first use.

.PARAMETER WW
    Work week to report on (default: current WW).
    Examples: WW24  or  WW24-2026

.PARAMETER Prev
    Report on the last completed work week (WW before current).

.PARAMETER Post
    Post the report to OneNote after generating it.

.PARAMETER Mail
    Email the report via Microsoft Graph (Mail.Send).
    Recipient is read from REPORT_MAIL_TO in .env, or override with -MailTo.

.PARAMETER MailTo
    Recipient address for -Mail. Overrides REPORT_MAIL_TO from .env.

.PARAMETER Out
    Override the output markdown file path.

.EXAMPLE
    .\weekly_report.ps1                    # current WW, markdown only
    .\weekly_report.ps1 -Prev              # last completed WW
    .\weekly_report.ps1 -Post              # current WW, post to OneNote
    .\weekly_report.ps1 -Mail              # current WW, email to REPORT_MAIL_TO
    .\weekly_report.ps1 -Post -Mail        # post to OneNote AND email
    .\weekly_report.ps1 -WW WW24 -Post     # WW24, post to OneNote
    .\weekly_report.ps1 -Mail -MailTo other@example.com
#>

[CmdletBinding()]
param(
    [string] $WW     = "",
    [switch] $Prev,
    [switch] $Post,
    [switch] $Mail,
    [string] $MailTo = "",
    [string] $Out    = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_DIR    = $PSScriptRoot
$REPORT_SCRIPT = Join-Path $SCRIPT_DIR "weekly_report.py"

# ── Find Python ────────────────────────────────────────────────────────────────
$venvPy = Join-Path $SCRIPT_DIR ".venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPy) {
    $venvPy
} else {
    $candidates = "python", "python3", "py"
    $found = $null
    foreach ($c in $candidates) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { $found = $c; break }
    }
    if (-not $found) { throw "Python 3.11+ not found. Create a venv at .venv or add Python to PATH." }
    $found
}

# ── Read REPORT_MAIL_TO from .env if -MailTo not explicitly provided ──────────
if (-not $MailTo) {
    $envFile = Join-Path $SCRIPT_DIR ".env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern '^REPORT_MAIL_TO=(.+)$'
        if ($match) { $MailTo = $match.Matches[0].Groups[1].Value.Trim() }
    }
}

# ── Build args ─────────────────────────────────────────────────────────────────
$pyArgs = [System.Collections.Generic.List[string]]@($REPORT_SCRIPT)

if ($Prev)          { $pyArgs.Add("--prev") }
elseif ($WW -ne "") { $pyArgs.AddRange([string[]]@("--ww", $WW)) }

if ($Post)          { $pyArgs.Add("--post") }
if ($Mail)          { $pyArgs.Add("--mail"); if ($MailTo) { $pyArgs.AddRange([string[]]@("--mail-to", $MailTo)) } }
if ($Out  -ne "")   { $pyArgs.AddRange([string[]]@("--out", $Out)) }

# ── Run ────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  IRE Weekly Report" -ForegroundColor Cyan
Write-Host "  Python : $pythonExe" -ForegroundColor DarkGray
Write-Host ""

& $pythonExe @pyArgs

if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    Write-Error "weekly_report.py exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}
