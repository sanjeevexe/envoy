"""Sample emulator RAM and CPU use on macOS.

Usage: python3 scripts/measure_resources.py --label one-idle --seconds 30
Prints per-emulator RSS and CPU (median over samples) plus system memory, and appends
a JSON record to logs/resources.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def emulator_procs() -> dict[int, str]:
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    procs = {}
    for line in out.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if "qemu-system-aarch64" in cmd:
            m = re.search(r"-avd\s+(\S+)", cmd)
            procs[int(pid)] = m.group(1) if m else "?"
    return procs


def top_sample(pids: list[int]) -> dict[int, tuple[float, float]]:
    """CPU % and memory footprint (MB) per pid from `top` (second sample, so CPU is a real rate)."""
    if not pids:
        return {}
    args = ["top", "-l", "2", "-s", "1", "-stats", "pid,cpu,mem"]
    for p in pids:
        args += ["-pid", str(p)]
    out = subprocess.run(args, capture_output=True, text=True).stdout
    last = out.split("PID")[-1].splitlines()[1:]
    res = {}
    for line in last:
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit():
            res[int(parts[0])] = (float(parts[1]), _mb(parts[2]))
    return res


def _mb(s: str) -> float:
    s = s.rstrip("+-")
    unit = s[-1]
    val = float(s[:-1]) if unit.isalpha() else float(s)
    return {"K": val / 1024, "M": val, "G": val * 1024, "B": val / 1024 / 1024}.get(unit, val)


def rss_mb(pid: int) -> float:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(out) / 1024 if out else 0.0


def system_memory() -> dict[str, float]:
    out = subprocess.run(["top", "-l", "1", "-n", "0"], capture_output=True, text=True).stdout
    m = re.search(r"PhysMem: (\S+) used \((\S+) wired, (\S+) compressor\), (\S+) unused", out)
    free_pct = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
    fp = re.search(r"free percentage: (\d+)%", free_pct)
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout.strip()
    return {
        "used_gb": _mb(m.group(1)) / 1024 if m else -1,
        "wired_gb": _mb(m.group(2)) / 1024 if m else -1,
        "compressor_gb": _mb(m.group(3)) / 1024 if m else -1,
        "unused_gb": _mb(m.group(4)) / 1024 if m else -1,
        "free_pct": float(fp.group(1)) if fp else -1,
        "swap": swap,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--seconds", type=int, default=30)
    args = ap.parse_args()

    procs = emulator_procs()
    samples: dict[int, list[tuple[float, float, float]]] = {p: [] for p in procs}
    end = time.time() + args.seconds
    while time.time() < end:
        tops = top_sample(list(procs))
        for p in procs:
            cpu, footprint = tops.get(p, (0.0, 0.0))
            samples[p].append((cpu, footprint, rss_mb(p)))
    sysmem = system_memory()

    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": args.label,
        "seconds": args.seconds,
        "emulators": {
            procs[p]: {
                "pid": p,
                "cpu_pct_median": statistics.median(s[0] for s in samples[p]),
                "cpu_pct_max": max(s[0] for s in samples[p]),
                "footprint_mb_median": statistics.median(s[1] for s in samples[p]),
                "rss_mb_median": statistics.median(s[2] for s in samples[p]),
                "n": len(samples[p]),
            }
            for p in procs
        },
        "system": sysmem,
    }
    (REPO / "logs").mkdir(exist_ok=True)
    with open(REPO / "logs" / "resources.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
