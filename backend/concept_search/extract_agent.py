"""Extract agent — parses NL queries into raw mentions (no tools)."""

from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent

from .models import ExtractResult

_PROMPT_PATH = Path(__file__).parent / "EXTRACT_PROMPT.md"
_DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"

_agent: Agent[None, ExtractResult] | None = None
_agent_model: str | None = None


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def _get_agent(model: str | None = None) -> Agent[None, ExtractResult]:
    global _agent, _agent_model  # noqa: PLW0603
    model = model or _DEFAULT_MODEL
    if _agent is None or model != _agent_model:
        _agent_model = model
        _agent = Agent(
            model,
            output_type=ExtractResult,
            system_prompt=_load_prompt(),
        )
    return _agent


async def run_extract(query: str, model: str | None = None) -> ExtractResult:
    """Parse a natural-language query into raw mentions.

    Args:
        query: The user's natural-language search query.
        model: Override the model (default: Haiku).

    Returns:
        ExtractResult with a list of RawMention items.
    """
    agent = _get_agent(model)
    result = await agent.run(query)
    return result.output
