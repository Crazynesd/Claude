"""
Opretter mappestruktur på Google Drive til marketing bureau.

Krav:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Opsætning:
  1. Gå til https://console.cloud.google.com/
  2. Opret et projekt og aktiver "Google Drive API"
  3. Opret OAuth 2.0-klientoplysninger (Desktop-app)
  4. Download credentials.json og placér den i samme mappe som dette script
  5. Kør scriptet: python setup_drive_folders.py
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDER_STRUCTURE = {
    "Claude": [
        "Tilbud",
        "Produkter & Priser",
        "Kunder",
        "Templates",
    ]
}


def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds


def create_folder(service, name, parent_id=None):
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id, name").execute()
    return folder


def folder_exists(service, name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    else:
        query += " and 'root' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0] if files else None


def setup_folders(service):
    for root_name, subfolders in FOLDER_STRUCTURE.items():
        existing = folder_exists(service, root_name)
        if existing:
            print(f"  Mappe eksisterer allerede: {root_name} (id: {existing['id']})")
            root_id = existing["id"]
        else:
            root = create_folder(service, root_name)
            root_id = root["id"]
            print(f"  Oprettet: {root_name} (id: {root_id})")

        for sub_name in subfolders:
            existing_sub = folder_exists(service, sub_name, parent_id=root_id)
            if existing_sub:
                print(f"    Mappe eksisterer allerede: {root_name}/{sub_name}")
            else:
                sub = create_folder(service, sub_name, parent_id=root_id)
                print(f"    Oprettet: {root_name}/{sub_name} (id: {sub['id']})")


def main():
    print("Opretter mappestruktur på Google Drive...")
    try:
        creds = authenticate()
        service = build("drive", "v3", credentials=creds)
        setup_folders(service)
        print("\nFaerdig! Mappestruktur oprettet pa Google Drive.")
    except FileNotFoundError:
        print(
            "FEJL: credentials.json ikke fundet.\n"
            "Hent den fra Google Cloud Console og placér den i samme mappe som scriptet."
        )
    except HttpError as e:
        print(f"Google Drive API-fejl: {e}")


if __name__ == "__main__":
    main()
