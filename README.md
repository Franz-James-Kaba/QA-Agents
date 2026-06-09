# QA Agents

A complete automated QA pipeline for Jira + Xray Cloud projects, built as Claude Code skills. One command generates test cases, another executes them in a real browser, and a third files structured bug tickets — all linked back to Xray automatically.

```
/qa-agent plan  →  /qa-agent run  →  /qa-agent bug
  (generate)         (execute)         (report)
```

---

## Skills

| Skill | Invoke with | What it does |
|-------|------------|--------------|
| **`qa-agent`** | `/qa-agent`, `/plan`, `/run`, `/bug` | All-in-one: generate TCs, execute against staging, file bugs. The primary skill. |
| `test-case-generator` | "generate test cases" | Generates Xray test hierarchy from sprint stories |
| `manual-executor` | "execute test cases" | Runs TCs via Playwright with vision-based pass/fail |
| `bug-maester` | "report a bug" | Files 6-section Bug tickets from failures or plain English |

> **New users:** Start with `qa-agent`. It covers the full workflow in one skill.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| [Claude Code](https://claude.ai/download) | Latest | The desktop app that runs these skills |
| Python | 3.10+ | `python --version` |
| Node.js + npm | 18+ | Required for the Jira MCP (`npm --version`) |
| Jira + Xray Cloud | — | Project must have Xray Cloud installed |
| Atlassian API token | — | Generate at [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |
| Xray API key pair | — | Generate at Xray → Global Settings → API Keys |

---

## Quick Install (5 minutes)

```bash
# 1. Clone this repo
git clone https://github.com/Franz-James-Kaba/QA-Agents.git
cd QA-Agents

# 2. Copy the qa-agent skill into Claude Code
#    Mac/Linux:
cp -r skills/qa-agent ~/.claude/skills/
#    Windows (PowerShell):
xcopy /E /I skills\qa-agent "$env:USERPROFILE\.claude\skills\qa-agent"

# 3. Install Playwright (needed for run mode)
pip install playwright
python -m playwright install chromium
```

Then follow the **Connect MCP Servers** and **Set Environment Variables** steps below, and restart Claude Code.

---

## Connect MCP Servers

Both the **Jira MCP** and the **Xray MCP** must be connected for the skills to work.

### 1 — Jira MCP

Add to your project's `.claude/mcp.json` (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "jira": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-rovo"]
    }
  }
}
```

On first use, Claude Code will prompt you to authenticate with your Atlassian account.

### 2 — Xray MCP (hosted — recommended)

A shared Xray MCP server is already deployed at `https://xray-mcp-server.vercel.app`. Add it alongside jira in your `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "jira": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-rovo"]
    },
    "xray": {
      "type": "sse",
      "url": "https://xray-mcp-server.vercel.app/sse"
    }
  }
}
```

> This server is pre-configured with shared Xray credentials. If your project uses different Xray credentials, see [Run Your Own Xray MCP Server](#run-your-own-xray-mcp-server) below.

### 3 — Restart Claude Code

Changes to `mcp.json` require a restart to take effect.

---

## Set Environment Variables

The skills need your Atlassian credentials to create Jira issues and read sprint data.

**Mac/Linux** — add to `~/.bashrc` or `~/.zshrc`:
```bash
export JIRA_EMAIL="your@email.com"
export JIRA_API_TOKEN="your_atlassian_api_token"
```

**Windows** — add as system environment variables (PowerShell):
```powershell
[System.Environment]::SetEnvironmentVariable("JIRA_EMAIL", "your@email.com", "User")
[System.Environment]::SetEnvironmentVariable("JIRA_API_TOKEN", "your_atlassian_api_token", "User")
```

Or set them in your project's `.claude/mcp.json` under an `env` block if you prefer project-scoped credentials.

---

## Using qa-agent

`qa-agent` has three modes triggered by natural language or slash commands.

### Plan mode — generate test cases

Reads stories from the active sprint, asks clarifying questions about the real implementation, then creates a full Xray hierarchy: Test Cases → Test Set → Test Plan → Test Execution.

```
/plan TBL-123
generate test cases for the active sprint
create test cases for TBL-456
```

### Run mode — execute tests

Launches a Playwright browser, runs each TC step by step with before/after screenshots, assesses pass/fail using Claude vision, and uploads results to the Xray Test Execution.

```
/run --from-xray TBL-123 --url http://your-staging-url --env staging
execute tests for TBL-456 against http://staging.example.com
run manual tests
```

### Bug mode — file bug tickets

Files structured 6-section Bug tickets. Can take a plain-English description or auto-fill from a failed Xray Test Execution.

```
/bug
report a bug: the login button stays disabled when the form is valid
/bug TBL-611          ← auto-fill from a specific Test Execution
/bug all              ← file bugs for all failures in the project
```

### Full workflow example

```
1. /plan TBL-123
   → 12 test cases created in Xray, linked to Test Set + Test Plan + Test Execution

