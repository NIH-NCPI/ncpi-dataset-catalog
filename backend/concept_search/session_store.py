"""Swappable conversation/session stores.

Provides a ``SessionStore`` protocol and an ``InMemorySessionStore``
implementation. A future DynamoDB-backed store (AWS-native, native TTL)
implements the same protocol — see issue #360.

The persisted ``SessionState`` is deliberately **lean**: the user/assistant
text turns plus the current resolved ``QueryModel``. The per-turn tool
scratchpad (concept-search candidates, study lookups) is never handed to the
store — the agent loop discards it when a turn ends. There is no trimming
step; the lean shape is the schema.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from .models import ConversationMessage, QueryModel


class SessionState(BaseModel):
    """Lean persisted conversation state — text turns plus the resolved query.

    Excludes the per-turn tool scratchpad by construction: the agent loop hands
    the store only the user/assistant text and the resulting ``QueryModel``.
    Pending disambiguation already lives inside ``QueryModel`` (via each
    mention's ``disambiguation`` list), so no separate field is needed.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    messages: list[ConversationMessage] = Field(default_factory=list)
    query: QueryModel | None = None


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


_DEFAULT_TTL_SECONDS = 86400.0

_session_store: SessionStore | None = None
_lock = threading.Lock()


def _resolve_ttl_seconds() -> float:
    """Resolve the in-memory store TTL from ``SESSION_TTL_SECONDS``.

    An unset or empty value falls back to the default. A non-empty value that
    is not a number is a misconfiguration and fails loudly.

    Returns:
        The TTL in seconds.

    Raises:
        ValueError: If ``SESSION_TTL_SECONDS`` is set to a non-numeric value.
    """
    raw = os.getenv("SESSION_TTL_SECONDS", "")
    if not raw.strip():
        return _DEFAULT_TTL_SECONDS
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid SESSION_TTL_SECONDS: {raw!r} (must be a number of seconds)"
        ) from exc


def get_session_store() -> SessionStore:
    """Return the process-wide session store, constructing it on first use.

    The backend is selected by ``SESSION_STORE_BACKEND`` (default ``"memory"``).
    The DynamoDB backend is added in a follow-up ticket.

    Returns:
        The singleton ``SessionStore`` for this process.
    """
    global _session_store  # noqa: PLW0603
    with _lock:
        if _session_store is None:
            backend = os.getenv("SESSION_STORE_BACKEND", "memory")
            if backend == "memory":
                _session_store = InMemorySessionStore(ttl_seconds=_resolve_ttl_seconds())
            else:
                raise ValueError(f"Unknown SESSION_STORE_BACKEND: {backend!r}")
    return _session_store
