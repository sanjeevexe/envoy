"""Tune the locator thresholds (STRICT, RELAXED, MARGIN) on SkyLark screens from all four layouts.

Ground truth comes from SkyLark's test tags, which stay the same across layout variants: for every
locator in the compiled routines (step targets and check anchors) and every recorded screen that
contains an element with that resource ID, that element is the right answer and every other element
is a wrong one. Each locator is scored twice: with IDs, and with IDs removed (as on real apps, whose
IDs are often obfuscated), so the text, description and neighbor attributes are tuned too.

  uv run --project backend python eval/tune_locators.py            # grid search + report
"""

from __future__ import annotations

import itertools
import json
import re
from collections import defaultdict
from pathlib import Path

from routines import locators
from routines.model import Locator, load
from routines.screens import load_tree, short_id

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "data" / "runs"
OUT = REPO / "eval" / "results" / "phase2"
_VARIANT = re.compile(r"-v(\d)-")


def routine_locators() -> list[tuple[str, Locator]]:
    out = []
    for p in sorted((OUT / "compiled").glob("*.yaml")):
        r = load(p)
        for st in r.steps:
            if st.action.target is not None and not st.action.target.text_has and st.action.target.resource_id \
                    and "*" not in st.action.target.resource_id:
                out.append((f"{r.routine}:{st.id}:target", st.action.target))
            for i, c in enumerate(st.pre + st.post):
                if c.locator is not None and not c.locator.text_has and c.locator.resource_id and "*" not in c.locator.resource_id \
                        and "{{" not in (c.locator.text or ""):
                    out.append((f"{r.routine}:{st.id}:check{i}", c.locator))
    # one locator per (id, text): checks repeat across routines
    seen, uniq = set(), []
    for name, loc in out:
        key = (loc.resource_id, loc.text, loc.kind)
        if key not in seen:
            seen.add(key)
            uniq.append((name, loc))
    return uniq


def screens() -> list[tuple[int, object]]:
    out = []
    for run in sorted(RUNS.iterdir()):
        if not (run.name.startswith("p1-") or run.name.startswith("p2-src-")):
            continue
        m = _VARIANT.search(run.name + "-")
        variant = int(m.group(1)) if m else 0
        for p in sorted((run / "screens").glob("*_before.json.gz")):
            out.append((variant, load_tree(p)))
    return out


# Variant 2's renames (testapps/skylark MainActivity.kt): the same element under its new label is still the right answer.
RENAMES = {"check in": "check-in now", "my trips": "trips", "change seat": "seats", "continue": "next",
           "confirm check-in": "complete check-in", "flight status": "status", "find trip": "look up"}


def _same_element(loc: Locator, e, role: str) -> bool:
    """Ground truth: the same test tag and the same label (or its variant-2 rename; a field's label without its value).
    For a check the type must match too, since it encodes state (a selected tab is a Text, not a Button).
    A shared tag with another label (screen_title on another screen) is a different element."""
    if short_id(e.resource_id) != loc.resource_id:
        return False
    if role == "check" and loc.kind and e.kind != loc.kind:
        return False
    if not loc.text:
        return True
    t, lab = loc.text.casefold(), (e.label or "").casefold()
    lab_field = lab.split(":", 1)[0] if e.editable else lab
    return t in (lab, lab_field, lab.split(" · ")[0]) or RENAMES.get(t) in (lab, lab_field)


def cases() -> list[dict]:
    """Positive cases (the element is on the screen: it must win) and hard negatives (an element shares
    its ID or label but is not it: nothing may match)."""
    locs = routine_locators()
    rows = []
    for variant, s in screens():
        for name, loc in locs:
            role = "target" if name.endswith(":target") else "check"
            truth = next((e for e in s.numbered if _same_element(loc, e, role)), None)  # type: ignore[attr-defined]
            near_miss = truth is None and any(short_id(e.resource_id) == loc.resource_id or
                                              (loc.text and (e.label or "").casefold() == loc.text.casefold())
                                              for e in s.numbered)  # type: ignore[attr-defined]
            if truth is None and not near_miss:
                continue
            for use_ids in (True, False):
                if not use_ids and not (loc.text or loc.desc):
                    continue  # an ID-only locator can't exist on an app without IDs: the compiler drops it
                scored = sorted(((locators.score(loc, e, s, use_ids=use_ids, role=role)[0], e) for e in locators.candidates(s)), key=lambda t: -t[0])  # type: ignore[arg-type]
                truth_score = next((sc for sc, e in scored if truth is not None and e.index == truth.index), None)
                best_wrong = max((sc for sc, e in scored if truth is None or e.index != truth.index), default=0.0)
                runner = scored[1][0] if len(scored) > 1 else 0.0
                rows.append({"variant": variant, "locator": name, "role": role, "use_ids": use_ids, "positive": truth is not None,
                             "truth": truth_score if truth_score is not None else 0.0, "wrong": best_wrong, "runner": runner})
    return rows


