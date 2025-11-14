import os
import psycopg
from openai import OpenAI
from pgvector.psycopg import register_vector
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

#
# This script queries the database using semantic search and generates answers using OpenAI.
#

# Initialize OpenAI client with API key from environment variable.
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
client = OpenAI()

# Connect to PostgreSQL database using environment variables.
conn = psycopg.connect(os.environ["PG_DSN"])
conn.autocommit = True

# Register vector type for database connection.
register_vector(conn)


def answer_with_context(query: str, k=5):
    """
    Answer a query using semantic search over the datasets table.

    Parameters
    ----------
    query : str
        The user's question.
    k : int, optional
        Number of nearest neighbors to retrieve. Defaults to 5.

    Returns
    -------
    str
        The AI-generated answer based on the retrieved context.
    """
    # 1) get query embedding
    query_vector = (
        client.embeddings.create(model="text-embedding-3-small", input=query)
        .data[0]
        .embedding
    )

    # 2) fetch neighbors
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT name, description, embedding <=> %s::vector AS distance
            FROM datasets
            ORDER BY distance ASC
            LIMIT %s
        """,
            (query_vector, k),
        )
        rows = cur.fetchall()

    print(f"Found {len(rows)} results\n")

    context = "\n\n---\n".join(
        f"Name: {r[0]}\nDesc: {r[1]}\nScore: {r[2]:.3f}" for r in rows
    )

    print(f"Context: {context}\n")

    # 3) ask the model to answer using ONLY this context (good guardrail)
    prompt = f"""
You are a helpful analyst. Use ONLY the context to answer.
If the answer isn't in the context, say you don't know.
Always give me the name of the dataset you are answering about.

User question: {query}

Context:
{context}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    # Example query
    query = "Which datasets mention austism?"
    # query = "Which datasets are about genomic research?"
    print(f"Query: {query}\n")
    answer = answer_with_context(query)
    print(f"Answer:\n{answer}")
