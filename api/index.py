"""
Vercel Serverless Entry Point
==============================
This module wraps the MCP server with an SSE HTTP transport so Vercel can
serve it as a public endpoint.

Vercel routes all traffic from /api/* → this function.
"""

from server import mcp

# Expose the ASGI app. Vercel's Python runtime (WSGI bridge) will call this.
app = mcp.get_asgi_app()
