"""Connect Envoy to Gmail (read-only). You run this; it opens Google's consent page in your browser.

One-time setup (about 10 minutes, in the Google Cloud console, signed in as the dedicated test account):
  1. Create a project (e.g. "envoy-personal") and enable the Gmail API.
  2. OAuth consent screen: External, testing mode; add the test account as a test user.
     Scope: https://www.googleapis.com/auth/gmail.readonly ("unverified app" is expected in testing mode).
  3. Credentials → Create OAuth client ID → Desktop app → download the JSON to data/gmail/client_secret.json.
Then:
  uv run --project backend python scripts/connect_gmail.py           # consent in the browser; saves data/gmail/token.json
  uv run --project backend python scripts/connect_gmail.py --check   # lists the 5 newest subjects

In testing mode Google expires the sign-in every 7 days; run this again to reconnect.
"""

from __future__ import annotations

import argparse
import sys

from integrations.mail import GMAIL_DIR, SCOPES, GmailMailbox


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    GMAIL_DIR.mkdir(parents=True, exist_ok=True)
    if not args.check:
        client = GMAIL_DIR / "client_secret.json"
        if not client.exists():
            print(f"Missing {client}. Follow the steps at the top of this file first.", file=sys.stderr)
            return 2
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES).run_local_server(port=0)
        (GMAIL_DIR / "token.json").write_text(creds.to_json())
        print("Connected. Token saved to data/gmail/token.json (gitignored).")
    box = GmailMailbox(max_messages=5)
    mails, cursor = box.fetch(None)
    for m in mails:
        print(f"- {m.subject[:80]}")
    print(f"history cursor: {cursor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
