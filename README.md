# GitHub Repository Analyzer — MCP Server

> A **Model Context Protocol (MCP)** server written in Python that gives Claude Desktop deep access to any GitHub repository. Browse, analyze, clone, and query repos through natural language.

---

## Features — 13 Tools

| # | Tool | What it does |
|---|------|-------------|
| 1 | `get_repo_info` | Metadata: stars, forks, language, license, topics, timestamps |
| 2 | `list_repo_tree` | Full recursive file/folder tree (filter by path or branch) |
| 3 | `read_file` | Read any file's content (binary detection, auto-truncation) |
| 4 | `search_code` | GitHub code search inside a repo |
| 5 | `get_commits` | Commit history (filter by branch or file path) |
| 6 | `get_branches` | All branches with SHA and protection status |
| 7 | `get_contributors` | Top contributors ranked by commit count |
| 8 | `get_issues` | Issues (open/closed, filter by label) |
| 9 | `get_pull_requests` | PRs (open/closed/all) |
| 10 | `compare_branches` | Diff two branches/commits: ahead/behind, files changed |
| 11 | `clone_repo` | Clone a repo to local disk (supports private repos via token) |
| 12 | `analyze_repo` | **Deep structural analysis**: language breakdown, entry points, tooling detection, README preview, health metrics |
| 13 | `get_file_url` | Get GitHub web URL and raw download URL for any file |

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Git installed and on PATH (required for `clone_repo`)
- A GitHub Personal Access Token (strongly recommended)

---

## Setup

### 1. Clone / open this project

```powershell
cd "D:\LLMOPS_Projects\Github MCP"
```

### 2. Install dependencies

```powershell
uv sync
```

### 3. Configure your GitHub token

Create a `.env` file in the project root:

```powershell
copy .env.example .env
```

Edit `.env` and replace the placeholder:

```
GITHUB_TOKEN=ghp_yourRealTokenHere
```

> **Why?** Without a token you're limited to 60 GitHub API requests/hour.
> With a token you get 5,000/hour. Private repos always need a token.
>
> Create a token at: https://github.com/settings/tokens  
> Scopes: `repo` (private) or `public_repo` (public only)

### 4. Test the server manually

```powershell
uv run server.py
```

You should see the MCP server start with stdio transport (no output = waiting for input — that's correct).

---

## Claude Desktop Configuration

Open or create the Claude Desktop config file:

```
%APPDATA%\Claude\claude_desktop_config.json
```

Add this (or merge the `mcpServers` block if the file already exists):

```json
{
  "mcpServers": {
    "github-analyzer": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "D:/LLMOPS_Projects/Github MCP",
        "D:/LLMOPS_Projects/Github MCP/server.py"
      ],
      "env": {
        "GITHUB_TOKEN": "ghp_yourRealTokenHere"
      }
    }
  }
}
```

> **Tip**: Use forward slashes `/` in the paths even on Windows — Claude Desktop handles them correctly.

**Restart Claude Desktop** after saving.

---

## Example Prompts in Claude

Once connected, try:

```
Analyze the repository microsoft/vscode
```
```
Read the file src/main.py in torvalds/linux on the master branch
```
```
Search for "def forward" in pytorch/pytorch
```
```
List all open issues in huggingface/transformers
```
```
Clone the repo langchain-ai/langchain to D:/projects/langchain
```
```
Compare main and develop branches in facebook/react
```
```
Who are the top 5 contributors to tensorflow/tensorflow?
```

---

## Project Structure

```
Github MCP/
├── server.py                  # MCP server — all 13 tools
├── pyproject.toml             # uv project config & dependencies
├── .env.example               # Token template
├── .env                       # Your actual token (gitignored)
├── claude_desktop_config.json # Config snippet for Claude Desktop
└── README.md
```

---

## Rate Limits

| Scenario | Requests/hour |
|----------|--------------|
| No token (anonymous) | 60 |
| With Personal Access Token | 5,000 |
| Code search (no token) | Blocked |
| Code search (with token) | 30/min |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git` not found in `clone_repo` | Install Git from https://git-scm.com and restart your terminal |
| 401 / 403 errors | Check your `GITHUB_TOKEN` in `.env` or the Claude Desktop config |
| Rate limit exceeded | Add a token or wait for the limit to reset |
| Tree truncated warning | Repo has >100k files; use `path` filter in `list_repo_tree` |
| Server not appearing in Claude | Restart Claude Desktop; check paths in `claude_desktop_config.json` |
