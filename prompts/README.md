# prompts/: build logs

This folder is the project's working record, kept public as part of how Envoy was built. It isn't documentation, and
it isn't evidence on its own.

- **What's here:** the phase prompts (`phase-0.md`, `phase-2.md` … `phase-7.md`; Phase 1 had no separate
  prompt), the plans written from them (`*-plan.md`), and the
  report each build session wrote when it finished (`*-report.md`, some with a folder of screenshots). They were written
  for the next session, so they use working names: session names, branch and staging names, backlog numbers, and "the
  user" for the author.
- **What they're worth:** a dated account of what was tried, what broke and why. A report's numbers are what that
  session measured at the time; later work may have changed them.
- **Where the evidence is:** raw results in [`eval/results/`](../eval/results/) (the evaluation's runs record their
  commit, tier and cost), learned routines and their version history in [`data/routines/`](../data/routines/), the Spark agent's runs
  in [`agents/meta-agent/evidence/`](../agents/meta-agent/evidence/), and the write-ups in [`docs/`](../docs/README.md).
  The [README](../README.md) and [`docs/submission.md`](../docs/submission.md) cite those first, and a report here only
  where nothing else records it.
