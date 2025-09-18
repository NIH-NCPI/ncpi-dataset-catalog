# server.py — Minimal MCP "echo" server using FastMCP.

from fastmcp import FastMCP

# Server name; this appears to MCP clients.
mcp = FastMCP("NCPI MCP Echo Server")


@mcp.tool()
async def echo(text: str) -> str:
    """Return the provided text unchanged."""
    return text


if __name__ == "__main__":
    mcp.run()
