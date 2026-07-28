# IRE Teams OneNote — WW Page Script
# Reads and writes to the notebook defined in .env (NOTEBOOK_NAME) in the IRE SharePoint site.
# Automatically finds or creates the current month section and WW page.
#
# Usage:
#   .\IRE-OneNote.ps1 -Action GetPage
#   .\IRE-OneNote.ps1 -Action AppendToPage -Content "<p>My update</p>"
#   .\IRE-OneNote.ps1 -Action CreatePage -Title "WW22" -Content "<h1>WW22</h1><p>Notes here</p>"
#   .\IRE-OneNote.ps1 -Action ListSections
#   .\IRE-OneNote.ps1 -Action GetToken
#
# NOTE: Requires IT admin approval of Notes.ReadWrite.All scope.
#       Submit request at https://login.microsoft.com/device and sign in.
#       You will receive an email when approved. Then re-run to authenticate.

param(
    [ValidateSet("GetPage","AppendToPage","CreatePage","ListSections","GetToken")]
    [string]$Action = "GetPage",

    [string]$Content,           # HTML content for AppendToPage / CreatePage
    [string]$Title,             # Page title override (default: current WW)
    [string]$SectionName,       # Section name override (default: current month/year)
    [string]$WorkWeek           # WW override e.g. "WW21" (default: current WW)
)

