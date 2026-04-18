"""
Vercel serverless entry point for the GitHub MCP Server.
Vercel looks for an `app` variable (ASGI) in api/index.py and routes all
requests to it.  FastMCP's HTTP transport exposes a Starlette ASGI app via
mcp.http_app(), so we just re-export it here.
"""
import os
import sys

# Make sure the project root (where server.py lives) is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import mcp  # noqa: E402  (import after sys.path patch)

# ── ASGI app consumed by Vercel's Python runtime ──────────────────────────
# FastMCP builds a Starlette app internally; http_app() returns it.
app = mcp.http_app()