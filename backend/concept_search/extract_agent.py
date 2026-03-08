"""Extract agent — parses NL queries into raw mentions (no tools)."""

from __future__ import annotations

import threading
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from .models import ExtractResult, QueryModel

_PROMPT_PATH = Path(__file__).parent / "EXTRACT_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[None, ExtractResult] | None = None
_agent_model: str | None = None
_lock = threading.Lock()


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[None, ExtractResult]:
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    with _lock:
        if _agent is None or model != _agent_model:
            _agent_model = model
            _agent = Agent(
                model,
                output_type=ExtractResult,
                system_prompt=_load_prompt(),
                model_settings=ModelSettings(
                    anthropic_cache_instructions=True,
                    temperature=0.0,
                ),
            )
        return _agent


def _format_previous_context(previous: QueryModel) -> str:
    """Format the previous query state as context for the extract agent.

    Args:
        previous: The previous QueryModel with active filters.

    Returns:
        A compact text summary of active filters.
    """
    lines: list[str] = []
    for m in previous.mentions:
        prefix = "exclude" if m.exclude else "include"
        values_str = ", ".join(m.values) if m.values else "(unresolved)"
        lines.append(
            f"- {m.facet.value}: \"{m.original_text}\" → [{values_str}] ({prefix})"
        )
    return "\n".join(lines)


async def run_extract(
    query: str,
    model: str | None = None,
    previous_query: QueryModel | None = None,
) -> ExtractResult:
    """Parse a natural-language query into raw mentions.

    Args:
        query: The user's natural-language search query.
        model: Override the model (default: Haiku).
        previous_query: Previous query state for multi-turn refinement.
            When present, the agent extracts only NEW mentions.

    Returns:
        ExtractResult with a list of RawMention items.
    """
    agent = _get_agent(model)

    if previous_query and (previous_query.mentions or previous_query.intent):
        context = _format_previous_context(previous_query)
        prompt = (
            f"Active intent: {previous_query.intent}\n"
            f"Active filters:\n{context}\n\n"
            f"New user input: {query}"
        )
    else:
        prompt = query

    result = await agent.run(prompt)
    return result.output
