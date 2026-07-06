"""Unit tests for the DynamoDB-backed session store.

Round-trip / CRUD behaviour is exercised against a moto-mocked DynamoDB; the
read-side TTL guard is exercised with a stub client so the assertions don't
depend on moto's own TTL-reaping timing.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
import pytest
from moto import mock_aws

from concept_search import session_store as session_store_module
from concept_search.models import ConversationMessage, QueryModel, ResolvedMention
from concept_search.session_store import (
    DynamoDBSessionStore,
    SessionState,
    get_session_store,
)

TABLE = "ncpi-sessions-test"
REGION = "us-east-1"


def _make_state(text: str = "glucose studies") -> SessionState:
    """Build a representative SessionState (turn + query + agent history)."""
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
        agent_message_history=[{"role": "user", "parts": [{"content": "hi"}]}],
    )


def _create_table(client: Any) -> None:
    """Create the session table with the schema the adapter expects + TTL."""
    client.create_table(
        TableName=TABLE,
        KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.update_time_to_live(
        TableName=TABLE,
        TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
    )


@pytest.fixture()
def _aws_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide dummy AWS creds/region so boto3 is happy under moto."""
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(key, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture()
def ddb_client(_aws_creds: None):
    """Yield a moto-mocked DynamoDB client with the session table created.

    The moto context stays active across the yield, so stores constructed in the
    test (and their threaded boto3 calls) are intercepted.
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        _create_table(client)
        yield client


def _store(**kwargs: Any) -> DynamoDBSessionStore:
    """Construct a store bound to the test table (region set for moto)."""
    kwargs.setdefault("table_name", TABLE)
    kwargs.setdefault("region_name", REGION)
    return DynamoDBSessionStore(**kwargs)


# --- CRUD against moto ------------------------------------------------------


@pytest.mark.asyncio()
async def test_save_get_round_trip(ddb_client: Any) -> None:
    """Saving then getting returns equal state."""
    store = _store()
    state = _make_state()
    await store.save("sess1", state)
    assert await store.get("sess1") == state


@pytest.mark.asyncio()
async def test_agent_history_and_pending_round_trip(ddb_client: Any) -> None:
    """The agent_message_history payload survives the JSON round-trip."""
    store = _store()
    state = _make_state()
    await store.save("sess1", state)
    got = await store.get("sess1")
    assert got is not None
    assert got.agent_message_history == state.agent_message_history


@pytest.mark.asyncio()
async def test_get_unknown_returns_none(ddb_client: Any) -> None:
    """Getting an unknown session id returns None."""
    assert await _store().get("nope") is None


@pytest.mark.asyncio()
async def test_save_replaces_existing(ddb_client: Any) -> None:
    """A second save for the same id replaces the first (single-item PutItem)."""
    store = _store()
    await store.save("sess1", _make_state("first"))
    await store.save("sess1", _make_state("second"))
    got = await store.get("sess1")
    assert got is not None
    assert got.messages[0].content == "second"


@pytest.mark.asyncio()
async def test_delete_removes_session(ddb_client: Any) -> None:
    """Delete removes the session; a subsequent get returns None."""
    store = _store()
    await store.save("sess1", _make_state())
    await store.delete("sess1")
    assert await store.get("sess1") is None


@pytest.mark.asyncio()
async def test_delete_unknown_is_noop(ddb_client: Any) -> None:
    """Deleting an unknown session id does not raise."""
    await _store().delete("nope")


@pytest.mark.asyncio()
async def test_ttl_attribute_written(ddb_client: Any) -> None:
    """save writes a numeric ttl ≈ now + ttl_seconds for native expiry."""
    store = _store(ttl_seconds=100.0, _now=lambda: 1000.0)
    await store.save("sess1", _make_state())
    item = ddb_client.get_item(TableName=TABLE, Key={"session_id": {"S": "sess1"}})["Item"]
    assert item["ttl"]["N"] == "1100"


@pytest.mark.asyncio()
async def test_no_ttl_omits_attribute(ddb_client: Any) -> None:
    """With ttl_seconds=None, no ttl attribute is written and state persists."""
    store = _store(ttl_seconds=None)
    await store.save("sess1", _make_state())
    item = ddb_client.get_item(TableName=TABLE, Key={"session_id": {"S": "sess1"}})["Item"]
    assert "ttl" not in item
    assert await store.get("sess1") is not None


# --- read-side TTL guard (stub client, no moto) -----------------------------


class _StubClient:
    """Minimal DynamoDB client stub returning a canned item."""

    def __init__(self, item: dict | None) -> None:
        self._item = item
        self.deleted: list[dict] = []

    def get_item(self, **_: Any) -> dict:
        return {"Item": self._item} if self._item is not None else {}

    def delete_item(self, **kwargs: Any) -> None:
        self.deleted.append(kwargs)


def _item_with_ttl(ttl: str) -> dict:
    return {
        "session_id": {"S": "sess1"},
        "state": {"S": _make_state().model_dump_json()},
        "ttl": {"N": ttl},
    }


@pytest.mark.asyncio()
async def test_get_past_ttl_treated_as_absent() -> None:
    """An item whose ttl has passed is treated as absent (native reap can lag)."""
    stub = _StubClient(_item_with_ttl("500"))  # ttl 500 < now 1000
    store = DynamoDBSessionStore(table_name=TABLE, client=stub, _now=lambda: 1000.0)
    assert await store.get("sess1") is None


@pytest.mark.asyncio()
async def test_get_future_ttl_returns_state() -> None:
    """An item whose ttl is still in the future is returned normally."""
    stub = _StubClient(_item_with_ttl("5000"))  # ttl 5000 > now 1000
    store = DynamoDBSessionStore(table_name=TABLE, client=stub, _now=lambda: 1000.0)
    assert await store.get("sess1") == _make_state()


# --- factory wiring ---------------------------------------------------------


@pytest.fixture()
def _reset_factory_singleton(monkeypatch: pytest.MonkeyPatch):
    """Reset the module-level singleton around a factory test."""
    session_store_module._session_store = None
    for key in ("SESSION_STORE_BACKEND", "SESSION_TABLE_NAME", "SESSION_TTL_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    yield
    session_store_module._session_store = None


def test_factory_dynamodb_requires_table_name(_reset_factory_singleton) -> None:
    """dynamodb backend without SESSION_TABLE_NAME fails loudly."""
    os.environ["SESSION_STORE_BACKEND"] = "dynamodb"
    with pytest.raises(ValueError, match="requires SESSION_TABLE_NAME"):
        get_session_store()


def test_factory_builds_dynamodb_store(
    _reset_factory_singleton, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dynamodb backend + table name constructs a DynamoDBSessionStore singleton."""
    monkeypatch.setenv("SESSION_STORE_BACKEND", "dynamodb")
    monkeypatch.setenv("SESSION_TABLE_NAME", TABLE)
    monkeypatch.setenv("AWS_REGION", REGION)
    store = get_session_store()
    assert isinstance(store, DynamoDBSessionStore)
    assert get_session_store() is store