def evaluate(rows: list[dict], strict: float, relaxed: float, margin: float) -> dict:
    """right: on a positive case the true element wins; wrong: some other element wins (dangerous: the routine
    would act on it). On a negative case any winner is wrong."""
    out: dict = defaultdict(lambda: {"n": 0, "pos": 0, "strict": 0, "relaxed": 0, "false_strict": 0, "false_relaxed": 0})
    for r in rows:
        key = (r["role"], "ids" if r["use_ids"] else "no-ids", r["variant"])
        o = out[key]
        o["n"] += 1
        o["pos"] += r["positive"]
        m = margin if r["role"] == "target" else 0.0  # a check only needs some element that proves the state; a target must be unambiguous
        for th, k in ((strict, "strict"), (relaxed, "relaxed")):
            if r["positive"] and r["truth"] >= th and (r["truth"] - r["wrong"] >= m or (m == 0.0 and r["truth"] >= r["wrong"])):
                o[k] += 1
            elif r["wrong"] >= th and r["wrong"] > r["truth"] and r["wrong"] - r["truth"] >= m:
                o["false_" + k] += 1
    return out


def main() -> int:
    rows = cases()
    print(f"{len(rows)} cases from {len({r['locator'] for r in rows})} locators")
    best = None
    grid = []
    for strict, relaxed, margin in itertools.product([0.7, 0.75, 0.8, 0.85, 0.9], [0.45, 0.5, 0.55, 0.6, 0.65], [0.0, 0.05, 0.08, 0.12]):
        if relaxed >= strict:
            continue
        ev = evaluate(rows, strict, relaxed, margin)
        tot = lambda k, ids: sum(v[k] for (_, i, _), v in ev.items() if i == ids)  # noqa: E731
        n_ids, n_no = max(1, tot("pos", "ids")), max(1, tot("pos", "no-ids"))
        false_ids = tot("false_strict", "ids") + tot("false_relaxed", "ids")
        false_no = tot("false_strict", "no-ids") + tot("false_relaxed", "no-ids")
        v0 = lambda k, ids: sum(v[k] for (_, i, var), v in ev.items() if i == ids and var == 0)  # noqa: E731
        # Objective: (1) no wrong element wins with IDs, (2) fewest wrong without IDs, (3) the unchanged app passes at
        # strict, (4) the most recoveries without a model (strict or relaxed) on the changed layouts, (5) the highest
        # strict threshold among ties, so a changed label is noticed (relaxed) and patched rather than silently accepted,
        # (6) then the lowest relaxed threshold and the widest margin.
        changed_ok = sum(v["relaxed"] for (_, i, var), v in ev.items() if var != 0)
        key = (-false_ids, -false_no, v0("strict", "ids") + v0("strict", "no-ids"), changed_ok, strict, -relaxed, margin)
        grid.append((key, strict, relaxed, margin, ev))
        if best is None or key > best[0]:
            best = (key, strict, relaxed, margin, ev)
    assert best is not None
    _, strict, relaxed, margin, ev = best
    cur = evaluate(rows, locators.STRICT, locators.RELAXED, locators.MARGIN)

    def table(ev: dict, title: str) -> list[str]:
        lines = [f"### {title}", "", "| Role | IDs | Variant | Positive cases | Right at strict | Right at strict or relaxed | Hard negatives | Wrong element at strict | Wrong element at relaxed |",
                 "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for (role, ids, v), o in sorted(ev.items()):
            p = max(1, o["pos"])
            lines.append(f"| {role} | {ids} | {v} | {o['pos']} | {o['strict'] / p:.0%} | {o['relaxed'] / p:.0%} | {o['n'] - o['pos']} | {o['false_strict']} | {o['false_relaxed']} |")
        return lines + [""]

    md = ["# Locator threshold tuning (SkyLark, all four layouts)", "",
          f"{len(rows)} cases: {len({r['locator'] for r in rows})} routine locators × recorded screens that contain their element, each scored "
          "with and without resource IDs. Right = the true element wins (score ≥ threshold and ahead of the runner-up by the margin); "
          "wrong = another element wins.", "",
          f"**Chosen:** STRICT {strict}, RELAXED {relaxed}, MARGIN {margin} (no wrong element wins at either threshold, then most right answers).", "",
          f"In use: STRICT {locators.STRICT}, RELAXED {locators.RELAXED}, MARGIN {locators.MARGIN}.", ""]
    md += table(ev, f"Chosen thresholds ({strict} / {relaxed} / {margin})")
    if (strict, relaxed, margin) != (locators.STRICT, locators.RELAXED, locators.MARGIN):
        md += table(cur, f"Thresholds in use ({locators.STRICT} / {locators.RELAXED} / {locators.MARGIN})")
    hard = [r for r in rows if not r["use_ids"] and r["positive"] and r["truth"] < relaxed]
    md += ["### Hardest cases without IDs (true element below the relaxed threshold)", ""]
    worst = sorted(hard, key=lambda r: r["truth"])[:12]
    md += [f"- {r['locator']} (variant {r['variant']}): true {r['truth']:.2f}, best wrong {r['wrong']:.2f}" for r in worst] or ["- none"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "locator_tuning.md").write_text("\n".join(md) + "\n")
    (OUT / "locator_tuning.json").write_text(json.dumps({"chosen": [strict, relaxed, margin], "cases": len(rows)}, indent=1))
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
