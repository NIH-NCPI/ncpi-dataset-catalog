"""Swappable conversation/session stores.

Provides a ``SessionStore`` protocol, an ``InMemorySessionStore`` (dev/tests),
and a ``DynamoDBSessionStore`` (production, AWS-native TTL) — both implement the
same protocol. See issues #360 (abstraction) and #400 (DynamoDB backend).

The persisted ``SessionState`` carries the user/assistant text turns, the
current resolved ``QueryModel``, open disambiguation choices, and — for the
agentic loop — the serialized pydantic-ai message history (tool calls and
results) needed for continuity. ``truncate_history`` bounds that history on
long conversations.
"""

from __future__ import annotations

import asyncio
import math
import os
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .models import ConversationMessage, PendingChoice, QueryModel


class SessionState(BaseModel):
    """Persisted conversation state for both search paths.

    Holds the user/assistant text turns, the resolved ``QueryModel``, any open
    disambiguation choices (``pending``), and — for the agentic loop — the
    serialized pydantic-ai message history (``agent_message_history``: tool calls
    and results) needed for continuity across turns. The deterministic
    ``/search`` pipeline leaves the agent fields empty.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    # Serialized pydantic-ai ModelMessage objects for the agentic loop
    # (tool calls + results), so the orchestrator has full continuity. Empty
    # for the deterministic /search pipeline, which carries no agent history.
    agent_message_history: list[dict] = Field(default_factory=list)
    messages: list[ConversationMessage] = Field(default_factory=list)
    # Open disambiguation choices offered but unresolved, so they survive into
    # the next turn's injected state block.
    pending: list[PendingChoice] = Field(default_factory=list)
    query: QueryModel | None = None


def truncate_history(messages: list, max_messages: int) -> list:
    """Bound the agent message history sent to the model on long conversations.

    Keeps the first message (the original intent) plus the most recent
    ``max_messages`` entries.

    Args:
        messages: The full message history, oldest first.
        max_messages: Maximum number of recent messages to retain. Values <= 0
            keep only the first message.

    Returns:
        The truncated history, or the original list if already within bounds.
    """
    if max_messages <= 0:
        return messages[:1]
    # Result is first + last max_messages, i.e. up to max_messages + 1 entries;
    # at or below that the history already fits, so return it unchanged.
    if len(messages) <= max_messages + 1:
        return messages
    return messages[:1] + messages[-max_messages:]


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for conversation-state backends.

    Full-state semantics: callers read the whole ``SessionState``, mutate it,
    and write it back. This mirrors a single DynamoDB item replaced by
    ``PutItem``, so every backend behaves identically.
    """

    async def get(self, session_id: str) -> SessionState | None:
        """Return the stored state for *session_id*, or None if absent/expired."""
        ...

    async def save(self, session_id: str, state: SessionState) -> None:
        """Persist *state* for *session_id*, replacing any existing state."""
        ...

    async def delete(self, session_id: str) -> None:
        """Remove any state for *session_id*. No-op if absent."""
        ...


