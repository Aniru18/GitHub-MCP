import sys
import os
from starlette.responses import JSONResponse

# Add the project root to the Python path to ensure server.py can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import mcp

# This exposes the Starlette ASGI application for Vercel's Python runtime
app = mcp.sse_app()

# Add a root route so the user doesn't just see "Not Found" when they visit the main URL
app.add_route("/", lambda req: JSONResponse({
    "status": "online",
    "message": "GitHub MCP Server is successfully deployed!",
    "instructions": "In your claude_desktop_config.json, make sure the URL ends with /sse"
}))
