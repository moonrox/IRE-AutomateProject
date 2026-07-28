# Microsoft Graph API — SharePoint List Editing Guide

How to read and write a SharePoint list from a script using Microsoft Graph API,
with no app registration, no admin consent, and no Power Automate.

> This pattern was tested against Intel's M365 tenant using PowerShell 5.1 and Python 3.12.

---

## How It Works (Overview)

```
Your Script
    │
    ▼
Device Code Auth ──► Microsoft Identity Platform (login.microsoftonline.com)
                              │  OAuth 2.0 token (delegated, your identity)
                              ▼
                    Microsoft Graph API (graph.microsoft.com)
                              │
                              ▼
                    SharePoint Online List
                    (intel.sharepoint.com/sites/ire)
```

You authenticate **as yourself** (delegated auth). The script acts with your
permissions — no service account, no secret, no client certificate needed.

---

## Authentication Flow

### Step 1 — Device Code (first run only)

The script requests a device code from Microsoft Identity:

```
POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/devicecode
Body: client_id={clientId}&scope=https://graph.microsoft.com/Sites.ReadWrite.All offline_access
```

Response gives you a URL + short code. You visit the URL, enter the code, sign in
with your Microsoft 365 account. The script polls every few seconds until sign-in completes.

### Step 2 — Token Exchange

Once you sign in, the script exchanges the device code for tokens:

```
POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token
Body: client_id={clientId}&grant_type=urn:ietf:params:oauth:grant-type:device_code
      &device_code={deviceCode}
```

Returns:
- `access_token` — short-lived (~1 hour), used in every API call
- `refresh_token` — long-lived, used to silently get new access tokens

### Step 3 — Silent Refresh (all subsequent runs)

On each script run, if a refresh token is cached, it silently exchanges it for a new access token:

```
POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token
Body: client_id={clientId}&grant_type=refresh_token&refresh_token={savedRefreshToken}
      &scope=https://graph.microsoft.com/Sites.ReadWrite.All
```

No browser, no user interaction. Works even if the original access token expired.

### Token Storage (PowerShell script)

| File | Contents | Security |
|---|---|---|
| `%APPDATA%\IRE-graph_token.txt` | Access token (plaintext, short-lived) | User-only ACL |
| `%APPDATA%\IRE-graph_token.bin` | Refresh token | DPAPI-encrypted (Windows-user-only decrypt) |

The refresh token is encrypted with **Windows Data Protection API (DPAPI)**:
- Only your Windows login can decrypt it
- Survives reboots; tied to your Windows user profile
- Even admins cannot read it without your credentials

### Token Storage (Python script)

MSAL's `SerializableTokenCache` stores tokens in `.sp_token_cache.bin` (project folder).
This file is gitignored. MSAL handles refresh automatically.

---

## Client IDs (No App Registration Needed)

These are Microsoft's own public client IDs, pre-authorized in every M365 tenant.
No admin consent required for delegated `Sites.ReadWrite.All`.

| Client ID | App Name | Works at Intel |
|---|---|---|
| `14d82eec-204b-4c2f-b7e8-296a70dab67e` | Microsoft Graph PowerShell SDK | ✅ Confirmed |
| `1b730954-1685-4b74-9bfd-dac224a7b894` | Azure CLI | ✅ Confirmed |
| `1950a258-227b-4e31-a9cf-717495945fc2` | Azure PowerShell | ❌ Blocked by Intel |

---

## Discovering Site ID and List ID

### Get Site ID

```powershell
$token = "YOUR_ACCESS_TOKEN"
$h = @{ Authorization = "Bearer $token" }

# Replace with your SharePoint site URL
Invoke-RestMethod "https://graph.microsoft.com/v1.0/sites/intel.sharepoint.com:/sites/ire" -Headers $h |
    Select-Object id, displayName, webUrl
```

The `id` field is your Site ID, in the format:
```
intel.sharepoint.com,{siteCollectionId},{webId}
```

