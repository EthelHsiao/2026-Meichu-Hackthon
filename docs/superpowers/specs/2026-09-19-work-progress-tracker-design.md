# Work Progress Tracker Architecture

**Date:** 2026-09-19  
**Status:** Design approved in conversation; implementation pending plan review

## Goal

Build a privacy-conscious work-progress tracker for an Ubuntu Ryzen AI PC that periodically collects deterministic desktop context, sends selected observations and screenshots to a vision-language model running natively on the remote AMD MI300, and stores validated semantic memories suitable for later RAG queries.

## Success criteria

- The collector works across arbitrary desktop applications, including code editors, browsers, office software, terminals, design tools, and meeting applications.
- Local collection is cheap and continuous; remote VLM calls are rate-limited and change-triggered rather than made at every poll.
- The MVP captures timestamp, foreground app, foreground window title, screenshot, idle time, and running applications.
- Git, VS Code, browser, terminal, and other application-specific metadata are optional enrichers, never required fields.
- The MI300 performs native VLM inference and returns constrained, validated semantic JSON.
- Stored records support time/project/activity filtering and provide normalized text for future embeddings and RAG.
- Raw keyboard input is never collected. Sensitive optional metadata is disabled by default or explicitly redacted.

## Architecture

```text
Ubuntu Ryzen AI PC
  local state poller (5–10 seconds)
      -> universal observation
  screenshot capture (30 seconds / on trigger)
      -> normalized change detector
  bounded delivery queue
      -> MI300 FastAPI endpoint
  native VLM inference on MI300
      -> schema validation
  SQLite memory store
      -> future embeddings, RAG, and work-session summaries
```

The local agent observes desktop state without involving the VLM on every poll. It captures a screenshot at most every 30 seconds by default and sends an observation when a meaningful change is detected or when the minimum VLM interval of 60 seconds has elapsed. The MI300 service runs the VLM through its existing local Ollama deployment; the network boundary carries structured metadata and a screenshot only for selected observations.

The current `ai-pc-agent/screen_watcher.py` and `mi300-deploy/app/main.py` are extended additively. Existing `/events/screen`, `/events/note`, `/status`, and dashboard behavior remains compatible during the MVP migration.

## Timing and trigger policy

Default settings:

```text
LOCAL_POLL_SECONDS=10
SCREENSHOT_SECONDS=30
MIN_VLM_SECONDS=60
IDLE_THRESHOLD_SECONDS=60
```

The local poller may detect state changes more frequently than screenshots are captured. A VLM submission is scheduled when one or more of these conditions holds:

1. Foreground application changes.
2. Foreground window title changes significantly after normalization.
3. A screenshot perceptual hash changes beyond the configured threshold.
4. The user becomes active after crossing the idle threshold.
5. An enabled optional enricher reports a meaningful change.
6. At least 60 seconds have elapsed since the previous VLM submission and the user is not idle.

The detector coalesces repeated changes and permits only one in-flight VLM request. If the service is unavailable, the observation remains in a bounded local retry queue and collection continues.

## Universal observation contract

The universal contract contains fields that can be collected on any supported desktop:

```json
{
  "observation_id": "uuid",
  "timestamp": "2026-09-19T16:30:00+08:00",
  "foreground": {
    "app": "libreoffice",
    "window_title": "Project Proposal.odt",
    "workspace": null
  },
  "system": {
    "running_apps": ["libreoffice", "chrome"],
    "idle_seconds": 4
  },
  "screen": {
    "screenshot_path": "/var/lib/work-tracker/screenshots/uuid.jpg",
    "image_sha256": "...",
    "perceptual_hash": "..."
  },
  "enrichments": {
    "git": null,
    "vscode": null,
    "browser": null,
    "terminal": null
  },
  "previous_context": {
    "task": "Writing project proposal",
    "last_observation_seconds_ago": 40
  }
}
```

`foreground.app`, `foreground.window_title`, `system.running_apps`, `system.idle_seconds`, and `screen` are MVP fields. `workspace` is nullable because arbitrary applications do not expose a workspace concept. Missing enrichments are represented as `null` or omitted and do not fail collection.

Screenshots are stored locally using a configurable directory and retention policy. The request payload may contain a resized JPEG as base64; raw keyboard input is never included.

## Optional enrichers

