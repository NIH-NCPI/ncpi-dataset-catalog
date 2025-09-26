# server.py — Minimal MCP "echo" server using FastMCP.
import logging
from fastmcp import FastMCP

# Configure logging to show INFO level messages
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Server name; this appears to MCP clients.
mcp = FastMCP("NCPI MCP Echo Server")


@mcp.tool()
async def echo(text: str) -> str:
    """Return the provided text unchanged."""
    logging.info(f"Echoing: {text}")
    return text


if __name__ == "__main__":
    mcp.run()
