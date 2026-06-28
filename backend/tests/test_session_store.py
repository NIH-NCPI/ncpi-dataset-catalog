"""Unit tests for the conversation/session store abstraction."""

from __future__ import annotations

import os

import pytest

from concept_search import session_store as session_store_module
from concept_search.models import (
    ConversationMessage,
    DisambiguationOption,
    PendingChoice,
    QueryModel,
    ResolvedMention,
)
from concept_search.session_store import (
    InMemorySessionStore,
    SessionState,
    SessionStore,
    get_session_store,
    truncate_history,
)


class _Clock:
    """A manually advanced monotonic clock for TTL tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _make_state(text: str = "glucose studies") -> SessionState:
    """Build a SessionState with one user turn and a minimal query."""
    return SessionState(
        messages=[ConversationMessage(role="user", content=text)],
        query=QueryModel(
            intent="study",
            mentions=[
                ResolvedMention(
                    facet="measurement",
                    original_text="glucose",
                    values=["phenx:blood_glucose"],
                )
            ],
        ),
    )


@pytest.mark.asyncio()
async def test_save_get_round_trip() -> None:
    """Saving then getting returns equal state."""
    store = InMemorySessionStore()
    state = _make_state()
    await store.save("sess1", state)
    got = await store.get("sess1")
    assert got == state


@pytest.mark.asyncio()
async def test_agent_message_history_round_trips() -> None:
    """The agent_message_history payload survives save/get unchanged."""
    store = InMemorySessionStore()
    state = _make_state()
    state.agent_message_history = [{"role": "user", "parts": [{"content": "hi"}]}]
    await store.save("sess1", state)
    got = await store.get("sess1")
    assert got is not None
    assert got.agent_message_history == state.agent_message_history


@pytest.mark.asyncio()
async def test_pending_round_trips() -> None:
    """The pending disambiguation choices survive save/get unchanged."""
    store = InMemorySessionStore()
    state = _make_state()
    state.pending = [
        PendingChoice(
            facet="measurement",
            options=[DisambiguationOption(concept_id="x", label="Blood glucose")],
            text="glucose",
        )
    ]
    await store.save("sess1", state)
    got = await store.get("sess1")
    assert got is not None
    assert got.pending == state.pending


def test_truncate_history_keeps_first_and_recent() -> None:
    """truncate_history keeps the first message plus the most recent N."""
    messages = list(range(10))
    assert truncate_history(messages, 3) == [0, 7, 8, 9]


def test_truncate_history_noop_within_bounds() -> None:
    """truncate_history returns the list unchanged when within bounds."""
    messages = [1, 2, 3]
    assert truncate_history(messages, 5) == [1, 2, 3]


def test_truncate_history_noop_at_boundary() -> None:
    """At first + max_messages total (len == max + 1), the original list is returned."""
    messages = [0, 1, 2, 3, 4, 5]  # len 6 == max(5) + 1, already fits
    assert truncate_history(messages, 5) is messages  # unchanged, not a copy


@pytest.mark.asyncio()
async def test_get_unknown_returns_none() -> None:
    """Getting an unknown session id returns None."""
    store = InMemorySessionStore()
    assert await store.get("nope") is None


@pytest.mark.asyncio()
async def test_sessions_are_isolated() -> None:
    """Distinct session ids hold independent state."""
    store = InMemorySessionStore()
    a = _make_state("glucose studies")
    b = _make_state("asthma studies")
    await store.save("a", a)
    await store.save("b", b)
    assert await store.get("a") == a
    assert await store.get("b") == b


@pytest.mark.asyncio()
async def test_save_replaces_existing() -> None:
    """A second save for the same id replaces the first."""
    store = InMemorySessionStore()
    await store.save("sess1", _make_state("first"))
    await store.save("sess1", _make_state("second"))
    got = await store.get("sess1")
    assert got is not None
    assert got.messages[0].content == "second"


@pytest.mark.asyncio()
async def test_delete_removes_session() -> None:
    """Delete removes the session; a subsequent get returns None."""
    store = InMemorySessionStore()
    await store.save("sess1", _make_state())
    await store.delete("sess1")
    assert await store.get("sess1") is None


@pytest.mark.asyncio()
async def test_delete_unknown_is_noop() -> None:
    """Deleting an unknown session id does not raise."""
    store = InMemorySessionStore()
    await store.delete("nope")


@pytest.mark.asyncio()
async def test_returned_state_is_isolated_copy() -> None:
    """Mutating a returned state does not corrupt stored data."""
    store = InMemorySessionStore()
    await store.save("sess1", _make_state())
    got = await store.get("sess1")
    assert got is not None
    got.messages.append(ConversationMessage(role="assistant", content="injected"))

    again = await store.get("sess1")
    assert again is not None
    assert len(again.messages) == 1


@pytest.mark.asyncio()
async def test_saved_state_is_snapshot() -> None:
    """Mutating the passed-in state after save does not corrupt stored data."""
    store = InMemorySessionStore()
    state = _make_state()
    await store.save("sess1", state)
    state.messages.append(ConversationMessage(role="assistant", content="injected"))

    got = await store.get("sess1")
    assert got is not None
    assert len(got.messages) == 1


@pytest.mark.asyncio()
async def test_ttl_expires_session() -> None:
    """A session is returned before its TTL and dropped after."""
    clock = _Clock()
    store = InMemorySessionStore(ttl_seconds=100.0, _now=clock)
    await store.save("sess1", _make_state())

    clock.advance(99.0)
    assert await store.get("sess1") is not None

    clock.advance(2.0)  # now past the 100s TTL
    assert await store.get("sess1") is None
    # Entry is dropped, not just hidden.
    assert "sess1" not in store._store


@pytest.mark.asyncio()
async def test_no_ttl_never_expires() -> None:
    """With TTL disabled, state persists regardless of clock movement."""
    clock = _Clock()
    store = InMemorySessionStore(ttl_seconds=None, _now=clock)
    await store.save("sess1", _make_state())
    clock.advance(1_000_000.0)
    assert await store.get("sess1") is not None


@pytest.fixture()
def _reset_factory_singleton():
    """Reset the module-level singleton and backend env around a test."""
    saved_env = {
        key: os.environ.get(key) for key in ("SESSION_STORE_BACKEND", "SESSION_TTL_SECONDS")
    }
    session_store_module._session_store = None
    yield
    session_store_module._session_store = None
    for key, value in saved_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_factory_defaults_to_in_memory_singleton(_reset_factory_singleton) -> None:
    """Default backend is in-memory and the factory returns a singleton."""
    os.environ.pop("SESSION_STORE_BACKEND", None)
    os.environ.pop("SESSION_TTL_SECONDS", None)
    store = get_session_store()
    assert isinstance(store, InMemorySessionStore)
    assert isinstance(store, SessionStore)
    assert get_session_store() is store


def test_factory_unknown_backend_raises(_reset_factory_singleton) -> None:
    """An unknown backend selector raises ValueError."""
    os.environ["SESSION_STORE_BACKEND"] = "redis"
    with pytest.raises(ValueError, match="Unknown SESSION_STORE_BACKEND"):
        get_session_store()


def test_factory_empty_ttl_uses_default(_reset_factory_singleton) -> None:
    """An empty SESSION_TTL_SECONDS falls back to the default TTL."""
    os.environ.pop("SESSION_STORE_BACKEND", None)
    os.environ["SESSION_TTL_SECONDS"] = ""
    store = get_session_store()
    assert isinstance(store, InMemorySessionStore)
    assert store._ttl_seconds == 86400.0


@pytest.mark.parametrize("bad_value", ["30s", "nan", "inf", "-5", "0"])
def test_factory_invalid_ttl_raises(_reset_factory_singleton, bad_value: str) -> None:
    """A non-numeric, non-finite, or non-positive SESSION_TTL_SECONDS fails loudly."""
    os.environ.pop("SESSION_STORE_BACKEND", None)
    os.environ["SESSION_TTL_SECONDS"] = bad_value
    with pytest.raises(ValueError, match="Invalid SESSION_TTL_SECONDS"):
        get_session_store()
