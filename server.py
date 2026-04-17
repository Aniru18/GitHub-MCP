"""
GitHub Repository Analyzer — MCP Server
=========================================
A Model Context Protocol server that lets Claude AI browse, analyze, clone,
and deeply understand any GitHub repository through 13 powerful tools.

Run locally (Claude Desktop):
    uv run server.py
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from github import Github, GithubException
from mcp.server.fastmcp import FastMCP

load_dotenv()

# ── Constants ────────────────────────────────────────────────────────────────
MAX_CONTENT_CHARS = 50_000   # Truncate files larger than this
MAX_ANALYZE_FILES = 500      # Max files to inspect during deep analysis

# ── MCP server instance ──────────────────────────────────────────────────────
mcp = FastMCP(
    name="GitHub Repository Analyzer",
    instructions=(
        "A powerful GitHub repository analysis server. "
        "Use these tools to browse file trees, read source code, search patterns, "
        "inspect commits, branches, contributors, issues, and pull requests, "
        "clone repositories locally, and run deep structural analysis across "
        "any public (or private, with token) GitHub repository."
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_github() -> Github:
    """Return an authenticated (or anonymous) GitHub client."""
    token = os.environ.get("GITHUB_TOKEN")
    return Github(token) if token else Github()


def _truncate(content: str, path: str) -> str:
    """Truncate file content if it exceeds MAX_CONTENT_CHARS."""
    if len(content) <= MAX_CONTENT_CHARS:
        return content
    return (
        content[:MAX_CONTENT_CHARS]
        + f"\n\n... [TRUNCATED: '{path}' exceeds {MAX_CONTENT_CHARS} chars. "
        f"Total size: {len(content)} chars.]"
    )


def _safe_decode(raw_content: str) -> str:
    """Decode base64 GitHub file content to a UTF-8 string."""
    return base64.b64decode(raw_content).decode("utf-8", errors="replace")


def _is_binary(text: str) -> bool:
    """Heuristic: if null bytes appear in the first 1 KB it's likely binary."""
    return "\x00" in text[:1024]


def _fmt(data: Any) -> str:
    """Pretty-print a dict / list as indented JSON-like text."""
    return json.dumps(data, indent=2, default=str)


# ── Tool 1: get_repo_info ────────────────────────────────────────────────────

