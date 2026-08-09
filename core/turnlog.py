"""Per-turn monitoring writes to Postgres (SPEC §8): the flat row behind Grafana.

Degrades gracefully: if Postgres is unreachable the write is logged and dropped —
monitoring must never take the chat path down.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

# USD per million tokens (input, output). Verify against anthropic.com/pricing
# when models change.
MTOK_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-5": (5.0, 25.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    # longest key first: deterministic when ids share prefixes
    for key in sorted(MTOK_PRICES, key=len, reverse=True):
        if key in model:
            in_price, out_price = MTOK_PRICES[key]
            return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    logger.warning("no price for model %s — cost recorded as 0", model)
    return 0.0


@dataclass
class Turn:
    turn_id: str
    question: str
    model: str
    tools_used: list[str]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    error: str | None


class TurnStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def ensure_schema(self) -> bool:
        try:
            schema = (Path(__file__).parent.parent / "monitoring" / "schema.sql").read_text()
            with psycopg.connect(self._dsn, connect_timeout=5) as con:
                con.execute(schema)  # type: ignore[arg-type,unused-ignore]
            return True
        except psycopg.Error:
            logger.warning("monitoring store unavailable — writes will retry per turn")
            return False

    def write_turn(self, turn: Turn) -> None:
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as con:
                con.execute(
                    "INSERT INTO turns (turn_id, question, model, tools_used, latency_ms,"
                    " input_tokens, output_tokens, cost_usd, error)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (turn_id) DO NOTHING",
                    (
                        turn.turn_id,
                        turn.question,
                        turn.model,
                        turn.tools_used,
                        turn.latency_ms,
                        turn.input_tokens,
                        turn.output_tokens,
                        cost_usd(turn.model, turn.input_tokens, turn.output_tokens),
                        turn.error,
                    ),
                )
        except psycopg.Error:
            logger.exception("failed to write turn %s", turn.turn_id)

    def set_feedback(self, turn_id: str, thumbs: str, comment: str | None) -> bool:
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as con:
                cursor = con.execute(
                    "UPDATE turns SET feedback = %s, feedback_comment = %s WHERE turn_id = %s",
                    (thumbs, comment, turn_id),
                )
                return cursor.rowcount == 1
        except psycopg.Error:
            logger.exception("failed to record feedback for turn %s", turn_id)
            return False
