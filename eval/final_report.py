"""Build eval/results/final/report.md and its charts (charts/*.png) from the suites' JSON.

  uv run --project backend python eval/run_final.py report

Every number comes from eval/results/final/<suite>.json; the report says which commit each suite ran on, and flags any
suite that did not run on the `eval-final` tag. Charts are plain matplotlib PNGs, legible on their own (title, axis
labels, direct value labels, a legend for two or more series), so they can be reused in the write-up.
"""

from __future__ import annotations

import re
from typing import Any

from final_common import OUT, REPO, load, med, pct

CHARTS = OUT / "charts"
LAYOUTS = {0: "Original", 1: "Moved button", 2: "Renamed labels", 3: "Extra screen", 4: "Hidden IDs", 5: "Renamed +\nhidden IDs"}
SYSTEMS = [("routine", "Envoy routines"), ("agent", "Full agent every time"), ("fixed", "Fixed replay")]
# The reference categorical palette (validated: 3 slots, all pairs, light mode); color follows the system, never its rank.
COLOR = {"routine": "#2a78d6", "agent": "#eb6834", "fixed": "#1baf7a"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"], "font.size": 11, "axes.edgecolor": AXIS, "axes.linewidth": 1,
        "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK, "axes.titlesize": 14, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.titlepad": 14, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 1, "axes.axisbelow": True, "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.labelcolor": INK2,
    })
    return plt


def _finish(fig, ax, name: str, note: str = "") -> str:
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)
    if note:
        fig.text(0.01, 0.01, note, fontsize=9, color=MUTED, ha="left", va="bottom")
    CHARTS.mkdir(parents=True, exist_ok=True)
    path = CHARTS / f"{name}.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return f"charts/{name}.png"


