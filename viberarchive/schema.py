"""archive.db schema. Rows are only ever added; nothing here deletes data."""
import os
import sqlite3

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS source_snapshot (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,            -- pc-old | pc-new | phone
    label TEXT,
    path TEXT,
    sha256 TEXT NOT NULL UNIQUE,
    imported_utc TEXT NOT NULL,
    first_event_ms INTEGER, last_event_ms INTEGER,
    events_total INTEGER, content_total INTEGER, reaction_total INTEGER, standalone_total INTEGER,
    excluded_events INTEGER, excluded_messages INTEGER,
    messages_created INTEGER, edits_attached INTEGER, edit_ref_missing INTEGER
);

CREATE TABLE IF NOT EXISTS chat (
    chat_key TEXT PRIMARY KEY,       -- direct:<digits> | group:<hash> | notes
    kind TEXT NOT NULL,
    title TEXT,
    peers_json TEXT,
    first_snapshot INTEGER REFERENCES source_snapshot(id)
);

CREATE TABLE IF NOT EXISTS contact (
    number TEXT PRIMARY KEY,         -- digits, or noid:<hash> when the contact has no number
    name TEXT, client_name TEXT, raw_json TEXT,
    first_snapshot INTEGER REFERENCES source_snapshot(id)
);

CREATE TABLE IF NOT EXISTS message (
    id TEXT PRIMARY KEY,
    chat_key TEXT NOT NULL REFERENCES chat(chat_key),
    token TEXT,                      -- Viber's original message token
    direction TEXT NOT NULL,         -- in | out
    author TEXT,                     -- digits, or 'self'
    composed_ms INTEGER NOT NULL,    -- UTC epoch ms, the time the PC stored
    sent_ms INTEGER,                 -- delivery time from the phone, when it differs
    sort_order INTEGER, seq INTEGER,
    kind TEXT, text TEXT, caption TEXT,
    reply_json TEXT,
    media_path TEXT,
    status INTEGER, tick TEXT,       -- seen | sent | none
    flags TEXT NOT NULL DEFAULT '[]',
    version_count INTEGER NOT NULL DEFAULT 1,
    edited_ms INTEGER,
    source TEXT NOT NULL,
    first_snapshot INTEGER REFERENCES source_snapshot(id)
);
CREATE INDEX IF NOT EXISTS message_chat_time ON message(chat_key, composed_ms, sort_order, seq);
CREATE INDEX IF NOT EXISTS message_token ON message(token);

CREATE TABLE IF NOT EXISTS message_version (
    message_id TEXT NOT NULL REFERENCES message(id),
    ver_token TEXT NOT NULL,         -- token of the event that carries this version
    version INTEGER NOT NULL,        -- 0 = original, then edits in time order
    composed_ms INTEGER NOT NULL,
    kind TEXT, text TEXT, caption TEXT,
    raw_json TEXT NOT NULL,          -- the complete Events and Messages rows
    first_snapshot INTEGER REFERENCES source_snapshot(id),
    PRIMARY KEY (message_id, ver_token)
);

CREATE TABLE IF NOT EXISTS reaction (
    id TEXT PRIMARY KEY,
    chat_key TEXT NOT NULL REFERENCES chat(chat_key),
    message_id TEXT REFERENCES message(id),   -- NULL: the target is not in the database
    target_token TEXT,
    reactor TEXT NOT NULL,           -- me | peer
    reaction_id INTEGER,             -- 0 clears a reaction; NULL when unreadable
    composed_ms INTEGER NOT NULL,
    sort_order INTEGER,
    flags TEXT NOT NULL DEFAULT '[]',
    raw_json TEXT NOT NULL,
    first_snapshot INTEGER REFERENCES source_snapshot(id)
);
CREATE INDEX IF NOT EXISTS reaction_target ON reaction(message_id, reactor, composed_ms, sort_order);

CREATE VIEW IF NOT EXISTS reaction_effective AS
SELECT r.* FROM reaction r
WHERE r.message_id IS NOT NULL AND r.reaction_id IS NOT NULL AND r.reaction_id <> 0
  AND NOT EXISTS (SELECT 1 FROM reaction r2
                  WHERE r2.message_id = r.message_id AND r2.reactor = r.reactor
                    AND (r2.composed_ms > r.composed_ms
                         OR (r2.composed_ms = r.composed_ms AND r2.sort_order > r.sort_order)));

CREATE TABLE IF NOT EXISTS standalone_event (
    id TEXT PRIMARY KEY,
    chat_key TEXT REFERENCES chat(chat_key),
    event_type INTEGER, composed_ms INTEGER,
    raw_json TEXT NOT NULL,
    first_snapshot INTEGER REFERENCES source_snapshot(id)
);

CREATE TABLE IF NOT EXISTS source_record (
    snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
    entity TEXT NOT NULL,            -- message | version | reaction | standalone
    entity_id TEXT NOT NULL,
    local_event_id INTEGER,
    PRIMARY KEY (snapshot_id, entity, entity_id)
);

CREATE TABLE IF NOT EXISTS media (
    sha256 TEXT PRIMARY KEY, size INTEGER, mime TEXT, first_snapshot INTEGER
);
CREATE TABLE IF NOT EXISTS message_media (
    message_id TEXT NOT NULL, sha256 TEXT, original_path TEXT, confidence TEXT,
    PRIMARY KEY (message_id, original_path)
);

CREATE TABLE IF NOT EXISTS revision (          -- reserved for the future replica app
    id INTEGER PRIMARY KEY, message_id TEXT NOT NULL, created_utc TEXT NOT NULL,
    field TEXT NOT NULL, old_value TEXT, new_value TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS recon_run (
    id INTEGER PRIMARY KEY, started_utc TEXT NOT NULL, finished_utc TEXT, params_json TEXT
);
CREATE TABLE IF NOT EXISTS recon_finding (
    id INTEGER PRIMARY KEY, run_id INTEGER REFERENCES recon_run(id), kind TEXT NOT NULL,
    message_id TEXT, detail_json TEXT
);

CREATE TABLE IF NOT EXISTS excluded_token (       -- tokens only, so later sources can skip the same chats
    token TEXT PRIMARY KEY, chat_key TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_log (
    id INTEGER PRIMARY KEY, at_utc TEXT NOT NULL, snapshot_id INTEGER, level TEXT, message TEXT
);
"""


def connect(path):
    """Open (and create) the archive. Foreign keys are on; the journal is WAL for safe interruption."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(DDL)
    con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
    con.commit()
    return con
