"""
GitHub Repository Analyzer — MCP Server (Async + Multi-User + HTTP)
=====================================================================
A Model Context Protocol server that lets Claude AI browse, analyze, clone,
and deeply understand any GitHub repository through 13 powerful tools.

Key upgrades over v1:
  - Fully async (asyncio + anyio) — multiple users can call tools simultaneously
    without blocking each other.
  - Per-request GitHub PAT token: each caller passes their own token via the
    `X-GitHub-Token` HTTP header (or the `github_token` tool argument as a
    fallback).  The server never uses a hard-coded / env-file token.
  - HTTP transport (Starlette/uvicorn) so the server can be deployed to
    FastMCP Cloud or any container platform.

Run locally:
    pip install "mcp[cli]" PyGithub python-dotenv anyio httpx starlette uvicorn
    python server.py                        # listens on 0.0.0.0:8000
    python server.py --port 9000            # custom port

Deploy to FastMCP Cloud:
    fastmcp deploy server.py

Clients must pass the header:
    X-GitHub-Token: <your_personal_access_token>

For private repos or higher rate-limits a fine-grained PAT with
`repo` / `read:org` scopes is recommended.  Public repos work with
a classic PAT (no extra scopes needed) or even without a token at
all (heavy rate-limiting applies).
"""

from __future__ import annotations

# import argparse
# import asyncio

import base64
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from github import Auth, Github, GithubException
import anyio
from mcp.server.fastmcp import FastMCP

# ── Constants ────────────────────────────────────────────────────────────────
MAX_CONTENT_CHARS = 50_000
MAX_ANALYZE_FILES = 500
DEFAULT_PORT      = 8000
DEFAULT_HOST      = "0.0.0.0"




# def _parse_args() -> tuple[str, int, str]:
#     parser = argparse.ArgumentParser(
#         description="GitHub Repository Analyzer MCP Server",
#         add_help=True,
#     )
#     parser.add_argument(
#         "--port", type=int,
#         default=int(os.environ.get("PORT", DEFAULT_PORT)),
#         help=f"Port to listen on (default {DEFAULT_PORT})",
#     )
#     parser.add_argument(
#         "--host",
#         default=os.environ.get("HOST", DEFAULT_HOST),
#         help=f"Host to bind (default {DEFAULT_HOST})",
#     )
#     parser.add_argument(
#         "--transport",
#         choices=["stdio", "sse", "streamable-http", "http"],  # "http" alias for FastMCP Cloud
#         default=os.environ.get("TRANSPORT", "streamable-http"),
#         help="Transport to use",
#     )
#     args, _ = parser.parse_known_args()

#     # FastMCP Cloud passes "http" — map it to the correct "streamable-http"
#     transport = args.transport
#     if transport == "http":
#         transport = "streamable-http"

#     return args.host, args.port, transport

# _HOST, _PORT, _TRANSPORT = _parse_args()

