"""
hello.py — starter training script for the PowerAutomateProject.

Demonstrates how to authenticate with Microsoft Graph using MSAL
(device-code flow, same pattern as the PowerShell scripts) and
make a simple GET request.

Usage:
    # Activate the venv first:
    #   .venv\Scripts\activate
    # Then:
    #   pip install -r requirements.txt
    #   python hello.py
"""

import os
import requests
import msal

# ── Config — read from .env (loaded by graph_auth.py or dotenv) ───────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLIENT_ID = os.environ.get("DEV_CLIENT_ID", "")
TENANT_ID = os.environ.get("DEV_TENANT_ID", "")
if not CLIENT_ID or not TENANT_ID:
    raise RuntimeError("DEV_CLIENT_ID and DEV_TENANT_ID must be set in your .env file.")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES    = ["https://graph.microsoft.com/Sites.ReadWrite.All"]

# MSAL token cache persisted to a file so re-runs skip the device-code prompt.
CACHE_FILE = os.path.join(os.environ.get("APPDATA", "."), "IRE-py_token_cache.bin")


def build_app() -> msal.PublicClientApplication:
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    return app, cache


def get_token() -> str:
    app, cache = build_app()

    # Try silent first (uses cached refresh token)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None

    if not result:
        # Device-code flow
        flow = app.initiate_device_flow(scopes=SCOPES)
        print("\n" + "=" * 43)
        print(f"Go to : {flow['verification_uri']}")
        print(f"Code  : {flow['user_code']}")
        print("=" * 43)
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description')}")

    # Persist cache (MSAL encrypts refresh tokens internally on Windows via CryptProtectData)
    with open(CACHE_FILE, "w") as f:
        f.write(cache.serialize())

    return result["access_token"]


def main():
    print("Hello, Microsoft Graph!\n")
    token = get_token()

    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers, timeout=10)
    resp.raise_for_status()
    me = resp.json()

    print(f"Signed in as : {me.get('displayName')} ({me.get('userPrincipalName')})")
    print(f"Mail         : {me.get('mail')}")
    print("\nGraph API is working ✅")


if __name__ == "__main__":
    main()
