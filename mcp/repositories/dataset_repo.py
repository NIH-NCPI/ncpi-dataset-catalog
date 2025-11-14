from __future__ import annotations
from typing import List, Tuple

# This repo ONLY talks to the DB. It receives a query vector and returns rows.


def ann_search(
    conn, query_vector: list[float], k: int = 5
) -> List[Tuple[str, str, str, float]]:
    """
    Returns [(id, name, description, similarity)] ordered by cosine distance.
    """
    sql = """
        SELECT name, description, embedding <=> %s::vector AS distance
        FROM datasets
        ORDER BY distance ASC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (query_vector, k))
        return cur.fetchall()
