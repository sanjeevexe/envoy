"""Look inside Envoy's memory.

  uv run --project backend python scripts/show_memory.py                       # entities by type
  uv run --project backend python scripts/show_memory.py --notes "What's my gate?"   # what retrieval gives the model
  uv run --project backend python scripts/show_memory.py --entity <id>         # every fact, its history and sources
  uv run --project backend python scripts/show_memory.py --events 20           # the last changes
  uv run --project backend python scripts/show_memory.py --db data/phase3/gate.db   # another database
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from memory.retrieval import Retriever
from memory.store import DB_PATH, MemoryStore


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--notes")
    ap.add_argument("--entity")
    ap.add_argument("--events", type=int)
    args = ap.parse_args()
    if not Path(args.db).exists():
        print(f"no memory at {args.db}", file=sys.stderr)
        return 1
    store = MemoryStore(args.db)
    r = Retriever(store)
    if args.notes:
        n = r.notes(args.notes)
        print(n.markdown or "(nothing relevant)")
        print(f"\n— {len(n.entities)} entities, {n.facts} facts, {n.stale} marked stale; linked: {n.linked}")
    elif args.entity:
        e = store.entity(args.entity)
        if e is None:
            print("no such entity")
            return 1
        print(f"{e['type']}: {e['name']} ({e['id']})")
        for f in store.history(e["id"]):
            state = "current" if f["valid_to"] is None and not f["retired_at"] and not f["conflict"] else (
                "conflict" if f["conflict"] else "retired" if f["retired_at"] else f"until {r.ago(f['valid_to'])}")
            srcs = "; ".join(r.where(s["source"]) for s in store.sources_of(f["id"])) or r.where(f["source"])
            print(f"  {f['attribute']:20s} {f['value'][:40]:40s} [{state}] — {srcs}")
        for edge in store.edges_of(e["id"]):
            other = edge["to_entity"] if store.resolve(edge["from_entity"]) == e["id"] else edge["from_entity"]
            print(f"  —{edge['relation']}→ {(store.entity(other) or {}).get('name')} ({other})")
    elif args.events:
        for ev in store.events()[-args.events:]:
            print(ev)
    else:
        for e in store.entities():
            facts = store.current_facts(e["id"])
            print(f"{e['type']:16s} {e['name'][:50]:50s} {len(facts):2d} facts  {e['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