### Get List ID

```powershell
$siteId = "intel.sharepoint.com,07fb3b8a-...,fa48f83e-..."
Invoke-RestMethod "https://graph.microsoft.com/v1.0/sites/$siteId/lists" -Headers $h |
    Select-Object -ExpandProperty value |
    Select-Object id, displayName
```

### Discover List Columns

```powershell
$listId = "0bd155fa-92d1-4149-af8b-728a49ad95c6"
Invoke-RestMethod "https://graph.microsoft.com/v1.0/sites/$siteId/lists/$listId/columns" -Headers $h |
    Select-Object -ExpandProperty value |
    Where-Object { -not $_.readOnly -and -not $_.hidden } |
    Select-Object name, displayName, @{n="type";e={
        if ($_.text) {"text"} elseif ($_.choice) {"choice: $($_.choice.choices -join ', ')"} elseif ($_.boolean) {"boolean"} elseif ($_.personOrGroup) {"personOrGroup"} else {"other"}
    }}
```

---

## CRUD Operations

### READ — Get All Items

```powershell
$baseUrl = "https://graph.microsoft.com/v1.0/sites/$siteId/lists/$listId/items"

$result = Invoke-RestMethod "$baseUrl`?expand=fields&`$orderby=fields/Created desc" -Headers $h
$result.value | ForEach-Object { $_.fields }
```

### READ — Get Single Item

```powershell
Invoke-RestMethod "$baseUrl/12?expand=fields" -Headers $h | Select-Object -ExpandProperty fields
```

### READ — Filter Items

```powershell
# Items where Status = "New"
Invoke-RestMethod "$baseUrl`?expand=fields&`$filter=fields/Status eq 'New'" -Headers $h
```

### CREATE — New Item

The Graph API expects a `fields` wrapper for POST:

```powershell
$body = @{
    fields = @{
        Title                 = "My Project"
        Status                = "New"
        Priority              = "High"
        Segment               = "Network"
        Projectphase          = "Planning"
        ManagerReview         = $false
        ProjectSummaryDetails = "Initial notes here"
    }
} | ConvertTo-Json -Depth 3

Invoke-RestMethod $baseUrl -Method POST -Headers $h -Body $body
```

> ⚠️ **Unicode gotcha:** If your strings contain special characters (em dash `—`, smart quotes, etc.),
> `ConvertTo-Json` may corrupt them. Send as raw UTF-8 bytes instead:
>
> ```powershell
> $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
> $req = [System.Net.HttpWebRequest]::Create($url)
> $req.Method = "POST"; $req.ContentType = "application/json"; $req.ContentLength = $bytes.Length
> $req.Headers.Add("Authorization", "Bearer $token")
> $s = $req.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
> $resp = $req.GetResponse()
> ```

### UPDATE — Patch Fields

PATCH goes directly to `/fields` (no wrapper):

```powershell
$body = '{"Status":"In progress","Priority":"High"}'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)

$req = [System.Net.HttpWebRequest]::Create("$baseUrl/12/fields")
$req.Method = "PATCH"; $req.ContentType = "application/json"; $req.ContentLength = $bytes.Length
$req.Headers.Add("Authorization", "Bearer $token")
$s = $req.GetRequestStream(); $s.Write($bytes, 0, $bytes.Length); $s.Close()
$req.GetResponse() | Out-Null
```

### UPDATE — People/Person Field (AssignedTo)

People fields use a lookup ID, not an email address. You must resolve the user first:

```powershell
# 1. Look up the user's SharePoint ID from the site's User Information List
$users = Invoke-RestMethod "https://graph.microsoft.com/v1.0/sites/$siteId/lists/User Information List/items?expand=fields&`$top=200" -Headers $h
$johnId = ($users.value | Where-Object { $_.fields.EMail -eq "john.monroe@intel.com" }).id
# Returns: 13