@mcp.tool()
def get_repo_info(owner: str, repo: str) -> str:
    """
    Get detailed metadata about a GitHub repository.

    Returns description, stars, forks, language, topics, license,
    default branch, visibility, size, and timestamps.

    Args:
        owner: GitHub username or organisation name.
        repo:  Repository name.
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        result = {
            "full_name":     r.full_name,
            "description":   r.description,
            "homepage":      r.homepage,
            "language":      r.language,
            "topics":        r.get_topics(),
            "stars":         r.stargazers_count,
            "forks":         r.forks_count,
            "watchers":      r.watchers_count,
            "open_issues":   r.open_issues_count,
            "default_branch": r.default_branch,
            "license":       r.license.name if r.license else "No license",
            "visibility":    "private" if r.private else "public",
            "size_kb":       r.size,
            "created_at":    str(r.created_at),
            "updated_at":    str(r.updated_at),
            "pushed_at":     str(r.pushed_at),
            "clone_url":     r.clone_url,
            "html_url":      r.html_url,
        }
        return _fmt(result)
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"


# ── Tool 2: list_repo_tree ───────────────────────────────────────────────────

@mcp.tool()
def list_repo_tree(
    owner: str,
    repo: str,
    path: str = "",
    branch: str = "",
) -> str:
    """
    List the complete file and folder tree of a GitHub repository.

    Recursively returns every file and folder path.
    Useful for understanding the project structure before reading specific files.

    Args:
        owner:  GitHub username or organisation name.
        repo:   Repository name.
        path:   Subdirectory path to list (leave empty for the whole repo).
        branch: Branch name or commit SHA (defaults to the repo's default branch).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        ref = branch or r.default_branch

        tree = r.get_git_tree(ref, recursive=True)
        items = tree.tree

        if path:
            prefix = path.rstrip("/") + "/"
            items = [i for i in items if i.path.startswith(prefix) or i.path == path]

        truncated_warning = (
            "\n⚠ WARNING: Tree was truncated by GitHub (too many files)."
            if tree.raw_data.get("truncated")
            else ""
        )

        formatted = [
            {
                "path":       i.path,
                "type":       "file" if i.type == "blob" else "folder",
                "size_bytes": i.size,
            }
            for i in items
        ]

        return (
            f"Tree for {owner}/{repo} @ {ref} ({len(formatted)} items):"
            f"{truncated_warning}\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"


# ── Tool 3: read_file ────────────────────────────────────────────────────────

@mcp.tool()
def read_file(
    owner: str,
    repo: str,
    path: str,
    branch: str = "",
) -> str:
    """
    Read the full content of any file in a GitHub repository.

    Decodes base64 content returned by the GitHub API. Binary files
    (images, compiled artifacts, etc.) are detected and reported instead
    of returned as garbled text.

    Args:
        owner:  GitHub username or organisation name.
        repo:   Repository name.
        path:   File path relative to the repo root, e.g. "src/main.py".
        branch: Branch name or commit SHA (defaults to default branch).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        ref = branch or r.default_branch

        file_content = r.get_contents(path, ref=ref)

        # get_contents can return a list when path is a directory
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
        return f"Error reading '{path}': {e}"


# ── Tool 4: search_code ──────────────────────────────────────────────────────

@mcp.tool()
def search_code(
    owner: str,
    repo: str,
    query: str,
    per_page: int = 10,
) -> str:
    """
    Search for code patterns, function names, or any text inside a repository.

    Uses GitHub Code Search API. Results include file paths and direct URLs.
    Note: requires a GitHub token for reliable results; unauthenticated
    code search is heavily rate-limited.

    Args:
        owner:    GitHub username or organisation name.
        repo:     Repository name.
        query:    Search term, e.g. "def train", "useState", "import numpy".
        per_page: Max results to return (1–30, default 10).
    """
    try:
        g = get_github()
        q = f"{query} repo:{owner}/{repo}"
        results = g.search_code(q)

        total = results.totalCount
        if total == 0:
            return f'No results found for "{query}" in {owner}/{repo}.'

        items = list(results[:per_page])
        formatted = [
            {
                "path":       item.path,
                "repository": item.repository.full_name,
                "url":        item.html_url,
                "sha":        item.sha,
            }
            for item in items
        ]
        return (
            f'Found {total} result(s) for "{query}" in {owner}/{repo} '
            f"(showing {len(items)}):\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error searching: {e}"


# ── Tool 5: get_commits ──────────────────────────────────────────────────────

@mcp.tool()
def get_commits(
    owner: str,
    repo: str,
    branch: str = "",
    path: str = "",
    per_page: int = 10,
) -> str:
    """
    Retrieve recent commit history for a repository branch or specific file.

    Args:
        owner:    GitHub username or organisation name.
        repo:     Repository name.
        branch:   Branch name (defaults to default branch).
        path:     Filter to commits touching this file path (optional).
        per_page: Number of commits to return (1–50, default 10).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        ref = branch or r.default_branch

        kwargs: dict[str, Any] = {"sha": ref}
        if path:
            kwargs["path"] = path

        commits_page = r.get_commits(**kwargs)
        commits = list(commits_page[:per_page])

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
        return f"Error fetching commits: {e}"


# ── Tool 6: get_branches ─────────────────────────────────────────────────────

@mcp.tool()
def get_branches(owner: str, repo: str) -> str:
    """
    List all branches in a GitHub repository.

    Returns branch names, their latest commit SHA, and protection status.

    Args:
        owner: GitHub username or organisation name.
        repo:  Repository name.
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        branches = list(r.get_branches())

        formatted = [
            {
                "name":      b.name,
                "sha":       b.commit.sha[:8],
                "protected": b.protected,
            }
            for b in branches
        ]
        return (
            f"{owner}/{repo} has {len(formatted)} branch(es):\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching branches: {e}"


# ── Tool 7: get_contributors ─────────────────────────────────────────────────

@mcp.tool()
def get_contributors(owner: str, repo: str, per_page: int = 10) -> str:
    """
    Get the top contributors to a GitHub repository sorted by commit count.

    Args:
        owner:    GitHub username or organisation name.
        repo:     Repository name.
        per_page: Number of contributors to return (default 10).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        contributors = list(r.get_contributors()[:per_page])

        formatted = [
            {
                "username":      c.login,
                "contributions": c.contributions,
                "profile":       c.html_url,
            }
            for c in contributors
        ]
        return (
            f"Top {len(formatted)} contributors for {owner}/{repo}:\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching contributors: {e}"


# ── Tool 8: get_issues ───────────────────────────────────────────────────────

@mcp.tool()
def get_issues(
    owner: str,
    repo: str,
    state: str = "open",
    labels: str = "",
    per_page: int = 10,
) -> str:
    """
    Fetch issues from a GitHub repository.

    Args:
        owner:    GitHub username or organisation name.
        repo:     Repository name.
        state:    "open", "closed", or "all" (default "open").
        labels:   Comma-separated label names to filter by, e.g. "bug,help wanted".
        per_page: Number of issues to return (default 10).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")

        kwargs: dict[str, Any] = {"state": state}
        if labels:
            label_objs = [
                r.get_label(lbl.strip()) for lbl in labels.split(",") if lbl.strip()
            ]
            kwargs["labels"] = label_objs

        issues_page = r.get_issues(**kwargs)
        # Filter out pull requests (GitHub returns PRs as issues too)
        issues = [
            i for i in list(issues_page[: per_page * 2]) if not i.pull_request
        ][:per_page]

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
        return (
            f"{len(formatted)} issue(s) ({state}) for {owner}/{repo}:\n\n{_fmt(formatted)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error fetching issues: {e}"


# ── Tool 9: get_pull_requests ────────────────────────────────────────────────

@mcp.tool()
def get_pull_requests(
    owner: str,
    repo: str,
    state: str = "open",
    per_page: int = 10,
) -> str:
    """
    Fetch pull requests from a GitHub repository.

    Args:
        owner:    GitHub username or organisation name.
        repo:     Repository name.
        state:    "open", "closed", or "all" (default "open").
        per_page: Number of pull requests to return (default 10).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        pulls = list(r.get_pulls(state=state)[:per_page])

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
        return f"Error fetching pull requests: {e}"


# ── Tool 10: compare_branches ────────────────────────────────────────────────

@mcp.tool()
def compare_branches(
    owner: str,
    repo: str,
    base: str,
    head: str,
) -> str:
    """
    Compare two branches, tags, or commits in a GitHub repository.

    Shows ahead/behind counts, differing commits, and changed files summary.

    Args:
        owner: GitHub username or organisation name.
        repo:  Repository name.
        base:  Base branch/commit/tag to compare from.
        head:  Head branch/commit/tag to compare to.
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        comparison = r.compare(base, head)

        result = {
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
        return (
            f"Comparison: {owner}/{repo}  {base}...{head}\n\n{_fmt(result)}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error comparing branches: {e}"


# ── Tool 11: clone_repo ──────────────────────────────────────────────────────

@mcp.tool()
def clone_repo(
    owner: str,
    repo: str,
    destination: str = "",
    branch: str = "",
) -> str:
    """
    Clone a GitHub repository to the local filesystem.

    Uses 'git clone' under the hood. The destination folder is created
    automatically. If no destination is given, clones into a temp directory.

    Args:
        owner:       GitHub username or organisation name.
        repo:        Repository name.
        destination: Local folder path to clone into. Defaults to a temp dir.
        branch:      Specific branch to clone (clones default branch if omitted).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        clone_url = r.clone_url

        # If the user has a token, embed it for private repos
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            clone_url = clone_url.replace(
                "https://", f"https://{token}@"
            )

        # Determine destination
        if destination:
            dest = Path(destination).expanduser().resolve()
        else:
            dest = Path(tempfile.mkdtemp(prefix=f"github_{owner}_{repo}_"))

        if dest.exists() and any(dest.iterdir()):
            return (
                f"Destination already exists and is not empty: {dest}\n"
                f"Please specify an empty or non-existent folder."
            )

        dest.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone"]
        if branch:
            cmd += ["--branch", branch, "--single-branch"]
        cmd += [clone_url, str(dest)]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            # Strip the token from any error message
            err = result.stderr.replace(token, "***") if token else result.stderr
            return f"Git clone failed:\n{err}"

        # Count cloned files
        cloned_files = sum(1 for _ in dest.rglob("*") if _.is_file())

        return (
            f"✅ Successfully cloned {owner}/{repo} to:\n"
            f"   {dest}\n\n"
            f"Branch: {branch or r.default_branch}\n"
            f"Files cloned: {cloned_files}\n"
            f"Repository size: {r.size} KB\n"
            f"Clone URL: {r.clone_url}"
        )

    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except FileNotFoundError:
        return (
            "Error: 'git' command not found. "
            "Please install Git and ensure it is on your PATH."
        )
    except subprocess.TimeoutExpired:
        return "Error: git clone timed out (> 5 minutes). The repository may be very large."
    except Exception as e:
        return f"Error cloning repo: {e}"


# ── Tool 12: analyze_repo ────────────────────────────────────────────────────

@mcp.tool()
def analyze_repo(owner: str, repo: str, branch: str = "") -> str:
    """
    Perform a comprehensive structural analysis of a GitHub repository.

    Returns:
    - Language breakdown (file counts and byte sizes per language)
    - Top-level directory structure
    - README content (first 3000 chars)
    - Key configuration files detected (CI, Docker, package managers, etc.)
    - Entry-point candidates
    - Dependency files found
    - Repository health summary (stars, issues, last push, contributors)

    Args:
        owner:  GitHub username or organisation name.
        repo:   Repository name.
        branch: Branch to analyse (defaults to the repo's default branch).
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        ref = branch or r.default_branch

        # ── 1. Fetch full tree ───────────────────────────────────────────────
        tree = r.get_git_tree(ref, recursive=True)
        all_items = tree.tree

        blob_items = [i for i in all_items if i.type == "blob"]
        tree_truncated = tree.raw_data.get("truncated", False)

        # ── 2. Language breakdown ────────────────────────────────────────────
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
            ext = Path(item.path).suffix.lower()
            # Special cases for extensionless config files
            name_lower = Path(item.path).name.lower()
            if name_lower == "dockerfile":
                lang = "Dockerfile"
            elif name_lower in ("makefile", "rakefile", "gemfile"):
                lang = name_lower.capitalize()
            elif ext in EXT_LANG:
                lang = EXT_LANG[ext]
            else:
                lang = "Other"

            lang_file_count[lang] += 1
            lang_byte_count[lang] += item.size or 0

        sorted_langs = sorted(
            lang_file_count.items(), key=lambda x: x[1], reverse=True
        )
        language_breakdown = [
            {
                "language":   lang,
                "files":      count,
                "total_bytes": lang_byte_count[lang],
            }
            for lang, count in sorted_langs
            if lang != "Other"
        ]

        # ── 3. Top-level directory structure ─────────────────────────────────
        top_level: dict[str, str] = {}
        for item in all_items:
            parts = item.path.split("/")
            name = parts[0]
            if name not in top_level:
                top_level[name] = "folder" if item.type == "tree" else "file"

        # ── 4. Detect key config / entry-point files ──────────────────────────
        KNOWN_CONFIGS = {
            # CI/CD
            ".github/workflows": "GitHub Actions CI/CD",
            ".gitlab-ci.yml":    "GitLab CI",
            "Jenkinsfile":       "Jenkins CI",
            ".circleci/config.yml": "CircleCI",
            "azure-pipelines.yml": "Azure Pipelines",
            # Containers
            "Dockerfile":        "Docker",
            "docker-compose.yml": "Docker Compose",
            "docker-compose.yaml": "Docker Compose",
            # Package managers
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
            # Infrastructure
            "terraform.tf":      "Terraform",
            "serverless.yml":    "Serverless Framework",
            "helm/":             "Helm Charts",
            "k8s/":              "Kubernetes Manifests",
            # Docs / meta
            "README.md":         "README (Markdown)",
            "README.rst":        "README (reStructuredText)",
            "CONTRIBUTING.md":   "Contributing Guide",
            "CHANGELOG.md":      "Changelog",
            "LICENSE":           "License File",
            ".env.example":      "Env Example",
        }

        all_paths_lower = {i.path.lower(): i.path for i in all_items}
        detected_configs: dict[str, str] = {}
        for pattern, label in KNOWN_CONFIGS.items():
            key = pattern.lower()
            if key in all_paths_lower:
                detected_configs[label] = all_paths_lower[key]

        # ── 5. Entry-point candidates ─────────────────────────────────────────
        ENTRY_CANDIDATES = [
            "main.py", "app.py", "server.py", "run.py", "cli.py", "manage.py",
            "index.js", "index.ts", "app.js", "server.js",
            "main.go", "main.rs", "main.java", "Program.cs",
            "Application.kt", "main.cpp",
        ]
        entry_points = [
            i.path
            for i in blob_items
            if Path(i.path).name in ENTRY_CANDIDATES
        ]

        # ── 6. README content ─────────────────────────────────────────────────
        readme_content = ""
        readme_keys = ["readme.md", "readme.rst", "readme.txt", "readme"]
        for key in readme_keys:
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

        # ── 7. Health summary ────────────────────────────────────────────────
        try:
            contributors_count = r.get_contributors().totalCount
        except Exception:
            contributors_count = "Unknown"

        health = {
            "stars":             r.stargazers_count,
            "forks":             r.forks_count,
            "open_issues":       r.open_issues_count,
            "watchers":          r.watchers_count,
            "last_push":         str(r.pushed_at),
            "created_at":        str(r.created_at),
            "contributors":      contributors_count,
            "has_wiki":          r.has_wiki,
            "has_pages":         r.has_pages,
            "archived":          r.archived,
            "fork":              r.fork,
            "primary_language":  r.language,
            "license":           r.license.name if r.license else "None",
        }

        # ── Assemble output ───────────────────────────────────────────────────
        total_files = len(blob_items)
        total_bytes  = sum(i.size or 0 for i in blob_items)

        output_parts = [
            f"{'═' * 70}",
            f"  DEEP ANALYSIS: {owner}/{repo}  @  {ref}",
            f"{'═' * 70}",
            f"\n📦 OVERVIEW",
            f"   Description : {r.description or 'No description'}",
            f"   Total files : {total_files}{' (tree truncated by GitHub)' if tree_truncated else ''}",
            f"   Total size  : {total_bytes:,} bytes ({r.size} KB reported by GitHub)",
            f"   URL         : {r.html_url}",
            f"\n📊 LANGUAGE BREAKDOWN\n{_fmt(language_breakdown)}",
            f"\n📁 TOP-LEVEL STRUCTURE\n{_fmt(top_level)}",
            f"\n⚙️  DETECTED TOOLING & CONFIGS\n{_fmt(detected_configs)}",
            f"\n🚀 ENTRY-POINT CANDIDATES\n{_fmt(entry_points)}",
            f"\n❤️  REPOSITORY HEALTH\n{_fmt(health)}",
        ]

        if readme_content:
            output_parts += [
                "\n📄 README PREVIEW",
                "─" * 60,
                readme_content,
            ]

        return "\n".join(output_parts)

    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error analyzing repo: {e}"


# ── Tool 13: get_file_url ────────────────────────────────────────────────────

@mcp.tool()
def get_file_url(
    owner: str,
    repo: str,
    path: str,
    branch: str = "",
    raw: bool = False,
) -> str:
    """
    Get the GitHub web or raw URL for any file in a repository.

    Useful when you need to share a link or download a file directly.

    Args:
        owner:  GitHub username or organisation name.
        repo:   Repository name.
        path:   File path relative to the repo root.
        branch: Branch name (defaults to the default branch).
        raw:    If True, return the raw.githubusercontent.com download URL.
    """
    try:
        g = get_github()
        r = g.get_repo(f"{owner}/{repo}")
        ref = branch or r.default_branch

        file_content = r.get_contents(path, ref=ref)
        if isinstance(file_content, list):
            return f'"{path}" is a directory, not a file.'

        if raw:
            raw_url = (
                f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
            )
            return f"Raw URL:\n{raw_url}"

        return (
            f"GitHub URL:\n{file_content.html_url}\n\n"
            f"Raw URL:\n"
            f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
        )
    except GithubException as e:
        return f"GitHub API error ({e.status}): {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
