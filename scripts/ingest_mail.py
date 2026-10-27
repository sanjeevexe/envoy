"""Read new email into Envoy's memory (data/memory.db by default).

  uv run --project backend python scripts/ingest_mail.py                  # Gmail: the last 60 days first, then only what is new
  uv run --project backend python scripts/ingest_mail.py --query newer_than:1y --max 300
  uv run --project backend python scripts/ingest_mail.py --folder eval/results/phase3/inbox --db data/phase3/try.db

Gmail needs scripts/connect_gmail.py first. The Gmail history cursor is kept in data/gmail/cursor, so a second
run only reads mail that arrived since. Each email is redacted, then read from its schema.org markup (no model)
or by Muse Spark; values not in the email are dropped. Prints what each email added.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from integrations.mail import GMAIL_DIR, GmailMailbox, LocalMailbox
from memory.service import MemoryService
from memory.store import DB_PATH, MemoryStore


def summary(rep) -> str:
    if rep.skipped:
        return f"skipped ({rep.skipped})"
    ents = ", ".join(f"{r.type} {r.how}" for r in rep.resolved) or "nothing to remember"
    facts = " ".join(f"{k} {v}" for k, v in rep.facts.items() if v)
    return f"{rep.method:6s} {ents}{' · ' + facts if facts else ''}{f' · dropped {len(rep.dropped)}' if rep.dropped else ''}"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--folder", help="a folder of .eml files instead of Gmail")
    ap.add_argument("--query", default="newer_than:60d")
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--from-start", action="store_true", help="ignore the saved Gmail cursor")
    args = ap.parse_args()

    cursor_file = GMAIL_DIR / "cursor"
    if args.folder:
        mails, cursor = LocalMailbox(Path(args.folder)).fetch(None)
    else:
        cursor = None if args.from_start or not cursor_file.exists() else cursor_file.read_text().strip()
        mails, cursor = GmailMailbox(query=args.query, max_messages=args.max).fetch(cursor)
    store = MemoryStore(args.db)
    service = MemoryService(store, data_scope="real")
    calls = cost = 0.0
    for mail in sorted(mails, key=lambda m: m.date or 0):
        rep = await service.ingest_email(mail)
        calls += rep.model_calls
        cost += rep.cost_usd
        print(f"- {mail.sender[:28]:28s} {mail.subject[:50]:50s} {summary(rep)}", flush=True)
    if not args.folder:
        cursor_file.write_text(cursor)
    print(f"\n{len(mails)} emails, {int(calls)} model calls, ${cost:.4f}. Memory: {len(store.entities())} entities in {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
