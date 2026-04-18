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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") # you can paste the token directly with out fetching from environment 
OWNER        = "Aniru18" # Example owner
REPO         = "SIFACT" # Example repo of the owner
# ─────────────────────────────────────────────────────────────────────────────

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
    result = await get_repo_info.fn(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 2: get_branches")
    print(sep)
    result = await get_branches.fn(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 3: get_contributors")
    print(sep)
    result = await get_contributors.fn(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 4: get_commits (last 5)")
    print(sep)
    result = await get_commits.fn(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN, per_page=5)
    print(result)

    print(f"\n{sep}")
    print("TEST 5: list_repo_tree")
    print(sep)
    result = await list_repo_tree.fn(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 6: read_file (README.md)")
    print(sep)
    result = await read_file.fn(owner=OWNER, repo=REPO, path="README.md", github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("TEST 7: analyze_repo")
    print(sep)
    result = await analyze_repo.fn(owner=OWNER, repo=REPO, github_token=GITHUB_TOKEN)
    print(result)

    print(f"\n{sep}")
    print("✅ All tests complete!")
    print(sep)


if __name__ == "__main__":
    asyncio.run(run_tests())