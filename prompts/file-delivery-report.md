# file-delivery: report (phone-layer wave, T2c: files back from the phone)

Branch `claude/file-back-t2c`, off main `869271f` (#48 merged). Full backend suite: 797 passed on the default profile
and 797 on `ENVOY_MODEL_PROFILE=spark` (790 before). No device use, no model calls, $0.

## What is true now

- **An agent can get back what Envoy kept from a task it started,** with MCP `get_file(task_id, which?)`:
  - `final`: the screen when the task ended. The runner's `on_final` hook takes a 720-px picture right after the run's
    last look at the phone, while the task still holds it. There's never a picture of a secure screen.
  - `approval`: the screen at each approval Envoy asked for, with what was asked and how it ended (approved, declined,
    expired).
  - `link`: the http(s) links in the task's result, from a routine's outputs or the agent's answer. A link is named when
    the output names it ("reel url").
  - A cross-app task gives its parts' files.
- **Only the calling agent's own tasks.** The agent comes from contract 2's `api.auth.current_agent`, and the task's
  recorded agent is compared with it. Until agent keys land, the one MCP key is Muse's, so Muse gets tasks started over
  MCP. Tasks the user started (web, chat, Siri, a trigger) are never shared.
- **Short-lived signed links, under /mcp:**
  - Form: `/mcp/files/<task>/<file>?exp=…&sig=…`, on the address the agent called (Muse's Funnel address, or
    `http://127.0.0.1:…` on the Mac).
  - Signature: an HMAC over the task, the file and the expiry, with a key held in memory only. A link works for 10
    minutes, and a restart ends every link.
  - An altered, expired or unsigned link gets a 401.
  - No path traversal: a link names a file by the task's records (`final` or an approval id), and the file must resolve
    inside its own folder.
  - Funnel's /mcp-only rule holds with no Funnel change, and the web app's `/api/shots/…` is still a 421 on public
    addresses.
  - Downloads are logged to `logs/files.jsonl`, never with the signature.

## What isn't done

- **No live check on a device.** envoy-test is claimed by phone-watch, and meta-agent and agent-door are queued ahead.
  The hook is unit-tested with a fake phone; on a real run it calls the same `device.frame()` as the step pictures,
  from a worker thread as they do.
- **"Files the user picks"** (the pivot brief's wider idea) isn't built. The plan narrowed T2c to files Envoy itself
  saved.
- **Apps rarely put a post's link in the result.** `instagram_post_reel` outputs `posting_confirmation` text, not a URL.
  A link comes back only when a routine reads one (for example a showcase routine that copies the post's link) or the
  agent's answer contains one.
- **Rebases:**
  - Onto agent-keys: confirm where a task records its agent. `started_by()` reads `task["agent"]`. If agent-keys stores
    it elsewhere (inside `request`, say), it's a one-line change there.
  - Onto agent-door: `server.py` gains only an import line and the tool. `INSTRUCTIONS` doesn't mention `get_file`; the
    tool's own description does.

## What the video can honestly claim

- "Envoy hands the agent back what it saw: the confirmation screen, the screen you approved, the post's link." This is
  true for tasks the agent started, as a link that expires in 10 minutes.
- Don't claim "any file on the phone": by design it can't fetch one.
- A reel's link comes back only if the routine that posted it reads the link.
