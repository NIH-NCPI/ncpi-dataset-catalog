# MCP Echo

A minimal **Model Context Protocol** server implemented in Python using **FastMCP**.  
It exposes a single tool:

- `echo(text: str) -> str`

## Prereqs

- Python 3.10+


## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install fastmcp # Required for running the service via the FastMCP CLI
```

## Run Options

Run via the FastMCP CLI using the default stdio transport:

```
fastmcp run server.py:mcp
```

Run via the FastMCP CLI using the HTTP transport:

```
fastmcp run server.py:mcp --transport http --port 8000
```

Run the client:

```
python client.py
```
