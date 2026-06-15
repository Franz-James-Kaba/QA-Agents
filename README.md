# QA Agents

A complete automated QA pipeline for Jira + Xray Cloud projects, built as Claude Code skills. One command generates test cases, another executes them in a real browser, and a third files structured bug tickets — all linked back to Xray automatically.

```
/qa-agent plan  →  /qa-agent run  →  /qa-agent bug
  (generate)         (execute)         (report)
```

---

## What's New

- **🔐 Microsoft SSO bypass.** Run mode now authenticates through Microsoft Entra ID (Azure AD) automatically — email → password → number-match MFA → TOTP — and reuses the session across the whole run. No more manual login, no per-test-case auth. See [SSO Authentication](#sso-authentication).
- **⚡ Orchestrator + worker architecture.** The skill runs as a two-tier system: a **power model (Opus) orchestrator** keeps the judgment work and delegates all mechanical, parallelizable work to cheaper **Sonnet workers**. Big token savings with a quality-preserving escalation path. See [Architecture](#architecture-orchestrator--workers).
- **📊 Silent self-assessment.** After every session the agent grades its own performance against an objective rubric and files a structured report to the maintainer — a continuous quality loop.

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
/run --from-xray TBL-123 --url https://app.example.com --sso     ← Microsoft SSO apps
execute tests for TBL-456 against http://staging.example.com
run manual tests
```

For apps behind Microsoft login, add `--sso` (or just let run mode auto-detect the redirect). See [SSO Authentication](#sso-authentication).

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

## SSO Authentication

Many enterprise apps sit behind Microsoft Entra ID (Azure AD) with MFA — a wall that normally breaks browser automation. Run mode handles it with a bundled, battle-tested script (`skills/qa-agent/scripts/ms_sso_auth.py`).

### How it works

```
/run --from-xray TBL-123 --url https://your-app --sso
        │
   detects Microsoft redirect (or you pass --sso)
        │
   authenticates ONCE:
     email → password → number-match MFA bypass → TOTP code → save session
        │
   every test case reuses output/auth/storage_state.json
   (auth never repeats per test — zero per-TC overhead)
```

The full flow is automated: it enters the email and password, clicks **"I can't use my Microsoft Authenticator app right now"** on the number-match screen, selects **"Use a verification code"**, generates the current TOTP from your test account's secret, and saves the authenticated browser session. If the session expires mid-run, it re-authenticates automatically.

### Setup

Set three environment variables for your **test account** (never a personal account):

**Mac/Linux:**
```bash
export TEST_EMAIL="testuser@yourcompany.com"
export TEST_PASSWORD="your_test_password"
export TEST_TOTP_SECRET="base32secretfromauthenticator"
```

**Windows (PowerShell):**
```powershell
[System.Environment]::SetEnvironmentVariable("TEST_EMAIL", "testuser@yourcompany.com", "User")
[System.Environment]::SetEnvironmentVariable("TEST_PASSWORD", "your_test_password", "User")
[System.Environment]::SetEnvironmentVariable("TEST_TOTP_SECRET", "base32secretfromauthenticator", "User")
```

> **`TEST_TOTP_SECRET`** is the Base32 seed shown when you set up the authenticator for the test account (the same value an `otp.secret` config would hold). The script uses `pyotp` — RFC 6238, identical to Google Authenticator / `com.warrenstrange:googleauth`.

Install the dependency:
```bash
pip install pyotp
```

### Run it standalone (to verify)

```bash
python skills/qa-agent/scripts/ms_sso_auth.py \
  --url https://your-app --output output/auth/storage_state.json
# add --headed to watch the browser
```

A successful run saves ~22 cookies plus app localStorage to `storage_state.json`. Full details and troubleshooting: `skills/qa-agent/references/run-sso-profile.md`.

---

## Architecture: Orchestrator + Workers

`qa-agent` runs as a **two-tier system** for token efficiency. The dispatcher is the **orchestrator** (run it on a power model like Opus); it keeps the judgment work and delegates everything mechanical to cheaper **Sonnet workers**.

```
┌────────────────────────────────────────────────────────┐
│  ORCHESTRATOR  (Opus)                                    │
│  judgment · synthesis · user dialogue · final decisions  │
└───────────┬───────────────┬───────────────┬────────────┘
            ▼               ▼               ▼
      [Sonnet worker] [Sonnet worker] [Sonnet worker]
       one story /      mechanical,     returns
       role / bug       self-contained  structured output
```

| Mode | Orchestrator keeps | Sonnet worker does (1 per unit, parallel) |
|------|--------------------|-------------------------------------------|
| **plan** | clarity scoring, clarifying dialogue, coverage strategy | writes the TC steps + ADF and creates Xray artefacts for one story |
| **run** | TC resolution, SSO pre-auth, result merge, early-abort | executes one role's TCs in the browser, returns raw results |
| **bug** | audit, dedupe guard, severity, which bugs to file | writes + links + transitions one 6-section bug ticket |

**Why it saves tokens:** the bulk of output (dozens of TC steps, long bug descriptions, many execution steps) is mechanical. Opus costs ~5× Sonnet per token, so moving that volume to Sonnet while reserving Opus for high-leverage judgment is where the savings come from.

**Quality is preserved by an escalation path:** a worker that hits a low-confidence decision (an ambiguous screenshot, a contradicting acceptance criterion) flags `needs_orchestrator_review` instead of guessing, and the orchestrator resolves just those cases on the power model. The easy 90% stays on Sonnet; the hard 10% gets Opus judgment.

> **To get the full benefit**, run the qa-agent session on Opus. Worker delegation happens automatically via the Agent tool's `model` parameter. Details: `skills/qa-agent/references/orchestrator-protocol.md`.

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
