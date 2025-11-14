# NCPI RAG Server

A FastAPI-based RAG (Retrieval-Augmented Generation) server that provides intelligent question-answering over the NCPI dataset catalog using OpenAI embeddings, pgvector for semantic search, and Pydantic AI for agentic workflows.

## Architecture

This service follows a clean layered architecture pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Application                     │
│                         (main.py)                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Controllers                           │
│                  (controllers/dataset_controller.py)         │
│  • Handle HTTP requests/responses                            │
│  • Route definitions and query parameter validation          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         Services                             │
│                  (services/dataset_service.py)               │
│  • Business logic and orchestration                          │
│  • Pydantic AI agent with tool definitions                   │
│  • Embedding generation and result formatting                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       Repositories                           │
│                  (repositories/dataset_repo.py)              │
│  • Data access layer (database queries only)                 │
│  • pgvector ANN search operations                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    PostgreSQL + pgvector                     │
│                      (datasets table)                        │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

#### **Controllers** (`controllers/`)
- Define API routes and endpoints
- Handle HTTP request/response formatting
- Validate query parameters
- Delegate business logic to services

#### **Services** (`services/`)
- Implement business logic and orchestration
- Configure and run Pydantic AI agents
- Define agent tools and instructions
- Coordinate between repositories and external APIs (OpenAI)
- Format responses for controllers

#### **Repositories** (`repositories/`)
- Pure data access layer
- Execute database queries
- Return raw data structures
- No business logic or external API calls

#### **Models** (`models/`)
- Pydantic schemas for data validation
- Type definitions for API contracts

#### **Config** (`config.py`)
- Environment variable management
- Singleton database connection
- OpenAI client initialization

## Components

### 1. Dataset Controller (`controllers/dataset_controller.py`)

Exposes a single endpoint for asking questions about datasets:

**Endpoint:** `GET /ask?q=<question>`

**Example:**
```bash
curl "http://localhost:8000/ask?q=What%20datasets%20are%20available%20for%20autism%20research?"
```

**Response:**
```json
{
  "question": "What datasets are available for autism research?",
  "answer": "Based on the search results, the Simons Simplex Collection (SSC) is available for autism research..."
}
```

### 2. Dataset Service (`services/dataset_service.py`)

The service layer implements a Pydantic AI agent with the following features:

- **Agent Configuration:**
  - Model: GPT-4o-mini (configurable via `OPENAI_MODEL`)
  - Temperature: 0 (deterministic responses)
  - Instructions: Always search datasets first, cite sources, admit when information is unavailable

- **Tool: `search_datasets`**
  - Embeds the user's query using OpenAI embeddings
  - Performs approximate nearest neighbor (ANN) search via pgvector
  - Returns structured `DatasetHit` objects with name, description, and similarity distance
  - Default: Returns top 5 most relevant datasets

- **Public API:**
  - `ask(question: str) -> str`: Main entrypoint for question-answering

### 3. Dataset Repository (`repositories/dataset_repo.py`)

Pure data access layer with a single function:

- **`ann_search(conn, query_vector, k=5)`**
  - Executes cosine similarity search using pgvector's `<=>` operator
  - Returns tuples of `(name, description, distance)`
  - Ordered by ascending distance (most similar first)

### 4. Data Models (`models/schemas.py`)

- **`DatasetHit`**: Represents a search result with dataset name, description, and similarity distance

## Setup

### Prerequisites

1. **PostgreSQL with pgvector extension** (see [scripts/readme.md](scripts/readme.md) for detailed setup)
2. **Python 3.9+**
3. **OpenAI API key**

### Installation

1. **Install dependencies:**
   ```bash
   cd mcp
   pip install -r scripts/requirements.txt
   ```

2. **Configure environment variables:**
   
   Create `scripts/.env`:
   ```bash
   OPENAI_API_KEY=<your-openai-api-key>
   PG_DSN=postgresql://localhost/ncpi_dataset_catalog
   OPENAI_MODEL=gpt-4o-mini
   EMBEDDING_MODEL=text-embedding-3-small
   ```

3. **Set up database:**
   
   See [scripts/readme.md](scripts/readme.md) for complete database setup instructions, including:
   - Installing PostgreSQL and pgvector
   - Creating the database and table
   - Running the embedding script
   - Creating the vector index

## Running the Server

### Development Mode

```bash
cd mcp
uvicorn main:app --reload --port 8000
```

## Usage Examples

### Basic Query

```bash
curl "http://localhost:8000/ask?q=Tell%20me%20about%20heart%20disease%20datasets"
```

### Complex Query

```bash
curl "http://localhost:8000/ask?q=What%20datasets%20include%20genomic%20data%20for%20pediatric%20populations?"
```

### Python Client

```python
import requests

response = requests.get(
    "http://localhost:8000/ask",
    params={"q": "What datasets study rare diseases?"}
)

data = response.json()
print(f"Question: {data['question']}")
print(f"Answer: {data['answer']}")
```

## How It Works

1. **User submits a question** via the `/ask` endpoint
2. **Controller** validates the query parameter and calls the service
3. **Service layer** invokes the Pydantic AI agent with the question
4. **Agent** automatically calls the `search_datasets` tool:
   - Generates an embedding for the question using OpenAI
   - Passes the embedding vector to the repository
5. **Repository** executes a pgvector ANN search and returns matching datasets
6. **Agent** receives the search results and generates a natural language answer
7. **Service** returns the answer to the controller
8. **Controller** formats and returns the JSON response

## Configuration

All configuration is managed through environment variables (no hardcoded fallbacks):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | - | OpenAI API key for embeddings and chat |
| `PG_DSN` | Yes | - | PostgreSQL connection string |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model for agent responses |
| `EMBEDDING_MODEL` | No | `text-embedding-3-small` | OpenAI embedding model |

## Design Principles

### Separation of Concerns
- Controllers handle HTTP concerns
- Services contain business logic and orchestration
- Repositories handle data access only
- Models define data contracts

### Agentic Architecture
- Uses Pydantic AI for tool-calling workflows
- Agent decides when to search and how to synthesize answers
- Structured tool outputs ensure type safety

### Simplicity
- Singleton connections for demo purposes (can be enhanced with connection pooling)
- Minimal dependencies
- Clear data flow from controller → service → repository → database

## Extending the Service

### Adding New Tools

Add tools to the agent in `services/dataset_service.py`:

```python
@agent.tool
def get_dataset_details(ctx: RunContext[Deps], dataset_name: str) -> dict:
    """Tool: Fetch detailed information about a specific dataset."""
    # Implementation here
    pass
```

### Adding New Endpoints

1. Add route to `controllers/dataset_controller.py`
2. Implement business logic in `services/dataset_service.py`
3. Add data access methods to `repositories/dataset_repo.py` if needed

### Adding New Models

Define Pydantic models in `models/schemas.py` for type safety and validation.

## Related Documentation

- [Database Setup and Scripts](scripts/readme.md) - Complete setup guide for PostgreSQL, pgvector, and data seeding
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)

## Troubleshooting

### Connection Errors
- Verify `PG_DSN` is correct and database is running
- Ensure pgvector extension is installed: `psql -d ncpi_dataset_catalog -c "\dx"`

### Empty Results
- Confirm datasets table is populated: `SELECT COUNT(*) FROM datasets;`
- Check if vector index exists: `\d datasets`

### OpenAI Errors
- Verify `OPENAI_API_KEY` is set and valid
- Check API quota and rate limits

## License

See repository root for license information.
