# NCPI Dataset Catalog Embed/Query Roundtrip

## Setup

### Using Postgres

#### Install Postgres

```bash
brew install postgresql
```

#### Install pgvector

Follow instructions at [pgvector](https://github.com/pgvector/pgvector?tab=readme-ov-file#linux-and-mac).

```bash
cd /tmp
git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git
cd pgvector
make
make install # may need sudo
```

#### Create Database

```bash
createdb ncpi_dataset_catalog
```

#### Add pgvector Extension

```bash
psql ncpi_dataset_catalog
```

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Confirm extension is installed with:

```sql
\dx
```

  Name   | Version |   Schema   |                     Description                      
---------|---------|------------|------------------------------------------------------
 vector  | 0.8.1   | public     | vector data type and ivfflat and hnsw access methods

#### Create Datasets Table

Using `text-embedding-3-small` (i.e. 1536 dimensions):

```sql
CREATE TABLE datasets (
  id              UUID PRIMARY KEY,
  name            TEXT,
  description     TEXT,
  embedding       vector(1536) 
);
```

## Running the Roundtrip

### Update scripts/.env 

```bash
OPENAI_API_KEY=your_openai_api_key
PG_DSN=postgresql://localhost/ncpi_dataset_catalog
```

### Embed Datasets

Seed datasets table from CSV. From the `mcp` directory, run:

```bash
python scripts/embed.py
```

### Create Index

```sql
CREATE INDEX ON datasets
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### Query Datasets

From the `mcp` directory, run:

```bash
python scripts/query.py
```







