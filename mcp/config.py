from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector
import logging
from openai import OpenAI

# Load .env from scripts directory
env_path = Path(__file__).parent / "scripts" / ".env"
load_dotenv(dotenv_path=env_path)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DATABASE_URL = os.environ["PG_DSN"]

# Singleton-ish DB connection for simplicity (fine for demos)
_conn = None


def get_db_conn():
    global _conn
    if _conn is None:
        _conn = psycopg.connect(DATABASE_URL, autocommit=True)
        register_vector(_conn)
    return _conn


# Set the logging level for the OpenAI library
# logging.getLogger("openai").setLevel(logging.DEBUG)

# Optionally, configure the logging format and handlers
logging.basicConfig(level=logging.DEBUG)

# OpenAI client
_client = None


def get_openai_client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client
