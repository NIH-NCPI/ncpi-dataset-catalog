"""Spike: conversation-aware router using Sonnet with full message history.

Drop-in alternative to router_agent.py for A/B comparison.  Uses the same
output types (RouterResult) but takes an optional conversation history and
passes it to the model as user/assistant message pairs.
"""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings

from .api_models import ConversationMessage
from .models import (
    QueryModel,
    RouteRefine,
    RouteRemove,
    RouteReplace,
    RouteReset,
    RouterResult,
    RouteSelect,
)

_PROMPT_PATH = Path(__file__).parent / "ROUTER_SPIKE_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-sonnet-4-20250514"

_agent: Agent[None, RouterResult] | None = None
_agent_model: str | None = None
_lock = threading.Lock()


def _load_prompt() -> str:
    """Load the spike router system prompt."""
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[None, RouterResult]:
    """Get or create the singleton agent, reinitializing if the model changes."""
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    with _lock:
        if _agent is None or model != _agent_model:
            _agent_model = model
            _agent = Agent(
                model,
                output_type=[RouteSelect, RouteRefine, RouteRemove, RouteReplace, RouteReset],  # type: ignore[arg-type]
                system_prompt=_load_prompt(),
                model_settings=ModelSettings(
                    temperature=0.0,
                ),
            )
    return _agent


def _format_filters(previous_query: QueryModel) -> str:
    """Format active filters for the router prompt."""
    lines: list[str] = []
    for m in previous_query.mentions:
        if m.disambiguation:
            prefix = "exclude" if m.exclude else "include"
            values_str = "[] (DISAMBIGUATION PENDING)"
            lines.append(f'- {m.facet.value}: "{m.original_text}" → {values_str} ({prefix})')
            for i, opt in enumerate(m.disambiguation, 1):
                lines.append(f"    {i}. {opt.concept_id} — {opt.label}")
        else:
            prefix = "exclude" if m.exclude else "include"
            values_str = ", ".join(m.values) if m.values else "(unresolved)"
            lines.append(f'- {m.facet.value}: "{m.original_text}" → [{values_str}] ({prefix})')
    return "\n".join(lines)


def _build_message_history(
    messages: list[ConversationMessage],
) -> list[ModelMessage]:
    """Convert conversation messages to pydantic-ai message history."""
    history: list[ModelMessage] = []
    for msg in messages:
        if msg.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
    return history


async def run_router(
    query: str,
    previous_query: QueryModel,
    messages: list[ConversationMessage] | None = None,
    model: str | None = None,
) -> RouterResult:
    """Classify a follow-up message into a route action.

    Args:
        query: The user's follow-up message.
        previous_query: Previous query state with active filters.
        messages: Optional conversation history for context.
        model: Override the model (default: Sonnet).

    Returns:
        One of RouteSelect, RouteRefine, RouteRemove, RouteReplace, RouteReset.
    """
    agent = _get_agent(model)
    filters = _format_filters(previous_query)
    prompt = f'Active filters:\n{filters}\n\nUser\'s message: "{query}"'

    message_history = _build_message_history(messages) if messages else None
    result = await agent.run(prompt, message_history=message_history)
    return result.output
