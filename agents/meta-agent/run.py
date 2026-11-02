"""Start the agent and its page:  uv run --project backend python agents/meta-agent/run.py  (from the repo root)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from meta_agent.web import main  # noqa: E402

main()