# ── Load .env ────────────────────────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $key, $val = $line -split '=', 2
        $key = $key.Trim(); $val = $val.Trim()
        if ($key -and -not [System.Environment]::GetEnvironmentVariable($key)) {
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

# ── Constants (all sourced from .env — see .env.example) ─────────────────────
$CLIENT_ID     = $env:DEV_CLIENT_ID
$TENANT_ID     = $env:DEV_TENANT_ID
$SITE_ID       = $env:SITE_ID
$NOTEBOOK_NAME = $env:NOTEBOOK_NAME
$SCOPE         = "https://graph.microsoft.com/Notes.ReadWrite.All https://graph.microsoft.com/Sites.ReadWrite.All offline_access"

foreach ($var in @{CLIENT_ID=$CLIENT_ID; TENANT_ID=$TENANT_ID; SITE_ID=$SITE_ID; NOTEBOOK_NAME=$NOTEBOOK_NAME}.GetEnumerator()) {
    if (-not $var.Value) { throw ".env is missing required key: $($var.Key)" }
}

$TOKEN_FILE   = "$env:APPDATA\IRE-onenote_token.txt"
$REFRESH_FILE = "$env:APPDATA\IRE-onenote_refresh.bin"

# ── Work Week Calculation (Intel WW: starts Sunday, WW1 contains Jan 1) ──────
function Get-IntelWorkWeek([datetime]$Date = (Get-Date)) {
    $jan1        = [datetime]"$($Date.Year)-01-01"
    $ww1Start    = $jan1.AddDays(-[int]$jan1.DayOfWeek)   # Sunday on or before Jan 1
    $weekNum     = [Math]::Floor(($Date - $ww1Start).TotalDays / 7) + 1
    return "WW$weekNum"
}

function Get-CurrentSectionName {
    return (Get-Date).ToString("MMMM yyyy")   # e.g. "May 2026"
}

# ── DPAPI token encryption ───────────────────────────────────────────────────
function Protect-Token([string]$plaintext) {
    Add-Type -AssemblyName System.Security
    $bytes     = [System.Text.Encoding]::UTF8.GetBytes($plaintext)
    $encrypted = [System.Security.Cryptography.ProtectedData]::Protect(
        $bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    return [Convert]::ToBase64String($encrypted)
}

function Unprotect-Token([string]$base64) {
    Add-Type -AssemblyName System.Security
    $encrypted = [Convert]::FromBase64String($base64)
    $bytes     = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $encrypted, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

# ── Authentication ───────────────────────────────────────────────────────────
function Get-GraphToken {
    # Try silent refresh first
    if (Test-Path $REFRESH_FILE) {
        try {
            $refresh = Unprotect-Token (Get-Content $REFRESH_FILE)
            $r = Invoke-RestMethod -Method POST `
                -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" `
                -ContentType "application/x-www-form-urlencoded" `
                -Body @{ client_id = $CLIENT_ID; grant_type = "refresh_token"; refresh_token = $refresh; scope = $SCOPE }
            $r.access_token | Set-Content $TOKEN_FILE
            Protect-Token $r.refresh_token | Set-Content $REFRESH_FILE
            return $r.access_token
        } catch { }
    }

    # Device code flow
    $dc = Invoke-RestMethod -Method POST `
        -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/devicecode" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{ client_id = $CLIENT_ID; scope = $SCOPE }

    Write-Host "`n===========================================" -ForegroundColor Cyan
    Write-Host "Go to: $($dc.verification_uri)" -ForegroundColor Yellow
    Write-Host "Enter code: $($dc.user_code)" -ForegroundColor Yellow
    Write-Host "===========================================" -ForegroundColor Cyan
    Write-Host "Waiting for sign-in..." -ForegroundColor Gray
    Write-Host "(IT admin must have approved Notes.ReadWrite.All first)" -ForegroundColor DarkGray

    $deadline = (Get-Date).AddSeconds($dc.expires_in)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $dc.interval
        try {
            $t = Invoke-RestMethod -Method POST `
                -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" `
                -ContentType "application/x-www-form-urlencoded" `
                -Body @{ client_id = $CLIENT_ID; grant_type = "urn:ietf:params:oauth:grant-type:device_code"; device_code = $dc.device_code }
            $t.access_token | Set-Content $TOKEN_FILE
            Protect-Token $t.refresh_token | Set-Content $REFRESH_FILE
            Write-Host "✅ Authenticated!" -ForegroundColor Green
            return $t.access_token
        } catch {
            $err = ($_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue).error
            if ($err -like "*admin_consent*" -or $err -like "*consent*") {
                Write-Host "`n❌ IT admin approval still pending for Notes.ReadWrite.All." -ForegroundColor Red
                Write-Host "   You'll receive an email when approved. Re-run this script then." -ForegroundColor Yellow
                exit 1
            }
        }
    }
    throw "Authentication timed out."
}

# ── HTTP helper (sends raw UTF-8 bytes, avoids encoding corruption) ──────────
function Invoke-GraphRaw {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [string]$Token,
        [string]$Body,
        [string]$ContentType = "application/json"
    )
    if ($Method -eq "GET" -or -not $Body) {
        return Invoke-RestMethod -Uri $Uri -Headers @{ Authorization = "Bearer $Token" } -Method $Method
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
    $req   = [System.Net.HttpWebRequest]::Create($Uri)
    $req.Method        = $Method
    $req.ContentType   = $ContentType
    $req.ContentLength = $bytes.Length
    $req.Headers.Add("Authorization", "Bearer $Token")
    $s = $req.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
    try {
        $resp    = $req.GetResponse()
        $content = (New-Object System.IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
        $resp.Close()
        if ($content) { return $content | ConvertFrom-Json }
    } catch [System.Net.WebException] {
        $errContent = (New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd()
        throw "HTTP $($_.Exception.Response.StatusCode): $errContent"
    }
}

# ── OneNote helpers ──────────────────────────────────────────────────────────
function Get-Notebook([string]$Token) {
    $result = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/notebooks" -Token $Token
    $nb = $result.value | Where-Object { $_.displayName -eq $NOTEBOOK_NAME }
    if (-not $nb) {
        $names = ($result.value | ForEach-Object { $_.displayName }) -join ", "
        throw "Notebook '$NOTEBOOK_NAME' not found. Available: $names"
    }
    return $nb
}

function Get-OrCreateSection([string]$Token, [string]$NotebookId, [string]$Name) {
    $sections = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/notebooks/$NotebookId/sections" -Token $Token
    $section  = $sections.value | Where-Object { $_.displayName -eq $Name }
    if ($section) {
        Write-Host "  Section '$Name' found." -ForegroundColor DarkGray
        return $section
    }
    Write-Host "  Section '$Name' not found — creating..." -ForegroundColor Yellow
    $newSection = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/notebooks/$NotebookId/sections" `
        -Method POST -Token $Token -Body "{`"displayName`":`"$Name`"}"
    Write-Host "  ✅ Created section '$Name'" -ForegroundColor Green
    return $newSection
}

function Get-OrCreatePage([string]$Token, [string]$SectionId, [string]$PageTitle, [string]$InitialHtml = "") {
    $pages = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/sections/$SectionId/pages" -Token $Token
    $page  = $pages.value | Where-Object { $_.title -eq $PageTitle }
    if ($page) {
        Write-Host "  Page '$PageTitle' found. ID: $($page.id)" -ForegroundColor DarkGray
        return $page
    }
    Write-Host "  Page '$PageTitle' not found — creating..." -ForegroundColor Yellow
    $html = if ($InitialHtml) { $InitialHtml } else {
        "<!DOCTYPE html><html><head><title>$PageTitle</title></head><body><h1>$PageTitle</h1><p>Created $(Get-Date -Format 'yyyy-MM-dd HH:mm')</p></body></html>"
    }
    $newPage = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/sections/$SectionId/pages" `
        -Method POST -Token $Token -Body $html -ContentType "text/html"
    Write-Host "  ✅ Created page '$PageTitle'" -ForegroundColor Green
    return $newPage
}

# ── Main ─────────────────────────────────────────────────────────────────────
$token       = Get-GraphToken
$wwLabel     = if ($WorkWeek)    { $WorkWeek }    else { Get-IntelWorkWeek }
$sectionLabel = if ($SectionName) { $SectionName } else { Get-CurrentSectionName }

Write-Host "`nNotebook : $NOTEBOOK_NAME" -ForegroundColor Cyan
Write-Host "Section  : $sectionLabel"
Write-Host "Page     : $wwLabel`n"

switch ($Action) {

    "GetToken" {
        Write-Host "✅ Token refreshed and cached." -ForegroundColor Green
    }

    "ListSections" {
        $nb = Get-Notebook $token
        Write-Host "Sections in '$NOTEBOOK_NAME':" -ForegroundColor Cyan
        $sections = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/notebooks/$($nb.id)/sections" -Token $token
        $sections.value | ForEach-Object {
            Write-Host "  $($_.displayName) | ID: $($_.id)"
        }
    }

    "GetPage" {
        $nb      = Get-Notebook $token
        $section = Get-OrCreateSection $token $nb.id $sectionLabel
        $page    = Get-OrCreatePage $token $section.id $wwLabel

        Write-Host "`nFetching page content..." -ForegroundColor Cyan
        $content = Invoke-RestMethod `
            -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/pages/$($page.id)/content" `
            -Headers @{ Authorization = "Bearer $token" }
        Write-Host "`n--- Page HTML ---" -ForegroundColor DarkGray
        Write-Host $content
        Write-Host "--- End ---`n" -ForegroundColor DarkGray
    }

    "AppendToPage" {
        if (-not $Content) { throw "-Content is required for AppendToPage. Pass HTML e.g. '<p>My update</p>'" }
        $nb      = Get-Notebook $token
        $section = Get-OrCreateSection $token $nb.id $sectionLabel
        $page    = Get-OrCreatePage $token $section.id $wwLabel

        Write-Host "Appending to $wwLabel..." -ForegroundColor Cyan
        $patch = "[{`"target`":`"body`",`"action`":`"append`",`"content`":`"$($Content -replace '"','\"')`"}]"
        Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/pages/$($page.id)/content" `
            -Method PATCH -Token $token -Body $patch | Out-Null
        Write-Host "✅ Content appended to $sectionLabel > $wwLabel" -ForegroundColor Green
    }

    "CreatePage" {
        $pageTitle = if ($Title) { $Title } else { $wwLabel }
        $nb        = Get-Notebook $token
        $section   = Get-OrCreateSection $token $nb.id $sectionLabel

        $html = if ($Content) {
            "<!DOCTYPE html><html><head><title>$pageTitle</title></head><body>$Content</body></html>"
        } else {
            "<!DOCTYPE html><html><head><title>$pageTitle</title></head><body><h1>$pageTitle</h1><p>Created $(Get-Date -Format 'yyyy-MM-dd HH:mm') by IRE-OneNote.ps1</p></body></html>"
        }

        Write-Host "Creating page '$pageTitle' in '$sectionLabel'..." -ForegroundColor Cyan
        $newPage = Invoke-GraphRaw -Uri "https://graph.microsoft.com/v1.0/sites/$SITE_ID/onenote/sections/$($section.id)/pages" `
            -Method POST -Token $token -Body $html -ContentType "text/html"
        Write-Host "✅ Page created: $($newPage.links.oneNoteWebUrl.href)" -ForegroundColor Green
    }
}
