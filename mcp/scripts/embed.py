import os, uuid, psycopg
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from pgvector.psycopg import register_vector

# Load environment variables from .env file
load_dotenv()

#
# This script embeds text using the OpenAI embeddings API and upserts the embedded text into a PostgreSQL database.
#

# Initialize OpenAI client with API key from environment variable.
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
client = OpenAI()

# Connect to PostgreSQL database using environment variables.
conn = psycopg.connect(os.environ["PG_DSN"])
conn.autocommit = True

# Register vector type for database connection.
register_vector(conn)

"""
Embed a string of text using the OpenAI embeddings API.

Parameters
----------
text : str
    The text to be embedded.
model : str, optional
    The model to use for the embedding. Defaults to "text-embedding-3-small".

Returns
-------
embedding : list of float
    The embedded text as a list of floats.

Notes
-----
- The "small" model has 1536 dimensions and the "large" model has 3072 dimensions.
- The embeddings are returned as a list of floats.
"""


def embed(text: str, model="text-embedding-3-small"):
    # small = 1536 dims; large = 3072 dims. :contentReference[oaicite:2]{index=2}
    e = client.embeddings.create(model=model, input=text)
    return e.data[0].embedding


"""
Embed a string of text using the OpenAI embeddings API.

Parameters
----------
text : str
    The text to be embedded.
model : str, optional
    The model to use for the embedding. Defaults to "text-embedding-3-small".

Returns
-------
list
    A list containing the embedding of the input text.

Notes
------
The OpenAI embeddings API returns a list of embeddings, where each embedding is a list of floats.
The length of the embedding list is determined by the model used. The small model returns embeddings of length 1536, while the large model returns embeddings of length 3072.
"""


def upsert_entity(name: str, description: str):
    v = embed(description, model="text-embedding-3-small")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO datasets (id, name, description, embedding)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                description = EXCLUDED.description,
                embedding = EXCLUDED.embedding
        """,
            (uuid.uuid4(), name, description, v),
        )


"""
Upserts an entity into the database.

Parameters
----------
name : str
    The name of the entity.
description : str
    The description of the entity.

Returns
-------
None

Notes
-----
- The OpenAI embeddings API returns a list of embeddings, where each embedding is a list of floats.
- The length of the embedding list is determined by the model used. The small model returns embeddings of length 1536, while the large model returns embeddings of length 3072.
"""


def process_datasets_from_csv(csv_file_path: str):
    """Read datasets from CSV and upsert them into the database."""
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file_path)

        print(f"Processing {len(df)} datasets from {csv_file_path}")

        for index, row in df.iterrows():
            name = row["name"]
            description = row["description"]

            # Skip rows with missing essential data
            if pd.isna(name) or pd.isna(description):
                print(f"Skipping row {index + 1}: missing name or description")
                continue

            print(f"Processing dataset: {name}")
            upsert_entity(name, description)

        print("Finished processing all datasets")

    except FileNotFoundError:
        print(f"Error: CSV file not found at {csv_file_path}")
    except Exception as e:
        print(f"Error processing CSV: {e}")


if __name__ == "__main__":
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file_path = os.path.join(script_dir, "datasets-seed.csv")

    # Process datasets from CSV
    process_datasets_from_csv(csv_file_path)
