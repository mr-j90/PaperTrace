-- PaperTrace monitoring store (SPEC §8): one row per chat turn, feedback folded in.
CREATE TABLE IF NOT EXISTS turns (
    turn_id       TEXT PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    question      TEXT NOT NULL,
    model         TEXT NOT NULL,
    tools_used    TEXT[] NOT NULL DEFAULT '{}',   -- route split: semantic/metadata/both/none
    latency_ms    INTEGER NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(10, 6) NOT NULL DEFAULT 0,
    error         TEXT,                            -- null = clean turn
    feedback      TEXT CHECK (feedback IN ('up', 'down')),
    feedback_comment TEXT
);

CREATE INDEX IF NOT EXISTS turns_ts_idx ON turns (ts);