2. /run --from-xray TBL-123 --url http://staging.example.com --env staging
   → Browser runs all 12 TCs, screenshots every step, results uploaded to Xray

3. /bug TBL-611
   → Bug tickets filed for each failure, linked to failing TCs and the story
```

---

## Other Skills

### test-case-generator

Standalone TC generator — same as `qa-agent` plan mode but as a separate skill.

```
generate test cases
create test plan for active sprint
```

### manual-executor

Standalone test runner with extended options for parallel sessions and account provisioning.

```
/manual-executor --from-xray TBL-XXX --url http://staging --env staging
/manual-executor --input output/test-cases/TBL-XXX.json --url http://localhost:4200
/manual-executor --from-xray TBL-XXX --url http://... --skip-to TBL-YYY
```

Output written to:
```
output/
  screenshots/{RUN_ID}/     ← PNG per step
  results/{RUN_ID}/
    results.json
    run-report.md
    pw_runner.py
```

### bug-maester

Standalone bug filer with an audit pass that repairs any existing open bug descriptions before creating new ones.

```
report a bug: description here
/bug-maester TBL-217        ← from a specific Test Execution
/bug-maester all            ← all executions in the project
```

---

## Install All Skills

To install all four skills at once:

**Mac/Linux:**
```bash
cp -r skills/qa-agent ~/.claude/skills/
cp -r skills/test-case-generator ~/.claude/skills/
cp -r skills/manual-executor ~/.claude/skills/
cp -r skills/bug-maester ~/.claude/skills/
```

**Windows (PowerShell):**
```powershell
foreach ($skill in @("qa-agent","test-case-generator","manual-executor","bug-maester")) {
    xcopy /E /I "skills\$skill" "$env:USERPROFILE\.claude\skills\$skill"
}
```

Restart Claude Code after copying.

---

## Run Your Own Xray MCP Server

If your project uses different Xray credentials than the shared server, you can deploy your own instance.

### Option A — Local (stdio)

Copy `xray-mcp/server.py` to your project root and update `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "xray": {
      "command": "python",
      "args": ["xray-mcp/server.py"],
      "env": {
        "XRAY_CLIENT_ID": "your_client_id",
        "XRAY_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

Install the dependency: `pip install mcp`

### Option B — Deploy to Vercel

1. Install Vercel CLI: `npm i -g vercel`
2. Deploy: `vercel --prod`
3. Set secrets:
   ```bash
   vercel env add XRAY_CLIENT_ID
   vercel env add XRAY_CLIENT_SECRET
   vercel --prod
   ```
4. Update your `mcp.json` with the new URL:
   ```json
   { "mcpServers": { "xray": { "type": "sse", "url": "https://your-project.vercel.app/sse" } } }
   ```

### Xray MCP tools available

| Tool | What it does |
|------|--------------|
| `authenticate` | Verify credentials, return token TTL |
| `add_test_step` / `update_test_step` / `remove_test_step` | Manage steps on a Test issue |
| `get_test_steps` | Read all steps on a Test issue |
| `get_test_runs` | Fetch all runs (with run IDs) from a Test Execution |
| `update_test_run_status` | Set PASS/FAIL/TODO/EXECUTING/ABORTED on a run |
| `get_test_execution_failures` | Read failed results from a Test Execution |
| `add_tests_to_test_set/plan/execution` | Link Tests into Xray artefacts |
| `add_test_executions_to_test_plan` | Link Executions into a Test Plan |

---

## Troubleshooting

**Skills not showing up in Claude Code**
→ Check the skill was copied to `~/.claude/skills/<skill-name>/SKILL.md` and restart Claude Code.

**`mcp__xray__*` tools unavailable**
→ Verify the `xray` entry is in your `.claude/mcp.json` and Claude Code was restarted after the change.

**`mcp__jira__*` tools unavailable**
→ Verify the `jira` entry is in `.claude/mcp.json`. Run `npx -y @modelcontextprotocol/server-rovo` manually to confirm npm can reach it.

**Playwright errors on form filling**
→ The generic runner uses label-based locators. If the app uses placeholder text instead of `<label>` elements, override with `get_by_placeholder()` or `#id` selectors. See `run-mode.md` in the `qa-agent` references for details.

**Xray SSE connection timeout**
→ Vercel Hobby plan has a 10s function timeout. Upgrade to Pro (60s) or use the local stdio option.
