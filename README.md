# IRE Project Tracking — Power Automate Setup

Power Automate solution for reading and writing to the IRE Project Tracking SharePoint list,
managed with the Power Platform CLI (pac) and version-controlled in VS Code.

- **SharePoint List:** https://intel.sharepoint.com/sites/ire/Lists/IRE%20Project%20Tracking/AllItems.aspx
- **Power Platform Environment:** Personal Productivity (default)
- **Environment ID:** `46c98d88-e344-4ed4-8496-4ed7712e255d`
- **Authenticated User:** john.monroe@intel.com

---

## Project Structure

```
PowerAutomateProject/
├── .vscode/
│   ├── tasks.json         # VS Code tasks for common pac commands
│   └── extensions.json    # Recommended Power Platform extension
├── flows/
│   └── IRE-ProjectTracking-flows.json   # Flow design reference
├── solutions/
│   ├── IREProjectTracking.zip           # Exported solution (latest)
│   └── IREProjectTracking/
│       └── src/
│           ├── Other/
│           │   └── Solution.xml         # Solution manifest
│           └── Workflows/
│               ├── Button-Getitems-*.json     # Get all list items flow
│               └── Button-Createitem-*.json   # Create new list item flow
└── README.md
```

---

## ⚡ Quick Start — Update SharePoint List from CLI

The fastest way to read/write the IRE Project Tracking list directly from PowerShell:

```powershell
cd C:\Users\JMONROE1\PowerAutomateProject

# Read all items
.\IRE-SharePoint.ps1 -Action GetItems

# Add an item
.\IRE-SharePoint.ps1 -Action CreateItem `
    -Title "My Project" `
    -Priority "High" `
    -Status "New" `
    -Segment "Network" `
    -Projectphase "Planning" `
    -ProjectSummaryDetails "Initial scoping complete"

# Delete an item by ID
.\IRE-SharePoint.ps1 -Action DeleteItem -ItemId 11
```

> First run opens a browser sign-in. After that, the token auto-refreshes — no repeated sign-ins needed.

---

## One-Time Setup

### Step 1 — Install Node.js
Download and install from https://nodejs.org (v24+ supported)

### Step 2 — Install Power Platform CLI
> ⚠️ Do NOT use `npm install -g pac` — that is the wrong package.

Download the official MSI installer:
```
https://aka.ms/PowerAppsCLI
```
Or install silently via PowerShell:
```powershell
Invoke-WebRequest -Uri "https://aka.ms/PowerAppsCLI" -OutFile "$env:TEMP\PowerPlatformCLI.msi"
Start-Process msiexec.exe -ArgumentList "/i `"$env:TEMP\PowerPlatformCLI.msi`" /quiet /norestart" -Wait
```
Verify install:
```powershell
pac --version
# Expected: Microsoft PowerPlatform CLI Version: 2.7.4+...
```

### Step 3 — Authenticate
```powershell
pac auth create
```
This opens a browser window. Sign in with your Intel Microsoft account.

Confirm connection:
```powershell
pac env list
# Should show: * Personal Productivity (default)  46c98d88-e344-4ed4-8496-4ed7712e255d
```

---

## Solution Setup

### Initialize the solution locally (first time only)
```powershell
New-Item -ItemType Directory -Path "solutions\IREProjectTracking" -Force
cd solutions\IREProjectTracking
pac solution init --publisher-name IntelIRE --publisher-prefix ire
```

### Pack and import to Power Platform (first time only)
```powershell
pac solution pack --zipfile "solutions\IREProjectTracking.zip" --folder "solutions\IREProjectTracking\src"
pac solution import --path "solutions\IREProjectTracking.zip" --environment "46c98d88-e344-4ed4-8496-4ed7712e255d"
```

---

## Day-to-Day Workflow

### Pull latest flows from Power Platform → local
```powershell
Remove-Item "solutions\IREProjectTracking.zip" -Force -ErrorAction SilentlyContinue
pac solution export --path "solutions" --name "IREProjectTracking" --managed false --environment "46c98d88-e344-4ed4-8496-4ed7712e255d"
pac solution unpack --zipfile "solutions\IREProjectTracking.zip" --folder "solutions\IREProjectTracking\src" --allowDelete true
```

### Push local changes → Power Platform
```powershell
pac solution pack --zipfile "solutions\IREProjectTracking.zip" --folder "solutions\IREProjectTracking\src"
pac solution import --path "solutions\IREProjectTracking.zip" --environment "46c98d88-e344-4ed4-8496-4ed7712e255d"
```

### Publish customizations after import
```powershell
pac solution publish --environment "46c98d88-e344-4ed4-8496-4ed7712e255d"
```

---

## Flows in This Solution

### 1. Button → Get items
Retrieves all items from the IRE Project Tracking SharePoint list.
- **Trigger:** HTTP Request (When an HTTP request is received)
- **Action:** SharePoint — Get items
- **Site:** https://intel.sharepoint.com/sites/ire
- **List:** IRE Project Tracking

Test from CLI (replace with your HTTP trigger URL):
```powershell
curl -X POST "YOUR_GET_ITEMS_FLOW_URL" -H "Content-Type: application/json" -d "{}"
```

### 2. Button → Create item
Creates a new item in the IRE Project Tracking SharePoint list.
- **Trigger:** HTTP Request (When an HTTP request is received)
- **Action:** SharePoint — Create item
- **Site:** https://intel.sharepoint.com/sites/ire
- **List:** IRE Project Tracking
- **Default fields:** `Status = New`, `ManagerReview = false`

Test from CLI (replace with your HTTP trigger URL):
```powershell
curl -X POST "YOUR_CREATE_ITEM_FLOW_URL" `
  -H "Content-Type: application/json" `
  -d '{"Title": "Test Project", "Status": "New", "ManagerReview": false}'
