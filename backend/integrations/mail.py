"""Mailboxes for memory: a local test inbox and Gmail (design doc, Interfaces › Gmail and Calendar).

Both return the same `Email` records. The local inbox reads `.eml` files (SkyLark's fixtures generate the
matching confirmation emails, so a code like KX7Q2M appears in both the app and the inbox). The Gmail
client uses a personal Google Cloud project in testing mode with the read-only scope; new mail is found by
polling Gmail's history (every 2 minutes in the service), and the history ID is the cursor.
Connecting needs the user once: `scripts/connect_gmail.py` (sign-in and consent are theirs).
"""

from __future__ import annotations

import base64
import email
import email.policy
import json
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol

REPO = Path(__file__).resolve().parents[2]
GMAIL_DIR = REPO / "data" / "gmail"  # token and client file (gitignored)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class Email:
    id: str
    sender: str
    to: str
    subject: str
    date: float  # epoch seconds
    text: str  # plain-text body (or the HTML's text)
    html: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def parse_message(raw: bytes, msg_id: str) -> Email:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    text, html = "", ""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        ctype = part.get_content_type()
        if part.get_content_disposition() == "attachment":
            continue
        if ctype == "text/plain" and not text:
            text = part.get_content()
        elif ctype == "text/html" and not html:
            html = part.get_content()
    if not text and html:
        text = html_to_text(html)
    try:
        when = parsedate_to_datetime(msg["Date"]).timestamp() if msg["Date"] else 0.0
    except (TypeError, ValueError):
        when = 0.0
    return Email(id=msg_id, sender=str(msg["From"] or ""), to=str(msg["To"] or ""), subject=str(msg["Subject"] or ""), date=when,
                 text=text, html=html, headers={k: str(v) for k, v in msg.items()})


def html_to_text(html: str) -> str:
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.out: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs: Any) -> None:
            if tag in ("script", "style"):
                self.skip += 1
            if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"):
                self.out.append("\n")

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style") and self.skip:
                self.skip -= 1

        def handle_data(self, data: str) -> None:
            if not self.skip:
                self.out.append(data)

    p = P()
    p.feed(html)
    return "\n".join(" ".join(line.split()) for line in "".join(p.out).splitlines() if line.strip())


class Mailbox(Protocol):
    def fetch(self, cursor: str | None = None) -> tuple[list[Email], str]:
        """New messages since `cursor` (None: everything available) and the cursor to use next time."""
        ...


class LocalMailbox:
    """A folder of .eml files; the cursor is the newest file name already read."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)

    def fetch(self, cursor: str | None = None) -> tuple[list[Email], str]:
        files = sorted(p for p in self.folder.glob("*.eml"))
        new = [p for p in files if cursor is None or p.name > cursor]
        mails = [parse_message(p.read_bytes(), p.stem) for p in new]
        return mails, (files[-1].name if files else (cursor or ""))


class GmailMailbox:
    """Gmail, read-only. The first fetch lists recent messages; later fetches follow the history API from the last history ID."""

    def __init__(self, service: Any = None, query: str = "newer_than:60d", max_messages: int = 200) -> None:
        self._service = service
        self.query = query
        self.max_messages = max_messages

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = gmail_service()
        return self._service

    def _get(self, mid: str) -> Email:
        r = self.service.users().messages().get(userId="me", id=mid, format="raw").execute()
        return parse_message(base64.urlsafe_b64decode(r["raw"]), mid)

    def fetch(self, cursor: str | None = None) -> tuple[list[Email], str]:
        users = self.service.users()
        if cursor is None:
            ids: list[str] = []
            page = None
            while len(ids) < self.max_messages:
                r = users.messages().list(userId="me", q=self.query, pageToken=page, maxResults=min(100, self.max_messages)).execute()
                ids += [m["id"] for m in r.get("messages", [])]
                page = r.get("nextPageToken")
                if not page:
                    break
            history_id = users.getProfile(userId="me").execute()["historyId"]
            return [self._get(i) for i in ids[: self.max_messages]], str(history_id)
        ids, page, latest = [], None, cursor
        while True:
            r = users.history().list(userId="me", startHistoryId=cursor, historyTypes=["messageAdded"], pageToken=page).execute()
            for h in r.get("history", []):
                ids += [m["message"]["id"] for m in h.get("messagesAdded", [])]
            latest = str(r.get("historyId", latest))
            page = r.get("nextPageToken")
            if not page:
                break
        return [self._get(i) for i in dict.fromkeys(ids)], latest


def gmail_service() -> Any:
    """The Gmail API client from the token saved by scripts/connect_gmail.py (refreshed when it expires)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token = GMAIL_DIR / "token.json"
    if not token.exists():
        raise RuntimeError("Gmail is not connected: run scripts/connect_gmail.py (you sign in; tokens expire every 7 days in testing mode)")
    creds = Credentials.from_authorized_user_info(json.loads(token.read_text()), SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
