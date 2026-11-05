# integrations

| File | What |
| --- | --- |
| `mail.py` | Mailboxes for memory: `LocalMailbox` (a folder of `.eml` files, e.g. the SkyLark test inbox) and `GmailMailbox` (read-only scope, first a recent-messages list, then Gmail's history API from the last history ID). |

Gmail needs a one-time setup by you (a Google Cloud project in testing mode, the test account as a test user, an OAuth client file, one consent): see `scripts/connect_gmail.py`. Then `scripts/ingest_mail.py` reads new mail into memory (the history cursor is kept in `data/gmail/cursor`, so later runs read only what arrived since). The scheduler and triggers (an `email` trigger fires on mail that reached memory) live in `api/scheduler.py`.