```

---

## IRE-SharePoint.ps1 — Direct SharePoint Script

Reads and writes the IRE Project Tracking list via **Microsoft Graph API**.
No Power Automate required. Token auto-refreshes after first sign-in.

### Fields

| Field | Type | Values |
|---|---|---|
| `Title` | Text | Project name |
| `Priority` | Choice | `High`, `Normal`, `Low` |
| `Status` | Choice | `New`, `In progress`, `Blocked`, `Completed` |
| `Segment` | Choice | `Network`, `Compute`, `Cloud`, `Storage` |
| `Projectphase` | Choice | `Analysis`, `Planning`, `Execution`, `Closure` |
| `ManagerReview` | Boolean | `$true` / `$false` |
| `ProjectSummaryDetails` | Text | Free text notes |

### Actions

```powershell
# Get all items
.\IRE-SharePoint.ps1 -Action GetItems

# Create item (Title required, all others optional)
.\IRE-SharePoint.ps1 -Action CreateItem `
    -Title "Project Name" `
    -Priority "High" `
    -Status "New" `
    -Segment "Network" `
    -Projectphase "Planning" `
    -ManagerReview $false `
    -ProjectSummaryDetails "Notes here"

# Delete item by ID
.\IRE-SharePoint.ps1 -Action DeleteItem -ItemId 5

# Force token refresh
.\IRE-SharePoint.ps1 -Action GetToken
```

### Authentication
- **First run:** Browser sign-in via https://login.microsoft.com/device
- **Client ID:** `14d82eec-204b-4c2f-b7e8-296a70dab67e` (Microsoft Graph PowerShell — pre-authorized in all M365 tenants)
- **Tenant ID:** `46c98d88-e344-4ed4-8496-4ed7712e255d`
- **Token cached at:** `%TEMP%\graph_token.txt` + `%TEMP%\graph_refresh.txt`

### SharePoint IDs (pre-configured in script)
- **Site:** `intel.sharepoint.com,07fb3b8a-262d-4601-bffb-fcf1a5b9d8a7,fa48f83e-3094-43b6-a3ca-79950d07f297`
- **List:** `0bd155fa-92d1-4149-af8b-728a49ad95c6` (IRE Project Tracking - Q2 2026)

---

## Getting HTTP Trigger URLs

HTTP trigger URLs are runtime-generated and not stored in source control.
To retrieve them:
1. Go to https://make.powerautomate.com
2. **Solutions** → **IREProjectTracking** → open the flow
3. Click the **"When an HTTP request is received"** trigger step
4. Copy the **HTTP POST URL**

> Store these URLs securely — they include authentication signatures.

---

## VS Code Tasks

Use `Ctrl+Shift+P` → **Tasks: Run Task**:

| Task | Description |
|---|---|
| PAC: Authenticate | Sign in to Power Platform |
| PAC: Init Solution | Initialize a new solution locally |
| PAC: Export IRE Solution | Pull latest from Power Platform |
| PAC: Import IRE Solution | Push local solution to Power Platform |
| Trigger Flow via HTTP | Run a flow by URL |

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `pac` not recognized after install | Open a new terminal window to reload PATH |
| Flow changes not showing in export | Edit flows from within **Solutions** menu, not **My flows** |
| Solution export says file exists | `Remove-Item solutions\IREProjectTracking.zip -Force` first |
| Trigger still shows "Button" after update | Ensure flow was saved and republished inside the solution |
