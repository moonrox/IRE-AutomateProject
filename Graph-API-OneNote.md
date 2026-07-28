# Microsoft Graph API — OneNote Editing Guide

How to read and write to a Teams-hosted OneNote notebook via Microsoft Graph API
from PowerShell or Python scripts, with no GUI required.

> Tested against the **IE** notebook in the IRE Teams channel at Intel.

---

## How Teams OneNote Differs from Personal Notebooks

| | Personal (OneDrive) | Teams / SharePoint |
|---|---|---|
| Stored at | `intel-my.sharepoint.com/personal/...` | `intel.sharepoint.com/sites/ire/...` |
| Graph root | `/me/onenote/` | `/sites/{siteId}/onenote/` |
| Scope needed | `Notes.ReadWrite` | **`Notes.ReadWrite.All`** |
| Admin consent | Not required | **Required (IT approval)** |
| Visible in `me/onenote/notebooks` | ✅ | ❌ (site-only) |

---

## One-Time Setup

### Step 1 — Request IT Admin Approval

`Notes.ReadWrite.All` requires IT admin consent in Intel's tenant.

1. Run: `.\IRE-OneNote.ps1 -Action GetToken`
2. Sign in at https://login.microsoft.com/device with your code
3. You'll see: *"Your admin has been notified..."*
4. Wait for approval email, then re-run the script — it will authenticate and cache the token

**You only do this once.** After that the token auto-refreshes silently.

### Step 2 — First successful auth

Once IT approves, run:
```powershell
.\IRE-OneNote.ps1 -Action GetToken
```
Sign in when prompted. Token cached at `%APPDATA%\IRE-onenote_token.txt`
(refresh token is DPAPI-encrypted at `%APPDATA%\IRE-onenote_refresh.bin`).

---

## Usage

### Get (or auto-create) the current WW page

```powershell
.\IRE-OneNote.ps1 -Action GetPage
```

Automatically:
- Resolves the **IE** notebook
- Finds or creates the **current month section** (e.g. `May 2026`)
- Finds or creates the **current WW page** (e.g. `WW22`)
- Prints the page HTML content

### Append content to current WW page

```powershell
.\IRE-OneNote.ps1 -Action AppendToPage -Content "<p>My update here</p>"

# With richer HTML
.\IRE-OneNote.ps1 -Action AppendToPage -Content "<h2>Status Update</h2><ul><li>Item 1</li><li>Item 2</li></ul>"
```

### Create a page explicitly

```powershell
# Create current WW page with custom content
.\IRE-OneNote.ps1 -Action CreatePage -Content "<h1>WW22 Notes</h1><p>Week summary here</p>"

# Create a specific page in a specific section
.\IRE-OneNote.ps1 -Action CreatePage -Title "WW23" -SectionName "June 2026" -Content "<h1>WW23</h1>"
```

### List all sections in the notebook

```powershell
.\IRE-OneNote.ps1 -Action ListSections
```

### Target a specific WW or section

```powershell
# Previous week
.\IRE-OneNote.ps1 -Action GetPage -WorkWeek "WW21" -SectionName "May 2026"

# Next month
.\IRE-OneNote.ps1 -Action AppendToPage -SectionName "June 2026" -WorkWeek "WW23" -Content "<p>Early planning</p>"
```

---

## Notebook Details

| Property | Value |
|---|---|
| Notebook name | `IE` |
| Location | IRE Teams → General channel |
| SharePoint URL | `https://intel.sharepoint.com/sites/ire` |
| Site ID | `intel.sharepoint.com,07fb3b8a-262d-4601-bffb-fcf1a5b9d8a7,fa48f83e-3094-43b6-a3ca-79950d07f297` |
| Section pattern | `{Month} {Year}` — e.g. `May 2026` |
| Page pattern | `WW{n}` — e.g. `WW22` |

---

## Intel Work Week Calculation

Intel WW starts on **Sunday**. WW1 contains January 1st.

```powershell
function Get-IntelWorkWeek([datetime]$Date = (Get-Date)) {
    $jan1     = [datetime]"$($Date.Year)-01-01"
    $ww1Start = $jan1.AddDays(-[int]$jan1.DayOfWeek)   # Sunday on or before Jan 1
    $weekNum  = [Math]::Floor(($Date - $ww1Start).TotalDays / 7) + 1
    return "WW$weekNum"
}
```

| Date | WW |
|---|---|
| Jan 1, 2026 (Thu) | WW1 |
| May 24–30, 2026 | **WW22** |
| May 31–Jun 6, 2026 | WW23 |

---

## Graph API Endpoints

```
GET    /sites/{siteId}/onenote/notebooks
GET    /sites/{siteId}/onenote/notebooks/{id}/sections
POST   /sites/{siteId}/onenote/notebooks/{id}/sections          ← create section
GET    /sites/{siteId}/onenote/sections/{id}/pages
POST   /sites/{siteId}/onenote/sections/{id}/pages              ← create page (text/html body)
GET    /sites/{siteId}/onenote/pages/{id}/content               ← get page HTML
PATCH  /sites/{siteId}/onenote/pages/{id}/content               ← append/update content
```

### Create a page — body format

```
POST /sites/{siteId}/onenote/sections/{sectionId}/pages
Content-Type: text/html
Authorization: Bearer {token}

<!DOCTYPE html>
<html>
  <head><title>WW22</title></head>
  <body>
    <h1>WW22</h1>
    <p>Content here</p>
  </body>
</html>
```

### Append to a page — body format

```
PATCH /sites/{siteId}/onenote/pages/{pageId}/content
Content-Type: application/json
Authorization: Bearer {token}

[
  {
    "target": "body",
    "action": "append",
    "content": "<p>New paragraph appended via script</p>"
  }
]
```

Other `action` values: `prepend`, `replace`, `insert`
Other `target` values: `title`, `#element-data-id` (use `?includeIDs=true` to find element IDs)

---

## Security Notes

| Concern | Status |
|---|---|
| Scope: `Notes.ReadWrite.All` | IT admin approved (one-time) |
| Refresh token | DPAPI-encrypted (`%APPDATA%\IRE-onenote_refresh.bin`) |
| Access token | Plaintext but short-lived (~1hr) in `%APPDATA%` |
| Token files gitignored | ✅ (`*.bin` in `.gitignore`) |
| No secrets in script | ✅ (only public Microsoft client ID) |

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `403` on `/sites/{id}/onenote/` | Missing `Notes.ReadWrite.All` | Wait for IT approval, re-auth |
| *"admin has been notified"* | Consent pending | Wait for email, re-run |
| `404` on notebook | Wrong notebook name | Run `-Action ListSections` to see actual names |
| `507` on page create | Section hit page limit | Script auto-creates a new section |
| Appended content not showing | OneNote sync delay | Refresh in Teams/browser (up to 30s) |
