-- Proposal only. Validate in an empty, isolated SQLite database.
-- This is not a migration for the existing events/state tables.
-- UTC timestamps: fixed-width ISO-8601, e.g. 2026-09-19T06:00:00.000Z.
-- Every connection must enable foreign_keys and configure busy_timeout.
-- Enable WAL separately ONLY after checking the filesystem supports it.
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

BEGIN;

CREATE TABLE memory_sessions (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    UNIQUE (owner_id, id)
);

CREATE TABLE memory_episodes (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_id TEXT,
    build_target TEXT,
    revision TEXT,
    issue_key TEXT NOT NULL,
    issue_key_version INTEGER NOT NULL DEFAULT 1,
    error_kind TEXT,
    error_code TEXT,
    file_path TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('active', 'paused', 'resolved', 'abandoned', 'unknown')
    ),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 0 CHECK (observation_count >= 0),
    confirmed_failure_runs INTEGER CHECK (confirmed_failure_runs >= 0),
    active_seconds_estimate REAL CHECK (active_seconds_estimate >= 0),
    resolved_at TEXT,
    resolution_text TEXT,
    resolution_evidence_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT,
    previous_episode_id TEXT REFERENCES memory_episodes(id),
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (owner_id, session_id) REFERENCES memory_sessions(owner_id, id),
    CHECK (last_seen_at >= first_seen_at)
);

CREATE INDEX memory_episodes_current
    ON memory_episodes(owner_id, session_id, status, last_seen_at);
CREATE INDEX memory_episodes_issue
    ON memory_episodes(owner_id, project_id, issue_key, last_seen_at);

CREATE TABLE memory_observations (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    project_id TEXT,
    source TEXT NOT NULL CHECK (
        source IN ('screen', 'utterance', 'run_result', 'task_switch',
                   'presence', 'agent_status', 'legacy')
    ),
    captured_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    capture_seq INTEGER,
    schema_version INTEGER NOT NULL,
    observation_json TEXT NOT NULL,
    hypotheses_json TEXT NOT NULL DEFAULT '[]',
    evidence_text TEXT NOT NULL DEFAULT '',
    content_hash TEXT,
    issue_key TEXT,
    run_id TEXT,
    producer_id TEXT,
    primary_episode_id TEXT REFERENCES memory_episodes(id),
    expires_at TEXT,
    FOREIGN KEY (owner_id, session_id) REFERENCES memory_sessions(owner_id, id)
);

CREATE INDEX memory_observations_recent
    ON memory_observations(owner_id, session_id, captured_at, seq);
CREATE INDEX memory_observations_episode
    ON memory_observations(primary_episode_id, captured_at);
CREATE INDEX memory_observations_run
    ON memory_observations(owner_id, session_id, producer_id, run_id);
-- Exactly one final run_result per producer/run in this contract.
-- If lifecycle/correction events are needed, version that contract first.
CREATE UNIQUE INDEX memory_observations_one_run_result
    ON memory_observations(owner_id, session_id, producer_id, run_id)
    WHERE source = 'run_result' AND producer_id IS NOT NULL AND run_id IS NOT NULL;

CREATE TABLE memory_working_state (
    session_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    project_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    last_processed_seq INTEGER NOT NULL DEFAULT 0,
    latest_screen_at TEXT,
    updated_at TEXT NOT NULL,
    state_json TEXT NOT NULL,
    FOREIGN KEY (owner_id, session_id) REFERENCES memory_sessions(owner_id, id)
);
-- last_processed_seq is a durable reducer cursor, not a deletable row FK.
-- state_json includes active episode IDs, recent interaction, uncertainty,
-- and source-specific watermarks for handling out-of-order observations.

CREATE TABLE memory_items (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    project_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('preference', 'solution', 'decision', 'episode_summary')),
    scope TEXT NOT NULL CHECK (scope IN ('project', 'user')),
    reusable INTEGER NOT NULL DEFAULT 0 CHECK (reusable IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'confirmed', 'superseded', 'expired')),
    preference_key TEXT,
    text TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT '',
    evidence_snapshot_json TEXT NOT NULL DEFAULT '[]',
    source_episode_id TEXT REFERENCES memory_episodes(id),
    valid_from TEXT NOT NULL,
    valid_until TEXT,
    supersedes_id TEXT REFERENCES memory_items(id),
    version INTEGER NOT NULL DEFAULT 1,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((scope = 'project' AND project_id IS NOT NULL)
        OR (scope = 'user' AND project_id IS NULL)),
    CHECK (kind != 'preference' OR preference_key IS NOT NULL)
);

CREATE INDEX memory_items_scope
    ON memory_items(owner_id, scope, project_id, status, kind);
CREATE UNIQUE INDEX memory_items_current_user_preference
    ON memory_items(owner_id, preference_key)
    WHERE kind = 'preference' AND scope = 'user' AND status = 'confirmed';
CREATE UNIQUE INDEX memory_items_current_project_preference
    ON memory_items(owner_id, project_id, preference_key)
    WHERE kind = 'preference' AND scope = 'project' AND status = 'confirmed';

CREATE TABLE memory_evidence (
    memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    observation_id TEXT NOT NULL REFERENCES memory_observations(id),
    PRIMARY KEY (memory_id, observation_id)
);
-- Restrictive source FK is intentional: retention/purge must first process
-- dependent memories and evidence snapshots, then remove these links.
-- Application must validate same-owner provenance before inserting any link.

-- Phase 2. Empty in MVP. Encoding: little-endian float32, L2-normalized.
CREATE TABLE memory_embeddings (
    memory_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    memory_version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (memory_id, model_id, model_version),
    CHECK (length(vector) = dimensions * 4)
);

COMMIT;

-- FTS5 is intentionally not installed by this baseline proposal.
-- Phase 2 must select Chinese tokenization, verify FTS5 availability, and
-- implement transactional insert/update/delete synchronization with memory_items.
-- Always scope retrieval to authenticated owner and allowed project BEFORE ranking.
-- Never compare vectors with different model/version/dimensions; reject stale hashes.
