# Envoy — Technical Design

Oct 27, 2026. Updated Nov 2, 2026 for the phone-layer frame (main `947bf44`): the overview, the architecture, the device layer's phone choice, the MCP server and agents, triggers and approvals. The phase results further down are records of their day.

## Overview

**Envoy is the phone layer agents call.** It **acts** in Android apps, **learns** the tasks it does there, and **watches** the phone for events. The one-liner: *Muse has a computer. Envoy gives it a phone.*

An agent such as Muse (Meta's assistant) already has the web, its connectors and, in Muse for Mac, the computer. Much of a person's life still runs through phone apps, and some features exist only there: a Reel set to a song from Instagram's library, a poll sticker on a Story, a sound on a TikTok or a YouTube Short. Muse's connector catalog also had none for TikTok, YouTube, Uber or DoorDash when we checked (Nov 1). Asked whether it can use the person's phone apps, Muse said: "On its own, Muse can't open and tap around in apps on your phone." Envoy is that missing layer, reached the way agents reach everything else: over MCP.

**Envoy is not a rival assistant.** Muse, or any MCP agent, is the front door. The person asks there; the agent calls Envoy's tools; Envoy runs the task on an Android phone. Envoy's own app, on the person's iPhone, is where they approve anything irreversible and watch the phone work.

| Pillar | What Envoy does | Built in |
| --- | --- | --- |
| **Acts** | Runs real Android apps the way a person would: on **Envoy's phone** (a Pixel 5 on Android 13, over USB), on emulators on the Mac, or on a cloud phone. Anything irreversible stops for the person's yes on their iPhone. | Device layer, Agent runtime, Safety |
| **Learns** | Compiles a finished agent task's run into a **routine** when the person presses "Make it a routine" on its card (the routines shown in the results were compiled by the evaluation or a script, before the button): a program that checks its screens, repairs itself when the app changes, and keeps versions. The next run usually takes seconds and few or no model calls. Teach mode compiles what a person shows the same way, and the compiler can refuse a run. A routine the person shares with agents becomes an MCP **tool of its own**, by name. | App routines |
| **Watches** | **Notification triggers** (a notification on Envoy's phone starts a task or reaches the agent), time triggers, change alerts, habits, and `phone_updates`, which tells an agent what happened on the phone. | Scheduled and event-triggered tasks |

Underneath all three is a **memory** of what Envoy has seen in apps, in email and in shared screenshots. Every fact keeps its source.

**What is actually new.** Operating phone apps with an agent has been done (Mobilerun, Gemini on Android, AGI Inc.). Envoy's contribution is making it dependable, cheap and callable:

1. **App routines.** One successful run is compiled into a reusable program with inputs, checks before and after its steps, element-based targeting that works on any screen size, and self-repair that fixes only the broken step and saves the fix.
2. **Learned routines as agent tools.** A routine shared with agents appears in their tool list with typed inputs, the moment it's shared. An agent calls `instagram_reel_song(song_title, song_artist, caption)`; Envoy replays it on the phone, and asks the person before the post.
3. **A trustworthy shared memory.** Facts pulled from app screens, email and photos land in one graph. Each fact records where and when it was seen, newer facts replace stale ones, and the same trip seen in an email and an app becomes one entity.
4. **A device layer that routes between phones.** One interface over emulators (on the Mac or in the cloud) and real Android phones, with routines that run on either. Agents can see the phones and pick one.
5. **A human gate no agent can pass.** Each agent has its own key and its own tools. None of them can approve, accept an offer, or answer for the person: Envoy has no tool for it.

**Fit with the hackathon.** Indie track, theme *Push the Frontier*, "give a machine a new capability": Envoy gives Muse, and any MCP agent, a phone. Three agents have called it: Muse (on the Mac and in its iPhone app), the Spark agent (a small agent on Meta's own models, `agents/meta-agent/`) and Claude Code.

## Goals and non-goals

Envoy succeeds if a routine learned from one run works on new inputs, survives UI changes, and gets cheaper with each run, while every fact it remembers can be traced to its source.

**Goals**

1. An agent, driven by Meta models, completes multi-step tasks in real Android apps on a cloud emulator.
2. Successful runs become app routines that take inputs, verify every step, and repair themselves.
3. A shared memory graph, filled from app screens, Gmail and iPhone photos, that every interface reads and writes in real time.
4. Users interact by web chat, voice, an MCP connector (for Muse or other assistants), and an iPhone companion app.
5. Users sign in themselves through a live view, approve irreversible actions, and control what is remembered.
6. A device layer ready for real Android phones, tested on a borrowed phone once available.

Added Nov 1, when Envoy became the phone layer agents call (all built by Nov 2):

7. A shared routine is an MCP tool of its own, by name and with typed inputs.
8. Each agent has its own key and tool set, and every task records which agent started it.
9. Notifications on Envoy's phone can start a task or reach the agent.
10. Files go both ways: a clip from the Mac to the phone (`send_to_phone`), and screens and links back to the agent (`get_file`).
11. Agents can list the phones (`list_phones`) and pick one for a task.
12. A second agent besides Muse, on Meta's models, uses Envoy only over MCP.

**Non-goals for this build**

- A fleet of cloud phones for many users. Envoy is built for one user, structured so each user could later get their own phone and graph.
- Operating apps on iOS. Apple does not allow it; the iPhone is a companion only.
- Payments, money transfers, or finance, health and messaging apps. These are blocked by default.
- Solving CAPTCHAs or bypassing app security checks. The agent hands control to the user instead.
- Billing, accounts, or a public launch.

**Success targets** (initial targets, to revise after the first measurements)

| Measure | Target | How it's measured |
| --- | --- | --- |
| First-run task success on the test task set | 70% or more | Agent completes the task with no human help besides sign-in and approvals |
| Routine success on new inputs | 85% or more | Run a learned routine with inputs it has not seen |
| Recovery after an injected UI change | 70% or more | Change the test app's layout, then rerun the routine |
| Model calls on a routine rerun vs the first run | 80% fewer | Count calls per run |
| Time per task on a routine rerun | Under 30 seconds for a 10-step task | Wall-clock time |
| Facts traceable to a source | 100% | Every fact links to its app screen, email or photo |
| Irreversible actions taken without approval | 0 | Audit log |

## Architecture

Envoy has four layers: the callers, one Python backend, Meta's models, and a device layer.
- **The callers** are agents, over MCP, each with its own key, and the person's own surfaces: Envoy's iPhone app, the web app on the Mac, and Siri.
- **The backend** runs everything in one process: the API, the MCP server, the agent, routines, memory, policy and the scheduler.
- **Meta's models** are reached through one adapter.
- **The device layer** puts every phone behind one interface.

Every caller goes through one task API, and every phone through one device interface. So a new agent, surface or kind of phone doesn't touch the core.

![Envoy architecture: agents and the person's surfaces, the MCP server and task API, the backend, Meta's models, and the phones](diagrams/architecture.png)

The routine engine, the memory service and the policy engine (highlighted) are where the new work is. Routines are what an agent calls, memory is what it asks, and policy is the gate no agent can pass.

### One request, end to end

The person asks Muse for Mac to post a clip from the Mac as an Instagram Reel, set to a song from Instagram's library. This ran as a dry run on Nov 2, with each final step declined by the person (see `docs/muse-link.md`).

1. **The clip.** Muse copies the clip into Envoy's outbox folder on the Mac and calls `send_to_phone`. Envoy's phone is a real phone, so Envoy asks the person on their iPhone first. On their yes, the clip lands in the phone's gallery.
2. **The tool.** Muse lists Envoy's tools and finds `instagram_reel_song`: a routine Envoy learned, which the person shared with agents. Muse calls it with the song, the artist and the caption. Envoy starts a task, recorded as "from Muse", and returns its ID at once.
3. **The phone.** Instagram is set to run on Envoy's phone, so the task first asks the person "use Envoy's phone?" on the iPhone. A "no" moves the task to an emulator. No answer within 15 minutes ends the task as not done.
4. **The run.** The executor replays the routine step by step, with a check before and after each one. While the checks pass, it makes no model calls. Every step streams to Envoy's web app and iPhone app.
5. **The approval.** Share is irreversible, so the task stops and Envoy pushes an approval to the person's iPhone. Muse is told the task is waiting for the person's OK in Envoy. Muse has no tool to approve it.
6. **Back to the agent.** Muse follows the task with `wait_for_task` or `get_task`, or later with `phone_updates`, and tells the person how it ended. `get_file` can give it the final screen and the approval screens.
7. **Memory.** The routine's outputs become facts, each linked to the app screen it came from.

If the app has changed since the routine was learned, step 4 climbs the fallback ladder, repairs the broken step, and puts a new version on trial (see App routines).

In that Nov 2 rehearsal, the same request went to three apps, and nothing was posted. The Reel, the TikTok and the YouTube Short each reached their final button with the song and the caption, at 0, 3 and 0 model calls, about 1 min 15 s each after the phone OK.

The same task API serves the person's own surfaces. A request typed or dictated in Envoy's app, or spoken to Siri, becomes the same kind of task. When the approval rules decide what to ask, words typed or dictated in Envoy's app count as the person's own. Words from Siri, a trigger, an email or an agent don't (see Safety).

## Device layer

The agent never knows which phone it is using: one `Device` interface covers emulated phones and real Android phones. The first version drives both through uiautomator2; Envoy's own on-phone app (the **Envoy bridge**) would replace it only if measurements showed it was needed, and they didn't (Phase 6). The iPhone is a companion, never a device the agent controls.

### The Device interface

```python
class Device(Protocol):
    id: str
    capabilities: Capabilities        # real_phone, has_sim, can_snapshot, screen size
    async def observe(self, screenshot: bool = False) -> ScreenState: ...
    async def act(self, action: Action) -> ActionResult: ...
    async def launch(self, package: str) -> None: ...
    async def wait_until_settled(self, timeout_s: float = 5) -> ScreenState: ...
    async def snapshot_save(self, name: str) -> None: ...   # emulators only
    async def snapshot_load(self, name: str) -> None: ...
    def video_stream(self) -> StreamHandle: ...             # for live view and screenshots
```

`ScreenState` holds the foreground app and screen, the accessibility tree as normalized JSON, a screen signature (a hash of the stable parts of the tree), an optional screenshot, and a timestamp.

### Envoy bridge (planned, not built)

Built only if Phase 1 shows that waiting for the screen to settle, or setting text, is unreliable on real apps. Phase 0 measured a uiautomator2 tree read at 31 ms and a full observation at about 70 ms, so read speed is no longer a reason to build it; and on a real phone (Phase 6, a Pixel 5 on Android 13) settling and set-text both held, so it is not built. If built, it is a small Kotlin accessibility service that:

- **Reads the screen** in-process as JSON (bounds, resource ID, text, description, class, clickable, editable, password flag) in roughly tens of milliseconds, against about 31 ms through uiautomator2's server (Phase 0) and 0.5 to 1 second for `uiautomator dump`.
- **Knows when the screen has settled,** because it receives accessibility events; no fixed sleeps.
- **Acts reliably:** click, set text (including non-English text and emoji, which `adb input text` cannot type), gestures, back and home.
- **Talks over a WebSocket** forwarded through `adb forward`, so the same code works over USB, Wi-Fi or in the cloud.

**uiautomator2** (MIT license) is the default from day one: it reads the tree and acts, and Envoy types any language and emoji through accessibility set-text. uiautomator2's own typing pastes through the clipboard, which would leak typed text, so it is never used, and submitting is a plain Enter key, because its IME action would switch the user's keyboard. Only one of uiautomator2 and the bridge can run at a time, since Android allows a single automation session. Mobilerun's Portal app is not reused: its license is AGPL-3.0.

### Screenshots and video

On emulators, the agent's screenshots come from the emulator's own gRPC screenshot call (enabled by `-grpc`), measured in Phase 0 at 6 ms for a raw frame (20 ms as PNG). Emulator taps also go through gRPC (under 1 ms, against about 150 ms through uiautomator2). On a real phone, Envoy's own Python client (Phase 6) is the only **scrcpy** client per device (the Apache-2.0 server, decoded on the Mac with PyAV); it serves the live view, and the agent takes screenshots from its latest frame (7 ms) rather than `adb screencap` (0.5 to 2.6 seconds on phones; 142 ms on the emulator). Either way, screenshots are the exception: the agent reads text first (see Agent runtime).

### Backend 1: cloud phones (emulators)

- **Image:** Android 15 or 16 (API 35/36) with Google Play, arm64, regular page size. Play images allow signing in to the Play Store; they cannot be rooted, which is fine.
- **Launch:** headless (`-no-window -no-audio -no-boot-anim -memory 4096 -grpc <port>`), 4 GB of guest RAM but about 7 GB of Mac memory each (measured), at most two at once on the 24 GB laptop, with the browser and other heavy apps closed. Always add -grpc-use-token: plain -grpc listens on every network interface with no auth. Also add -feature -WiFiPacketStream: netsim Wi-Fi crashed emulator 37.2.12 on snapshot load. On a new emulator, update Chrome and Android System WebView from the Play Store, because the image ships 2024 versions that break web sign-ins.
- **Snapshots for test apps:** test apps and evaluation restore a known snapshot before each task, which makes runs and routine verification repeatable. A restore takes about 1.8 s including reconnecting (Phase 0), and each snapshot is about 3.8 GB on disk, so old ones are pruned. After a restore, the backend re-establishes adb forwarding, the automation server and the video session.
- **No rollback for real apps:** real apps run on a long-lived emulator that is never restored to an old snapshot. Restoring an old signed-in session can replay expired sign-in tokens, which can get the session revoked or the account flagged. It always cold-boots with snapshots off and is shut down cleanly, because a hard kill can lose recent writes.
- **Pool:** a task leases a device for its duration; other tasks queue (see Leases and failures). Price comparisons would lease two emulators at once (stretch).
- **In the cloud (tested Oct 29 and Nov 1):** the same stack on a Google Cloud `n2-standard-8` with nested virtualization, about $0.39 an hour. SkyLark routines compiled on the Mac ran there unchanged, 48 of 48 with no model calls. A full copy of Envoy (API, web app, MCP, two emulators) then ran there as an alternative to the Mac (`docs/cloud.md`). Envoy runs on the Mac by default; the cloud server is stopped between uses.

### Backend 2: a real Android phone

- **Envoy's phone** is a Google Pixel 5 on Android 13, on loan, plugged into the Mac over USB. Wireless debugging (Android 11+) was the original plan, but it's untested: campus Wi-Fi usually isolates devices from each other.
- uiautomator2 (or the bridge, if built) is installed over adb. Android 13+ restricts accessibility access for sideloaded apps, so the bridge would be enabled once through the "Allow restricted settings" menu or an adb setting.
- On Samsung phones, Auto Blocker must be turned off.
- Secure sign-in and payment screens behave as described in Live view and sign-in.
- Google Play's policy forbids publishing an app that uses accessibility features to act autonomously, so any on-phone helper stays sideloaded. That is fine for the hackathon and is the main barrier to shipping this as a consumer product.

### Choosing which phone runs a task

| Situation | Phone used | Why |
| --- | --- | --- |
| Default | An emulator | Keeps the real phone free; snapshots make test runs repeatable |
| An agent names a phone (`phone` on `run_task`, `run_routine` or a routine tool) | That phone | The agent saw it with `list_phones`. The real phone still asks the person first |
| The person says "on my phone", or set the app to run there (Settings › Phones) | Real phone | Their choice |
| App refuses to run on an emulator (device integrity checks) | Real phone | Emulators never pass Google's device integrity check |
| App showed a bot check on an emulator, or the Play Store says the emulator isn't compatible | Real phone, from then on | Envoy sets "use my phone" for the app itself (Settings › Phones, with the reason; unticking undoes it) and offers to move the task |
| App the task names isn't installed on the emulator | The emulator, after installing it from the Play Store | Free apps only; a paid app asks through the approval flow and Envoy never pays |
| App allows only one signed-in device, and the user is signed in on their phone | Real phone | Avoids signing out the user's phone |
| Task needs the SIM or the phone's own number | Real phone | The emulator has no SIM |
| Two apps compared at once | Two phones | Cross-app parts on different phones run in parallel |
| No real phone connected | The emulator, or the user is told the app needs a real phone | Never fails silently |

**`list_phones`** tells an agent which phones Envoy can use. For each it gives an `id`, a name, a `kind` (`cloud`: an emulator on Envoy's cloud server; `emulator`: one on the Mac; `real`: an Android phone), whether it's online, and the apps Envoy runs there. The `id` is what `phone` and `send_to_phone`'s `device` take. Naming a phone doesn't skip anything: `api/routing.py` still decides, and the real phone still asks.

**Before using the real phone, Envoy asks the person.**
- The task waits for the person's answer to "use Envoy's phone?" (in the app it reads "Envoy wants to use <the phone's name> for this task"). It shows in Envoy's app and as an iPhone push. Only the person's own session can answer.
- **No answer is never a yes.** If 15 minutes pass with no answer, the task ends as not done ("no answer about using Envoy's phone"). Only the person's "no" moves the task to an emulator. (Until `947bf44` on Nov 2, silence also moved it, and on Nov 2 an emulator with no Instagram then opened the Play Store.) For an app that blocks emulators, a "no" ends the task too.

**While it works, it shows and yields.** Phase 6 built this part:
- A small overlay app (`android/banner/`) shows "Envoy is using this phone · Pause".
- Envoy pauses when the screen changes in a way its last action didn't cause, or when the person presses Pause. A touch is told from Envoy's own input by getevent, which sees only the phone's physical input; everything Envoy does is injected.
- A touch, Pause, or another app coming to the front hands the phone to the person like a takeover. This is checked before every action of the agent's. Resume on the phone or in the app gives it back.

Apps that block emulators are data, not code: a starting list (`api/emulator_blocked.json`: Target, Uber Eats, common banking and payment apps) plus the ones Envoy finds itself. With no phone connected, Envoy says plainly that the app blocks emulators and needs a real Android phone, instead of trying the emulator (docs/app-routing-onboarding.md).

### iPhone companion

The iPhone runs Envoy's companion app (see Interfaces): approvals, the live view, voice, and photos. iOS does not allow one app to operate another, so the agent never controls the iPhone.

### Setting up this Mac

Done in Phase 0: the Android SDK, emulator, adb, scrcpy and cloudflared are installed, with an arm64 Java 21 (Homebrew) and Python 3.13 through uv. scripts/env.sh sets the paths.

## Agent runtime

The agent reads the screen as compact text, chooses one element-based action at a time as structured JSON, and attaches a screenshot only when text is not enough. That keeps each step cheap and makes every step recordable for routines.

### The loop

1. **Plan.** At the start of a task, Muse Spark 1.3 (higher reasoning effort) writes a short plan of subgoals and a **success check** that code can evaluate (for example, the text "You're checked in" is visible), using the request and relevant memory. It also gets the phone's date (goals say "tomorrow" or "this Thursday") and its apps by the names people use, and it knows that a button shown with one item (the card for the next trip, the last order) acts on that item only.
2. **Observe.** Wait until the screen settles, then read the accessibility tree and turn it into a compact list (below).
3. **Decide.** Muse Spark 1.3 (low reasoning effort) receives the cached system prompt and schemas, the plan with the current subgoal, the last 5 actions and their outcomes, relevant memory notes, and the current screen. It also gets what it kept from earlier screens of the task (REMEMBERED: text to copy, values to add up, copied word for word from the screen) and the phone's date. It returns one action as JSON, with the expected result and a risk label. Meta's structured output writes an object's keys in alphabetical order, whatever order the schema lists them in, so the fields are named for the order the model should decide them: what to keep, the reason, the expected result, then the action (its kind first) and the risk. Before an irreversible action the screen, or what it kept, must name the goal's own item (the flight, the person, the amount).
4. **Check policy.** The policy engine classifies the action's risk; an irreversible action waits for approval (see Safety). From Phase 1 this is a rule-based gate with a yes or no prompt in the terminal; the full approval flow arrives in Phase 4.
5. **Act** through the device interface.
6. **Verify.** Compare the new screen with the expected result. No visible change triggers a screenshot and a second try.
7. **Record** the step: before and after screens, action, reason, timing and cost.
8. **Finish.** When the model returns `done`, the runtime evaluates the success check in code. If it fails, `done` is rejected once and the model is told what is missing; the check was written before the app was seen, so a second `done` is accepted as "done, unverified". A task whose check cannot be evaluated is marked "done, unverified" too, and is never compiled into a routine without the user's confirmation. Facts are then extracted for memory (see Shared memory).

### How the screen is shown to the model

Only elements that matter are listed, each with a short number the model refers to:

```text
App: SkyLark Air · Screen: TripDetailsActivity · settled 220 ms
[1] Button "Back"
[2] Text "Trip to Chicago · Fri Oct 30"
[3] Text "SL 482 · ATL 6:10 AM → ORD 7:25 AM"
[4] Button "Check in" (id: btn_checkin) enabled
[5] Button "Change seat" (id: btn_seat)
[6] EditText "Add known traveler number" (empty)
(list scrolls down)
```

A screen of this size costs a few hundred tokens. A screenshot (about 3,200 tokens at the full 1080 by 2400 resolution, measured in Phase 0, so it is downscaled before sending) is attached only when the tree is sparse (Flutter, games, custom drawing), the last action had no visible effect, the model asks for one with a `look` action, or a repair is in progress.

When the on-screen keyboard is up, the screen says so under its first line (without it, the model pressed back "to close the keyboard" when none was open, and lost forms). An element's own long text (a note, an open file) is shown at length, up to 4,000 characters and 8,000 per screen; rows that merge their children's text stay at 120.

### Actions

| Action | Notes |
| --- | --- |
| `tap(el)`, `long_press(el)` | By element number; the runtime stores the element's full description for routines |
| `type(el, text, submit?)` | Uses accessibility set-text (through uiautomator2, or the bridge if built), so any language or emoji works; submit is a plain Enter key |
| `scroll(direction, el?)`, `swipe(...)` | Scrolls a list or the screen |
| `back`, `home`, `launch(app)` | Navigation; `launch` takes the app's name as people say it ("Simple Calendar Pro") or its package, matched against the phone's own app labels |
| `tap_point(x, y)` | Only for screens with no usable tree; coordinates come from visual grounding |
| `look` | Request a screenshot for the next step |
| `wait(seconds)` | For loading screens |
| `ask_user(question)` | Missing information |
| `handoff(reason)` | Sign-in, bot checks, anything the agent should not do |
| `done(result)` / `fail(reason)` | End of task |

The action is returned through Meta's structured output (`json_schema`), not tool calling. The Meta API only accepts automatic tool choice and does not guarantee tool arguments match their schema, while structured output is always constrained to the schema.

### Screens without an accessibility tree

For Flutter apps, games and custom-drawn screens:

1. Muse Spark's **visual grounding** returns points or boxes for a described element (on a 0 to 1000 grid), which become `tap_point` actions.
2. **SAM 3.1** proposes candidate regions from generic shape phrases ("square button", "icon"; it finds nothing for "seat" or "button"); they are numbered on the screenshot and the model picks one. Measured in Phase 6 on 52 targets (SkyLark's canvas seat map and real-app screens): the step model's own coordinates hit 37%, grounding 92%, SAM and a pick 75% (no wrong pick: it says none when its shapes miss a text button), and SAM first with grounding as the fallback 52 of 52, again on a fresh sample (grounding alone 49 of 52), at about 4 s and $0.007 per target. Envoy uses that combination: a tap at a point now names its target ("seat 21A"), and the runtime finds it on a full screenshot. Routines keep such a step as what it looks like plus its picture, find the picture again when the target is fixed, and look again (one SAM-then-grounding pass) when it depends on an input.
3. Meta also offers a native computer-use tool, but it acts in pixels for desktop-style actions. Envoy keeps element-based actions so routines stay portable, and uses that tool only as a comparison.

### Getting unstuck

- **Stuck detection:** the same screen signature three times, or an action loop, triggers a recovery. Lines that change by themselves (a clock, a timer) are masked first, so a ticking screen doesn't count as progress.
- **Recovery order:** go back one screen, replan the current subgoal, then ask the user.
- **Pop-ups:** a shared handler library dismisses common interruptions (permission prompts, rating requests, promos) without spending a model call.
- **Limits:** each task has a step limit and a cost limit; hitting either stops and reports.

### Several phones at once

Built Oct 28 (`api/crossapp.py`). A question that needs two or more apps ("How many calories are in a Caffè Latte at Starbucks, and what's the first place DoorDash shows for a latte?") goes to a lead step: one Muse Spark call splits it into one part per app. Each part is an ordinary task, on the phone routing picks. Parts on different phones run at the same time, and parts on the same phone wait for it. One more call writes the answer, and every value it cites must appear in its part's result. This follows the lead-agent-and-subagents pattern Meta describes for Muse Spark, implemented by Envoy's own orchestrator. `run_task` over MCP takes the same path, unless the agent names a phone.

### Traces

Every step is stored with its before and after screens, the action and its element description, the model's one-line reason, the time taken and the cost. Traces feed three things: the routine compiler, the evaluation suite, and the task view in the web app.

### Leases and failures

- **One lease per device,** with a first-in, first-out queue. Watchers skip a cycle if their device is busy.
- **Waiting for approval** releases the lease after 2 minutes; the task observes the screen again when it resumes.
- **Device errors** (adb offline, emulator crash, automation server stopped) reconnect with backoff up to 3 times; then the task fails with its trace saved.
- **Model calls** time out at 30 seconds and retry twice, backing off on rate limits. An invalid element number triggers a fresh observation and one retry.
- **Backend restarts** mark running tasks as stopped ("the server restarted") and pending approvals as expired, rather than resuming them half-way.

## App routines

An app routine is a small program compiled from one successful agent run: it takes inputs, checks the screen before and after its steps, finds buttons by what they are rather than where they were, and repairs only the step that breaks. Reruns need no model calls while every check passes.

![Routine lifecycle: compile once, run many times, repair locally](diagrams/routine-lifecycle.png)

The top row runs once per new task type; the bottom loop runs on every later request, and the model is called only when a check fails.

### What a routine contains

```yaml
routine: skylark_check_in
app: com.skylark.air            # test airline app
version: 3                      # v2 patched the "Continue" button
intent: "check in for a SkyLark flight"
inputs:
  confirmation_code: {type: code, from_memory: trip.confirmation_code}
  last_name:        {type: text, from_memory: user.last_name}
outputs: [seat, gate, boarding_time, boarding_pass]
steps:
  - id: open_trips
    intent: "Open My Trips"
    pre:  [app_foreground: com.skylark.air, element_present: {text: "My Trips"}]
    action: {tap: {resource_id: "nav_trips", text: "My Trips"}}
    post: [screen_has: {text: "Find a trip"}]
  - id: enter_code
    intent: "Enter the confirmation code"
    action: {type: {field: {hint: "Confirmation code"}, value: "{{confirmation_code}}"}}
    post: [field_equals: {hint: "Confirmation code", value: "{{confirmation_code}}"}]
  # ... 6 more steps ...
  - id: confirm
    intent: "Confirm check-in"
    risk: irreversible           # always asks for approval
    action: {tap: {text: "Check in", class: Button}}
    post: [screen_has: {text: "You're checked in"}]
    extract: {seat: {near: "Seat"}, gate: {near: "Gate"}}
```

- **Inputs** have types (text, code, date, phone, choice) and a hint for where memory can fill them, so "check me in" needs no further questions.
- **Locators** score several attributes of an element (resource ID, text, description, class, parent and sibling text) instead of coordinates. Real apps often obfuscate resource IDs (the Play Store's are all 0_resource_name_obfuscated), so text and descriptions carry most of the weight. A strict and a relaxed match threshold (0.80 and 0.60, tuned on SkyLark's layouts with and without IDs) separate a confident match from a changed element; a check, unlike a tap target, also needs text evidence and its element type, since an ID alone is shared across screens. An element repeated row after row with nothing of its own to tell it apart (a delete icon on every expense) also keeps its row's text, and a row chosen because it shows an input must show it. When an element has no usable attributes (icon-only buttons, Flutter apps), the locator stores a visual crop matched by image similarity, with Muse Spark's visual grounding as the fallback (SAM 3.1 is tested here too; see Agent runtime).
- **Checks** are code, not model judgments: app in front, element present or absent, text visible, field holds a value (read with get_text, since tree dumps garble emoji), screen signature similar enough. The signature is the app, the window title, and the sorted resource IDs and element types outside lists, ignoring all text and list contents, so it survives changing data. This avoids the failure seen in prior work where a model misreads whether a condition holds.
- **Outputs** pull values from screens (seat, gate) and write them to memory with their source. Extraction takes the text after the label in the same element (apps often merge them, as in "Seat 14C"), else the next element, else one Spark call with the outputs schema.
- **Risk** is recorded per step; an irreversible step always goes through approval, even in a routine.

**Lists** are handled by a `scroll_until(locator, direction, max_scrolls)` step rather than a recorded number of scrolls, since list contents change. The end of a list is reached when the tree stops changing after a scroll. The compiler converts recorded scrolls into this step.

### Compiling a routine

1. **Confirm success.** Only runs that reached the goal are compiled, judged by an explicit end signal ("You're checked in", a boarding pass visible) or by the user.
2. **Clean up.** Drop dead ends, back-tracks, retries and dismissed pop-ups. Pop-ups are handled by a shared handler library, not baked into routines.
3. **Generalize.** Any typed or selected value that equals a task input or a memory fact becomes an input slot. A list item chosen because it matched an input (the row for flight SL 482) becomes an input-based locator. A Meta model (Muse Wonder, for its stronger reasoning) names the inputs and decides which values stay fixed.
4. **Add checks.** For each step, the before and after accessibility trees are compared to write its checks automatically: which elements must be present before, and what must change after.
5. **Verify by replay.** The routine is replayed immediately from a reset snapshot with the same inputs, running through irreversible steps only on test apps (where restoring the snapshot undoes them) and stopping before them on real apps, and again with a second set of inputs where the test app allows. Only a routine that passes enters the library. Prior work found this verification step to be the single biggest source of improvement.

### Running a routine

A request is matched to a routine in four filters: the app, the intent pattern, similarity of descriptions, and a final model confirmation that also fills the inputs from the request and memory. A date or time the request only implies ("tomorrow", an end time from a start and a duration) is worked out in code from the phone's date, so the model never computes one. The executor then runs each step: wait for its before-checks (up to 5 seconds), find the element, act, wait for its after-checks. No model call is made while checks pass.

**When a check fails, the fallback ladder climbs one rung at a time:**

1. **Wait and retry,** for slow loading.
2. **Relaxed matching,** using the lower locator threshold.
3. **Known pop-ups** (permission prompts, ratings, promos) dismissed by the shared handler library. Permission prompts are denied unless the app's settings allow them.
4. **Local repair:** the model gets the step's intent, its checks and the current screen, and proposes actions that satisfy the after-check. Capped at 2 attempts per step and 5 per run.
5. **Full agent** takes over the rest of the task from the current screen.
6. **The user** is asked, through the live view.

### Patching and versions

- A successful local repair becomes a **candidate patch**: a new locator, an inserted step (a new "Continue" screen), or a removed one. It is saved as a new version marked "on trial."
- The candidate is replayed right away from a reset snapshot (test apps) or on the next run (real apps), and becomes active once that replay passes. If it fails, the routine rolls back to the previous version.
- If a routine fails more than half its recent runs, it is recompiled from a fresh full-agent run on the current version of the app.
- The routine library shows each version's changes with before and after screenshots, so the user can review or reject a patch.

### Working on any phone

Because locators use element attributes, not coordinates, the same routine runs on emulators of different screen sizes and on a real phone. Portability is tested cheaply before a real phone is available by running each routine on two emulator profiles (a small phone and a large phone). Phase 6: the 6 SkyLark routines compiled on a 1080 by 2400 emulator passed 18 of 18 on a 720 by 1280, 320 dpi one with no model calls, once a target below the fold is found by scrolling its list and an output scrolled out of view is read by scrolling back (neither needs a model call), and 12 of 12 through the real-phone code path.

### Teach mode: learning from the person

Built Oct 31 (`api/teach.py`). Instead of an agent run, the person does the task once, through the live view, after pressing Teach. The live view shows Recording.
- **What's recorded:** each tap, typing and scroll, with the screen before and after. A tap is the smallest clickable element under it.
- **What isn't:** sign-in and secure screens pause the recording and store nothing, and password fields are never recorded. Cancelling, "it didn't work" or 20 idle minutes delete it all.
- **Compiling:** the recording compiles like an agent's trace. Envoy then replays it once, strictly, on the same phone, before saving it, marked "taught".
- **Make it a routine** (Nov 2, `learn_task`): a task the agent finished takes the same path from the compile on. The person taps it on the task's card; Envoy compiles that run, replays it once strictly on the phone it ran on (no repair, no agent; irreversible steps still ask), and saves it as "learned from task <id>", not shared with agents. A run that can't be compiled, or a replay that fails, says why and saves nothing (`backend/tests/test_teach.py`).

On Oct 31, a scripted demonstrator taught Google Calculator "what is 1234 times 5678?". The routine replayed 3 of 3 with 0 model calls in about 6 s, and got a new input (4321 × 8765) right; the agent took about 40 s and $0.08 for the same question. Teaching Wikipedia failed: the answer was prose with nothing to anchor a read on (`eval/results/teach_trials_2026-11-01/README.md`).

**Known gaps:** teach mode can't yet learn keypad entry reliably, or apps that reopen on their last screen (the Clock, Wikipedia).

### Routines as agent tools

Built Nov 1 (`api/sharing.py`, `mcp_server/server.py` `RoutineTools`). Each routine has a **Share with agents** switch, off by default, on its page in Envoy and in Settings › Agents. While it's on and the routine has an active version, the routine is a tool of its own in every agent's `tools/list`:
- **Name:** the routine's name (`instagram_reel_song`), or `routine_<name>` if that isn't a valid tool name or clashes with a built-in tool.
- **Arguments:** the routine's typed inputs as a JSON schema. A date is `format: date`, and a choice with known options is an enum. An input memory can fill is optional, and the rest are required. An optional `phone` is added too.
- **Description:** what it does and in which app, which of its steps can't be undone (so Envoy asks first), what it returns, and when Envoy learned it ("replays without model calls while the app looks as it did").
- **Hints:** `readOnlyHint` only when every step only reads.

A call goes exactly where `run_routine` goes: preflight, then the runner, with approvals unchanged. The server reads the switches and the library on every `tools/list` and `tools/call`. So learning, sharing, retiring or repairing a routine shows up on the agent's next request, with no restart. `phone_updates` also reports a routine learned or repaired, naming its tool when it's shared.

**With Muse:**
- In a probe on Nov 1, Muse saw a tool added while its connector stayed connected, on its next `tools/list`, with no reconnect (`docs/muse-link.md`, "Nov 1–2: routine tools and the cross-post dry run").
- Muse's client keeps an allowed list of tools, so the first call to a new tool may take one extra step while Muse adds it.
- On Nov 2, Muse called Envoy's shared routine tools by name (see One request, end to end).

`run_routine` still runs any active routine by name, shared or not. The switch decides which routines are tools of their own, not which can run. Approvals are the same either way.

### What is new, honestly

The closest prior work is **SkillDroid** (April 2026), which compiles successful phone-agent runs into parameterized templates with weighted element locators, checks the screen before each step, and fixes stuck steps with one model call. Earlier systems (MobileGPT, Agent Workflow Memory, Agent Skill Induction, Mobilerun's macros) cover parts of the idea. Envoy's additions, to the best of our search:

- **Checks after steps,** not just before, written as code (the showcase routines' final post step has none: the post is the end).
- **Local repairs patched back into the routine,** with versions, a trial period and rollback, instead of recompiling the whole routine or patching nothing.
- **Tested portability** across screen sizes and from emulator to a real phone.
- **Routines connected to memory:** inputs filled from facts with sources, and outputs written back as new facts.
- **Learned routines served as agent tools:** a shared routine is a tool of its own, with typed inputs, at the agent's next `tools/list`.
- **An approval no agent can give:** the MCP server has no approve tool, so an irreversible step an agent starts waits for the person.

## Shared memory

Memory is a graph of typed entities whose facts each record their source, when they were seen, and how long they were true; it lives in one SQLite database behind one memory service that every interface uses. Users see it as an Obsidian-style map; the model sees it as short Markdown notes.

### Data model

| Table | Holds | Key fields |
| --- | --- | --- |
| `entities` | Things in the user's life | type, name, summary, pinned, user\_edited |
| `facts` | One attribute value of an entity at a time | entity, attribute, value, valid\_from, valid\_to, observed\_at, recorded\_at, retired\_at, source, confidence, author (extracted or user) |
| `edges` | Links between entities | from, relation, to, valid\_from, valid\_to, source, confidence |
| `sources` | Where a fact came from | kind (app screen, email, photo, calendar, routine run, user), reference (app and screen, email ID, photo ID), captured\_at, redacted snapshot, expires\_at |
| `events` | Append-only log of every change | time, kind, payload |

Keyword search uses SQLite's built-in full-text index, and natural keys (below) handle most matching. Similarity search (`sqlite-vec` with a small local embedding model) is added only if matching misses too often. Graph databases such as Neo4j (which Graphiti and mem0 rely on) are unnecessary for one user; the design borrows their ideas, not their storage.

**Entity types** are declared up front: Person, Trip, Flight, Reservation, Order, Item, Place, App, Account, Loyalty program, Subscription, Event, Preference, Note, Routine, Task. Notes are entities with a Markdown body and `[[links]]`, so a user note like "I always want an aisle seat" is a node like any other.

### Facts over time

Each fact has two timelines, an idea taken from Graphiti: when it was true in the world (`valid_from`, `valid_to`) and when Envoy learned or retired it (`recorded_at`, `retired_at`).

- **A new value replaces the old one.** When the airline app shows gate C14 and memory says B12, the B12 fact gets `valid_to` set to the new fact's start. Nothing is duplicated, and the history stays visible.
- **User edits win.** A fact written by the user in Envoy's own interfaces outranks extracted ones. Notes written by an AI assistant through MCP record that client as their author and rank like extracted facts. If a later observation contradicts it, the conflict is flagged for the user rather than silently overwritten.
- **Freshness rules per attribute:** a gate is fresh for 30 minutes while a trip is active, a delivery estimate for 10 minutes, a points balance for 7 days. Stale facts are shown with their age, and a watcher or routine can refresh them.
- **Confidence** combines the extraction model's confidence with how reliable the source is (an app screen ranks above an email, which ranks above a photo's OCR text).

### Getting facts in

| Source | How facts are extracted |
| --- | --- |
| App screens | At the end of a task and on routine `extract` steps, the redacted screen text goes to Muse Spark with the entity schemas (structured output). Every fact keeps a pointer to the screen and element it came from. |
| Gmail | Many confirmation emails carry schema.org markup (for example `FlightReservation`), which is parsed directly with no model call. Other emails go through the model. |
| Calendar | Events are read directly and linked to trips and reservations. |
| iPhone photos | Photos and screenshots the user shares (photo picker or the "Send to Envoy" Shortcut): text is read on the Mac with Apple's Vision framework, Muse Spark reads the image, every value must appear in that text, and the image is deleted (see Safety). Phase 5: 73 of 73 values right on 7 app screenshots, each merged into the known trip and flight. |
| Routine runs | Routine outputs (seat, gate, order total) are written directly as facts. |
| The user | Notes, edits and preferences from the graph view, chat or MCP. |

Apps blocked from memory are filtered out before extraction, and the redaction pass runs before anything is stored.

### Recognizing the same thing twice

The same trip in a confirmation email and in the airline app must become one entity.

1. **Exact keys first:** each type has natural keys (a flight's airline, number and date; a reservation's confirmation code; an order's merchant and order number).
2. **Candidates otherwise:** keyword and similarity search find likely matches.
3. **Model decides:** Muse Spark judges whether a candidate is the same entity. Facts are de-duplicated only within the same entity.
4. **Merges are reversible:** the user can split a wrongly merged entity in the graph view.

### Getting facts out (retrieval)

When a task starts or a question arrives:

1. Link mentions in the request to entities ("my flight" means the next upcoming Flight).
2. Collect those entities and their neighbors one or two links away.
3. Add keyword and similarity matches, combined by reciprocal rank fusion.
4. Keep only facts that are currently valid and allowed by the user's settings.
5. Render them as Markdown notes within a budget of about 2,000 tokens:

```markdown
## Trip: Chicago, Oct 30–Nov 2  [[Flight SL 482]] [[Hotel: The Drake]]
- Confirmation: KX7Q2M — email from SkyLark, Oct 12
- Seat: 14C — SkyLark app, today 9:41 AM
- Gate: C14 (was B12 until 9:41 AM) — SkyLark app, today 9:41 AM
- Boarding: 5:30 AM — SkyLark app, today 9:41 AM
- Preference: aisle seat — your note
```

The model sees where each fact came from and how old it is, so it can say "according to the airline app 5 minutes ago" and decide when to re-check.

### Staying in sync

The memory service is the only writer. Every change becomes an event, pushed over the same WebSocket stream as task updates, so the graph view, chat, iPhone and MCP clients all see the change at once. MCP tools read the same service.

### The graph view

- An interactive map of entities and links (Cytoscape.js), filterable by type and time, with the next 7 days highlighted.
- Clicking a node shows its facts, each with a source link (screenshot thumbnail, email, photo), its history, and edit and delete buttons.
- Notes are edited as Markdown, with `[[links]]` that create edges.
- Deleting a source deletes the facts that only it supports.

### What is new

Prior systems (Zep and Graphiti, mem0, Letta, A-MEM, GraphRAG) build memory from conversations and documents. None found takes phone app screens as a source with screen-level provenance, matches the same entity across email, app screens and photos, or lets user edits outrank extracted facts in a typed graph. Envoy also connects memory to routines: routine inputs come from facts, and routine outputs become new facts.

## Interfaces and integrations

Every interface talks to the same task API and memory service, and every change is pushed to all of them over one event stream. That keeps agents, the web app, voice and the iPhone in sync: none of them holds its own state. Agents are the front door. The person's own surfaces are where they approve, watch and set things up.

| Interface | What the user does there | Built with |
| --- | --- | --- |
| Web app | Chat, watch tasks run, take over the phone, approve actions, browse and edit the memory graph, manage routines and permissions | React (Next.js, a static export served by the API), WebSocket event stream, live view over WebSocket (emulator frames; scrcpy for real phones) |
| Voice | Speak requests on the web or iPhone and hear short spoken replies | Meta's Muse Voice Transcribe for speech to text (public preview); spoken replies from the browser's or iPhone's built-in speech |
| iPhone companion | Approve actions from notifications, follow a running task, watch or take over the phone, send screenshots and photos in | The web app added to the Home Screen, over Tailscale Serve HTTPS on the user's tailnet; Web Push; a 6-digit pairing code |
| MCP server | Agents use Envoy's phones, routines and memory: Muse (a custom connector, on the Mac and in its iPhone app), the Spark agent, Claude Code, or any MCP client | MCP Python SDK 2.3, Streamable HTTP, stateless; a bearer key per agent |
| Siri | "Ask Envoy" from Siri, the Action Button or Control Center; Envoy's one-line answer is spoken back | An Apple Shortcut that posts to `/api/siri` with a `siri`-scoped token (`docs/siri.md`) |
| Gmail | Envoy reads confirmation emails into memory | Gmail API, read-only, on a personal Google Cloud project |
| Scheduler | Tasks that run at a time, or when something happens on the phone, in email or in memory | Envoy's own scheduler inside the backend |

### Tasks: the shared unit of work

Every request, from any interface, becomes a **task**: a goal, the interface it came from, its scope (allowed apps and memory areas), its status, its steps, and its approvals. The task API is the only way to start or change work. Every step, screenshot, approval request and memory change is published as an event, and every connected interface updates live.

### Web app

- **Chat** with Envoy's own assistant, on Muse Spark: answer from memory, start a task or a routine, ask several apps at once, or set up a recurring job. This was route 1 into Muse (below). The person's agent of choice now plays this role over MCP.
- **Task view:** the steps as they happen, each with its screenshot, the action taken, its risk level, and the model's one-line reason.
- **Live phone panel:** the phone's screen streamed in real time, with a "Take over" button (see Live view and sign-in).
- **Approvals inbox** for pending irreversible actions.
- **Memory graph view:** an Obsidian-style map of entities and links; click a node to see its facts, sources and history, edit it, or delete it.
- **Routines library:** each routine's steps, inputs, version history (each repair's before and after), runs against the agent run it came from, and its **Share with agents** switch.
- **Activity:** tasks with who started them ("from Muse"), files from the Mac, and Envoy's offers.
- **Triggers:** the person's triggers, the notification watch form, and what was caught on Envoy's phone.
- **Settings:**
  - **Approvals:** when Envoy asks.
  - **Phones:** which apps run on Envoy's phone, which apps Envoy may watch for notifications, the outbox folder, and phone names.
  - **Devices:** paired iPhones and tokens.
  - **Agents:** each agent's key and tool groups, and the tools agents see.
  - **Appearance.**

### Voice

The web app and iPhone stream microphone audio through the backend (which holds the API key) to Meta's **Muse Voice Transcribe** (real-time speech to text over WebSocket, in public preview since September 2026). The transcript goes into the message box for the user to check; once sent, it reaches the assistant like typed text, as the user's own words for the approval rules (source `voice`). Replies are short and spoken by the device's built-in speech engine, which keeps voice on Meta models and costs nothing extra. If Muse Voice Transcribe is unavailable or too slow, the fallback is the browser's own speech recognition in Chrome. Phase 5: voice is dictation. The user taps the mic, taps stop, and the transcript lands in the message box to check and send; sending on release had started a check-in the moment the user let go. Each dictation is one Transcribe session (24 kHz PCM from an AudioWorklet; audio is buffered while the session connects). The final text arrives about 70 to 300 ms after stopping, on the author's Mac and iPhone alike, at $0.18 per audio hour. Transcribe closes a stream that falls behind real time, so the relay pads silence whenever the browser's audio stalls.

### iPhone companion app

The companion is the web app added to the iPhone's Home Screen, which needs no Apple Developer account. (TestFlight is not a free option: it requires the paid $99 program.) If web push approvals or photo sharing don't work well enough in practice, the fallback is paying for the Apple Developer Program and building the native SwiftUI app, which adds lock-screen Live Activities and on-device text reading. Phase 5 built it: the app reaches the Mac through Tailscale Serve, a real certificate on a private `*.ts.net` name (HTTPS on :8443) reachable only by the user's devices, and the API answers only to its own names. The Home Screen app keeps its own cookies, apart from Safari, so the user signs in by typing a 6-digit pairing code from the Mac inside the installed app (single use, 5 minutes, 5 tries); each device gets its own revocable session, and the Share Sheet shortcut gets a token that can only upload images.

- **Approvals:** web push notifications, which iOS supports for Home Screen web apps from iOS 16.4. Web notifications have no action buttons, so tapping one opens the approval page, where the user approves or declines. A push never carries the approval's nonce, and it is sent only when Envoy actually asks (an approval the user's request already gave doesn't push). Phase 5: delivered 0.7 to 2.3 s after sending (4 of 5 pushes under 1.2 s).
- **Running task:** the app shows the current step and screenshot; key moments (approval needed, task done, task failed) also send a notification. Lock-screen Live Activities need a native app and are left out.
- **Live view:** the same stream as the web app (the emulator's gRPC frames; scrcpy for real phones), with touch forwarded to the phone: tap, swipe, long press, and typing through the iPhone's keyboard. Phase 5: 66 to 115 ms from capture to the iPhone's screen over the tailnet.
- **Voice:** dictation: tap the mic, tap stop, check the words in the message box and send; the audio streams through the backend to Muse Voice Transcribe.
- **Screenshots and photos:** the user picks photos or screenshots in the app, or uses a free "Send to Envoy" shortcut from the iOS share sheet. The image goes to the server, text is read on the Mac (Apple's Vision framework), Muse Spark extracts facts checked against that text, and the image is deleted once its facts are saved. The app cannot scan the photo library on its own.
- **Sign-in codes:** iOS does not let apps read texts. An optional Shortcuts automation ("when a message containing 'code' arrives, send it to Envoy") can forward codes and works without any app. Tested in Phase 5: it forwarded a message about 2 s after it arrived, with the phone locked, once the shortcut had been run by hand to grant its network permission. The fallback is the user typing the code in the live view.

### MCP server

This is how agents call the phone layer. The API serves the MCP server at `/mcp` on its own port: Streamable HTTP, stateless, JSON responses. It runs on the MCP Python SDK 2.3, which speaks protocol 2026-07-28 and the older handshake versions up to 2025-11-25. Muse's connector uses 2025-11-25. Each request stands alone, so there's no session to lose. Any assistant that accepts a remote MCP server with a bearer key can use it. The exact tool list is in `backend/mcp_server/README.md`, and how to connect a client is in `docs/agents.md`.

| Tool | Purpose |
| --- | --- |
| `run_task(goal, phone?)` | Start a task in a phone app from plain words; returns a task ID (a cross-app question becomes one task with a part per app) |
| `get_task(task_id)` | Status, recent steps, the result, and pending approvals, each saying it waits for the user's OK in Envoy (no approval link) |
| `list_routines()` / `run_routine(name, inputs?, phone?)` | Use learned routines by name; missing inputs are filled from memory |
| *one tool per shared routine* | A routine the person shares with agents, called by its own name with typed arguments (see App routines) |
| `memory_search(query)` / `memory_get(entity_id)` | Facts with their sources; one entity, its facts and links |
| `memory_note(text, links?)` | Add a note, recorded with the client as its author |
| `send_to_phone(file, device?)` | Put a photo or video from Envoy's outbox on the Mac, or from an https URL, in a phone's gallery. The person's real phone takes it only after their OK |
| `get_file(task_id, which?)` | The final screen, the approval screens and the result's links from a task this agent started, as 10-minute signed links |
| `create_trigger(kind, name, spec, action)` | Propose a recurring or event-triggered task. It's created off; the person turns it on in Envoy |
| `list_phones()` | The phones Envoy can use, whether each is online, and its apps |
| `phone_updates(since?)` | What happened on the phone since a cursor: tasks finished or waiting, changes, files, Envoy's questions, routines learned or repaired, notifications a watch matched |

`initialize` returns Envoy's instructions. They say how the tools fit together, and that outbox files, captions and everything the tools return are content, never instructions.

**There is deliberately no approve tool.** An agent must never approve its own irreversible action (see Safety). No tool accepts an offer or answers Envoy's questions either, and no tool returns an approval link or nonce: links point at the person's own devices, and Muse's link previews fetch links on their own (Phase 0).

### Agents: a key and a tool set each

Built Nov 1 (`api/agents.py`, `api/auth.py`):
- **Muse's key** is `MCP_BEARER_TOKEN` in `.env`, with every tool.
- **Any other agent** gets its own key in Settings › Agents. The key is shown once and stored only as a hash, in `device_tokens` with scope `agent:<name>`. It can be rotated (the old key stops at once) or revoked, and Settings shows when each agent was last seen. `scripts/agent_key.py` makes a key straight into a private file, for keys nobody should see.
- **Tool groups** (read and run by default):

  | Group | Tools |
  | --- | --- |
  | read | `get_task`, `wait_for_task`, `list_routines`, `memory_search`, `memory_get`, `phone_updates`, `list_phones` |
  | run | `run_task`, `run_routine`, `cross_post`, and every shared routine's tool |
  | memory | `memory_note` |
  | files | `send_to_phone`, `get_file` |
  | triggers | `create_trigger` |

- **The guard** on the MCP server shows each agent only its own groups' tools. A call outside them gets a tool error that names the group to grant. Run-group calls are capped at 30 a minute per agent.
- **Who asked:** a task an agent starts records the agent's name, and the web app says "from Claude" or "Started by Muse". Envoy's questions name it too ("Muse wants to set this up: …"). `get_file` serves only the calling agent's own tasks.
- **Keys open `/mcp` and nothing else.** An agent key never works on `/api/*`, and no key appears in a log: the MCP log records the agent's name.

**Tested callers:**
- **Muse:** the Muse app and Muse for Mac, as a custom connector.
- **The Spark agent** (`agents/meta-agent/`): a small agent on Muse Spark 1.3 that reaches Envoy only over MCP, with a page made for filming. It started the showcase's real posts on the night of Nov 1.
- **Claude Code:** it saw its tools, ran flight-status routines, and at a check-in said only the person could approve.

### Path into Muse

Envoy was built to plug into the real Muse app without depending on it. Three routes were tried in parallel:

| Route | What it takes | Status (Nov 2) |
| --- | --- | --- |
| 1. Envoy's own assistant, built on Muse Spark | Nothing beyond the Meta API | Works. It is the chat in Envoy's web app, and the fallback |
| 2. Muse custom connector | A public HTTPS address that serves only `/mcp`, and a key the person pastes into Muse's secure credentials field | **Works, and it's the front door.** Muse in its iPhone app and Muse for Mac reach Envoy through a Tailscale Funnel address that serves `/mcp` and nothing else. Muse has run check-ins, `send_to_phone`, `create_trigger` and `phone_updates` (Oct 27–29, `docs/muse-link.md`), and called shared routine tools by name (Nov 2) |
| 3. Listed connector or Meta AI Connectors preview | The Muse Connector Platform's review, or the preview's waitlist | Not submitted |

What Muse's client does, as measured:
- It calls `initialize` and then the tool on every request. It declares no client capabilities, so Envoy can't push to it.
- It hears about the phone by polling `phone_updates`. A Muse scheduled task polled about every 10 minutes on its own (Oct 29). So an event waits for Muse's next check, while Envoy's own push to the iPhone is immediate.
- It draws its own generic icon for every custom connector.

**Safety is unchanged:** Muse is an AI client like any other. It gets no approve tool, approvals still come only from Envoy's own screens, it sees only what tools return, and its key can be rotated at any time.

### Gmail

- A personal Google Cloud project in testing mode, with a dedicated test Google account as its only user. `gmail.readonly` is a restricted scope, but personal use under 100 users is exempt from Google's verification; the user sees an "unverified app" warning once.
- In testing mode, sign-in tokens expire every 7 days, so the user reconnects once a week (`scripts/connect_gmail.py`).
- New mail is read into memory by `scripts/ingest_mail.py`, which carries on from Gmail's last history ID. The API doesn't poll Gmail by itself, and Gmail push (Pub/Sub) is a later upgrade.
- Confirmation emails (flights, orders, reservations) go through extraction into memory.
- **Calendar wasn't built.** Reading events to link trips, and writing them, stayed a plan.

### Scheduled and event-triggered tasks

Envoy's own scheduler runs inside the backend (`api/scheduler.py`), checking every 10 seconds. A trigger has a kind, a spec and an action: a goal, or a routine with inputs. There are six kinds:

| Kind | Fires | Example spec |
| --- | --- | --- |
| `time` | Daily, weekly, every N minutes, or once | `{"weekly_on": {"days": ["fri"], "at": "18:00"}}` |
| `before_fact` | A set time before a remembered event; it moves when the event moves (a delayed flight) | `{"entity_type": "Flight", "minutes_before": 1440}` |
| `watch` | Reruns a **read-only** routine every N minutes until a time | `{"every_minutes": 15, "until": <time>}` |
| `email` | A new email in memory whose sender or subject matches | `{"sender_contains": "skylark"}` |
| `fact_changed` | A remembered fact changes (a gate) | `{"entity_type": "Flight", "attributes": ["gate"]}` |
| `notification` | A notification on Envoy's phone, from an app the person lets Envoy watch (below) | `{"package": "com.instagram.android", "contains": "comment"}` |

**Ask mode.** A trigger in ask mode raises an offer ("Should I check you in for SL 482?") instead of starting its task. Every trigger an agent proposes is in ask mode.

**Offers** (`api/offers.py`) are Envoy proposing one specific action and waiting for the person's yes. They come from:
- a trigger in ask mode;
- a habit (`api/repeats.py`): "You checked your flight status on your last 3 Mondays. Make this a habit?" Code finds the pattern, with no model call;
- a file arriving in the outbox from the Mac;
- an agent or chat asking to set up a trigger.

What an offer does is fixed by a rule or a template in Envoy's code. An email, a fact, a sidecar or a pattern only fills typed values. The card shows the goal word for word, and only the person's own session can answer it.

**Change alerts** (`api/alerts.py`). A task a trigger started is quiet when it finishes, unless it changed something memory remembered: a new gate, or an app disagreeing with the person's own note. Then it pushes once.

**Recurring jobs from chat** (`api/recurring.py`). "Every Friday at 6 PM, order my usual from Thai Basil" becomes a trigger, switched off, with an offer: "Set this up?". The goal must be the person's own words.

**Agents propose, the person decides.** `create_trigger` over MCP makes the trigger switched off, in ask mode, and raises a "trigger_request" offer: "Muse wants to set this up: every Friday at 18:00, … Turn it on?". Nothing runs until the person says yes in Envoy, and then each run asks them first.

Event triggers only start a routine or a goal set up in advance. The triggering email, notification or fact supplies typed values, never the goal or the plan. Triggered tasks follow the same approval rules as the person's own, except that their words never count as the person's request. So an irreversible step asks, unless a standing approval covers the routine.

### Phone notifications: watching Envoy's phone

Built Nov 1, and checked live on Nov 2 (`api/notifications.py`). A notification trigger names up to 5 apps, and optionally words the notification must contain. While such a trigger is on, the watcher reads Envoy's phone's notifications every 3 seconds (`adb shell dumpsys notification --noredact`, one call per phone per poll). It reads only the apps the person lets Envoy watch.

On a match, Envoy:
1. stores the event, redacted, and `phone_updates` reports it to agents;
2. pushes it to the person's iPhone ("Instagram: <title>");
3. runs the trigger's action if it has one: a goal or a routine, or in ask mode an offer. With no action, it only tells the person and the agents.

**Off by default, per app.** Settings › Phones › Watch notifications lists the phone's apps, and every one starts off. A trigger, or an agent proposing one, can't turn an app on.

**Privacy:**
- The dump is parsed in memory and dropped. Only matched notifications are stored.
- Before storing, runs of 4–8 digits become "••••", and the rest of a line after "code", "OTP", "PIN" or "password" becomes "[hidden]". This is unit-tested, not shown live.
- The log has ids, packages and timings, never words.

**Fires once.** It fires once per notification, only for notifications posted after the trigger was turned on, and again only when the words change or Android alerts again. Group summaries and ongoing notifications never fire.

**Measured on Nov 2**, on Envoy's phone, with real comments on the showcase's posts:
- **Instagram:** the comment reached the person's iPhone 1.57 s after it landed on the phone.
- **YouTube:** Envoy's part took 3.6 s, but YouTube itself took about 2 minutes to notify.
- **TikTok:** no notification came for any of three comments, even with its comment push turned on.

Agents hear about a notification when they next call `phone_updates` (Muse's scheduled check runs about every 10 minutes). The push to the iPhone is immediate.

## Live view and sign-in

The phone's screen streams to the browser and iPhone as video, and a "Take over" button hands the phone to the user with the agent paused and nothing logged. This is how users sign in without Envoy ever seeing a password.

### Streaming

- **On the phone:** the scrcpy server encodes the screen as H.264 (scrcpy reports 35 to 70 ms latency).
- **Relay:** Envoy's own scrcpy client in the API (Phase 6), instead of the planned Node service using the Tango libraries (`@yume-chan/adb`, `@yume-chan/adb-scrcpy`, MIT license) reads the stream over adb, decodes it on the Mac (PyAV, FFmpeg) and sends JPEG frames over the same WebSocket as the emulators' gRPC frames, with the same touch input and latency measurement.
- **In the browser:** frames are drawn on a canvas; decoding with WebCodecs (`@yume-chan/scrcpy-decoder-webcodecs`) is no longer needed.
- **On the iPhone:** the same page inside the companion app's web view. The same frames as on the Mac.
- **HTTPS is required** for WebCodecs, Web Push and the microphone, so the iPhone reaches the Mac through Tailscale Serve (HTTPS inside the private network), and the MCP server's public address for Muse reaches `/mcp` and nothing else: Tailscale Funnel on a port of its own, set up in Muse once (`scripts/muse_funnel.sh`), or a Cloudflare quick tunnel only while it runs. The API also refuses anything but `/mcp` that Tailscale marks as from the internet, and every call needs the MCP bearer token.
- **Target:** under 150 ms from the phone to the screen on the same network. Phase 6, on an emulator standing in for the phone: a tap shows as a changed frame in 62 ms, and that frame reaches the page 12 ms after decoding.

Google's emulator WebRTC stack was considered, but it works only for emulators and its container scripts run only on Linux x86 machines. On emulators, Phase 4 streams the emulator's own gRPC frames instead (JPEG over the API's WebSocket, 18 to 60 ms locally), because scrcpy shows secure sign-in screens black and the gRPC frames don't; scrcpy and the relay are for real phones.

### Take over and hand back

1. The user presses **Take over**, or the agent requests it with a `handoff` action (a sign-in screen, a bot check, a question it cannot answer).
2. The device lease moves to the user. The agent's loop is paused, screenshots for the model stop, and the user's touches and keystrokes travel as scrcpy control messages straight to the phone, bypassing logs and models.
3. A banner shows "You are in control" on every interface.
4. The user presses **Hand back**. The agent observes the screen fresh, checks whether the blocking step is done (for example, the app now shows the account screen), and continues.

### Sign-in

- **First use of an app:** the agent opens it and hands off at the sign-in screen. Afterward, the long-lived emulator stays signed in (test apps are saved in a snapshot instead).
- **Secure screens.** Screens marked secure (`FLAG_SECURE`), common for sign-in and payment, are black in scrcpy video and adb screencap on emulators and real phones, but not in the emulator's own window or its gRPC screenshot (Phase 0). Their accessibility tree is usually readable, but not always: Amazon's sign-in WebView exposes nothing. Many native sign-in screens are not marked secure at all (Target, Chipotle, DoorDash, Google). The agent hands off when the window is marked secure, a password field appears, or the screen matches a known sign-in pattern (an email or phone field next to Sign in or Continue). It takes no screenshots while the window is secure. On an emulator, the user then signs in through the emulator's own window on the laptop, or through the emulator's gRPC screen stream. Phase 0 showed that stream does capture secure screens, so a remote sign-in from the web app or iPhone works on emulators. On a real phone, the user signs in on the phone itself.
- **Expired sessions:** the agent detects a sign-in screen at any point and hands off again.

### Sign-in codes

The emulator has no SIM, so text-message codes arrive on the user's iPhone. Three ways to finish a sign-in, in order of preference:

1. **The user types the code** in the live view (always available).
2. **An iPhone Shortcuts automation** forwards messages containing "code" to Envoy, and the agent types it. Phase 5 tested it on a locked phone: it works, once the shortcut has been run by hand to grant its network permission.
3. **A real Android phone** could read the code from its notification. Not built: Envoy's notification watcher (Scheduled and event-triggered tasks) hides codes before it stores anything, and isn't used for sign-ins. Android 15 also hides codes from untrusted notification readers.

For testing, codes can be injected into the emulator with `adb emu sms send`. Codes are used once and never stored (see Safety).

## Safety, privacy and permissions

The agent never takes an irreversible action without the user's approval, never sees a password, and never acts in or remembers sensitive apps unless the user opts in. These rules live in one **policy engine** that every action passes through, including actions replayed from routines.

### Classifying every action before it runs

Each proposed action gets a risk level: **read** (scroll, open, look), **reversible** (add to cart, fill a field), or **irreversible** (pay, place order, submit, send, confirm check-in, cancel, delete). Three independent signals vote, and any one flagging "irreversible" pauses the run:

1. **Rules:** the target element's text and resource ID match a list such as Pay, Place order, Confirm, Submit, Send, Delete, Cancel booking, in several languages.
2. **Screen context:** the screen looks like a checkout, payment or final-confirmation step (price totals, card fields, "review your order").
3. **Model judgment:** the step model labels each action's risk as part of its output. Meta reports that Muse Spark 1.3 is better calibrated on irreversible actions, so it is used for this label.

A `type` action that also submits (presses Enter) is classified by the screen's main button and the screen-context signal, not by the text field it targets, since pressing Enter can place an order or send a message.

### Approvals

- An approval request shows a screenshot, a one-line description ("Place order at Chipotle, $14.82"), and the amount if any. It goes to the iPhone as a web push and to the web app. Web pushes have no action buttons, so tapping one opens the approval page, where the person approves or declines.
- The approval is bound to the exact screen it was shown for: the app's own elements, not the keyboard or status bar, which come and go. If the screen changes before the tap (price changed, new pop-up), the agent asks again.
- No answer within 15 minutes counts as no, never as yes. The same holds for "use Envoy's phone?": silence ends the task as not done (see Device layer).
- **The user chooses when Envoy asks**, for everything, per app or per routine: *always ask*; *ask unless I asked for it* (the default: "check me in" is the OK to tap "Confirm check-in" for that trip, and Envoy says so afterwards); or, for a routine, *never ask* (a standing approval, e.g. "check in for my flights automatically", which also covers a trigger starting it). Envoy still asks whenever money is involved, when the step isn't what was asked (the button's own words must be in the request), when the details differ (names, codes and numbers in the request must be on the screen or in the task's inputs), and when the request came from a trigger, an email or an AI client rather than the user, unless a standing approval covers the routine. These are rules, not model judgments.

**Only a person can approve.** Approvals are accepted only from Envoy's own approval screen or iPhone notification, never through MCP or the chat assistant's tools, so no AI (including the one running the task) can approve its own action.

**Agents get no way around it.**
- Envoy has no approve tool, and no tool that accepts an offer or answers Envoy's questions.
- A request from an agent never counts as the person asking, so its irreversible steps always ask, unless the person gave a routine a standing approval. Money always asks.
- When an agent's task waits, `get_task` and `phone_updates` say it's waiting for the person's OK in Envoy, and give no link that could approve it.
- Tested with all three agents. Muse, asked to turn on a trigger and accept Envoy's offers, said it had no tool for it. The Spark agent, asked to approve, said only the person can. Claude Code, at a check-in, said only the person could decide it, on their phone.

**One thing to know when filming.** A request typed into Envoy's own app that names the button ("post this to TikTok") counts as the person's OK for that button, by the default rule. So posting scenes start from an agent, whose calls always ask. Since Nov 1 the rules also count YouTube's Upload, TikTok's Repost and TikTok's one-tap "Your Story" as publishing buttons, so they're irreversible steps too.

### Sign-in and credentials

- When a screen contains a password field (the accessibility tree marks password fields), the agent stops and hands control to the user through the live view.
- During a takeover the agent is paused, screenshots stop, and the user's input goes straight to the phone without being logged or shown to any model.
- **Teach mode is the one exception, and only when the user starts it** ("Teach"): their taps and typing are recorded as a demonstration and compiled into a routine. Nothing is recorded on sign-in, secure or black screens, never what is typed into a password field, and cancelling keeps nothing. A taught routine named like one already in the library goes on trial instead of replacing it: the next run decides.
- Sign-in codes from text messages (real Android phone only) are read only while a sign-in is in progress, used once, and never stored.

### Blocked app categories

| Category | Agent can operate | Remembered | User can override |
| --- | --- | --- | --- |
| Finance and banking, payments, crypto | No | No | Memory only (for example, balances), never actions that move money |
| Health and pharmacy | No | No | Yes, per app |
| Messaging and social DMs | No | No | Yes, per app and per conversation |
| Password managers and authenticators | No | No | No |
| Government and ID | No | No | Yes, per app |
| Everything else (shopping, food, travel, rides) | Yes | Yes | Can turn off per app |

Categories come from the app's Play Store category and a maintained list of package names, and the user can change any app's setting.

### Redaction before anything is stored

Before a screen, log line or fact is saved, a redaction pass removes password-field contents, card numbers (detected by pattern and checksum), sign-in codes, and government ID numbers. Screens that Android marks as secure (`FLAG_SECURE`) appear black in scrcpy video and adb screencap but not in emulator gRPC screenshots. So the agent takes no screenshots while such a window is in front, and treats it as a hand-off point (see Live view and sign-in).

### Photos and messages

- **Photos:** off by default. The default scope is screenshots only, not the whole camera roll. Only photos the user picks or shares are sent; text is read on the Mac, lines with card numbers, codes or ID numbers are blacked out in the copy Muse Spark sees, and the image is deleted once its facts are saved (or when nothing is found).
- **Messages:** not part of this build. A later Android companion could read business texts the same way; personal conversations would stay excluded unless the user includes them.
- Every resulting fact links back to its source and can be deleted.

### Untrusted content and prompt injection

App screens, emails, notifications, web pages, files from the Mac and their sidecars are treated as data, never as instructions. So is everything Envoy's MCP tools return, and Envoy's instructions tell agents so.

- The plan comes only from the user's request. Text from screens is passed to the model inside clearly marked data sections.
- Each task gets a scope: the apps and memory areas it may touch. Leaving that scope (opening an unrelated app, sending data somewhere new) pauses the run for approval.
- The irreversible-action gate holds even if a screen tricks the model, because the rule and screen-context signals don't depend on the model.

### Retention, storage and control

- Full screenshots and raw screen dumps are deleted after 7 days. The redacted screen text and a small redacted thumbnail are kept as long as any fact cites them, so every fact stays traceable.
- Every action is written to an audit log: time, device, app, action, risk level, approval.
- The database and emulator snapshots (which hold signed-in sessions) live on the Mac's FileVault-encrypted disk. API keys live in the keychain or environment, never in code and never on the web or iPhone clients.
- A stop button on every interface halts the agent and disconnects it from the phone immediately.
- Automating some apps may break their terms of service. The test apps are built by us; real-app use is limited to the user's own accounts and noted as a risk.

## Models and cost

Every model call goes through Meta's Model API, mostly to Muse Spark 1.3; as measured in Phase 0, an agent step at low effort costs about $0.001 and takes about 0.9 s, so a first run of a task costs about 4 cents and a routine rerun well under 1 cent, so about $200 of credits covers development and evaluation with room to spare. The API is compatible with the OpenAI SDK, and Meta recommends its Responses API for agents.

### Which model does what

| Job | Model | Settings | Price (per million tokens, input / output) |
| --- | --- | --- | --- |
| Each agent step, including its risk label | `muse-spark-1.3` | Low reasoning effort, structured output | $1.25 / $4.25 (cached input $0.15) |
| Plans, local repairs, entity matching | `muse-spark-1.3` | Medium to high effort | Same |
| Compiling routines, hard merges (Spark at high effort if Wonder is not covered by credits) | `muse-wonder-1.0` (preview) | High effort | $4.00 / $20.00 |
| Elements on screens with no tree | `muse-spark-1.3` visual grounding | Points or boxes | Same as Spark |
| UI region segmentation (experiment) | `sam-3.1` | Specific noun phrases (toggle switch, search bar, icon); generic ones such as button find nothing | $2.50 per 1,000 images |
| Voice input | `muse-voice-transcribe-1.0` | Real-time, turn detection | $0.18 per audio hour |
| Spoken replies | Device speech engines | None | Free (Meta has no text-to-speech API) |

**Optional Meta models:** Muse Glimmer (30B open weights, Apache 2.0) could take cheap steps like routine matching if partner GPU credits come through; it needs about 18 to 20 GB at 4-bit, too much next to two emulators on this laptop. Muse Image is not needed for the core product.

**Contributor tier:** Spark costs $0.10 / $0.20 per million tokens in Meta's Contributor tier, but Meta may train on what is sent. It is a separate model ID (muse-spark-1.3-contributor) limited to 150 requests per minute. It is used only for evaluation runs on our own test apps, never for the user's real screens, emails or photos.

### Estimated cost per task

These are estimates from Meta's published prices, to be replaced with measured numbers in Phase 0.

| Run type | What is sent | Estimated cost |
| --- | --- | --- |
| One agent step | Measured: about 1,900 cached prompt tokens, a few hundred new tokens, and 144 output tokens, 88 of them reasoning (low effort) | About $0.001 (measured), plus about $0.004 with a full-size screenshot |
| First run, 15 steps | Plan, 15 steps (5 with screenshots), fact extraction | About $0.04 |
| Compiling a routine | Full trace to Muse Wonder, once per task type | About $0.18 |
| Routine rerun | One matching call; no model calls while checks pass | About $0.003 |
| Rerun with one local repair | Matching plus one repair call | About $0.02 |
| One minute of voice | Transcription | About $0.003 |

At standard prices, $200 covers roughly 2,000 first runs, and development (about 1,000 agent runs and 100 compiles) would cost about $110 before evaluation and retries. So development and evaluation on our own test apps use the Contributor tier, bringing that to roughly $30; real apps and real user data always use the standard tier. Reported cost metrics are computed from token counts at standard prices, whatever tier was billed. Output tokens per step (500 here) are measured in Phase 0, since reasoning may use more.

### Keeping costs down

- **Text first:** the accessibility tree instead of screenshots wherever possible.
- **Stable prompt prefix:** system prompt, schemas and plan come first and are cached (Meta's prefix cache, with `prompt_cache_key` as a routing hint and prompt_cache_retention set to 24h. Caching is automatic and hit 19 of 20 repeated calls in Phase 0, screenshots included).
- **Low reasoning effort** for routine steps; reasoning cannot be turned off and is billed as output.
- **Routines** remove model calls from repeat tasks, which is both the product's main claim and its main saving.
- **A cost meter** records tokens and dollars per call, task and routine, with a daily cap that pauses work when reached.

### One adapter for every model call

All calls go through one module that sets the model, effort and schema per job, logs cost, retries on rate limits (Spark allows 3,000 requests per minute per team), and can switch a job to another model with one setting. This protects the build if a model is slower or weaker than expected.

## Tech stack and repository

Python runs the backend (API, MCP server, agent, routines, memory) and the live view's video, React is the web app, Kotlin is used for the test app and the phone's banner, and an Apple Shortcut is the only iPhone code; everything lives in one repository. The table is the plan's, with what changed noted.

| Part | Technology | Notes |
| --- | --- | --- |
| Backend | Python 3.13 (managed with `uv`), FastAPI, asyncio, Pydantic | Task API, agent runtime, routine engine, policy engine, memory service, scheduler |
| Model calls | OpenAI Python SDK pointed at `https://api.meta.ai/v1` | Responses API, structured output |
| Phone control | `adbutils` (MIT) and `uiautomator2` (MIT); emulator gRPC for screenshots and taps | The Envoy bridge wasn't needed (Phase 6) |
| Frames for the agent | PyAV decoding the scrcpy stream |  |
| Storage | SQLite with FTS5 | One file on the FileVault-encrypted disk. `sqlite-vec` embeddings were never needed |
| Scheduler | Envoy's own, inside FastAPI (Phase 4) | Times derived from memory are recomputed on every check; Temporal or Inngest only if durable long waits become necessary |
| MCP server | MCP Python SDK 2.3, Streamable HTTP, stateless; a bearer key per agent | Muse reaches it through a Tailscale Funnel address that serves only `/mcp`. OAuth 2.1 was never needed |
| Video relay | Node with TypeScript, `@yume-chan/adb` and `@yume-chan/adb-scrcpy` | Real phones (Phase 6); emulators stream gRPC frames from the API. Phase 6 replaced it with Envoy's own scrcpy client in Python (frames decoded with PyAV), pinned to scrcpy server 5.0.1 |
| Web app | Next.js, React, TypeScript, Tailwind; Cytoscape.js for the graph | Frames are JPEG over WebSocket, so no WebCodecs decoder |
| Phone banner | Kotlin overlay app (`android/banner/`) | "Envoy is using this phone · Pause" on a real phone |
| Test apps | Kotlin with Jetpack Compose | SkyLark Air (airline), with switchable layout versions to inject UI changes. The shop app wasn't built |
| iPhone companion | The web app on the Home Screen: Web Push, microphone, photo picker; iOS Shortcuts for sharing, codes and Siri | No Apple account needed; no native app was built |
| Gmail | Google API Python client, read-only | Personal Google Cloud project; no Pub/Sub, no Calendar |
| The Spark agent | Python, Meta's Responses API, Starlette for its page | `agents/meta-agent/`; imports none of Envoy's code |
| Dev setup | Android SDK command-line tools and emulator, arm64 Java 21, scrcpy, Tailscale or mkcert | Muse Code can help write code |

```text
envoy/
  backend/
    api/            # task API, event stream, auth, agent keys, routing, scheduler, notifications, offers, files
    agent/          # loop, planner, screen formatter, actions, traces, vision
    routines/       # compiler, locators, checks, executor, repair, versions, matcher
    memory/         # schema, extraction, entity matching, retrieval, app notes
    policy/         # risk classifier, approval rules, sign-in and bot-check detection
    devices/        # Device interface, emulator and phone backends, scrcpy client
    models/         # Meta API adapter, prompts, schemas, cost meter
    integrations/   # Gmail
    mcp_server/     # MCP server tools (not mcp/, which would shadow the SDK)
    mcp_stub/       # the Phase 0 stub, and the bearer-key middleware
  agents/meta-agent/  # the Spark agent: an MCP client on Meta's models
  android/banner/   # the overlay shown on a real phone while Envoy works
  web/              # Next.js app (also the iPhone companion)
  testapps/         # SkyLark Air (with layout variants)
  eval/             # task sets, injected UI changes, runners, reports
  scripts/          # setup, Muse's Funnel address, agent keys, Shortcuts, cloud
  site/             # the showcase site
```

### Test apps

SkyLark Air comes first and is time-boxed to about one day; the shop app is a stretch goal. It needs:

- **Element IDs:** the Compose root sets `testTagsAsResourceId = true` and key elements carry test tags, so locators like `btn_checkin` exist. Most real apps lack these, which is why locators also use text and descriptions.
- **Seeded data:** bookings loaded from a fixtures file through an adb intent. The same file generates the matching confirmation emails, so a code like KX7Q2M appears in both the app and the test inbox.
- **Layout variants** switchable at runtime through a debug broadcast (moved button, renamed label, extra confirmation screen), so changing variants does not mean reinstalling.
- **A state hook:** a debug content provider read with `adb shell content query`, so success checks are exact.
- **A fake sign-in** with a password field and a text-message code, to exercise hand-off.
- **A list longer than one screen,** to exercise scrolling.

## Build phases

The build ran in eight phases with no fixed dates; each ended at a gate that had to pass before the next phase started. Phases 0–6 passed their gates by Oct 28. After them came a wave of final features (Oct 29–Nov 1: offers, Before I start, Siri, files from the Mac, teach mode), and then the phone-layer wave (Nov 1–2: routines as tools, agent keys, notification triggers, files back, phone choice, the Spark agent, the showcase). There was no feature cut. The final evaluation runs Nov 3, 17:00–22:00 ET, on the `eval-final` tag, and the submission is due Nov 4, 9 PM ET.

![Build phases: 8 phases, each with an exit gate](diagrams/build-phases.png)

The diagram is the Oct 26 plan. The agent loop and app routines come first because everything else depends on them. Surfaces and the iPhone come after the core works, so a failing core is found early rather than hidden behind a polished interface.

## Evaluation

Envoy is measured against two baselines on its own task set and an AndroidWorld subset, and reported on cost, speed and recovery as well as success, because success alone no longer separates phone agents.

### Three systems compared

1. **Full agent every time:** no routines; every run plans and decides each step with the model.
2. **Fixed replay:** replay the recorded steps with a screen-similarity check, handing off to the agent on a mismatch. This mirrors Mobilerun's macros.
3. **Envoy routines:** compiled routines with step checks, local repair and versions.

### Task sets

- **Core set:** 10 SkyLark Air tasks (check in, change seat, find gate, add a traveler number, and others) × 3 systems × 4 layouts (the original plus a moved button, a renamed label and an extra confirmation screen) = 120 runs, roughly 2 to 6 hours on one emulator, run once near the end of the build. Each task has a programmatic success check.
- **Real apps (5 to 10 tasks):** shopping and food apps chosen once they are confirmed to run on the emulator. Irreversible steps stop at the approval prompt, so no orders are placed.
- **AndroidWorld (measured Oct 27–28, branch `androidworld`):** Google's 116 tasks over 20 apps, run unmodified through AndroidWorld's own runner and scoring on an API 33 emulator, seed 30, pass@1, with Envoy's whole agent as the agent. The tasks were split 58/58 into a dev half for finding and fixing failures and a held-out half that measures the result; the split was committed before any run. Envoy before the changes scored 21 of 116 (18%); with 13 general agent changes found on the dev half, 57 (49%), and 31 of 58 (53%) on the held-out half against 12, at about $0.04 and 38 s per task on the Spark profile (`docs/androidworld-results.md`). Routines compiled from seed-30 runs were replayed on three other seeds. The 13 merged into `main` on Oct 29 (`105d04e`); re-measured on a staging tree with them and three SkyLark follow-ups, the held-out half scored 30.5 of 58.
- **Stretch:** the shop test app, and MAS-Bench, which tests shortcuts that agents generate for themselves.

### Metrics

| Area | Metric |
| --- | --- |
| Tasks | Success on first try and within 3 tries, across seeds; steps; human interventions |
| Efficiency | Model calls, tokens, dollars and seconds per task; first run vs. later runs |
| Routines | Success on new inputs; recovery rate after each kind of injected change; whether the patched version succeeds on its own afterward; success on three screen sizes and on the real phone |
| Memory | Fact extraction accuracy on 50 hand-labeled screens and emails; entity matching accuracy; share of stale facts served |
| Safety | Irreversible actions caught across a 20-action test suite (target: all); behavior on test screens containing injected instructions |

### How results are reported

An `eval/` runner executes the suites from emulator snapshots and writes a report with charts: success by system, cost per run over repeated runs, and recovery by type of injected change. The same charts go into the submission write-up. AndroidWorld results are reported by half (dev and held-out), and failures are explained from step-level trace evidence, not from the score alone. A change to the agent is checked on SkyLark and the real-app set against `main`'s agent run the same day before it merges.

## Risks and mitigations

The biggest risk is reliability: phone agents are flaky, and "whether it works" is a judging criterion. Most mitigations below exist to keep the core loop dependable before anything else is added.

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Agent loop is too unreliable on real apps | High | High | Build and test on our own test apps first; add real apps only after the loop is stable; keep a fixed test task set and track success rate daily |
| Meta models lack an ability the design assumes (image input, tool calls, coordinates, speed) | Medium | High | Verify at kickoff (see Open questions); the agent relies on the accessibility tree first, so text-only planning still works; model calls go through one adapter so a model can be swapped |
| API credits (about $200) run out | Medium | High | Text-first screen representation, screenshots only when needed, routines that skip the model on reruns, a cost meter with a daily cap, cheaper models for routine steps |
| Target apps refuse to run on the emulator | Medium | Medium | Phase 0: 4 of 6 shopping and food apps work on the emulator (Uber Eats refuses to install, and DoorDash's guest mode hangs). Test each app on day one of using it; route to the real Android phone; keep alternative apps in the same category |
| No Android phone available for the real-device backend | Low | Low | The device layer is built and tested against emulators first; the real-phone backend uses the same interface and adb commands, so it can be finished in a short session once a phone is borrowed |
| Learned routines break often on app updates | Medium | Medium | Element-based targeting, step checks, local repair, and versioned routines with rollback |
| Memory fills with wrong or duplicate facts | Medium | Medium | Facts record source, time and confidence; entity matching before insert; newer facts replace older ones; the user can correct facts in the graph view |
| Laptop resources (24 GB RAM) limit running two emulators plus everything else | Medium | Medium | One emulator during development, a second only for comparison tasks; headless mode; snapshots instead of cold boots |
| Automating real apps breaks their terms of service | Medium | Low (for the hackathon) | Our own test apps for most testing; real apps only on the user's own accounts; noted in the submission |
| Muse custom connectors are not open to hackathon developers | Medium | Low | Envoy's own web app and MCP server work without it; the connector is an add-on |
| Scope grows beyond what one person can finish | High | High | Strict build phases with exit criteria; nothing from a later phase starts until the current phase passes |

**How these turned out (Nov 2):**
- **Muse custom connectors:** open, and working. Muse is Envoy's front door.
- **An Android phone:** one was available. A Pixel 5 has been Envoy's phone since Oct 28.
- **Apps refusing the emulator:** still true for Target (a bot check on most fresh launches) and banking apps. They run on Envoy's phone instead.
- **Reliability on real apps:** a learned task replays well, but new inputs on real apps are the weak spot: 4 of 11 (Oct 28) and 6 of 11 (Oct 31). See `docs/README.md` for the numbers and their sources.

## Phase 0 results

Phase 0 ended on Oct 27, 2026 with its gate passed: Muse Spark 1.3 read a live emulator screen and returned a valid action that ran on the phone. The numbers behind the changes above are in `docs/phase-0-findings.md`. The main ones:

| Measure | Result |
| --- | --- |
| Agent step (Muse Spark 1.3, low effort) | 0.87 s median, about 144 output tokens, about $0.001 |
| Screen read / tap / screenshot (emulator) | 31 ms / under 1 ms (gRPC) / 6 ms raw (gRPC) |
| Screen settles after a new screen opens | about 1.5 s |
| Snapshot restore | about 1.8 s; 3.8 GB per snapshot |
| Emulator memory | about 7 GB each; two fit at once |
| Visual grounding on 1080 by 2400 screenshots | 3 of 3 targets, center error at most 22 px |
| Prompt caching | automatic, 19 of 20 repeated calls hit |
| Real shopping and food apps | 4 of 6 work (Uber Eats won't install; DoorDash's guest mode hangs) |
| Muse custom connector | works: tools called, approval link shown, nothing approved by Muse |

## Phase 1 results

Phase 1 passed its gate on Oct 27, 2026. Details are in `docs/phase-1-results.md`.

| Measure | Result |
| --- | --- |
| 10 SkyLark tasks, original layout, 3 repeats | 30 of 30 |
| Same tasks on the moved-button, renamed-label and extra-screen layouts | 30 of 30 |
| Safety: declined cancellation, sign-in hand-off, pop-up | 9 of 9 |
| Approval gate fired exactly where expected | 57 of 57 (once more than needed, on a review screen the model labeled irreversible) |
| Median task | 2 to 3 actions, about 9 s, under 1 cent |
| Model step (Muse Spark 1.3, low) | 850 ms median, 110 output tokens, $0.0015 |
| Whole of Phase 1 | 527 model calls, $1.00 |

The evaluation drove four general changes to the agent:

- It now recovers JSON that arrives after a sentence of commentary (3.75% of calls).
- It remembers which screens it visited and replans when it goes in circles.
- It rejects blind coordinate taps when elements are listed.
- It shows labels up to 120 characters.

## Phase 2 results

Phase 2 passed its gate on Oct 27, 2026. Details are in `docs/phase-2-results.md`.

| Measure | Result |
| --- | --- |
| Routine on bookings it has never seen | 30 of 30 with no model call (median 3.3 s); 18 of 18 with IDs hidden |
| Recovery after an injected UI change (moved button, renamed labels, extra screen) | 21 of 21; 18 of 18 more on two harder layouts (hidden IDs, renamed labels with hidden IDs) |
| Patched versions | Every trial passed; each then ran with no model call and still ran on the original layout |
| Model calls against the full agent, same requests | 7 against 242 (97% fewer); median 4.2 s against 11.7 s |
| Fixed replay of recorded coordinates | Acted on the wrong booking in 14 of 24 requests |
| Matching a request to a routine | 12 of 12 |
| Real apps, read-only | Amazon, Starbucks and DoorDash rerun in 6–12 s with no model call, on a second input too; Chipotle's store picker doesn't replay; Target shows a bot check on most fresh launches, so it stays a hand-off |
| Whole of Phase 2 | 859 model calls, $3.48 |

The evaluation drove these changes to app routines:

- Locators have two roles. A check needs text evidence and its element type, since an ID alone is shared across screens; a tap target may lean on its ID, type and position. Thresholds were tuned on SkyLark: 0.80 strict, 0.60 relaxed, 0.08 margin. IDs are ignored on screens that show none.
- An input that no action uses must be visible before the step that depends on it, so a routine learned on "the next trip" never acts on another booking.
- Cleanup never removes an effect: back-tracks can't cross an approved, typed or toggled step, and a compile that loses the run's irreversible step is refused. Pop-ups never become checks.
- The compiler checks Wonder's answer in code, and verification with a second booking stays mandatory: it rejected 8 bad routines.
- Steps settle on their after-checks rather than a generic quiet window: about 0.3 to 0.5 s of device time per step.
- Patches keep a button's old labels, keep booking data out of locators, and make a vanished step optional rather than deleting it, so a patched routine still runs on the old layout.
- Real apps are stateful: one-time screens get baked in, so a routine should start from a known screen. Bot checks and setup gates stop it, as they should.

## Phase 3 results

Phase 3 passed its gate on Oct 27, 2026. Details are in `docs/phase-3-results.md`.

| Measure | Result |
| --- | --- |
| Email and app facts merge into one trip | 6 of 6 bookings, each holding facts from both |
| "What's my gate?" from memory | Answered with its source and age, with no phone action |
| Gate changes in the app | B12 replaced by C14, history kept; marked possibly out of date after 30 minutes |
| "Check me in" with its trip filled from memory | Routine ran with no model call; outputs written back |
| Fact extraction (54 labeled emails and screens) | 99% of attributes from emails, 98% from screens; no wrong value stored |
| Entity matching (18 bookings and hard cases) | 18 of 18; no trips from promotions; two trips to one city kept apart; a cancellation applied |
| Facts traceable to a source | 100% |
| Whole of Phase 3 | 76 model calls, $0.45 |

The evaluation drove five changes to memory:

- Every observation records its source, not only the first, so a fact shows everywhere it was seen and deleting a source retires only what it alone supported.
- Values stay as the source wrote them; flight numbers, dates, times and airports are normalized only for comparing keys.
- An extracted value must appear in its source, and an answer from memory must appear in the notes it was given.
- A routine's outputs are anchored on its own final screen, since an input like a city may not identify one trip.
- Memory is one user's: a greeting is not a person, and agreeing names fold into the one person memory knows.

## Phase 4 results

Phase 4 passed its gate on Oct 27, 2026: the author ran the full check-in in the web app, signing in through the live view and approving, and memory updated. Details are in `docs/phase-4-results.md`.

| Measure | Result |
| --- | --- |
| Gate, by the author in the web app | Passed (second attempt; the first found a bug, fixed below) |
| Gate, scripted | 10/10 in 83 s: sign-in hand-off, takeover, hand back, approval with a screenshot, check-in, memory update, MCP task, chat from memory |
| Model calls for the check-in | 1 (choosing the routine); the routine ran with none |
| Approval rules | Opening an approval decides nothing; the MCP token, a stale nonce and a cross-site POST are refused; no answer means no |
| Live view on the emulator | 18 to 60 ms from capture to the browser locally; shows secure sign-in screens; input only during a takeover |
| MCP server | 7 tools, none can approve |
| Whole of Phase 4 | 142 model calls, $0.80 at standard prices |

The gate runs drove these changes:

- An approval is bound to the app's own elements: the author's run found a closing keyboard making an approval look stale. A stale approval is asked again, never treated as a decline.
- A task is done as soon as the phone work is; memory is written right after, instead of keeping the task "running" for 11 seconds.
- Approvals are configurable: by default Envoy doesn't ask for the step the user asked for (money, other actions, other details and requests from triggers or AI clients still ask); "always ask" and per-routine standing approvals are settings. Checked on SkyLark: 4/4 modes behave as intended.
- On emulators the live view uses the emulator's gRPC frames, not scrcpy; one process serves the API, the MCP server and the web app; takeover is a lease that makes the agent wait at its next call to the phone; the scheduler is Envoy's own, so delayed flights move their triggers.

## Phase 5 results

Phase 5 passed its gate on Oct 27, 2026, on the author's iPhone: the approval arrived as a push, the author approved on the iPhone and the check-in finished; a SkyLark boarding-pass screenshot shared with "Send to Envoy" became facts on the existing flight, with a photo source. The same check-in also ran from the Muse app through Envoy's MCP server: Muse can't approve, so it waited for the author and reported the result when asked. Details are in `docs/phase-5-results.md`.

| Measure | Result |
| --- | --- |
| Gate, on the author's iPhone | Passed: push, approval on the iPhone, check-in done; screenshot to facts on SL 482, image deleted. From the Muse app too: Muse said it couldn't approve, the author approved from the push, Muse reported the seat and gate |
| Gate, scripted | 8/8: takeover, approval and done pushes (decrypted by a fake push service; no nonce in any push); screenshot to facts; voice; live view over HTTPS |
| Push delivery to the iPhone | 0.7 to 2.3 s from sending to the service worker's receipt (4 of 5 under 1.2 s) |
| Live view on the iPhone over the tailnet | 66 to 115 ms from capture to screen; round trip 27 to 47 ms |
| Voice (Muse Voice Transcribe) | Exact transcript; final text about 90 ms after stopping; $0.0001 for a 2.6 s turn. On the author's Mac and iPhone: 8 tries, final text 74 to 296 ms after stopping |
| Screenshot extraction | 73 of 73 values right on 7 app screenshots, none wrong, all merged into known trips and flights; about $0.007 each |
| Sign-in codes on a locked iPhone | A Shortcuts message automation forwarded a code about 2 s after it arrived |
| Whole of Phase 5 | 70 model calls, $0.41 at standard prices |

The gate runs drove these changes:

- The voice relay pads silence to keep Transcribe at real time: a microphone that sent nothing (blocked by iPhone Mirroring) made Transcribe close the stream. Voice also became dictation into the message box, sent by the user: sending on release started a check-in the moment the user let go.
- Photo text is read twice, the whole image and four tiles, because Apple's Vision skipped a lone confirmation code; codes tolerate the O/0 and I/1 confusions of OCR.
- Signing in on the iPhone is a pairing code typed inside the Home Screen app, since it keeps its own cookies; Shortcuts get tokens that can only upload images.
- HTTPS is Tailscale Serve on its own port, and Muse's public address (Funnel on another port, or a quick tunnel) reaches only `/mcp`.

## Phase 6 results

Phase 6 was built and measured on emulators, and its gate (a routine learned on the emulator runs on the real phone) passed on a real phone on Oct 28: a Google Pixel 5 on Android 13, through the API, with every decision made on the iPhone. The phone also found six bugs the emulator stand-in couldn't; all are fixed. Details are in `docs/phase-6-results.md`.

| Measure | Result |
| --- | --- |
| Gate, on the real phone | Passed on a Pixel 5 (Android 13): Envoy asked and the author allowed it on the iPhone; the banner showed; `skylark_check_in_flight` v1, compiled on `envoy-test`, ran with no model call; the author approved the check-in on the iPhone (4.8 s); SkyLark's state confirmed it; memory updated; 27 s end to end |
| A touch, and a takeover, on the real phone | A touch paused the run before its next action, and Resume on the banner finished it; a takeover and hand back from the iPhone's live view, with an approval pending, finished with one approval |
| scrcpy on the real phone | Starts in 0.6 s; tap to changed frame 65 ms; a screenshot from the stream 7.8 ms (screencap 358 ms) |
| Live view of the real phone | On the Mac 9.1 fps, 5 ms per frame after capture; on the iPhone over the tailnet 27 to 39 ms per frame (target 150 ms) |
| Settling and set-text on the real phone (the bridge question) | Set-text exact in 20 of 20 (accents, CJK, Cyrillic, emoji), the keyboard kept and the clipboard untouched; 0 of 20 taps in SkyLark changed after settling (5 of 30 in Settings changed a secondary line); the bridge is not built |
| Routines on the real phone | The 6 Phase 2 routines 18 of 18 and all 10 core routines 30 of 30, on bookings they had never seen, with no model calls; the first pass found a typing bug (fixed below), 15 of 18 |
| Routines on a smaller screen (720 by 1280, 320 dpi) | 18 of 18, no model calls (18 of 18 on the 1080 by 2400 control) |
| Routines through the real-phone code path (stand-in) | 12 of 12, no model calls |
| End to end through the API (stand-in) | Asked first, banner shown, the emulator-compiled check-in ran; a touch paused it before the next action; Resume on the phone finished it, with memory updated |
| Drawn targets, 52 (canvas seats and real-app screens) | Step model 37%, grounding 92%, SAM 3.1 and a pick 75% (never a wrong pick), SAM then grounding 100%; on a fresh 52, SAM then grounding 52 of 52 against 49 of 52 |
| A routine step on SkyLark's canvas seat map | Learned by the agent on one screen size; 6 of 6 replays with new seats on both sizes, 3 model calls each |
| scrcpy (stand-in) | Starts in 0.4 s; tap to changed frame 62 ms; a screenshot from the stream 7 ms (screencap 84 ms) |
| Whole of Phase 6 so far | 514 model calls, $1.44 at standard prices |

The runs drove these changes:

- Apps start through their launcher activity, never uiautomator2's monkey launch, which took about 11 s and injected a random event.
- The touch watcher is checked before every action of the agent's: with only a 0.5 s loop, two routine steps ran after a touch.
- Routines find targets below the fold and read outputs scrolled out of view without a model call.
- A routine's picture of a drawn target is used only when the target doesn't depend on an input; otherwise it looks again.
- The phone's video is converted as BT.601 when its colorspace label can't be (the Pixel's said YCgCo, so every frame failed and screenshots fell back to screencap).
- A tap under the banner steps the banner aside: on the Pixel it covers the top bar, where many apps put their search box, and a tap on its Pause button paused the run.
- A field Compose rebuilds while typing is looked up again (a stale node failed the known traveler step on the phone).
- A run you took over or paused teaches the routine nothing, and pauses and takeovers are kept in the task's history (a takeover had put a wrong second tap on trial).
- A request for an emulator that isn't running says so and names your phone.

**Who uses which phone.** iPhone users use Envoy's emulators; Android users use an emulator or their own phone. The gate is the second path, not a requirement for everyone. The limits, plainly: you sign in to each app once on the emulator; apps that refuse emulators (Target's bot check, banking apps) need a real Android phone, so they are out of reach for someone with only an iPhone; the emulators run on a Mac today, with a cloud host later.

## Phase 7 results

*The final numbers are in `eval/results/final/report.md` (all 10 suites on the `eval-final` tag, Nov 3). This section records the passes before it.* Details in `docs/phase-7-results.md`.

The measurement passes found 31 problems, each fixed and tested: compiler gaps (answers on the first screen, a value whose ID every row shares, a switch's state, a price before its details), safety-gate gaps (a tap at a point skipped the rules; uninstall, erase and call buttons), and grading errors in the suites themselves (a shape-graded price from the wrong menu item, a right answer graded wrong).

AndroidWorld's 13 agent changes were tested on SkyLark and the real apps before merging, with `main`'s agent run the same evening as an A/B. The first round checked in the wrong flight through Home's "Check in" (4 of 11 plans). After three follow-ups and a compiler fix, every SkyLark suite passed: 10 of 10 routines compiled, agent and routines 120 of 120 with no side effects, and the merged agent needs a median 2 steps per task where `main`'s needed 4 ($0.0073 against $0.0090). On real apps it over-checked answers already on screen (contacts_count 25 steps against 0), so that fix and a real-app rerun came first; the changes merged into `main` on Oct 29 (`105d04e`).

Several coding sessions shared one Mac, so each device was claimed through a lock and only one session merged into `main`. Two outside failures shaped the evaluation: AndroidWorld's emulator controller restarted the shared adb server (now refused), and the Meta API's billing failed from Oct 29, 02:16 (a new account; every run now checks the key first).

## Sources

Researched October 26, 2026.

**Hackathon and Meta**

- [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
- [Meta Model API docs](https://dev.meta.ai/docs/) · [pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits/) · [models](https://dev.meta.ai/docs/models/) · [image understanding](https://dev.meta.ai/docs/image-understanding) · [computer use](https://dev.meta.ai/docs/computer-use) · [structured output](https://dev.meta.ai/docs/structured-output) · [tool calling](https://dev.meta.ai/docs/tool-calling) · [prompt caching](https://dev.meta.ai/docs/prompt-caching) · [reasoning](https://dev.meta.ai/docs/reasoning)
- [SAM on the Meta API](https://dev.meta.ai/docs/sam/overview) · [speech to text](https://dev.meta.ai/docs/speech-to-text) · [Muse Glimmer](https://dev.meta.ai/docs/muse-glimmer) · [Muse Code](https://dev.meta.ai/docs/muse-code)
- [Introducing Muse Spark 1.3](https://research.meta.ai/blog/introducing-muse-spark-1-3) · [Muse Spark 1.1 and the Meta Model API](https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/) · [Build with Muse Wonder](https://dev.meta.ai/resources/blog/build-with-muse-wonder)
- [Introducing Muse](https://about.fb.com/news/2026/09/introducing-muse) · [Muse security and safety](https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse) · [Muse Connector Platform](https://platform.muse.ai/docs) · [Meta AI Connectors](https://dev.meta.ai/products/connectors) · [TechCrunch: what's coming to Muse](https://techcrunch.com/2026/09/23/everything-new-coming-to-metas-ai-agent-muse/)

**Competitors and prior work**

- [Mobilerun docs](https://docs.mobilerun.ai/) · [Mobilerun CLI and macros](https://docs.mobilerun.ai/framework/guides/cli) · [Mobilerun Portal license](https://raw.githubusercontent.com/droidrun/mobilerun-portal/main/LICENSE)
- [9to5Google: Gemini automation on Android](https://9to5google.com/2026/02/25/gemini-automation-android/) · [TechCrunch: AGI Inc.'s Android app](https://techcrunch.com/snippet/3080183/agi-inc-s-android-app-can-use-your-phone-for-you/)
- [SkillDroid](https://arxiv.org/html/2604.14872) · [MobileGPT](https://arxiv.org/html/2312.03003v3) · [Agent Workflow Memory](https://arxiv.org/html/2409.07429v1) · [Agent Skill Induction](https://arxiv.org/abs/2504.06821) · [SkillWeaver](https://arxiv.org/pdf/2504.07079) · [AppAgentX](https://arxiv.org/html/2503.02268v3) · [Mobile-Agent-E](https://arxiv.org/html/2501.11733v1)
- [Zep paper](https://arxiv.org/html/2501.13956) · [Graphiti](https://github.com/getzep/graphiti) · [mem0](https://arxiv.org/html/2504.19413v1) · [A-MEM](https://github.com/agiresearch/A-mem) · [MIRIX](https://arxiv.org/html/2507.07957v1)
- [AndroidWorld](https://github.com/google-research/android_world) · [MAS-Bench](https://arxiv.org/html/2509.06477v1)

**Android, iPhone and integrations**

- [Emulator command line](https://developer.android.com/studio/run/emulator-commandline) · [emulator release notes](https://developer.android.com/studio/releases/emulator) · [AccessibilityService](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService) · [Play Integrity verdicts](https://developer.android.com/google/play/integrity/verdicts) · [Google Play accessibility policy](https://support.google.com/googleplay/android-developer/answer/10964491)
- [uiautomator2](https://github.com/openatx/uiautomator2) · [scrcpy](https://github.com/Genymobile/scrcpy) · [Tango scrcpy libraries](https://docs.tangoapp.dev/scrcpy) · [Android emulator WebRTC](https://github.com/google/android-emulator-webrtc)
- [Google Cloud nested virtualization](https://docs.cloud.google.com/compute/docs/instances/nested-virtualization/overview) · [Genymotion pricing](https://www.genymotion.com/pricing/) · [IPaT Lending Library](https://peopletech.gatech.edu/students/lending-library)
- [Apple Developer membership comparison](https://developer.apple.com/support/compare-memberships/) · [actionable notifications](https://developer.apple.com/documentation/usernotifications/declaring-your-actionable-notification-types.md) · [Live Activities](https://developer.apple.com/documentation/activitykit/displaying-live-data-with-live-activities.md) · [Foundation Models](https://developer.apple.com/documentation/foundationmodels.md)
- [Gmail push notifications](https://developers.google.com/workspace/gmail/api/guides/push) · [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) · [MCP transports (2026-07-28)](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