def chart_systems(d: dict[str, Any]) -> str | None:
    from final_core import systems_summary
    sm = systems_summary(d["rows"])
    layouts = sorted({v["layout"] for v in sm.values()})
    if not layouts:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(10, 5.2))
    width = 0.24
    for i, (key, name) in enumerate(SYSTEMS):
        xs, ys, labels = [], [], []
        for j, layout in enumerate(layouts):
            v = sm.get(f"{key}|{layout}")
            if not v:
                continue
            xs.append(j + (i - 1) * (width + 0.02))
            ys.append(100 * v["first_try"] / v["cells"])
            labels.append(f"{100 * v['first_try'] / v['cells']:.0f}%")
        bars = ax.bar(xs, ys, width=width, color=COLOR[key], label=name, zorder=3)
        for b, lab in zip(bars, labels):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, lab, ha="center", va="bottom", fontsize=9, color=INK2)
    ax.set_xticks(range(len(layouts)), [LAYOUTS[x] for x in layouts])
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("Tasks right on the first try")
    ax.set_title("Success by system and layout (SkyLark core set)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
    cells = max(v["cells"] for v in sm.values())
    return _finish(fig, ax, "success_by_system_and_layout",
                   f"{cells} requests per bar (10 tasks × {cells // 10} seeds of bookings). Checked in code on the app's state; anything else changed counts as a failure.")


def chart_repeats(d: dict[str, Any], systems: dict[str, Any] | None) -> str | None:
    rows = d["rows"]
    ns = sorted({r["n"] for r in rows})
    if len(ns) < 2:
        return None
    plt = _plt()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6))
    env_cost = [med([r["standard_usd"] for r in rows if r["n"] == n], 5) for n in ns]
    env_s = [med([r["duration_s"] for r in rows if r["n"] == n], 1) for n in ns]
    agent = [r for r in (systems or {}).get("rows", []) if r["system"] == "agent" and r["layout"] == 0 and r["try"] == 1]
    a_cost, a_s = med([r["standard_usd"] for r in agent], 5), med([r["duration_s"] for r in agent], 1)
    for ax, env, ag, unit, title in ((a1, env_cost, a_cost, "$", "Cost per request"), (a2, env_s, a_s, "s", "Time per request")):
        ax.plot(ns, env, color=COLOR["routine"], linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=2, label="Envoy (agent once, then the routine)", zorder=3)
        if ag is not None:
            ax.plot(ns, [ag] * len(ns), color=COLOR["agent"], linewidth=2, label="Full agent every time", zorder=2)
        ax.set_xticks(ns)
        ax.set_xlabel("Request number (same task, a new booking each time)")
        ax.set_title(title)
        if unit == "$":
            ax.set_yscale("log")
            ax.set_ylabel("Median $ per request, standard prices (log)")
            ax.annotate(f"${env[0]:.3f}\nagent + compile", (ns[0], env[0]), textcoords="offset points", xytext=(10, -4), fontsize=9, color=INK2)
            ax.annotate(f"${env[-1]:.4f}", (ns[-1], env[-1]), textcoords="offset points", xytext=(-10, 8), fontsize=9, color=INK2, ha="right")
            if ag is not None:
                ax.annotate(f"${ag:.4f}", (ns[-1], ag), textcoords="offset points", xytext=(-10, 6), fontsize=9, color=INK2, ha="right")
        else:
            ax.set_ylabel("Median seconds per request")
            ax.set_ylim(0, max(env + ([ag] if ag else [])) * 1.15)
            ax.annotate(f"{env[-1]:.1f} s", (ns[-1], env[-1]), textcoords="offset points", xytext=(-10, 8), fontsize=9, color=INK2, ha="right")
            if ag is not None:
                ax.annotate(f"{ag:.1f} s", (ns[-1], ag), textcoords="offset points", xytext=(-10, 6), fontsize=9, color=INK2, ha="right")
        ax.grid(axis="x", visible=False)
        ax.tick_params(length=0)
    a1.legend(loc="upper center", bbox_to_anchor=(1.1, -0.18), ncol=2)
    fig.suptitle("First run vs later runs: the same request, ten times", x=0.01, ha="left", fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout()
    return _finish(fig, a2, "cost_and_time_over_repeated_runs",
                   "Medians over the 10 core tasks. Request 1 includes compiling (Muse Wonder) and verifying the routine; later requests include the matcher's one call.")


def chart_change(d: dict[str, Any]) -> str | None:
    exps = d.get("experiments") or []
    layouts = sorted({e["layout"] for e in exps})
    if not layouts:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(10, 5))
    series = [("first", "Recovered on first meeting the change", COLOR["routine"]),
              ("after", "Then ran with no model call", COLOR["agent"])]
    width = 0.34
    for i, (key, name, color) in enumerate(series):
        ys = []
        for layout in layouts:
            es = [e for e in exps if e["layout"] == layout]
            ok = sum(e[key]["passed"] and (key == "first" or e[key]["calls"] == 0) for e in es)
            ys.append(100 * ok / len(es))
        xs = [j + (i - 0.5) * (width + 0.02) for j in range(len(layouts))]
        bars = ax.bar(xs, ys, width=width, color=color, label=name, zorder=3)
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5, f"{b.get_height():.0f}%", ha="center", va="bottom", fontsize=9, color=INK2)
    ax.set_xticks(range(len(layouts)), [LAYOUTS[x] for x in layouts])
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("Routines (of 10)")
    ax.set_title("Recovery by type of injected UI change")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    return _finish(fig, ax, "recovery_by_injected_change",
                   "Each of the 10 routines, compiled on the original layout, meets each changed layout on a new booking (repair and the agent allowed); its patches go on trial, then the active version runs on another booking.")


def chart_real(d: dict[str, Any]) -> str | None:
    s = d.get("stages")
    if not s:
        return None
    plt = _plt()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    names = ["1. Agent's first run right", "2. Compiled into a routine", "3. Rerun right, no model call", "4. Right on a new input"]
    vals = [s["first_run"], s["compiled"], s["same_input"], s["new_input"]]
    tots = [s["n"], s["n"], s["n"], s["n_second"]]
    ys = list(range(len(names)))[::-1]
    bars = ax.barh(ys, [v / t * 100 for v, t in zip(vals, tots)], height=0.5, color=COLOR["routine"], zorder=3)
    for b, v, t in zip(bars, vals, tots):
        ax.text(b.get_width() + 1.5, b.get_y() + b.get_height() / 2, f"{v}/{t}", va="center", fontsize=10, color=INK2)
    ax.set_yticks(ys, names)
    ax.set_xlim(0, 115)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.grid(axis="y", visible=False)
    ax.set_title("Real apps: where learning holds and where it breaks")
    return _finish(fig, ax, "real_apps_stages", f"{s['n']} read-only workflows on real Play Store apps (envoy-real); stage 4 counts the workflows that have a second input.")


# ---- the report ----------------------------------------------------------------------------------------------------------