class InMemorySessionStore:
    """Process-local dict-backed ``SessionStore`` with optional TTL eviction.

    Used for unit tests, evals, and local dev with zero AWS dependency. The
    optional ``ttl_seconds`` mirrors DynamoDB native TTL so expiry behaviour
    matches across backends; expired entries are dropped lazily on access.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float | None = None,
        _now: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an empty store.

        Args:
            ttl_seconds: Seconds before a saved session expires. None disables expiry.
            _now: Monotonic clock, injectable so TTL is testable without sleeping.
        """
        self._ttl_seconds = ttl_seconds
        self._now = _now
        self._lock = threading.Lock()
        # session_id -> (state, expires_at). expires_at is None when TTL is off.
        self._store: dict[str, tuple[SessionState, float | None]] = {}

    async def get(self, session_id: str) -> SessionState | None:
        """Return a deep copy of the stored state, or None if absent/expired."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return None
            state, expires_at = entry
            if expires_at is not None and self._now() >= expires_at:
                del self._store[session_id]
                return None
            return state.model_copy(deep=True)

    async def save(self, session_id: str, state: SessionState) -> None:
        """Store a deep copy of *state*, replacing any existing entry."""
        with self._lock:
            expires_at = None if self._ttl_seconds is None else self._now() + self._ttl_seconds
            self._store[session_id] = (state.model_copy(deep=True), expires_at)

    async def delete(self, session_id: str) -> None:
        """Remove any state for *session_id*. No-op if absent."""
        with self._lock:
            self._store.pop(session_id, None)


class DynamoDBSessionStore:
    """DynamoDB-backed ``SessionStore`` for production session persistence.

    Each session is one item ``{session_id, state, ttl}``: ``state`` is the
    ``SessionState`` serialized to JSON, ``ttl`` is a Unix-epoch expiry for
    DynamoDB native TTL. Because native TTL deletion can lag by up to ~48h,
    ``get`` also treats an item whose ``ttl`` has passed as absent, so expiry
    behaviour matches ``InMemorySessionStore``.

    boto3 is synchronous, so each call runs in a worker thread
    (``asyncio.to_thread``) to avoid blocking the event loop. The low-level
    boto3 client is thread-safe, so a single client is shared across calls.
    """

    def __init__(
        self,
        *,
        table_name: str,
        ttl_seconds: float | None = None,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        client: Any = None,
        _now: Callable[[], float] = time.time,
    ) -> None:
        """Create a store bound to a DynamoDB table.

        Args:
            table_name: The session table name.
            ttl_seconds: Seconds before a saved session expires. None disables the
                ``ttl`` attribute (no native expiry).
            region_name: AWS region; when None, boto3 resolves it from the env.
            endpoint_url: Override endpoint (e.g. DynamoDB Local); None in cloud.
            client: Preconstructed boto3 DynamoDB client, for tests. When None a
                client is constructed here (boto3 is imported lazily so the
                memory backend needs no AWS SDK).
            _now: Wall-clock source (Unix seconds), injectable for testing.
        """
        self._table_name = table_name
        self._ttl_seconds = ttl_seconds
        self._now = _now
        if client is not None:
            self._client = client
        else:
            import boto3  # local import: only needed for the DynamoDB backend

            kwargs: dict[str, Any] = {}
            if region_name:
                kwargs["region_name"] = region_name
            if endpoint_url:
                kwargs["endpoint_url"] = endpoint_url
            self._client = boto3.client("dynamodb", **kwargs)

    async def get(self, session_id: str) -> SessionState | None:
        """Return the stored state, or None if absent or past its TTL.

        ConsistentRead so a turn sees the prior turn's write even across instances.
        """
        resp = await asyncio.to_thread(
            self._client.get_item,
            TableName=self._table_name,
            Key={"session_id": {"S": session_id}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if item is None:
            return None
        ttl = item.get("ttl", {}).get("N")
        if ttl is not None and float(ttl) <= self._now():
            # Expired but not yet reaped by native TTL — treat as absent.
            return None
        return SessionState.model_validate_json(item["state"]["S"])

    async def save(self, session_id: str, state: SessionState) -> None:
        """Persist *state*, replacing any existing item (single-item PutItem)."""
        item: dict[str, Any] = {
            "session_id": {"S": session_id},
            "state": {"S": state.model_dump_json()},
        }
        if self._ttl_seconds is not None:
            item["ttl"] = {"N": str(int(self._now() + self._ttl_seconds))}
        await asyncio.to_thread(self._client.put_item, TableName=self._table_name, Item=item)

    async def delete(self, session_id: str) -> None:
        """Remove any state for *session_id*. No-op if absent."""
        await asyncio.to_thread(
            self._client.delete_item,
            TableName=self._table_name,
            Key={"session_id": {"S": session_id}},
        )


_DEFAULT_TTL_SECONDS = 86400.0

_session_store: SessionStore | None = None
_lock = threading.Lock()


def _resolve_ttl_seconds() -> float:
    """Resolve the in-memory store TTL from ``SESSION_TTL_SECONDS``.

    An unset or empty value falls back to the default. A non-empty value that
    is not a positive, finite number is a misconfiguration and fails loudly
    (``"nan"``/``"inf"`` would silently disable expiry, a negative value would
    expire every session immediately).

    Returns:
        The TTL in seconds.

    Raises:
        ValueError: If ``SESSION_TTL_SECONDS`` is set but is not a positive,
            finite number.
    """
    raw = os.getenv("SESSION_TTL_SECONDS", "")
    if not raw.strip():
        return _DEFAULT_TTL_SECONDS
    try:
        ttl = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid SESSION_TTL_SECONDS: {raw!r} (must be a positive number of seconds)"
        ) from exc
    if not math.isfinite(ttl) or ttl <= 0:
        raise ValueError(
            f"Invalid SESSION_TTL_SECONDS: {raw!r} (must be a positive number of seconds)"
        )
    return ttl


def get_session_store() -> SessionStore:
    """Return the process-wide session store, constructing it on first use.

    The backend is selected by ``SESSION_STORE_BACKEND`` (``"memory"`` default, or
    ``"dynamodb"``). Both honour ``SESSION_TTL_SECONDS``. The DynamoDB backend
    additionally requires ``SESSION_TABLE_NAME`` and reads ``AWS_REGION`` and the
    optional ``SESSION_DDB_ENDPOINT_URL`` (DynamoDB Local) from the env.

    Returns:
        The singleton ``SessionStore`` for this process.

    Raises:
        ValueError: On an unknown backend, or ``dynamodb`` without a table name.
    """
    global _session_store  # noqa: PLW0603
    with _lock:
        if _session_store is None:
            backend = os.getenv("SESSION_STORE_BACKEND", "memory")
            if backend == "memory":
                _session_store = InMemorySessionStore(ttl_seconds=_resolve_ttl_seconds())
            elif backend == "dynamodb":
                table_name = os.getenv("SESSION_TABLE_NAME", "").strip()
                if not table_name:
                    raise ValueError("SESSION_STORE_BACKEND=dynamodb requires SESSION_TABLE_NAME")
                _session_store = DynamoDBSessionStore(
                    table_name=table_name,
                    ttl_seconds=_resolve_ttl_seconds(),
                    region_name=os.getenv("AWS_REGION") or None,
                    endpoint_url=os.getenv("SESSION_DDB_ENDPOINT_URL") or None,
                )
            else:
                raise ValueError(f"Unknown SESSION_STORE_BACKEND: {backend!r}")
    return _session_store
