# Connecting agents to Envoy

Envoy is the phone layer agents call. Any MCP client can use it. Three have, so far: Muse (Meta's assistant, on the
Mac and in its iPhone app), the Spark agent in `agents/meta-agent/` (on Meta's models), and Claude Code. Each one gets
its own key, with only the tools you give it. Every task it starts says which agent asked ("from Claude").

What each tool does is in [backend/mcp_server/README.md](../backend/mcp_server/README.md). Muse's side (files from the
Mac, `phone_updates`, what was tested) is in [muse-link.md](muse-link.md).

## What an agent gets

- **The server:** `/mcp` on Envoy's address, Streamable HTTP, stateless. On this Mac that's `http://127.0.0.1:8700/mcp`.
  The public Funnel address serves `/mcp` and nothing else.
- **The key:** `Authorization: Bearer <key>` on every request. Keys are made in Envoy's Settings › Agents (below).
  `MCP_BEARER_TOKEN` in `.env` stays Muse's key.
- **The tools, in groups** (`backend/api/auth.py` `TOOL_GROUPS`):

  | Group | Tools |
  | --- | --- |
  | read | `get_task`, `wait_for_task`, `list_routines`, `memory_search`, `memory_get`, `phone_updates`, `list_phones` |
  | run | `run_task`, `run_routine`, `cross_post`, and every learned routine you share as a tool |
  | memory | `memory_note` |
  | files | `send_to_phone`, `get_file` |
  | triggers | `create_trigger` |

  `tools/list` shows an agent only its own groups' tools. A call to anything else gets a tool error that names the group
  to grant, and the connection stays fine. `run` calls are limited to 30 a minute per agent.
- **What no agent can do,** whatever its groups:
  - approve a step;
  - accept or decline Envoy's offers;
  - answer Envoy's questions for you.

  Envoy has no tool for any of these. Anything irreversible (a check-in, an order, a payment, a post) waits for your OK
  in Envoy on your iPhone, and the agent is told it's waiting for your OK there (it gets no approval link). A request
  from an agent never counts as you asking, so its irreversible steps always ask, unless you gave that routine a
  standing approval.

## Learned routines as tools

A routine Envoy learned can be a tool of its own, so an agent sees, say, `instagram_reel_song(song_title,
song_artist, caption, phone?)` in its tool list instead of having to know `run_routine`.

- **Share it:** turn on **Share with agents** on the routine's page, or in **Settings › Agents › Agent tools**. Every
  routine starts off. Settings › Agents lists each shared tool as an agent calls it, with its inputs, what it returns,
  and whether it asks before an irreversible step. A tool that appears while you watch is marked New.
- **It shows up at once.** The agent's next `tools/list` has it: no restart, no reconnect. Muse's client keeps an
  allowed list of tools, so the first time it may say it's adding the new tool before calling it.
- **It's in the run group.** An agent with only Read doesn't see it.
- **Calling it is `run_routine`** with that routine: the same approvals and the same "Before I start" lines.
  `run_routine` still runs any learned routine by name; sharing decides which ones are tools of their own.
- **Several posts in one request: `cross_post`.** It takes one entry per destination (a shared routine and its inputs)
  and runs them as one task with a part per post, one after another, TikTok last. It returns the task's id at once;
  `get_task` gives each part's outcome: done, failed, declined, waiting, outcome unknown (the post tap went through
  before its check; tell the person to look in that app) or not started. `cross_post` with `retry` set to the task's id
  runs only the parts that didn't post. Every post still waits for the person's OK, unless they gave that routine a
  standing approval (`backend/tests/test_crosspost.py`, `eval/results/agent-door/cross-post-pixel.json`).

Envoy also tells agents, through `phone_updates`, when it learns or repairs a routine, and names the tool when the
routine is shared.

## Phones and files

- **`list_phones`** shows the phones Envoy can use: Envoy's phone (a real Android phone), emulators on the Mac, or a
  cloud phone, whether each is online, and the apps Envoy runs on each. Pass a phone's `id` as `phone` to `run_task`,
  `run_routine` or a routine tool, or leave it out and Envoy picks. A real phone still asks you before each task.
