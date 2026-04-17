import sys
import os

# Add the project root to the Python path to ensure server.py can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import mcp

# This exposes the Starlette ASGI application for Vercel's Python runtime
app = mcp.sse_app()
