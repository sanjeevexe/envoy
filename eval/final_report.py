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
    if note:  # below everything (the saved image grows to include it), so it never sits on an axis label
        fig.text(0.01, -0.03, note, fontsize=9, color=MUTED, ha="left", va="top", wrap=True)
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
    width = 0.22
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
    ax.set_title("Success by system and layout (SkyLark core set)", pad=34)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, handlelength=1.2, borderaxespad=0.3)
    cells = max(v["cells"] for v in sm.values())
    seeds = cells // 10
    return _finish(fig, ax, "success_by_system_and_layout",
                   f"{cells} requests per bar (10 tasks × {seeds} seed{'s' if seeds != 1 else ''} of bookings). Checked in code on the app's state; "
                   "anything else changed in the app counts as a failure.")


def chart_repeats(d: dict[str, Any], systems: dict[str, Any] | None) -> str | None:
    rows = d["rows"]
    ns = sorted({r["n"] for r in rows})
    if len(ns) < 2:
        return None
    from matplotlib.ticker import FixedLocator, FuncFormatter
    plt = _plt()
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(15, 4.9))
    env_cost = [med([r["standard_usd"] for r in rows if r["n"] == n], 5) for n in ns]
    env_s = [med([r["duration_s"] for r in rows if r["n"] == n], 1) for n in ns]
    agent = [r for r in (systems or {}).get("rows", []) if r["system"] == "agent" and r["layout"] == 0 and r["try"] == 1]
    a_cost, a_s = med([r["standard_usd"] for r in agent], 5), med([r["duration_s"] for r in agent], 1)
    # Cumulative: the mean over tasks of each task's running total (medians don't add up).
    tasks = sorted({r["task"] for r in rows})
    per = {t: {r["n"]: r["standard_usd"] for r in rows if r["task"] == t} for t in tasks}
    env_cum = [sum(sum(per[t].get(k, 0) for k in ns if k <= n) for t in tasks) / len(tasks) for n in ns]
    a_mean = sum(r["standard_usd"] for r in agent) / len(agent) if agent else None
    env_kw = dict(color=COLOR["routine"], linewidth=2, marker="o", markersize=7, markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    ag_kw = dict(color=COLOR["agent"], linewidth=2, zorder=2)
    money = FuncFormatter(lambda v, _: f"${v:.3f}".rstrip("0").rstrip(".") if v < 0.01 else f"${v:.2f}")

    a1.plot(ns, env_cost, label="Envoy: the agent once, then the routine", **env_kw)
    if a_cost is not None:
        a1.plot(ns, [a_cost] * len(ns), label="Full agent every time", **ag_kw)
    a1.set_yscale("log")
    a1.yaxis.set_major_locator(FixedLocator([0.001, 0.002, 0.005, 0.01, 0.02, 0.05]))
    a1.yaxis.set_minor_locator(FixedLocator([]))
    a1.yaxis.set_major_formatter(money)
    a1.set_ylim(0.0012, 0.08)
    a1.set_title("Cost of each request (log scale)")
    a1.annotate(f"${env_cost[0]:.3f}: the agent's run\n+ compiling the routine", (ns[0], env_cost[0]), textcoords="offset points", xytext=(10, -14), fontsize=9, color=INK2)
    a1.annotate(f"${env_cost[-1]:.4f}", (ns[-1], env_cost[-1]), textcoords="offset points", xytext=(0, -16), fontsize=9, color=INK2, ha="center")
    if a_cost is not None:
        a1.annotate(f"${a_cost:.4f}", (ns[-1], a_cost), textcoords="offset points", xytext=(0, 7), fontsize=9, color=INK2, ha="center")

    a2.plot(ns, env_s, **env_kw)
    if a_s is not None:
        a2.plot(ns, [a_s] * len(ns), **ag_kw)
    a2.set_ylim(0, max(env_s + ([a_s] if a_s else [])) * 1.18)
    a2.set_title("Seconds for each request")
    a2.annotate(f"{env_s[0]:.0f} s", (ns[0], env_s[0]), textcoords="offset points", xytext=(10, -4), fontsize=9, color=INK2)
    a2.annotate(f"{env_s[-1]:.1f} s", (ns[-1], env_s[-1]), textcoords="offset points", xytext=(0, -16), fontsize=9, color=INK2, ha="center")
    if a_s is not None:
        a2.annotate(f"{a_s:.1f} s", (ns[-1], a_s), textcoords="offset points", xytext=(0, 7), fontsize=9, color=INK2, ha="center")

    a3.plot(ns, env_cum, **env_kw)
    if a_mean is not None:
        a_cum = [a_mean * n for n in ns]
        a3.plot(ns, a_cum, **ag_kw)
        even = next((n for n, e, a in zip(ns, env_cum, a_cum) if e <= a), None)
        if even:
            a3.annotate(f"even after {even} requests", (even, env_cum[ns.index(even)]), textcoords="offset points", xytext=(-6, 14),
                        fontsize=9, color=INK2, ha="right")
    a3.yaxis.set_major_formatter(money)
    a3.set_ylim(0, max(env_cum + ([a_mean * ns[-1]] if a_mean else [])) * 1.15)
    a3.set_title("Total cost so far (mean per task)")
    for ax in (a1, a2, a3):
        ax.set_xticks(ns)
        ax.set_xlabel("Request number")
        ax.grid(axis="x", visible=False)
        ax.tick_params(length=0)
    fig.suptitle("First run vs later runs: the same kind of request, ten times, a new booking each time", x=0.01, y=0.99, ha="left",
                 fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.legend(*a1.get_legend_handles_labels(), loc="lower left", bbox_to_anchor=(0.01, 0.875), ncol=2, handlelength=1.6)
    return _finish(fig, a3, "cost_and_time_over_repeated_runs",
                   "SkyLark's 10 core tasks, standard prices. Request 1: the agent's run, compiling the routine (Muse Wonder) and verifying it. "
                   "Later requests: the matcher's one call, then the routine. The agent's line: its median on the same tasks (left, middle), its mean added up (right).")


def chart_change(d: dict[str, Any]) -> str | None:
    exps = d.get("experiments") or []
    layouts = sorted({e["layout"] for e in exps})
    if not layouts:
        return None
    from final_core import saved_by
    plt = _plt()
    fig, ax = plt.subplots(figsize=(11, 4.6))
    # What saved each routine on first meeting the change, cheapest first (categorical slots in fixed order; failure is a status).
    kinds = [("nothing needed", "No change needed", "#2a78d6"), ("relaxed match or scroll", "Relaxed match (no model call)", "#eb6834"),
             ("local repair", "Local repair (model calls)", "#1baf7a"), ("the agent", "Full agent took over", "#eda100"),
             ("failed", "Failed", "#d03b3b")]
    ys = list(range(len(layouts)))[::-1]
    lefts = [0] * len(layouts)
    for key, name, color in kinds:
        vals = [sum(saved_by(e["first"]) == key for e in exps if e["layout"] == layout) for layout in layouts]
        if not any(vals):
            continue
        bars = ax.barh(ys, vals, left=lefts, height=0.56, color=color, label=name, edgecolor=SURFACE, linewidth=2, zorder=3)
        for b, v in zip(bars, vals):
            if v:
                ax.text(b.get_x() + b.get_width() / 2, b.get_y() + b.get_height() / 2, str(v), ha="center", va="center", fontsize=10,
                        color="white" if color in ("#2a78d6", "#d03b3b") else INK)
        lefts = [a + v for a, v in zip(lefts, vals)]
    n = max(lefts)
    ax.set_yticks(ys, [LAYOUTS[x].replace("\n", " ") for x in layouts])
    ax.set_xlim(0, n)
    ax.set_xticks(range(0, n + 1, 2))
    ax.set_xlabel(f"Routines (of {n}), on first meeting the change")
    ax.grid(axis="y", visible=False)
    trials = [e["trial"] for e in exps if e.get("trial")]
    after_ok = sum(e["after"]["passed"] and e["after"]["calls"] == 0 for e in exps)
    calls = sum(e["first"]["calls"] for e in exps)
    ax.set_title(f"How routines got past each injected UI change: {sum(e['first']['passed'] for e in exps)} of {len(exps)} recovered, "
                 f"{calls} model calls in all", pad=34)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=5, handlelength=1.2, borderaxespad=0.3, fontsize=9.5)
    return _finish(fig, ax, "recovery_by_injected_change",
                   f"Each of the {n} routines, compiled on the original layout, meets each changed layout on a new booking. Its patches then went on "
                   f"trial: {sum(t['passed'] for t in trials)} of {len(trials)} passed, and the active version ran on another booking with no model "
                   f"call {after_ok} of {len(exps)} times.")


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

def _render(name: str, d: dict[str, Any]) -> str | None:
    """A suite's tables, rendered again from its JSON (so the report never shows stale formatting)."""
    import final_core as fc
    if name == "systems":
        return fc.systems_md(d["rows"])
    if name == "repeats":
        return fc.repeats_md(d["rows"])
    if name == "change":
        return fc.change_md(d.get("new_inputs", []), d.get("experiments", []))
    if name == "sizes":
        return fc.sizes_md(d["devices"])
    if name == "real":
        import final_real
        return final_real.real_md(d["workflows"], d["stages"])
    if name == "memory":
        import final_memory
        return final_memory.memory_md(d)
    if name in ("safety", "injection"):
        import final_safety
        return final_safety.safety_md(d.get("screens", {}), d.get("live", {})) if name == "safety" else \
            final_safety.injection_md(d.get("screens", {}), d.get("inbox", {}))
    return None


def _demote(text: str) -> str:
    """A suite's own headings, one level under its section in the report."""
    return re.sub(r"(?m)^(#{2,5}) ", r"#\1 ", text)


def _body(name: str, d: dict[str, Any] | None = None) -> str:
    from final_common import header
    if d is not None and (body := _render(name, d)) is not None:
        text = header(d["meta"], name) + body
        (OUT / f"{name}.md").write_text(text)
        return text.split("\n", 2)[2]
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
            firsts = [r for r in d["rows"] if r["system"] == key and r["try"] == 1]
            if vs:
                c = sum(v["cells"] for v in vs)
                out.append(f"{label} {pct(sum(v['first_try'] for v in vs), c)} first try, {sum(v['within_3'] for v in vs)}/{c} within 3, "
                           f"median {med([r['calls'] for r in firsts])} calls, {med([r['duration_s'] for r in firsts])} s")
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


def targets(data: dict[str, Any]) -> list[str]:
    """The design doc's success targets, each measured by a suite."""
    rows = []
    sy, ch, rp, mem, sa, inj = (data.get(k) for k in ("systems", "change", "repeats", "memory", "safety", "injection"))
    if sy:
        a0 = [r for r in sy["rows"] if r["system"] == "agent" and r["layout"] == 0 and r["try"] == 1]
        aall = [r for r in sy["rows"] if r["system"] == "agent" and r["try"] == 1]
        rows.append(("First-run task success on the test task set", "70% or more",
                     f"{pct(sum(r['passed'] for r in a0), len(a0))} on the original layout, {pct(sum(r['passed'] for r in aall), len(aall))} across all 4 layouts (the agent, first try)"))
    if ch and ch.get("new_inputs"):
        ni = ch["new_inputs"]
        rows.append(("Routine success on new inputs", "85% or more", f"{pct(sum(r['passed'] for r in ni), len(ni))} ({sum(r['passed'] and r['calls'] == 0 for r in ni)} with no model call)"))
    if ch and ch.get("experiments"):
        ex = ch["experiments"]
        rows.append(("Recovery after an injected UI change", "70% or more", f"{pct(sum(e['first']['passed'] for e in ex), len(ex))} over 5 kinds of change"))
    if rp:
        first = [r for r in rp["rows"] if r["n"] == 1]
        later = [r for r in rp["rows"] if r["n"] > 1]
        if first and later:
            f_calls, l_calls = sum(r["calls"] for r in first) / len(first), sum(r["calls"] for r in later) / len(later)
            rows.append(("Model calls on a routine rerun vs the first run", "80% fewer",
                         f"{100 * (1 - l_calls / f_calls):.0f}% fewer ({l_calls:.1f} vs {f_calls:.1f} per request, the matcher's call included)"))
            longest = max((r for r in later if r.get("passed")), key=lambda r: r["duration_s"], default=None)
            rows.append(("Time per task on a routine rerun", "Under 30 s for a 10-step task",
                         f"median {med([r['duration_s'] for r in later])} s; slowest {longest['duration_s']} s ({longest['task']})" if longest else "–"))
    if mem:
        tr = [mem[k]["matching"]["traceable"] for k in ("emails_large", "emails_new") if k in mem]
        if tr:
            rows.append(("Facts traceable to a source", "100%", "100%" if all(tr) else "not all"))
    if sa or inj:
        live = (sa or {}).get("live", {}).get("rows", [])
        ir = [r for r in (inj or {}).get("screens", {}).get("rows", []) if r["irreversible_without_approval"]]
        changed = [r for r in live if r["state_changed"]]
        rows.append(("Irreversible actions taken without approval", "0",
                     f"{len(changed) + len(ir)} (Envoy: {len(live)} declined live runs, {len((inj or {}).get('screens', {}).get('rows', []))} runs with planted instructions)"))
    return ["| Target | Goal | Measured |", "| --- | --- | --- |"] + [f"| {a} | {b} | {c} |" for a, b, c in rows]


def build() -> None:
    data = {n: load(n) for n in ("compile", "systems", "repeats", "change", "sizes", "real", "memory", "safety", "injection", "interfaces")}
    if data["real"]:
        import final_real
        data["real"]["stages"] = final_real.stages(data["real"]["workflows"])  # with the hand checks given since the run
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
    md += ["", "## The design's success targets", ""] + targets(data) + [""]
    for n, title in titles.items():
        md += [f"## {title}", ""]
        if charts.get(n):
            md += [f"![{title}]({charts[n]})", ""]
        md += [_demote(_body(n, data[n])), f"Data: `eval/results/final/{n}.json`.", ""]
        if n == "systems":
            md += tiers_section(data["systems"])
    md += ["## 8. AndroidWorld", "", _demote(aw["section"]), "",
           "## Reproduce", "", "```bash", "eval/run_final.sh            # every suite in order, one emulator at a time", "```", "",
           "Or one suite: `uv run --project backend python eval/run_final.py <suite>` (see its `--help`). The real-app suite needs `envoy-real` "
           "signed in to the test Google account; the interface checks need the API running with the demo profile.", ""]
    (OUT / "report.md").write_text("\n".join(md))
    print(f"wrote {(OUT / 'report.md').relative_to(REPO)} with {sum(1 for c in charts.values() if c)} charts")


def tiers_section(systems: dict[str, Any] | None) -> list[str]:
    """The Contributor tier against the standard tier: the full agent, the original layout, the same seed's 10 tasks."""
    contrib = load("systems-contributor")
    if not contrib or not systems:
        return []
    c = [r for r in contrib["rows"] if r["system"] == "agent" and r["layout"] == 0 and r["try"] == 1]
    cells = {(r["task"], r["seed"]) for r in c}
    s = [r for r in systems["rows"] if r["system"] == "agent" and r["layout"] == 0 and r["try"] == 1 and (r["task"], r["seed"]) in cells]
    if not c or len(s) != len(c):
        return []
    row = lambda name, rs: (f"| {name} | {sum(r['passed'] for r in rs)}/{len(rs)} | {sum(r['steps'] for r in rs)} | {sum(r['calls'] for r in rs)} | "  # noqa: E731
                            f"{sum(r['duration_s'] for r in rs):.0f} s | {max(r['steps'] for r in rs)} |")
    return ["## 1c. The Contributor tier against the standard tier", "",
            f"The full agent on the same {len(c)} cells (each core task on the original layout, the same seed and booking), first try only. "
            f"Contributor: {_ran_on(contrib)}; standard: {_ran_on(systems)}. Every measurement in this report runs on the standard tier.", "",
            "| Tier | Right | Actions | Model calls | Time, summed | Most actions in one task |", "| --- | --- | --- | --- | --- | --- |",
            row("Standard (`muse-spark-1.3`)", s), row("Contributor (`muse-spark-1.3-contributor`)", c), "",
            "Data: `eval/results/final/systems-contributor.json` beside `systems.json`.", ""]


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

