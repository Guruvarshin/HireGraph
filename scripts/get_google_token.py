#!/usr/bin/env python3
import os
import json
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

def get_google_token():
    client_config = {
        "installed": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=8080)

    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_expiry": creds.expiry.isoformat() if creds.expiry else None,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    print("\nToken obtained successfully!")
    print("Save this in MongoDB under google_tokens collection:")
    print(json.dumps(token_data, indent=2))

    return token_data

if __name__ == "__main__":
    print("=== Google OAuth Token Generator ===\n")
    print("This will open a browser for you to authorize the app.")
    print("Make sure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set in .env\n")

    try:
        token = get_google_token()
    except Exception as e:
        print(f"ERROR: {e}")
        exit(1)
