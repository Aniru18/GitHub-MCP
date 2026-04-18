"""
Local test for GitHub Repository Analyzer MCP tools.
Run with:  python test.py
"""

import asyncio
import sys
import os
from dotenv import load_dotenv
load_dotenv()
# ── CONFIG — edit these before running ───────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")   # <-- paste your PAT here
OWNER        = "Aniru18"                        # <-- repo owner
REPO         = "SIFACT"                         # <-- repo name
# ─────────────────────────────────────────────────────────────────────────────


# Import tools directly from your server module
sys.path.insert(0, ".")
from server import (
    get_repo_info,
    list_repo_tree,
    read_file,
    get_commits,
    get_branches,
    get_contributors,
    analyze_repo,
)


async def run_tests():
    sep = "=" * 60

    print(f"\n{sep}")
    print("TEST 1: get_repo_info")
    print(sep)
    result = await get_repo_info(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 2: get_branches")
    print(sep)
    result = await get_branches(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 3: get_contributors")
    print(sep)
    result = await get_contributors(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 4: get_commits (last 5)")
    print(sep)
    result = await get_commits(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN, per_page=5)
    print(result)

    print(f"\n{sep}")
    print("TEST 5: list_repo_tree")
    print(sep)
    result = await list_repo_tree(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 6: read_file (README.md)")
    print(sep)
    result = await read_file(owner=OWNER, repo=REPO, path="README.md", github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 7: analyze_repo")
    print(sep)
    result = await analyze_repo(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("✅ All tests complete!")
    print(sep)


if __name__ == "__main__":
    asyncio.run(run_tests())