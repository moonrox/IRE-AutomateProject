<#
.SYNOPSIS
    PowerShell wrapper around scaffold.py — create a new IRE project or sync an
    existing one to the current template.

.DESCRIPTION
    Thin, faithful forwarder to `python scaffold.py`. All real logic lives in
    scaffold.py; this wrapper only maps friendly PowerShell parameters to the
    Python CLI so the documented `.\ire-scaffold.ps1` commands work.

.PARAMETER Mode
    New (default) or Sync.

.PARAMETER Name
    (New) Project/folder name; rendered into all template files.

.PARAMETER Description
    (New) Short description written into README and pyproject.toml.

.PARAMETER CreateFolder
    (New, optional) Pre-create this folder under -Output before scaffolding.

.PARAMETER Output
    (New) Parent directory for the new project. Default: C:\scripts\ai_scripts.

.PARAMETER Path
    (Sync) Existing project directory to bring up to the current template.

.PARAMETER NoVenv
    (New) Skip .venv creation.

.PARAMETER Force
    Overwrite existing/changed files (New: scaffold into existing dir;
    Sync: overwrite files that differ from the template).

.PARAMETER DryRun
    (Sync only) Preview changes without writing any files.

.EXAMPLE
    .\ire-scaffold.ps1 -Mode New -Name IRE-Alerts -Description "Alert routing" -CreateFolder IRE-Alerts

.EXAMPLE
    .\ire-scaffold.ps1 -Mode Sync -Path C:\scripts\ai_scripts\IRE-Observability -DryRun
#>
[CmdletBinding()]
param(
    [ValidateSet("New", "Sync")]
    [string]$Mode = "New",

    [string]$Name,
    [string]$Description,
    [string]$CreateFolder,
    [string]$Output = "C:\scripts\ai_scripts",
    [string]$Path,

    [switch]$NoVenv,
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scaffold = Join-Path $PSScriptRoot "scaffold.py"
if (-not (Test-Path $scaffold)) {
    throw "scaffold.py not found next to this script: $scaffold"
}

$pyArgs = New-Object System.Collections.Generic.List[string]

if ($Mode -eq "Sync") {
    if (-not $Path) { throw "-Path is required in Sync mode." }
    $pyArgs.Add("--sync"); $pyArgs.Add($Path)
    if ($DryRun) { $pyArgs.Add("--dry-run") }
    if ($Force)  { $pyArgs.Add("--force") }
}
else {
    if (-not $Name)        { throw "-Name is required in New mode." }
    if (-not $Description) { throw "-Description is required in New mode." }

    $pyArgs.Add($Name)
    $pyArgs.Add($Description)

    $forceNeeded = [bool]$Force
    if ($CreateFolder) {
        $target = Join-Path $Output $CreateFolder
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        # Pre-created dir means scaffold.py needs an explicit exact target + force.
        $pyArgs.Add("--path"); $pyArgs.Add($target)
        $forceNeeded = $true
    }
    else {
        $pyArgs.Add("--output"); $pyArgs.Add($Output)
    }

    if ($NoVenv)      { $pyArgs.Add("--no-venv") }
    if ($forceNeeded) { $pyArgs.Add("--force") }
}

Write-Host "python `"$scaffold`" $($pyArgs -join ' ')" -ForegroundColor DarkGray
& python $scaffold @pyArgs
exit $LASTEXITCODE
