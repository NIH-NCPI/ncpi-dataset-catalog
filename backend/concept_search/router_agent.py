"""Router agent — classifies follow-up messages in multi-turn search."""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from .models import (
    QueryModel,
    RouteAdd,
    RouteRemove,
    RouteReplace,
    RouteReset,
    RouteSelect,
    RouterResult,
)

_PROMPT_PATH = Path(__file__).parent / "ROUTER_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[None, RouterResult] | None = None
_agent_model: str | None = None
_lock = threading.Lock()


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[None, RouterResult]:
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    with _lock:
        if _agent is None or model != _agent_model:
            _agent_model = model
            _agent = Agent(
                model,
                output_type=[RouteSelect, RouteAdd, RouteRemove, RouteReplace, RouteReset],  # type: ignore[arg-type]
                system_prompt=_load_prompt(),
                model_settings=ModelSettings(
                    anthropic_cache_instructions=True,
                    temperature=0.0,
                ),
            )
    return _agent


def _format_filters(previous_query: QueryModel) -> str:
    """Format active filters for the router prompt."""
    lines: list[str] = []
    for m in previous_query.mentions:
        if m.disambiguation:
            values_str = "[] (DISAMBIGUATION PENDING)"
            lines.append(f'- {m.facet.value}: "{m.original_text}" → {values_str}')
            for i, opt in enumerate(m.disambiguation, 1):
                lines.append(f"    {i}. {opt.concept_id} — {opt.label}")
        else:
            prefix = "exclude" if m.exclude else "include"
            values_str = ", ".join(m.values) if m.values else "(unresolved)"
            lines.append(
                f'- {m.facet.value}: "{m.original_text}" → [{values_str}] ({prefix})'
            )
    return "\n".join(lines)


async def run_router(
    query: str,
    previous_query: QueryModel,
    model: str | None = None,
) -> RouterResult:
    """Classify a follow-up message into a route action.

    Args:
        query: The user's follow-up message.
        previous_query: Previous query state with active filters.
        model: Override the model (default: Haiku).

    Returns:
        One of RouteSelect, RouteAdd, RouteRemove, RouteReplace, RouteReset.
    """
    agent = _get_agent(model)
    filters = _format_filters(previous_query)
    prompt = f"Active filters:\n{filters}\n\nUser's message: \"{query}\""
    result = await agent.run(prompt)
    return result.output