# ── MCP server instance ──────────────────────────────────────────────────────
# host / port must be set here — FastMCP.run() does NOT accept them as kwargs.
# Supported transports in current FastMCP: "stdio" | "sse" | "streamable-http"
mcp = FastMCP(
    name="GitHub Repository Analyzer",
    instructions=(
        "A powerful GitHub repository analysis server. "
        "IMPORTANT: You must supply your own GitHub Personal Access Token (PAT) "
        "via the `github_token` parameter on every tool call. "
        "Use these tools to browse file trees, read source code, search patterns, "
        "inspect commits, branches, contributors, issues, pull requests, "
        "clone repositories locally, and run deep structural analysis across "
        "any public (or private, with a suitable PAT) GitHub repository."
    )
    # host=_HOST,
    # port=_PORT,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

# def _get_github(token: str) -> Github:
#     """Return an authenticated GitHub client using the caller-supplied token."""
#     if not token:
#         raise ValueError(
#             "No GitHub token provided. "
#             "Pass your Personal Access Token via the `github_token` parameter."
#         )
#     # Strip common prefixes and whitespace users accidentally include
#     for prefix in ("token ", "Token ", "bearer ", "Bearer "):
#         if token.startswith(prefix):
#             token = token[len(prefix):]
#     token = token.strip()
#     return Github(token)

def _get_github(token: str) -> Github:
    """Return an authenticated GitHub client using the caller-supplied token."""
    if not token:
        raise ValueError(
            "No GitHub token provided. "
            "Pass your Personal Access Token via the `github_token` parameter."
        )
    # Strip common prefixes and stray whitespace users accidentally include
    for prefix in ("token ", "Token ", "bearer ", "Bearer "):
        if token.startswith(prefix):
            token = token[len(prefix):]
    token = token.strip()
    # Use the new auth API (login_or_token is deprecated since PyGithub 2.x)
    from github import Auth
    return Github(auth=Auth.Token(token))

def _truncate(content: str, path: str) -> str:
    if len(content) <= MAX_CONTENT_CHARS:
        return content
    return (
        content[:MAX_CONTENT_CHARS]
        + f"\n\n... [TRUNCATED: '{path}' exceeds {MAX_CONTENT_CHARS} chars. "
        f"Total size: {len(content)} chars.]"
    )


def _safe_decode(raw_content: str) -> str:
    return base64.b64decode(raw_content).decode("utf-8", errors="replace")


def _is_binary(text: str) -> bool:
    return "\x00" in text[:1024]


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _mask_token(text: str, token: str) -> str:
    """Remove the token from any error strings before returning to the caller."""
    return text.replace(token, "***") if token else text


# ── Tool 1: get_repo_info ────────────────────────────────────────────────────

@mcp.tool()
async def get_repo_info(owner: str, repo: str, github_token: str) -> str:
    """
    Get detailed metadata about a GitHub repository.

    Returns description, stars, forks, language, topics, license,
    default branch, visibility, size, and timestamps.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))
        r = await anyio.to_thread.run_sync(lambda: g.get_repo(f"{owner}/{repo}"))
        result = {
            "full_name":      r.full_name,
            "description":    r.description,
            "homepage":       r.homepage,
            "language":       r.language,
            "topics":         r.get_topics(),
            "stars":          r.stargazers_count,
            "forks":          r.forks_count,
            "watchers":       r.watchers_count,
            "open_issues":    r.open_issues_count,
            "default_branch": r.default_branch,
            "license":        r.license.name if r.license else "No license",
            "visibility":     "private" if r.private else "public",
            "size_kb":        r.size,
            "created_at":     str(r.created_at),
            "updated_at":     str(r.updated_at),
            "pushed_at":      str(r.pushed_at),
            "clone_url":      r.clone_url,
            "html_url":       r.html_url,
        }
        return _fmt(result)
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {_mask_token(str(e), github_token)}"


# ── Tool 2: list_repo_tree ───────────────────────────────────────────────────

@mcp.tool()
async def list_repo_tree(
    owner: str,
    repo: str,
    github_token: str,
    path: str = "",
    branch: str = "",
) -> str:
    """
    List the complete file and folder tree of a GitHub repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        path:         Subdirectory path to list (leave empty for the whole repo).
        branch:       Branch name or commit SHA (defaults to default branch).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r   = g.get_repo(f"{owner}/{repo}")
            ref = branch or r.default_branch
            return r, ref, r.get_git_tree(ref, recursive=True)

        r, ref, tree = await anyio.to_thread.run_sync(_fetch)
        items = tree.tree

        if path:
            prefix = path.rstrip("/") + "/"
            items  = [i for i in items if i.path.startswith(prefix) or i.path == path]

        truncated_warning = (
            "\n⚠ WARNING: Tree was truncated by GitHub (too many files)."
            if tree.raw_data.get("truncated") else ""
        )

        formatted = [
            {"path": i.path, "type": "file" if i.type == "blob" else "folder", "size_bytes": i.size}
            for i in items
        ]
        return (
            f"Tree for {owner}/{repo} @ {ref} ({len(formatted)} items):"
            f"{truncated_warning}\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {_mask_token(str(e), github_token)}"


# ── Tool 3: read_file ────────────────────────────────────────────────────────

@mcp.tool()
async def read_file(
    owner: str,
    repo: str,
    path: str,
    github_token: str,
    branch: str = "",
) -> str:
    """
    Read the full content of any file in a GitHub repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        path:         File path relative to the repo root, e.g. "src/main.py".
        github_token: Your GitHub Personal Access Token (PAT).
        branch:       Branch name or commit SHA (defaults to default branch).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r   = g.get_repo(f"{owner}/{repo}")
            ref = branch or r.default_branch
            return r.get_contents(path, ref=ref), ref

        file_content, ref = await anyio.to_thread.run_sync(_fetch)

        if isinstance(file_content, list):
            return (
                f'"{path}" is a directory. Use list_repo_tree to explore it.\n\n'
                + _fmt([f.path for f in file_content])
            )

        if file_content.encoding == "none" or not file_content.content:
            return (
                f'File "{path}" has no decodable content '
                f"(size: {file_content.size} bytes, encoding: {file_content.encoding})."
            )

        decoded = _safe_decode(file_content.content)
        if _is_binary(decoded):
            return (
                f'File "{path}" appears to be binary.\n'
                f"Size: {file_content.size} bytes | SHA: {file_content.sha}"
            )

        header = (
            f"File: {path}\n"
            f"Size: {file_content.size} bytes | SHA: {file_content.sha}\n"
            f"URL: {file_content.html_url}\n"
            f"{'─' * 60}\n\n"
        )
        return header + _truncate(decoded, path)

    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error reading '{path}': {_mask_token(str(e), github_token)}"


# ── Tool 4: search_code ──────────────────────────────────────────────────────

@mcp.tool()
async def search_code(
    owner: str,
    repo: str,
    query: str,
    github_token: str,
    per_page: int = 10,
) -> str:
    """
    Search for code patterns, function names, or any text inside a repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        query:        Search term, e.g. "def train", "useState", "import numpy".
        github_token: Your GitHub Personal Access Token (PAT).
        per_page:     Max results to return (1–30, default 10).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _search():
            q       = f"{query} repo:{owner}/{repo}"
            results = g.search_code(q)
            total   = results.totalCount
            items   = list(results[:per_page])
            return total, items

        total, items = await anyio.to_thread.run_sync(_search)

        if total == 0:
            return f'No results found for "{query}" in {owner}/{repo}.'

        formatted = [
            {"path": i.path, "repository": i.repository.full_name,
             "url": i.html_url, "sha": i.sha}
            for i in items
        ]
        return (
            f'Found {total} result(s) for "{query}" in {owner}/{repo} '
            f"(showing {len(items)}):\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error searching: {_mask_token(str(e), github_token)}"


# ── Tool 5: get_commits ──────────────────────────────────────────────────────

@mcp.tool()
async def get_commits(
    owner: str,
    repo: str,
    github_token: str,
    branch: str = "",
    path: str = "",
    per_page: int = 10,
) -> str:
    """
    Retrieve recent commit history for a repository branch or specific file.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        branch:       Branch name (defaults to default branch).
        path:         Filter to commits touching this file path (optional).
        per_page:     Number of commits to return (1–50, default 10).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r      = g.get_repo(f"{owner}/{repo}")
            ref    = branch or r.default_branch
            kwargs: dict[str, Any] = {"sha": ref}
            if path:
                kwargs["path"] = path
            commits = list(r.get_commits(**kwargs)[:per_page])
            return ref, commits

        ref, commits = await anyio.to_thread.run_sync(_fetch)

        formatted = [
            {
                "sha":     c.sha[:8],
                "message": c.commit.message.split("\n")[0],
                "author":  c.commit.author.name if c.commit.author else "Unknown",
                "date":    str(c.commit.author.date) if c.commit.author else None,
                "url":     c.html_url,
            }
            for c in commits
        ]
        label = f" (path: {path})" if path else ""
        return (
            f"Last {len(formatted)} commits for {owner}/{repo} @ {ref}{label}:\n\n"
            + _fmt(formatted)
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching commits: {_mask_token(str(e), github_token)}"


# ── Tool 6: get_branches ─────────────────────────────────────────────────────

@mcp.tool()
async def get_branches(owner: str, repo: str, github_token: str) -> str:
    """
    List all branches in a GitHub repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r = g.get_repo(f"{owner}/{repo}")
            return list(r.get_branches())

        branches = await anyio.to_thread.run_sync(_fetch)
        formatted = [
            {"name": b.name, "sha": b.commit.sha[:8], "protected": b.protected}
            for b in branches
        ]
        return f"{owner}/{repo} has {len(formatted)} branch(es):\n\n{_fmt(formatted)}"
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching branches: {_mask_token(str(e), github_token)}"


# ── Tool 7: get_contributors ─────────────────────────────────────────────────

@mcp.tool()
async def get_contributors(
    owner: str, repo: str, github_token: str, per_page: int = 10
) -> str:
    """
    Get the top contributors to a GitHub repository sorted by commit count.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        per_page:     Number of contributors to return (default 10).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r = g.get_repo(f"{owner}/{repo}")
            return list(r.get_contributors()[:per_page])

        contributors = await anyio.to_thread.run_sync(_fetch)
        formatted = [
            {"username": c.login, "contributions": c.contributions, "profile": c.html_url}
            for c in contributors
        ]
        return f"Top {len(formatted)} contributors for {owner}/{repo}:\n\n{_fmt(formatted)}"
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching contributors: {_mask_token(str(e), github_token)}"


# ── Tool 8: get_issues ───────────────────────────────────────────────────────

@mcp.tool()
async def get_issues(
    owner: str,
    repo: str,
    github_token: str,
    state: str = "open",
    labels: str = "",
    per_page: int = 10,
) -> str:
    """
    Fetch issues from a GitHub repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        state:        "open", "closed", or "all" (default "open").
        labels:       Comma-separated label names, e.g. "bug,help wanted".
        per_page:     Number of issues to return (default 10).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r      = g.get_repo(f"{owner}/{repo}")
            kwargs: dict[str, Any] = {"state": state}
            if labels:
                label_objs = [r.get_label(l.strip()) for l in labels.split(",") if l.strip()]
                kwargs["labels"] = label_objs
            raw = list(r.get_issues(**kwargs)[: per_page * 2])
            return [i for i in raw if not i.pull_request][:per_page]

        issues = await anyio.to_thread.run_sync(_fetch)
        formatted = [
            {
                "number":       i.number,
                "title":        i.title,
                "state":        i.state,
                "author":       i.user.login if i.user else None,
                "labels":       [lbl.name for lbl in i.labels],
                "comments":     i.comments,
                "created_at":   str(i.created_at),
                "url":          i.html_url,
                "body_preview": (i.body or "")[:200] if i.body else None,
            }
            for i in issues
        ]
        return f"{len(formatted)} issue(s) ({state}) for {owner}/{repo}:\n\n{_fmt(formatted)}"
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching issues: {_mask_token(str(e), github_token)}"


# ── Tool 9: get_pull_requests ────────────────────────────────────────────────

@mcp.tool()
async def get_pull_requests(
    owner: str,
    repo: str,
    github_token: str,
    state: str = "open",
    per_page: int = 10,
) -> str:
    """
    Fetch pull requests from a GitHub repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        state:        "open", "closed", or "all" (default "open").
        per_page:     Number of pull requests to return (default 10).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r = g.get_repo(f"{owner}/{repo}")
            return list(r.get_pulls(state=state)[:per_page])

        pulls = await anyio.to_thread.run_sync(_fetch)
        formatted = [
            {
                "number":      pr.number,
                "title":       pr.title,
                "state":       pr.state,
                "author":      pr.user.login if pr.user else None,
                "base_branch": pr.base.ref,
                "head_branch": pr.head.ref,
                "draft":       pr.draft,
                "created_at":  str(pr.created_at),
                "url":         pr.html_url,
            }
            for pr in pulls
        ]
        return (
            f"{len(formatted)} pull request(s) ({state}) for {owner}/{repo}:\n\n"
            + _fmt(formatted)
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching pull requests: {_mask_token(str(e), github_token)}"


# ── Tool 10: compare_branches ────────────────────────────────────────────────

@mcp.tool()
async def compare_branches(
    owner: str,
    repo: str,
    base: str,
    head: str,
    github_token: str,
) -> str:
    """
    Compare two branches, tags, or commits in a GitHub repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        base:         Base branch/commit/tag to compare from.
        head:         Head branch/commit/tag to compare to.
        github_token: Your GitHub Personal Access Token (PAT).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r          = g.get_repo(f"{owner}/{repo}")
            comparison = r.compare(base, head)
            return {
                "status":        comparison.status,
                "ahead_by":      comparison.ahead_by,
                "behind_by":     comparison.behind_by,
                "total_commits": comparison.total_commits,
                "commits": [
                    {
                        "sha":     c.sha[:8],
                        "message": c.commit.message.split("\n")[0],
                        "author":  c.commit.author.name if c.commit.author else "Unknown",
                        "date":    str(c.commit.author.date) if c.commit.author else None,
                    }
                    for c in list(comparison.commits)[:10]
                ],
                "files_changed": [
                    {
                        "filename":  f.filename,
                        "status":    f.status,
                        "additions": f.additions,
                        "deletions": f.deletions,
                        "changes":   f.changes,
                    }
                    for f in list(comparison.files)[:20]
                ],
            }

        result = await anyio.to_thread.run_sync(_fetch)
        return f"Comparison: {owner}/{repo}  {base}...{head}\n\n{_fmt(result)}"
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error comparing branches: {_mask_token(str(e), github_token)}"


# ── Tool 11: clone_repo ──────────────────────────────────────────────────────

@mcp.tool()
async def clone_repo(
    owner: str,
    repo: str,
    github_token: str,
    destination: str = "",
    branch: str = "",
) -> str:
    """
    Clone a GitHub repository to the local filesystem.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        destination:  Local folder path to clone into. Defaults to a temp dir.
        branch:       Specific branch to clone (defaults to default branch).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _get_meta():
            r = g.get_repo(f"{owner}/{repo}")
            return r.clone_url, r.default_branch, r.size

        clone_url, default_branch, size_kb = await anyio.to_thread.run_sync(_get_meta)

        # Embed token for private repos
        auth_url = clone_url.replace("https://", f"https://{github_token}@")

        # Resolve destination
        if destination:
            dest = Path(destination).expanduser().resolve()
        else:
            dest = Path(tempfile.mkdtemp(prefix=f"github_{owner}_{repo}_"))

        if dest.exists() and any(dest.iterdir()):
            return (
                f"Destination already exists and is not empty: {dest}\n"
                "Please specify an empty or non-existent folder."
            )
        dest.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone"]
        if branch:
            cmd += ["--branch", branch, "--single-branch"]
        cmd += [auth_url, str(dest)]

        # Run git clone in a thread so we don't block the event loop
        def _clone():
            return subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        result = await anyio.to_thread.run_sync(_clone)

        if result.returncode != 0:
            err = _mask_token(result.stderr, github_token)
            return f"Git clone failed:\n{err}"

        cloned_files = sum(1 for _ in dest.rglob("*") if _.is_file())
        return (
            f"✅ Successfully cloned {owner}/{repo} to:\n"
            f"   {dest}\n\n"
            f"Branch: {branch or default_branch}\n"
            f"Files cloned: {cloned_files}\n"
            f"Repository size: {size_kb} KB\n"
            f"Clone URL: {clone_url}"   # show clean URL, not auth URL
        )

    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except FileNotFoundError:
        return "Error: 'git' command not found. Please install Git and ensure it is on your PATH."
    except subprocess.TimeoutExpired:
        return "Error: git clone timed out (> 5 minutes). The repository may be very large."
    except Exception as e:
        return f"Error cloning repo: {_mask_token(str(e), github_token)}"


# ── Tool 12: analyze_repo ────────────────────────────────────────────────────

@mcp.tool()
async def analyze_repo(owner: str, repo: str, github_token: str, branch: str = "") -> str:
    """
    Perform a comprehensive structural analysis of a GitHub repository.

    Returns language breakdown, top-level directory structure, README preview,
    key config files, entry-point candidates, and a repository health summary.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        github_token: Your GitHub Personal Access Token (PAT).
        branch:       Branch to analyse (defaults to default branch).
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _analyze():  # noqa: C901
            r   = g.get_repo(f"{owner}/{repo}")
            ref = branch or r.default_branch

            tree       = r.get_git_tree(ref, recursive=True)
            all_items  = tree.tree
            blob_items = [i for i in all_items if i.type == "blob"]
            tree_trunc = tree.raw_data.get("truncated", False)

            # ── Language breakdown ──────────────────────────────────────────
            EXT_LANG: dict[str, str] = {
                ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
                ".tsx": "TypeScript/React", ".jsx": "JavaScript/React",
                ".java": "Java", ".kt": "Kotlin", ".scala": "Scala",
                ".go": "Go", ".rs": "Rust", ".cpp": "C++", ".cc": "C++",
                ".c": "C", ".h": "C/C++ Header", ".cs": "C#",
                ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
                ".dart": "Dart", ".lua": "Lua", ".r": "R", ".m": "MATLAB/ObjC",
                ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
                ".html": "HTML", ".htm": "HTML", ".css": "CSS",
                ".scss": "SCSS", ".sass": "SASS", ".less": "LESS",
                ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
                ".toml": "TOML", ".xml": "XML", ".md": "Markdown",
                ".rst": "reStructuredText", ".tf": "Terraform",
                ".sql": "SQL", ".graphql": "GraphQL",
                ".dockerfile": "Dockerfile", ".proto": "Protobuf",
            }

            lang_file_count: dict[str, int] = defaultdict(int)
            lang_byte_count: dict[str, int] = defaultdict(int)

            for item in blob_items[:MAX_ANALYZE_FILES]:
                ext       = Path(item.path).suffix.lower()
                name_low  = Path(item.path).name.lower()
                if name_low == "dockerfile":
                    lang = "Dockerfile"
                elif name_low in ("makefile", "rakefile", "gemfile"):
                    lang = name_low.capitalize()
                elif ext in EXT_LANG:
                    lang = EXT_LANG[ext]
                else:
                    lang = "Other"
                lang_file_count[lang] += 1
                lang_byte_count[lang] += item.size or 0

            language_breakdown = [
                {"language": lang, "files": count, "total_bytes": lang_byte_count[lang]}
                for lang, count in sorted(lang_file_count.items(), key=lambda x: -x[1])
                if lang != "Other"
            ]

            # ── Top-level structure ─────────────────────────────────────────
            top_level: dict[str, str] = {}
            for item in all_items:
                name = item.path.split("/")[0]
                if name not in top_level:
                    top_level[name] = "folder" if item.type == "tree" else "file"

            # ── Config file detection ───────────────────────────────────────
            KNOWN_CONFIGS = {
                ".github/workflows": "GitHub Actions CI/CD",
                ".gitlab-ci.yml":    "GitLab CI",
                "Jenkinsfile":       "Jenkins CI",
                ".circleci/config.yml": "CircleCI",
                "azure-pipelines.yml": "Azure Pipelines",
                "Dockerfile":        "Docker",
                "docker-compose.yml": "Docker Compose",
                "docker-compose.yaml": "Docker Compose",
                "pyproject.toml":    "Python (pyproject / uv / poetry)",
                "requirements.txt":  "Python (pip)",
                "setup.py":          "Python (setup.py)",
                "package.json":      "Node.js / npm / yarn",
                "pnpm-lock.yaml":    "pnpm",
                "bun.lockb":         "Bun",
                "Cargo.toml":        "Rust (Cargo)",
                "go.mod":            "Go Modules",
                "pom.xml":           "Java / Maven",
                "build.gradle":      "Java / Gradle",
                "Gemfile":           "Ruby / Bundler",
                "composer.json":     "PHP / Composer",
                "pubspec.yaml":      "Dart / Flutter",
                "terraform.tf":      "Terraform",
                "serverless.yml":    "Serverless Framework",
                "README.md":         "README (Markdown)",
                "README.rst":        "README (reStructuredText)",
                "CONTRIBUTING.md":   "Contributing Guide",
                "CHANGELOG.md":      "Changelog",
                "LICENSE":           "License File",
                ".env.example":      "Env Example",
            }

            all_paths_lower = {i.path.lower(): i.path for i in all_items}
            detected_configs = {
                label: all_paths_lower[p.lower()]
                for p, label in KNOWN_CONFIGS.items()
                if p.lower() in all_paths_lower
            }

            # ── Entry points ────────────────────────────────────────────────
            ENTRY_CANDIDATES = {
                "main.py", "app.py", "server.py", "run.py", "cli.py", "manage.py",
                "index.js", "index.ts", "app.js", "server.js",
                "main.go", "main.rs", "main.java", "Program.cs",
                "Application.kt", "main.cpp",
            }
            entry_points = [i.path for i in blob_items if Path(i.path).name in ENTRY_CANDIDATES]

            # ── README ──────────────────────────────────────────────────────
            readme_content = ""
            for key in ["readme.md", "readme.rst", "readme.txt", "readme"]:
                if key in all_paths_lower:
                    try:
                        fc = r.get_contents(all_paths_lower[key], ref=ref)
                        if not isinstance(fc, list) and fc.content:
                            decoded = _safe_decode(fc.content)
                            readme_content = decoded[:3000]
                            if len(decoded) > 3000:
                                readme_content += "\n\n... [README truncated at 3000 chars]"
                    except Exception:
                        pass
                    break

            # ── Health summary ──────────────────────────────────────────────
            try:
                contrib_count = r.get_contributors().totalCount
            except Exception:
                contrib_count = "Unknown"

            health = {
                "stars":            r.stargazers_count,
                "forks":            r.forks_count,
                "open_issues":      r.open_issues_count,
                "watchers":         r.watchers_count,
                "last_push":        str(r.pushed_at),
                "created_at":       str(r.created_at),
                "contributors":     contrib_count,
                "has_wiki":         r.has_wiki,
                "has_pages":        r.has_pages,
                "archived":         r.archived,
                "fork":             r.fork,
                "primary_language": r.language,
                "license":          r.license.name if r.license else "None",
            }

            total_files = len(blob_items)
            total_bytes  = sum(i.size or 0 for i in blob_items)

            return (
                r, ref, total_files, total_bytes, tree_trunc,
                language_breakdown, top_level, detected_configs,
                entry_points, readme_content, health,
            )

        (
            r, ref, total_files, total_bytes, tree_trunc,
            language_breakdown, top_level, detected_configs,
            entry_points, readme_content, health,
        ) = await anyio.to_thread.run_sync(_analyze)

        parts = [
            f"{'═' * 70}",
            f"  DEEP ANALYSIS: {owner}/{repo}  @  {ref}",
            f"{'═' * 70}",
            f"\n📦 OVERVIEW",
            f"   Description : {r.description or 'No description'}",
            f"   Total files : {total_files}{' (tree truncated by GitHub)' if tree_trunc else ''}",
            f"   Total size  : {total_bytes:,} bytes ({r.size} KB reported by GitHub)",
            f"   URL         : {r.html_url}",
            f"\n📊 LANGUAGE BREAKDOWN\n{_fmt(language_breakdown)}",
            f"\n📁 TOP-LEVEL STRUCTURE\n{_fmt(top_level)}",
            f"\n⚙️  DETECTED TOOLING & CONFIGS\n{_fmt(detected_configs)}",
            f"\n🚀 ENTRY-POINT CANDIDATES\n{_fmt(entry_points)}",
            f"\n❤️  REPOSITORY HEALTH\n{_fmt(health)}",
        ]
        if readme_content:
            parts += ["\n📄 README PREVIEW", "─" * 60, readme_content]

        return "\n".join(parts)

    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error analyzing repo: {_mask_token(str(e), github_token)}"


# ── Tool 13: get_file_url ────────────────────────────────────────────────────

@mcp.tool()
async def get_file_url(
    owner: str,
    repo: str,
    path: str,
    github_token: str,
    branch: str = "",
    raw: bool = False,
) -> str:
    """
    Get the GitHub web or raw URL for any file in a repository.

    Args:
        owner:        GitHub username or organisation name.
        repo:         Repository name.
        path:         File path relative to the repo root.
        github_token: Your GitHub Personal Access Token (PAT).
        branch:       Branch name (defaults to the default branch).
        raw:          If True, return the raw.githubusercontent.com download URL.
    """
    try:
        g = await anyio.to_thread.run_sync(lambda: _get_github(github_token))

        def _fetch():
            r   = g.get_repo(f"{owner}/{repo}")
            ref = branch or r.default_branch
            return r.get_contents(path, ref=ref), ref

        file_content, ref = await anyio.to_thread.run_sync(_fetch)

        if isinstance(file_content, list):
            return f'"{path}" is a directory, not a file.'

        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"

        if raw:
            return f"Raw URL:\n{raw_url}"

        return (
            f"GitHub URL:\n{file_content.html_url}\n\n"
            f"Raw URL:\n{raw_url}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {_mask_token(str(e), github_token)}"


# ── Entry point ──────────────────────────────────────────────────────────────

# def main() -> None:
#     if _TRANSPORT == "stdio":
#         print("🔍 Running in STDIO mode (fastmcp dev / inspector)")
#     else:
#         print(f"🚀 GitHub Repository Analyzer MCP server starting on {_HOST}:{_PORT}")
#         path = "/mcp" if _TRANSPORT == "streamable-http" else "/sse"
#         print(f"   Transport : {_TRANSPORT}")
#         print(f"   Endpoint  : http://{_HOST}:{_PORT}{path}")
#         print("   Pass your GitHub PAT via the `github_token` tool parameter.")
#         print("   Press Ctrl+C to stop.\n")

#     mcp.run(transport=_TRANSPORT)


# if __name__ == "__main__":
#     main()

# if __name__ == "__main__":
#     import argparse

#     parser = argparse.ArgumentParser(description="GitHub Repository Analyzer MCP Server")
#     parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
#     parser.add_argument("--host", default=os.environ.get("HOST", DEFAULT_HOST))
#     parser.add_argument(
#         "--transport",
#         choices=["stdio", "sse", "streamable-http"],
#         default=os.environ.get("TRANSPORT", "stdio"),
#     )
#     args, _ = parser.parse_known_args()

#     transport = args.transport

#     print(f"🚀 Starting locally on {args.host}:{args.port} | transport: {transport}")
#     mcp.run(transport=transport)


if __name__ == "__main__":
    import uvicorn
    # Get the ASGI app from FastMCP and serve it directly
    # This avoids the double asyncio.run() conflict
    app = mcp.get_asgi_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8081)))