# 2. Use that ID as AssignedtoLookupId (note: internal name NOT "AssignedToId")
$body = "{`"Assignedto0LookupId`":$johnId}"
# ... send as PATCH (see above)
```

> **Intel-specific lookup IDs (IRE Project Tracking list):**
> | Name | Email | LookupId |
> |---|---|---|
> | Monroe, John | john.monroe@intel.com | **13** |

### DELETE — Remove Item

```powershell
Invoke-RestMethod "$baseUrl/12" -Method DELETE -Headers $h
```

---

## IRE List — Field Reference

| Internal Name | Display Name | Type | Valid Values |
|---|---|---|---|
| `Title` | Title | Text | Any string |
| `Status` | Status | Choice | `New`, `In progress`, `Blocked`, `Completed` |
| `Priority` | Priority | Choice | `High`, `Normal`, `Low` |
| `Segment` | Segment | Choice | `Network`, `Compute`, `Cloud`, `Storage` |
| `Projectphase` | Project Phase | Choice | `Analysis`, `Planning`, `Execution`, `Closure` |
| `ManagerReview` | Manager Review | Boolean | `true` / `false` |
| `ProjectSummaryDetails` | Project Summary | Text | Free text |
| `Assignedto0LookupId` | Assigned To | PersonOrGroup (lookup) | Integer user ID |

---

## Python Usage (`sharepoint_sync.py`)

```python
import httpx

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# CREATE
resp = httpx.post(
    f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items",
    headers=_headers(token),
    json={"fields": {"Title": "My Project", "Status": "New", "Priority": "High"}},
    timeout=20
)
resp.raise_for_status()

# UPDATE
resp = httpx.patch(
    f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items/{item_id}/fields",
    headers=_headers(token),
    json={"Status": "In progress"},
    timeout=20
)
resp.raise_for_status()
```

Python's `httpx`/`requests` handle UTF-8 encoding correctly by default — no raw-bytes workaround needed.

---

## Security Notes

| Concern | Status | Notes |
|---|---|---|
| Secrets in code | ✅ None | Only public client IDs and internal site/list IDs |
| Refresh token encrypted | ✅ DPAPI | PowerShell: Windows-user-only decrypt |
| Token files gitignored | ✅ Yes | `*.bin`, `.sp_token_cache.bin` in `.gitignore` |
| Token in TEMP folder | ⚠️ Access token only | Short-lived (~1hr); plaintext but in user-scoped APPDATA |
| Scope breadth | ⚠️ `Sites.ReadWrite.All` | Broad — ideal would be `Sites.Selected` (requires IT admin) |
| Delete confirmation | ✅ Yes | Script prompts "Type YES to confirm" before deleting |
| IT admin access to tokens | ⚠️ Low risk | DPAPI refresh token tied to your Windows user; access token short-lived |

### To tighten scope further (optional — requires IT admin)
Ask your Azure AD admin to register an app with `Sites.Selected` permission scoped
only to `intel.sharepoint.com/sites/ire`. This limits blast radius if tokens are ever compromised.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `400 Bad Request` on PATCH | Special chars in JSON string | Use raw UTF-8 bytes (see Unicode gotcha above) |
| `401 Unauthorized` | Token expired and refresh failed | Delete `%APPDATA%\IRE-graph_token.bin` and re-run |
| `403 Forbidden` | User doesn't have list edit rights | Ask site owner to grant Contribute access |
| `AADSTS500011` | Wrong environment URL as audience | Use `https://graph.microsoft.com/` scope, not Power Platform URL |
| `AADSTS65002` | Client ID blocked by Intel | Use `14d82eec-...` (Graph PowerShell SDK) not Azure PowerShell |
| People field `400` | Using email instead of lookup ID | Query User Information List first, use integer ID |
| Choice field `400` | Invalid choice value | Must exactly match list's allowed values (e.g., `Normal` not `Medium`) |