def _body(name: str) -> str:
    p = OUT / f"{name}.md"
    if not p.exists():
        return "_Not run yet._\n"
    text = p.read_text()
    return text.split("\n", 2)[2] if text.startswith("# ") else text  # drop the suite's own title; keep its run line and tables


def _ran_on(d: dict[str, Any] | None) -> str:
    if not d:
        return "not run"
    code = d["meta"]["code"]
    return "`eval-final`" if code["is_eval_final"] else f"`{code['short']}`{' (uncommitted changes)' if code['dirty'] else ''}"


def headline(name: str, d: dict[str, Any] | None) -> str:
    if not d:
        return "not run yet"
    if name == "systems":
        from final_core import systems_summary
        sm = systems_summary(d["rows"])
        out = []
        for key, label in SYSTEMS:
            vs = [v for v in sm.values() if v["system"] == key]
            if vs:
                c = sum(v["cells"] for v in vs)
                out.append(f"{label} {pct(sum(v['first_try'] for v in vs), c)} first try, {sum(v['within_3'] for v in vs)}/{c} within 3, "
                           f"median {med([v['median_calls'] for v in vs])} calls")
        return "; ".join(out)
    if name == "repeats":
        rows = d["rows"]
        later = [r for r in rows if r["n"] > 1]
        first = [r for r in rows if r["n"] == 1]
        return (f"request 1 median ${med([r['standard_usd'] for r in first], 4)} and {med([r['duration_s'] for r in first])} s; requests 2–10 "
                f"{sum(r['passed'] for r in later)}/{len(later)} right, median {med([r['calls'] for r in later])} call, "
                f"${med([r['standard_usd'] for r in later], 4)}, {med([r['duration_s'] for r in later])} s")
    if name == "change":
        ni, ex = d.get("new_inputs", []), d.get("experiments", [])
        return (f"new inputs {pct(sum(r['passed'] for r in ni), len(ni))} ({sum(r['passed'] and r['calls'] == 0 for r in ni)} with no model call); "
                f"injected changes recovered {pct(sum(e['first']['passed'] for e in ex), len(ex))}, then "
                f"{sum(e['after']['passed'] and e['after']['calls'] == 0 for e in ex)}/{len(ex)} ran alone with no model call")
    if name == "sizes":
        return "; ".join(f"{k} {sum(r['passed'] for r in v['rows'])}/{len(v['rows'])}" for k, v in d["devices"].items())
    if name == "real":
        s = d.get("stages", {})
        return (f"first run {s.get('first_run')}/{s.get('n')}, compiled {s.get('compiled')}/{s.get('n')}, rerun right with no call "
                f"{s.get('same_input')}/{s.get('n')}, new input {s.get('new_input')}/{s.get('n_second')}; bot checks: {', '.join(s.get('bot_checks', [])) or 'none'}")
    if name == "memory":
        parts = [k for k in ("emails_large", "emails_new", "screens", "photos") if k in d]
        out = []
        if parts:
            f = sum(d[k]["attributes"]["found"] for k in parts)
            w = sum(d[k]["attributes"]["wrong"] for k in parts)
            m = sum(d[k]["attributes"]["missing"] for k in parts)
            out.append(f"extraction {pct(f, f + w + m)} on {sum(d[k]['items'] for k in parts)} labeled items, {w} wrong")
        if "stale" in d:
            rs = d["stale"]["rows"]
            out.append(f"stale facts served without a warning {sum(r['stale_without_warning'] for r in rs)}/{sum(r['stale'] for r in rs)}")
        return "; ".join(out)
    if name == "safety":
        rows = [r for r in d.get("screens", {}).get("rows", []) if "missing" not in r]
        irr = [r for r in rows if r["irreversible"]]
        rev = [r for r in rows if not r["irreversible"]]
        live = d.get("live", {}).get("rows", [])
        return (f"irreversible caught {sum(r['flagged_gate'] for r in irr)}/{len(irr)} (code alone {sum(r['flagged_code'] for r in irr)}); "
                f"reversible flagged by code {sum(r['flagged_code'] for r in rev)}/{len(rev)}; live declines held {sum(r['held'] for r in live)}/{len(live)}")
    if name == "injection":
        rows = d.get("screens", {}).get("rows", [])
        inbox = d.get("inbox", {})
        ag = [r for r in rows if r["by"] == "agent"]
        return (f"agent right {sum(r['passed'] for r in ag)}/{len(ag)} with planted text, tried to follow it {sum(bool(r['followed_attempts']) for r in ag)}; "
                f"irreversible without approval {sum(bool(r['irreversible_without_approval']) for r in rows)}; injected values stored from email "
                f"{len(inbox.get('violations', []))}")
    if name == "interfaces":
        return "; ".join(f"{k} {v.get('result', '?')}" for k, v in d.get("checks", {}).items())
    return ""


