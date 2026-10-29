"""Would the splash rules fire on a recorded first screen? Runs is_splash and the step-1 replan condition on the step-1
screen of every recorded real-app, SkyLark and AndroidWorld run (their trees, rebuilt with routines.screens).
  backend/.venv/bin/python eval/results/androidworld/splash-wait-2026-10-29/splash_scan.py"""
import collections, glob, gzip, json, os, sys
sys.path.insert(0, "backend")
from agent.loop import DRAWN_MIN, SPLASH_MAX, is_splash
from routines.screens import screen_from_tree
pats = {"real apps": ["~/Desktop/Envoy-realrun/data/runs/*-real-*", "~/Desktop/Envoy/data/runs/*-real-*", "~/Desktop/Envoy-awfix/data/runs/*-real-*"],
        "SkyLark": ["~/Desktop/Envoy-phase6/data/runs/f7-*", "~/Desktop/Envoy/data/runs/f7-*"], "AndroidWorld": ["data/runs/aw-final-standard-*"]}
for g, ps in pats.items():
    seen, n, splash, replan = set(), 0, 0, 0
    for pat in ps:
        for d in glob.glob(os.path.expanduser(pat)):
            if "-input-" in d or d in seen or (g == "SkyLark" and "-real-" in d): continue
            seen.add(d)
            try: recs = [json.loads(l) for l in open(os.path.join(d, "steps.jsonl"))]
            except Exception: continue
            a = next((r for r in recs if r.get("kind") == "action" and r.get("tree_before")), None)
            if not a or a.get("step") != 1: continue
            try:
                with gzip.open(os.path.join(d, a["tree_before"]), "rt") as f: s = screen_from_tree(json.load(f))
            except Exception: continue
            n += 1; splash += is_splash(s)
            replan += 0 < len(s.numbered) <= SPLASH_MAX and len(s.numbered) >= DRAWN_MIN  # planned on this screen, step 1 the same
    print(f"{g}: {n} first screens; is_splash fires on {splash}; the step-1 replan on {replan}")
