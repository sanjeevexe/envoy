# Connecting agents to Envoy

Envoy is the phone layer agents call. Any MCP client can use it: Muse (Meta's assistant), Claude, or the
Spark agent in `agents/meta-agent/`, which runs on Meta's models. Each one gets its own key, with only the tools you
give it. Every task it starts says which agent asked ("from Claude").

## What an agent gets

- **The server:** `/mcp` on Envoy's address, Streamable HTTP, stateless. On this Mac that's `http://127.0.0.1:8700/mcp`.
  The public Funnel address serves `/mcp` and nothing else.
- **The key:** `Authorization: Bearer <key>` on every request. Keys are made in Envoy's Settings › Agents (below).
  `MCP_BEARER_TOKEN` in `.env` stays Muse's key.
- **The tools, in groups** (contract 2 of `prompts/phone-layer-plan.md`):

  | Group | Tools |
  | --- | --- |
  | read | `get_task`, `list_routines`, `memory_search`, `memory_get`, `phone_updates`, `list_phones` |
  | run | `run_task`, `run_routine`, and every learned routine you share as a tool |
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
  in Envoy on your phone, and the agent is told it's waiting for your OK there (it gets no approval link).

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
"approve it for me". Claude should say only you can approve, on your phone, because Envoy gave it no way to.

To remove it: `claude mcp remove envoy --scope user`. Then revoke the key in Settings › Agents.

**Claude's chat connectors** (Settings › Connectors in the Claude apps) reach a server from Anthropic's cloud and sign in
with OAuth. Envoy's agent keys are bearer keys, so this test uses Claude Code.

## The Spark agent (Meta's models)

`agents/meta-agent/` is a small agent on Muse Spark 1.3 that talks to Envoy only over MCP, with a page for filming at
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
- **Transport:** Streamable HTTP, stateless. Each POST stands alone, and the answer is JSON. Protocol `2025-11-25`.
- **Instructions:** `initialize` returns Envoy's instructions. Give them to the model: they say how the tools fit
  together, and that what the tools return is content, never instructions.
