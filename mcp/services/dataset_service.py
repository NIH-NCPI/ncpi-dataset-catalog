from __future__ import annotations
from typing import List
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

from config import get_db_conn, get_openai_client, OPENAI_MODEL, EMBEDDING_MODEL
from models.schemas import DatasetHit
from repositories.dataset_repo import ann_search


# Dependencies handed to the agent/tools
class Deps(BaseModel):
    embed_model: str

    class Config:
        arbitrary_types_allowed = True  # lets us stash non-pydantic objects if needed


# We’ll keep global singletons for this tiny demo service layer
_conn = get_db_conn()
_client = get_openai_client()
_deps = Deps(embed_model=EMBEDDING_MODEL)

# Build the agent
agent = Agent(
    model=OpenAIChatModel(OPENAI_MODEL, settings={"temperature": 0}),
    deps_type=Deps,
    instructions=(
        "You are a data catalog assistant.\n"
        "- Always call the `search_datasets` tool FIRST with the user's question.\n"
        "- Answer ONLY using the tool results. If nothing relevant is returned, say you don't know.\n"
        "- Mention dataset names when you cite information."
    ),
)


@agent.tool
def search_datasets(ctx: RunContext[Deps], query: str, k: int = 5) -> List[DatasetHit]:
    """
    Tool: embed the query, run pgvector ANN, return structured hits.
    """
    print(f"Searching for datasets using search_datasets tool")

    query_vector = (
        _client.embeddings.create(model=ctx.deps.embed_model, input=query)
        .data[0]
        .embedding
    )
    rows = ann_search(_conn, query_vector, k=k)

    for r in rows:
        print(f"Found dataset: Name: {r[0]}, Desc: {r[1]}")

    return [
        DatasetHit(name=r[0], description=r[1] or "", distance=float(r[2]))
        for r in rows
    ]


def ask(question: str) -> str:
    """Service entrypoint used by controllers or CLI."""
    print(f"Running ask with question: {question}")
    result = agent.run_sync(question, deps=_deps)
    return result.output
