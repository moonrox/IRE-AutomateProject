# IRE Project Tracking - SharePoint List Script
# Uses Microsoft Graph API to read and write the IRE Project Tracking list
#
# Usage:
#   .\IRE-SharePoint.ps1 -Action GetItems
#   .\IRE-SharePoint.ps1 -Action CreateItem -Title "My Project" -Priority "High" -Status "New" -Segment "Network"
#   .\IRE-SharePoint.ps1 -Action DeleteItem -ItemId 11

param(
    [ValidateSet("GetItems","CreateItem","DeleteItem","GetToken")]
    [string]$Action = "GetItems",

    # CreateItem params
    [string]$Title,
    [ValidateSet("High","Normal","Low")]
    [string]$Priority = "Normal",
    [ValidateSet("New","In progress","Blocked","Completed")]
    [string]$Status = "New",
    [ValidateSet("Network","Compute","Cloud","Storage","")]
    [string]$Segment = "",
    [ValidateSet("Analysis","Planning","Execution","Closure","")]
    [string]$Projectphase = "",
    [string]$ProjectSummaryDetails = "",
    [bool]$ManagerReview = $false,

    # DeleteItem params
    [string]$ItemId
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
$CLIENT_ID = $env:DEV_CLIENT_ID
$TENANT_ID = $env:DEV_TENANT_ID
$SITE_ID   = $env:SITE_ID
$LIST_ID   = $env:LIST_ID

foreach ($var in @{CLIENT_ID=$CLIENT_ID; TENANT_ID=$TENANT_ID; SITE_ID=$SITE_ID; LIST_ID=$LIST_ID}.GetEnumerator()) {
    if (-not $var.Value) { throw ".env is missing required key: $($var.Key)" }
}
$REFRESH_FILE = "$env:APPDATA\IRE-graph_refresh.bin"   # DPAPI-encrypted

function Invoke-GraphRequest {
    param([string]$Uri, [string]$Method = "GET", [string]$Token, [hashtable]$Body)
    $h = @{ Authorization = "Bearer $Token" }
    if ($Body) {
        $json  = $Body | ConvertTo-Json -Depth 3 -Compress
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
        $req   = [System.Net.HttpWebRequest]::Create($Uri)
        $req.Method        = $Method
        $req.ContentType   = "application/json"
        $req.ContentLength = $bytes.Length
        $req.Headers.Add("Authorization", "Bearer $Token")
        $s = $req.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
        $resp    = $req.GetResponse()
        $content = (New-Object System.IO.StreamReader($resp.GetResponseStream())).ReadToEnd()
        $resp.Close()
        return $content | ConvertFrom-Json
    }
    return Invoke-RestMethod -Uri $Uri -Headers $h -Method $Method
}

function Protect-Token([string]$plaintext) {
    $bytes     = [System.Text.Encoding]::UTF8.GetBytes($plaintext)
    $encrypted = [System.Security.Cryptography.ProtectedData]::Protect(
        $bytes, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    return [Convert]::ToBase64String($encrypted)
}

function Unprotect-Token([string]$base64) {
    $encrypted = [Convert]::FromBase64String($base64)
    $bytes     = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $encrypted, $null, [System.Security.Cryptography.DataProtectionScope]::CurrentUser)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Get-GraphToken {
    Add-Type -AssemblyName System.Security

    # Try refresh token first (DPAPI-encrypted)
    if (Test-Path $REFRESH_FILE) {
        try {
            $refresh = Unprotect-Token (Get-Content $REFRESH_FILE)
            $r = Invoke-RestMethod -Method POST `
                -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/token" `
                -ContentType "application/x-www-form-urlencoded" `
                -Body @{
                    client_id     = $CLIENT_ID
                    grant_type    = "refresh_token"
                    refresh_token = $refresh
                    scope         = "https://graph.microsoft.com/Sites.ReadWrite.All"
                }
            $r.access_token | Set-Content $TOKEN_FILE
            Protect-Token $r.refresh_token | Set-Content $REFRESH_FILE
            return $r.access_token
        } catch { }
    }

    # Device code flow
    $dc = Invoke-RestMethod -Method POST `
        -Uri "https://login.microsoftonline.com/$TENANT_ID/oauth2/v2.0/devicecode" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{ client_id = $CLIENT_ID; scope = "https://graph.microsoft.com/Sites.ReadWrite.All offline_access" }

    Write-Host "`n===========================================" -ForegroundColor Cyan
    Write-Host "Go to: $($dc.verification_uri)" -ForegroundColor Yellow
    Write-Host "Enter code: $($dc.user_code)" -ForegroundColor Yellow
    Write-Host "===========================================" -ForegroundColor Cyan
    Write-Host "Waiting for sign-in..." -ForegroundColor Gray

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
        } catch { }
    }
    throw "Authentication timed out."
}

# Get token
$token = Get-GraphToken
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
$baseUrl = "https://graph.microsoft.com/v1.0/sites/$SITE_ID/lists/$LIST_ID/items"

switch ($Action) {

    "GetItems" {
        Write-Host "`nFetching all items from IRE Project Tracking..." -ForegroundColor Cyan
        $result = Invoke-RestMethod -Uri "$baseUrl`?expand=fields&`$orderby=fields/Created desc" -Headers $headers
        Write-Host "Total items: $($result.value.Count)`n" -ForegroundColor Green
        $result.value | ForEach-Object {
            $f = $_.fields
            Write-Host "[$($_.id)] $($f.Title)" -ForegroundColor White
            Write-Host "  Status: $($f.Status) | Priority: $($f.Priority) | Segment: $($f.Segment)"
            Write-Host "  Phase:  $($f.Projectphase) | Manager Review: $($f.ManagerReview)"
            if ($f.ProjectSummaryDetails) { Write-Host "  Notes:  $($f.ProjectSummaryDetails)" }
            Write-Host ""
        }
    }

    "CreateItem" {
        if (-not $Title) { throw "Title is required for CreateItem." }
        Write-Host "`nCreating item: '$Title'..." -ForegroundColor Cyan
        $created = Invoke-GraphRequest -Uri $baseUrl -Method POST -Token $token -Body @{
            Title                 = $Title
            Priority              = $Priority
            Status                = $Status
            Segment               = $Segment
            Projectphase          = $Projectphase
            ManagerReview         = $ManagerReview
            ProjectSummaryDetails = $ProjectSummaryDetails
        }
        Write-Host "✅ Created! ID: $($created.id) | Title: $($created.fields.Title)" -ForegroundColor Green
    }

    "DeleteItem" {
        if (-not $ItemId) { throw "ItemId is required for DeleteItem." }
        # Fetch item title so user knows exactly what they're deleting
        $item = Invoke-RestMethod -Uri "$baseUrl/$ItemId`?expand=fields" -Headers $headers
        $title = $item.fields.Title
        Write-Host "`n⚠️  About to permanently delete:" -ForegroundColor Yellow
        Write-Host "   ID:    $ItemId" -ForegroundColor White
        Write-Host "   Title: $title" -ForegroundColor White
        $confirm = Read-Host "`nType YES to confirm"
        if ($confirm -ne "YES") { Write-Host "❌ Cancelled." -ForegroundColor Red; exit 0 }
        Invoke-RestMethod -Uri "$baseUrl/$ItemId" -Method DELETE -Headers $headers | Out-Null
        Write-Host "✅ Deleted item ID $ItemId" -ForegroundColor Green
    }

    "GetToken" {
        Write-Host "✅ Token refreshed and saved." -ForegroundColor Green
    }
}