- **`send_to_phone`** puts a photo or video from Envoy's outbox on the Mac (or an https URL) on a phone. To an emulator
  it goes at once; to a real phone it waits for your OK in Envoy.
- **`get_file`** gives an agent what Envoy kept from a task *that agent* started: the final screen, the approval
  screens, and links in the result, each as a download link that works for 10 minutes. It's in the files group.

## Hearing back

MCP over stateless HTTP can't push to an agent, so an agent checks `phone_updates` with the cursor from its last call.
It lists finished tasks, tasks waiting for you, changes Envoy noticed, files, Envoy's questions to you, routines learned
or repaired, and notifications a watch matched. A Muse scheduled task checked it about every 10 minutes on its own
(Oct 29). Envoy's own push to your iPhone is immediate.

## Make a key (you, in Envoy, about a minute)

1. Open Envoy's web app on the Mac → **Settings › Agents › Add an agent**.
2. Name it, such as "Claude" or "Spark agent". The name is what tasks show as "from …".
3. Under **What it may do**, keep **Read** and **Run** (the default), or pick others.
4. Press **Make its key**. The key is shown once: Envoy keeps only a fingerprint of it.
5. Press **Copy the key**, and paste it straight into the agent's settings (below). Never paste it into a chat.

Rotating a key stops the old one at once. Revoking an agent ends its access and leaves every other agent's key working,
Muse's included. Settings shows when each agent was last seen.

## Claude Code (terminal, or the Code tab in the Claude desktop app)

Claude Code sends a bearer header to an HTTP MCP server, so Envoy's agent key works as is. With the key on the
clipboard (step 5 above), in a terminal:

```bash
claude mcp add --transport http --scope user envoy http://127.0.0.1:8700/mcp --header "Authorization: Bearer $(pbpaste)"
```

- `$(pbpaste)` puts the key in Claude Code's settings (`~/.claude.json`), not in your shell history.
- `--scope user` makes Envoy available in every project. Leave it out to add Envoy to the current project only.
- Check it with `claude mcp list`: `envoy` should say connected.
- In a new Claude Code session, `/mcp` lists Envoy's tools.

**Try it:** "Use Envoy to check the status of SkyLark flight SL 1190." Claude calls a routine (or `run_task`) and then
`get_task`. The task shows in Envoy as "from Claude". Then ask "Check me in for my SkyLark flight to Chicago" and
"approve it for me". Claude should say only you can approve, in Envoy on your iPhone, because Envoy gave it no way to.

**Tested Nov 1** with a "Claude" key (Read and Run), on the live Envoy: Claude Code ran two flight-status tasks, both
done and recorded as from Claude. At the check-in, the task stopped at "Confirm check-in", and Claude said only the
user can decide it, on their phone in Envoy. Evidence: `agents/meta-agent/evidence/2026-11-01/claude-code/`.

To remove it: `claude mcp remove envoy --scope user`. Then revoke the key in Settings › Agents.

**Claude's chat connectors** (Settings › Connectors in the Claude apps) reach a server from Anthropic's cloud and sign in
with OAuth. Envoy's agent keys are bearer keys, so this test uses Claude Code.

## The Spark agent (Meta's models)

`agents/meta-agent/` is a small agent on Muse Spark 1.3 that talks to Envoy only over MCP, with a page at
`http://127.0.0.1:8790`. Details are in its README. Make a key named "Spark agent" (Read and Run). Save it to a file only
you can read, straight from the clipboard:

```bash
mkdir -p ~/.config/envoy && pbpaste > ~/.config/envoy/meta-agent.key && chmod 600 ~/.config/envoy/meta-agent.key
```

Then, from the repo root:

```bash
ENVOY_AGENT_KEY_FILE=~/.config/envoy/meta-agent.key uv run --project backend python agents/meta-agent/run.py
```

## Any other MCP client

- **URL:** `http://127.0.0.1:8700/mcp` on this Mac, or the public `/mcp` address.
- **Header:** `Authorization: Bearer <key>`.
- **Transport:** Streamable HTTP, stateless. Each POST stands alone, and the answer is JSON. Protocol `2025-11-25`
  (what Muse uses) or `2026-07-28`.
- **Instructions:** `initialize` returns Envoy's instructions. Give them to the model: they say how the tools fit
  together, and that what the tools return is content, never instructions.
