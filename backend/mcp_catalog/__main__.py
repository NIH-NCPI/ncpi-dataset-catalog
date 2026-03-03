"""Entry point for ``python -m mcp_catalog``."""

from dotenv import load_dotenv

# Load .env BEFORE importing server (consent_logic reads files at module level).
load_dotenv()

from mcp_catalog.server import mcp  # noqa: E402

mcp.run()