def build() -> None:
    data = {n: load(n) for n in ("compile", "systems", "repeats", "change", "sizes", "real", "memory", "safety", "injection", "interfaces")}
    charts = {}
    if data["systems"]:
        charts["systems"] = chart_systems(data["systems"])
    if data["repeats"]:
        charts["repeats"] = chart_repeats(data["repeats"], data["systems"])
    if data["change"]:
        charts["change"] = chart_change(data["change"])
    if data["real"]:
        charts["real"] = chart_real(data["real"])
    titles = {"compile": "0. The core set's routines", "systems": "1. Three systems on SkyLark's core set", "repeats": "2. First run vs later runs",
              "change": "3. Routines under change", "sizes": "3b. Three screen sizes and the real phone", "real": "4. Real apps",
              "memory": "5. Memory", "safety": "6. Safety: irreversible actions", "injection": "6b. Safety: planted instructions",
              "interfaces": "7. Interfaces, end to end"}
    on_tag = [n for n, d in data.items() if d and d["meta"]["code"]["is_eval_final"]]
    total_std = sum((d["meta"]["cost"].get("standard_usd") or 0) for d in data.values() if d)
    total_billed = sum((d["meta"]["cost"].get("billed_usd") or 0) for d in data.values() if d)
    md = ["# Envoy: final evaluation", "",
          "Every suite runs from a known state and scores with code (the app's real state, or the right answer on screen), never a model's judgment. "
          "Dollars are at Meta's standard prices whatever tier was billed. Built by `eval/run_final.py report` from the JSON beside this file.", "",
          f"**Ran on:** {len(on_tag)} of {sum(1 for d in data.values() if d)} suites on the `eval-final` tag"
          + ("." if len(on_tag) == sum(1 for d in data.values() if d) else "; the others are marked below (earlier commits are measurements, not final numbers)."),
          f"**Cost of these runs:** ${total_std:.2f} at standard prices (${total_billed:.2f} billed).", "",
          "| Suite | Result | Ran on |", "| --- | --- | --- |"]
    for n, title in titles.items():
        md.append(f"| {title} | {headline(n, data[n]) if n != 'compile' else (str(sum(r.get('status') == 'added' for r in data[n]['rows'])) + ' of ' + str(len(data[n]['rows'])) + ' routines compiled and verified' if data[n] else 'not run yet')} | {_ran_on(data[n])} |")
    aw = androidworld()
    md.append(f"| 8. AndroidWorld (the other chat's branch) | {aw['headline']} | `androidworld` branch |")
    md.append("")
    for n, title in titles.items():
        md += [f"## {title}", ""]
        if charts.get(n):
            md += [f"![{title}]({charts[n]})", ""]
        md += [_body(n), f"Data: `eval/results/final/{n}.json`.", ""]
    md += ["## 8. AndroidWorld", "", aw["section"], "",
           "## Reproduce", "", "```bash", "eval/run_final.sh            # every suite in order, one emulator at a time", "```", "",
           "Or one suite: `uv run --project backend python eval/run_final.py <suite>` (see its `--help`). The real-app suite needs `envoy-real` "
           "signed in to the test Google account; the interface checks need the API running with the demo profile.", ""]
    (OUT / "report.md").write_text("\n".join(md))
    print(f"wrote {(OUT / 'report.md').relative_to(REPO)} with {sum(1 for c in charts.values() if c)} charts")


def androidworld() -> dict[str, str]:
    """The other chat's results, read from its branch (never merged here by this script)."""
    import subprocess
    r = subprocess.run(["git", "show", "androidworld:docs/androidworld-results.md"], cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return {"headline": "not available yet", "section": "_The AndroidWorld results (`docs/androidworld-results.md` on the `androidworld` branch) don't exist yet._"}
    text = r.stdout
    first = next((line for line in text.splitlines() if re.search(r"\d+(\.\d+)?\s*%|\d+\s*/\s*116", line)), "see the branch's report")
    return {"headline": first.strip("#* ")[:200], "section": "From `docs/androidworld-results.md` on the `androidworld` branch (its own setting and caveats apply):\n\n"
            + "\n".join(text.splitlines()[:60])}

