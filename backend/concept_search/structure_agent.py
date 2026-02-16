"""Structure agent — determines boolean logic between resolved mentions."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic_ai import Agent

from .models import QueryModel, ResolvedMention

_PROMPT_PATH = Path(__file__).parent / "STRUCTURE_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[None, QueryModel] | None = None
_agent_model: str | None = None


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[None, QueryModel]:
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    if _agent is None or model != _agent_model:
        _agent_model = model
        _agent = Agent(
            model,
            output_type=QueryModel,
            system_prompt=_load_prompt(),
        )
    return _agent


def _format_mentions(mentions: list[ResolvedMention]) -> str:
    """Format resolved mentions as a readable list for the agent."""
    items = []
    for m in mentions:
        items.append({
            "facet": m.facet.value,
            "original_text": m.original_text,
            "values": m.values,
        })
    return json.dumps(items, indent=2)


async def run_structure(
    query: str,
    mentions: list[ResolvedMention],
    model: str | None = None,
) -> QueryModel:
    """Determine boolean logic for resolved mentions.

    Args:
        query: The original user query (for context).
        mentions: Resolved mentions (without exclude flags set yet).
        model: Override the model (default: Haiku).

    Returns:
        QueryModel with exclude flags applied.
    """
    agent = _get_agent(model)
    prompt = (
        f"Original query: {query}\n\n"
        f"Resolved mentions:\n{_format_mentions(mentions)}"
    )
    result = await agent.run(prompt)
    return result.output
