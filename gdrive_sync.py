#!/usr/bin/env python3
"""
gdrive_sync.py — Syncs a shared Google Drive folder to the local images/ directory.

Setup (one-time, on the Pi):
    pip3 install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages

Then run once interactively to authenticate:
    python3 gdrive_sync.py --auth

After that it runs headlessly (via cron or the display script).
"""

import os
import io
import json
import time
import hashlib
import argparse
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ─────────────────────────────────────────────
# CONFIG — edit these two lines
# ─────────────────────────────────────────────

# Paste the ID of your shared Google Drive folder here.
# It's the long string in the URL when you open the folder:
# https://drive.google.com/drive/folders/THIS_PART_HERE
DRIVE_FOLDER_ID = "1WdIGnUTlL4tpexmwDdzMZnDGXH6U2Ene"

LOCAL_IMAGE_DIR  = "./images"           # Where images live on the Pi
CREDENTIALS_FILE = "./gdrive_creds.json"   # OAuth client secret (downloaded from Google Cloud)
TOKEN_FILE       = "./gdrive_token.json"   # Saved auth token (auto-created after --auth)
SYNC_LOG         = "./gdrive_sync.log"

# Supported mime types → local file extensions
SUPPORTED_TYPES = {
    "image/png":  ".png",
    "image/jpeg": ".jpg",
    "image/bmp":  ".bmp",
    "image/gif":  ".gif",
}

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

def get_credentials() -> Credentials:
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"[SYNC] ERROR: {CREDENTIALS_FILE} not found.")
                print("  1. Go to https://console.cloud.google.com/")
                print("  2. Create a project → Enable Google Drive API")
                print("  3. Create OAuth 2.0 credentials (Desktop app)")
                print(f"  4. Download as {CREDENTIALS_FILE}")
                print("  5. Run: python3 gdrive_sync.py --auth")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # Use console flow for headless Pi (no browser needed on the Pi itself —
            # you authenticate on another machine and paste the code)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds


# ─────────────────────────────────────────────
# SYNC
# ─────────────────────────────────────────────

def list_drive_files(service) -> list[dict]:
    """Return all supported image files in the configured Drive folder."""
    mime_query = " or ".join(f"mimeType='{m}'" for m in SUPPORTED_TYPES)
    query = f"'{DRIVE_FOLDER_ID}' in parents and ({mime_query}) and trashed=false"

    results = []
    page_token = None
    while True:
        resp = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, md5Checksum, mimeType)",
            pageToken=page_token,
        ).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def local_md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(service, file_id: str, dest_path: str):
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    with open(dest_path, "wb") as f:
        f.write(buf.getvalue())


def sync(log=True):
    os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

    def logprint(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        if log:
            with open(SYNC_LOG, "a") as f:
                f.write(line + "\n")

    logprint("Starting Drive sync...")

    try:
        creds   = get_credentials()
        service = build("drive", "v3", credentials=creds)
    except Exception as e:
        logprint(f"Auth failed: {e}")
        return

    try:
        drive_files = list_drive_files(service)
    except Exception as e:
        logprint(f"Failed to list Drive folder: {e}")
        return

    logprint(f"Drive folder contains {len(drive_files)} supported file(s).")

    # Build a map of what's on Drive: filename → {id, md5, mimeType}
    drive_map = {}
    for f in drive_files:
        name = f["name"]
        ext  = SUPPORTED_TYPES.get(f["mimeType"], "")
        # Ensure file has the right extension
        if not name.lower().endswith(tuple(SUPPORTED_TYPES.values())):
            name = Path(name).stem + ext
        drive_map[name] = f

    # ── Download new or changed files ──────────────────────────────
    for name, meta in drive_map.items():
        local_path = os.path.join(LOCAL_IMAGE_DIR, name)
        drive_md5  = meta.get("md5Checksum")

        if os.path.exists(local_path):
            if drive_md5 and local_md5(local_path) == drive_md5:
                logprint(f"  SKIP (unchanged): {name}")
                continue
            logprint(f"  UPDATE: {name}")
        else:
            logprint(f"  DOWNLOAD: {name}")

        try:
            download_file(service, meta["id"], local_path)
            logprint(f"    ✓ Saved to {local_path}")
        except Exception as e:
            logprint(f"    ✗ Failed: {e}")

    # ── Remove local files no longer in Drive ──────────────────────
    local_files = set(
        f for f in os.listdir(LOCAL_IMAGE_DIR)
        if Path(f).suffix.lower() in SUPPORTED_TYPES.values()
    )
    drive_names = set(drive_map.keys())
    to_remove   = local_files - drive_names

    for name in to_remove:
        local_path = os.path.join(LOCAL_IMAGE_DIR, name)
        os.remove(local_path)
        logprint(f"  REMOVED (deleted from Drive): {name}")

    logprint("Sync complete.")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true",
                        help="Run interactive OAuth flow to authorize the Pi")
    args = parser.parse_args()

    if args.auth:
        print("Starting OAuth flow — a browser window will open (or give you a URL).")
        print("Complete sign-in, then the token will be saved for headless use.")
        get_credentials()
        print("Auth complete. Token saved. You can now run sync headlessly.")
    else:
        sync()