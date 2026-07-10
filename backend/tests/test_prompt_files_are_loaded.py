"""Every prompt file in concept_search/ must be loaded by some module.

#412 deleted the extract, router and structure agents but left their prompts
behind. Those files are not inert: they state rules about a query model that
still exists, so a reader — or a future agent — can mistake them for live
instructions and edit the wrong prompt. EXTRACT_PROMPT.md still explained the
intra-facet OR rule that #363 spent a day relitigating, in a file nothing had
read for three PRs.

This test fails when a prompt is orphaned (delete it) or when a new prompt is
added without being wired up (load it).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parent.parent / "concept_search"


def _prompt_files() -> list[Path]:
    """Every markdown file shipped inside the concept_search package."""
    return sorted(_PACKAGE.glob("*.md"))


def _python_sources() -> str:
    """The concatenated text of every module in the package."""
    return "\n".join(p.read_text() for p in _PACKAGE.glob("*.py"))


def test_there_are_prompt_files_to_check() -> None:
    """Guard the guard: a bad glob would make every assertion below vacuous."""
    assert _prompt_files(), f"no *.md found in {_PACKAGE}"


@pytest.mark.parametrize("prompt", _prompt_files(), ids=lambda p: p.name)
def test_prompt_file_is_referenced_by_a_module(prompt: Path) -> None:
    """A prompt nobody loads is a lie waiting to be believed."""
    assert prompt.name in _python_sources(), (
        f"{prompt.name} is not referenced by any module in concept_search/. "
        f"Either it is orphaned (delete it — see #421) or it was added without "
        f"being loaded. A prompt that ships but is never read still reads like "
        f"live instructions to whoever opens it next."
    )
