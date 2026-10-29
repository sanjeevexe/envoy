# Set-aside episodes of the final re-measure (kept for the record, not counted)

## api-outage/ (99 episodes, Oct 28, 10:49–11:12 EDT)

From 10:49 the Mac could not reach Meta's Model API: every model call failed with `APIConnectionError: Connection
error.` (the network itself was up again by 11:19, when `https://api.meta.ai/v1/models` answered 401 without a key, as it
should). The runner kept going, so 98 episodes in a row ended within seconds with Envoy's status `error`, and AndroidWorld
scored them 0:
- 97 failed at the plan call, before Envoy touched the phone (0 device steps).
- ExpenseDeleteDuplicates2 lost the API mid-episode, after 12 device steps and 18 model calls.
- RetroPlayingQueue: Envoy failed before acting, so Retro Music's playing queue was never created and AndroidWorld's own
  check raised `sqlite3.OperationalError: no such table: playing_queue` (a harness exception).

None of these measures the agent. All 99 tasks were rerun into the same stage once the API answered. The 17 episodes
before the outage (AudioRecorderRecordAudio through ExpenseDeleteDuplicates) stand.

Fix in the runner: if Envoy can't reach the model before it acts, the agent shim waits for the API (polling every 30 s,
up to an hour) and starts the episode again with a new run id, recording `harness.api_outage_retries`. If the API is lost
mid-episode, the episode is recorded as it happened and flagged `harness.api_lost_mid_episode`, and the next task waits
for the API. If the API never comes back, the stage stops, and a resume reruns the task.

## A second outage (Oct 28, from about 11:56 EDT)

The resumed stage ran 31 more episodes normally. Then RecipeAddMultipleRecipesFromMarkor2 lost the API after 9 device
steps and 9 model calls (Envoy run `aw-final-standard-1028-115503-469b`, status `error`, `APIConnectionError`). The new
guard did what it should: it waited an hour for the API, then stopped the stage (exit 3) before AndroidWorld scored the
task. So there is no record or checkpoint for it here, and the resume at 16:34 reran it first. The connectivity problem
was on this Mac's side (the user confirmed it). None of the 48 episodes kept by then had an API error, an outage retry
or a lost-API flag.
