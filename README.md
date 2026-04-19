# GitHub Repository Analyzer — MCP Server

> A **Model Context Protocol (MCP)** server written in Python that gives Claude deep access to any GitHub repository. Browse, analyze, and query repos through natural language — available as a hosted cloud service or run locally.

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
| 11 | `clone_repo` | Clone a repo to local disk — **local mode only** |
| 12 | `analyze_repo` | **Deep structural analysis**: language breakdown, entry points, tooling detection, README preview, health metrics |
| 13 | `get_file_url` | Get GitHub web URL and raw download URL for any file |

---

## Option 1 — Cloud Deployment (Vercel) ☁️

No installation required. Just add the hosted server to Claude as an MCP connector.

### Add to Claude.ai

1. Go to **Claude.ai → Settings → Connectors**
2. Click **Add MCP Server** and paste this URL:

```
https://git-hub-mcp.vercel.app/mcp
```

3. Give it a name like `GitHub Analyzer` and save
4. Start a conversation — Claude will ask for your GitHub PAT on the first tool call
5. If not asked you better paste the token at beginning of the conversation and tell Claude to use it for all subsequent tool calls for git hub access. 



> **Note:** The cloud version disables `clone_repo` because Vercel's serverless runtime has no `git` binary and a read-only filesystem. All 12 other tools work fully.

### Token handling

Each tool call requires your GitHub Personal Access Token via the `github_token` parameter. The server never stores or logs your token — it is used only for the duration of each request and masked from all error output.

---

## Option 2 — Deploy Your Own Vercel Instance 🚀

Deploy your own copy of this server to Vercel using the Vercel CLI. You get your own URL, full control, and free hosting on Vercel's serverless platform.

### Prerequisites

- A [Vercel account](https://vercel.com/signup) (free tier works)
- [Node.js](https://nodejs.org) installed (required for the Vercel CLI)
- The Vercel CLI installed:

```bash
npm install -g vercel
```

### Required files

Make sure these two files exist in your project root alongside `server.py`:

**`api/index.py`**
```python
from server import mcp

app = mcp.http_app()
```

**`vercel.json`**
```json
{
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ]
}
```

### Deploy to production

**1. Log in to Vercel**

```bash
vercel login
```

Follow the prompts to authenticate via GitHub, GitLab, or email.

**2. Navigate to your project folder**

```bash
cd path/to/github-mcp-server
```

**3. Deploy to production**

```bash
vercel --prod
```

Vercel will ask a few setup questions the first time:

```
? Set up and deploy "github-mcp-server"? → Y
? Which scope do you want to deploy to? → (select your account)
? Link to existing project? → N
? What's your project's name? → github-mcp-server
? In which directory is your code located? → ./
```

After a short build, you'll see:

```
✅  Production: https://github-mcp-server.vercel.app [ready]
```

**4. Your MCP endpoint is live**

Append `/mcp` to your deployment URL:

```
https://github-mcp-server.vercel.app/mcp
```

**5. Add to Claude.ai**

- Go to **Claude.ai → Settings → Connectors**
- Click **Add MCP Server**
- Paste your `/mcp` URL and save

> **No environment variables needed in the Vercel dashboard.** This server accepts tokens per request via the `github_token` parameter — nothing to configure on the Vercel side.

### Redeploy after changes

Every time you update `server.py`, just run:

```bash
vercel --prod
```

Vercel will rebuild and push the new version to the same URL instantly.

---

## Option 3 — Run Locally 🖥️

Use this if you want `clone_repo`, want to run privately without Vercel, or prefer to keep your token stored in `.env` rather than passing it per tool call.

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Git installed and on PATH (required for `clone_repo`)
- A GitHub Personal Access Token

### Setup

**1. Clone this repo**

```bash
git clone https://github.com/your-username/github-mcp-server.git
cd github-mcp-server
```

**2. Install dependencies**

```bash
uv sync
```

**3. Configure your GitHub token**


Edit `.env`:

```
GITHUB_TOKEN=ghp_yourRealTokenHere
```

> Create a token at: https://github.com/settings/personal-access-tokens
> Scopes: `repo` (private repos) or `public_repo` (public only)

**4. Switch to the local version of `server.py`**

The file ships with two versions of the server:

- **Top section** — async HTTP version for Vercel (active by default)
- **Bottom section** — stdio version for local/Claude Desktop (commented out by default)

To use locally:

- **Comment out** the top block (everything after `# ...vercel deployment...` down to `if __name__ == "__main__":`)
- **Uncomment** the large block at the bottom (the stdio version that reads from `.env`)

**5. Test the server**

```bash
uv run server.py
```

No output means it's waiting for MCP input — that's correct.

### Claude Desktop Configuration

Open:

```
1. Go to settings -> Developer -> Edit Config -> open claude_desktop_config.json file

```

Add this block (merge into `mcpServers` if the file already exists):

```json
{
  "mcpServers": {
    "github-analyzer": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "D:/path/to/github-mcp-server",
        "D:/path/to/github-mcp-server/server.py"
      ],
      "env": {
        "GITHUB_TOKEN": "ghp_yourRealTokenHere"
      }
    }
  }
}
```

> Use forward slashes `/` in paths even on Windows.

**Restart Claude Desktop** after saving.

---

## Example Prompts

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
List all open issues labeled "bug" in huggingface/transformers
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
github-mcp-server/
├── server.py                   # MCP server — all 13 tools (Vercel + local versions)
├── pyproject.toml              # uv project config & dependencies
├── .env.example                # Token template
├── .env                        # Your actual token (gitignored)
├── claude_desktop_config.json  # Config snippet for Claude Desktop
└── README.md
```

---

## Rate Limits

| Scenario | Requests/hour |
|----------|--------------|
| With Personal Access Token | 5,000 |
| GitHub Enterprise Cloud Users | upto 15,000 |


---

## Contributing

Contributions are welcome! This project is **MIT licensed** — fork it, extend it, ship it.

### Adding a new tool

1. Fork the repository and create a branch named `tool/your-tool-name`
2. Add your tool in `server.py` using the `@mcp.tool()` decorator
3. Follow the existing async pattern — include `github_token: str` as a parameter, use `anyio.to_thread.run_sync` for blocking GitHub API calls, and handle `GithubException` + generic exceptions
4. Add your tool to the features table in this README with a short one-line description
5. Open a PR — include what the tool does, which GitHub API endpoints it uses, and a sample output

### Ideas for new tools

- GitHub Releases & tags
- Repository traffic stats (views, clones)
- Code review comments on PRs
- GitHub Actions run history
- Dependency graph / dependents
- Repository discussions
- Starred repositories by user
- Webhooks list

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git` not found in `clone_repo` | Install Git from https://git-scm.com and restart your terminal |
| 401 / 403 errors | Check your `GITHUB_TOKEN` in `.env` or the Claude Desktop config |
| Rate limit exceeded | Add or rotate your PAT, or wait for the limit to reset |
| Tree truncated warning | Repo has >100k files; use the `path` filter in `list_repo_tree` |
| Server not appearing in Claude Desktop | Restart Claude Desktop; double-check paths in `claude_desktop_config.json` |
| `clone_repo` not available | This tool only works in local mode — see Option 3 above |

---

## License

[MIT](LICENSE) — free to use, modify, and distribute.