"""Replay chat's router (api/chat.py) on run 1's routine library: how often does a request with no learned routine
(P2, "Add a checked bag to my Chicago trip.") get a reply ("no routine for that") instead of a task, and does one more
line in the instructions fix it without moving the others?

  uv run --project backend python eval/results/personal/2026-10-28-run1/p2-router/replay_router.py [N]

APPS is the list chat saw in run 1 (apps.txt beside this file: the active routines in that run's library).
"""
import collections
import concurrent.futures as cf
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "backend"))
from models.adapter import ModelAdapter  # noqa: E402
from models.prompts import CHAT_INSTRUCTIONS  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
APPS = Path(__file__).with_name("apps.txt").read_text().splitlines()
FIX = ("A task needs no learned routine: APPS lists only what Envoy has already learned, and it can do anything else in a "
       "phone app too, so a request to do something in an app is a task even when APPS has nothing for it.\n")
# request -> (the right kind, how many times per condition)
REQUESTS = {"Add a checked bag to my Chicago trip.": ("task", N),
            "Which seat am I in on my Denver flight?": ("memory|task", N // 2),
            "Turn on Wi-Fi.": ("task", N // 2),  # no routine either (Settings has Bluetooth and the Android version)
            "What can you do?": ("reply", N // 2)}


def content(message: str) -> str:
    return f"REQUEST: {message}\n\nAPPS (learned routines):\n" + "\n".join(f"- {a}" for a in APPS) + "\n"


def one(adapter: ModelAdapter, message: str, fix: bool, i: int) -> tuple[str, str, float]:
    res = adapter.call("chat", content(message), instructions=CHAT_INSTRUCTIONS + (FIX if fix else ""), data_scope="real",
                       task_id=f"probe-router-{int(fix)}-{i}")
    r = res.parsed
    return r.kind, r.reply or r.goal, res.cost_at_standard_usd


def main() -> None:
    adapter = ModelAdapter()
    jobs = [(m, fix, i) for m, (_, n) in REQUESTS.items() for fix in (False, True) for i in range(n)]
    out: dict = collections.defaultdict(list)
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(one, adapter, *j): j for j in jobs}
        for f in cf.as_completed(futs):
            m, fix, _ = futs[f]
            try:
                out[(m, fix)].append(f.result())
            except Exception as e:  # noqa: BLE001
                out[(m, fix)].append(("error", str(e)[:80], 0.0))
    total = 0.0
    for m, (right, _) in REQUESTS.items():
        for fix in (False, True):
            rs = out[(m, fix)]
            total += sum(c for _, _, c in rs)
            kinds = collections.Counter(k for k, _, _ in rs)
            wrong = sum(n for k, n in kinds.items() if k not in right.split("|"))
            print(f"{m[:44]:44} fix={'on ' if fix else 'off'} right={right:11} wrong {wrong}/{len(rs)}  {dict(kinds)}")
            for k, text, _ in rs:
                if k not in right.split("|"):
                    print(f"      {k}: {text[:110]}")
    print(f"cost ${total:.3f}")


if __name__ == "__main__":
    main()