Enrichers are independent, best-effort adapters behind a common interface. They must not make the universal collector fail.

- `git`: nearest repository, branch, and changed-file summary for coding work.
- `vscode`: active file and workspace when derivable from the focused window or local integration.
- `browser`: URL and title only when explicitly enabled; URL collection is privacy-sensitive and disabled by default.
- `terminal`: recent commands only when explicitly enabled; raw command arguments may contain secrets and must be redacted or disabled by default.
- Future application adapters: office document title, design document title, meeting metadata, or other non-keystroke context.

## MI300 semantic output

The MI300 endpoint accepts the observation plus image and invokes the native VLM with a strict JSON-only prompt. The service validates and normalizes the response before storing it.

```json
{
  "memory_id": "uuid",
  "start_time": "2026-09-19T16:29:30+08:00",
  "end_time": "2026-09-19T16:30:00+08:00",
  "project": "wildbot",
  "task": "Debugging microphone input",
  "activity": "debugging",
  "description": "Testing STT microphone capture and investigating audio-device issues.",
  "evidence": [
    "VS Code was focused on stt.py",
    "The wildbot Git repository had stt.py modified",
    "Terminal output showed audio-related debugging"
  ],
  "progress": "Still investigating microphone capture",
  "status": "in_progress",
  "confidence": 0.93,
  "source_observation_ids": ["uuid"],
  "search_text": "wildbot debugging microphone input STT audio device stt.py"
}
```

Allowed `activity` values:

```text
coding, debugging, researching, reading, writing, meeting,
communication, testing, designing, idle, unknown
```

`project`, `task`, and other semantic fields may be `null` or `unknown` when evidence is insufficient. The model must not invent a project, accomplishment, command, URL, or error that is not visible in the observation. Confidence is a number in the inclusive range 0–1.

`search_text` is a deterministic normalized concatenation of useful semantic fields for future embedding generation. It is not the embedding itself. The stored source observation remains available for auditability and reprocessing.

## Persistence

The existing MI300 SQLite database remains the MVP database. Add tables conceptually equivalent to:

```text
observations(
  observation_id PRIMARY KEY,
  timestamp,
  payload_json,
  screenshot_path,
  screenshot_hash,
  delivery_status,
  created_at
)

semantic_memories(
  memory_id PRIMARY KEY,
  start_time,
  end_time,
  project,
  task,
  activity,
  description,
  evidence_json,
  progress,
  status,
  confidence,
  source_observation_ids_json,
  search_text,
  raw_model_response,
  created_at
)
```

The schema supports later queries such as “what did I work on today?”, “how long did I spend debugging audio?”, and “what progress did I make on project X?” without requiring embeddings in this MVP. Embeddings and RAG retrieval are a follow-up layer over `semantic_memories.search_text` and structured filters.

## Privacy and failure behavior

- No raw keyboard or mouse input is collected.
- Browser URLs, terminal commands, and other potentially sensitive enrichments are opt-in.
- Screenshot retention is configurable; the remote service need not retain image bytes after inference.
- The VLM prompt instructs the model to use visible evidence only and return `unknown` when uncertain.
- A malformed VLM response is rejected, recorded as a failed analysis, and does not become a semantic memory.
- Network failure does not stop local polling; retries are bounded and observable.
- Screenshot capture, foreground detection, and optional enrichers fail independently with nullable fields and diagnostic logs.

## Testing strategy

- Unit-test foreground/idle/process adapters using command-output fixtures and dependency injection.
- Unit-test title normalization and perceptual screenshot change thresholds.
- Unit-test trigger coalescing, 60-second rate limiting, idle-to-active detection, and retry queue bounds.
- Validate observation and semantic JSON schemas, including unknown/null optional fields and invalid activity/confidence values.
- Test the MI300 endpoint with mocked model output for valid JSON, fenced JSON, malformed JSON, and out-of-range values.
- Test SQLite persistence and source-observation linkage.
- Run the existing project tests plus new AI-PC and MI300 tests without requiring a live desktop, network, or Ollama process.

## Non-goals for this MVP

- Embedding generation and vector database integration.
- Natural-language RAG query endpoints.
- Automatic long-term session segmentation beyond storing start/end context.
- Keystroke logging or full input event capture.
- Application-specific integrations that are not needed to validate the universal collector.
