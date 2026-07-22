# QA Agents

A complete automated QA pipeline for Jira + Xray Cloud projects, built as Claude Code skills. One command generates test cases, another executes them in a real browser, and a third files structured bug tickets — all linked back to Xray automatically.

```
/qa-agent plan  →  /qa-agent run  →  /qa-agent bug
  (generate)         (execute)         (report)
```

---

## What's New

- **🔐 Microsoft SSO bypass.** Run mode authenticates through Microsoft Entra ID (Azure AD) automatically — email → password → number-match MFA → TOTP — and reuses the session across the whole run. See [SSO Authentication](#sso-authentication).
- **⚡ Orchestrator + worker architecture.** A power-model orchestrator keeps the judgment work and delegates mechanical work to cheaper worker models. Big token savings with a quality-preserving escalation path. See [Architecture](#architecture-orchestrator--workers).
- **📊 Silent self-assessment.** After every session the agent grades its own performance and files a structured report to the maintainer.

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

## ⚡ Install This Agent (instructions for an AI agent)

**If you are an AI agent (Claude Code, or similar) with access to this repository, follow these steps exactly to install the QA Agent for the user. Do not skip steps. Do not ask the user for any Xray credentials — the Xray connection is hosted and needs none.**

**Step 1 — Locate the repo.** You are either already inside the cloned `QA-Agents` repo, or you must clone it first:
```bash
git clone https://github.com/Franz-James-Kaba/QA-Agents.git
cd QA-Agents
```

**Step 2 — Copy the skills into the user's Claude Code skills directory.**

Mac/Linux:
```bash
mkdir -p ~/.claude/skills
cp -r skills/qa-agent skills/test-case-generator skills/manual-executor skills/bug-maester ~/.claude/skills/
```
Windows (PowerShell):
```powershell
foreach ($s in @("qa-agent","test-case-generator","manual-executor","bug-maester")) {
    xcopy /E /I "skills\$s" "$env:USERPROFILE\.claude\skills\$s"
}
```

**Step 3 — Write the MCP configuration.** Create or update `.claude/mcp.json` in the user's project root with **exactly** this content. The Xray server is hosted — use the live URL as-is and set no Xray credentials:
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

**Step 4 — Install runtime dependencies** (needed for run mode / execution):
```bash
pip install playwright pyotp
python -m playwright install chromium
```

**Step 5 (optional) — Connect Atlassian.** First ask the user how they run Claude:

- **Claude desktop app →** tell them to use the **built-in Atlassian connector** instead of setting anything manually: Settings → Connectors → Atlassian → Connect, and sign in. No credentials, no env vars, and the `jira` entry in `mcp.json` is not required. This is the recommended path for desktop users. **Skip the commands below.**
- **Terminal / CLI only →** set the Atlassian credentials as environment variables (ask the user for these two values):
```bash
# Mac/Linux
export JIRA_EMAIL="user@company.com"
export JIRA_API_TOKEN="user_atlassian_api_token"
```
```powershell
# Windows
[System.Environment]::SetEnvironmentVariable("JIRA_EMAIL", "user@company.com", "User")
[System.Environment]::SetEnvironmentVariable("JIRA_API_TOKEN", "user_atlassian_api_token", "User")
```

**Step 6 — Tell the user to restart Claude Code** so the skills and MCP servers load.

**Step 7 — Verify.** After restart, confirm the skill responds to `/qa-agent` and that `mcp__jira__*` and `mcp__xray__*` tools are available. The user does **not** need Xray API keys — if anything asks for `XRAY_CLIENT_ID` or `XRAY_CLIENT_SECRET`, that is a hosted-server issue for the maintainer, not a user action (see [Troubleshooting](#troubleshooting)).

---

## Prerequisites (for manual install)

| Requirement | Version | Notes |
|-------------|---------|-------|
| [Claude Code](https://claude.ai/download) | Latest | Runs these skills |
| Python | 3.10+ | `python --version` — for Playwright / SSO |
| Node.js + npm | 18+ | `npm --version` — for the Jira MCP |
| Jira + Xray Cloud project | — | Your project must have Xray Cloud installed |
| Atlassian access | — | **Desktop app:** the built-in Atlassian connector (no token). **Terminal only:** an API token from [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |

> **You do NOT need Xray API keys.** The Xray connection uses a shared hosted server that already holds its own credentials.
> **Desktop app users** connect Atlassian through the app's built-in connector — no token required.

---

## Manual Install (step by step)

Follow these in order, then restart Claude Code.

### 1. Clone the repo
```bash
git clone https://github.com/Franz-James-Kaba/QA-Agents.git
cd QA-Agents
```

### 2. Install the skills

Mac/Linux:
```bash
mkdir -p ~/.claude/skills
cp -r skills/qa-agent skills/test-case-generator skills/manual-executor skills/bug-maester ~/.claude/skills/
```
Windows (PowerShell):
```powershell
foreach ($s in @("qa-agent","test-case-generator","manual-executor","bug-maester")) {
    xcopy /E /I "skills\$s" "$env:USERPROFILE\.claude\skills\$s"
}
```

### 3. Connect the MCP servers

Create or update `.claude/mcp.json` in your project root with both servers. **Copy this exactly** — the Xray server is hosted, so there are no Xray credentials to set:
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
On first use, Claude Code prompts you to authenticate the Jira MCP with your Atlassian account. The Xray MCP connects with no prompt.

### 4. Connect Atlassian (optional — pick one)

**Using the Claude desktop app?** Use the built-in Atlassian connector instead of any manual setup: **Settings → Connectors → Atlassian → Connect** and sign in. No credentials or env vars needed, and you can skip the `jira` entry in `mcp.json`. This is the recommended path.

**Using the terminal / CLI only?** Provide your Atlassian email and API token as environment variables:

Mac/Linux (add to `~/.bashrc` or `~/.zshrc`):
```bash
export JIRA_EMAIL="your@email.com"
export JIRA_API_TOKEN="your_atlassian_api_token"
```
Windows (PowerShell):
```powershell
[System.Environment]::SetEnvironmentVariable("JIRA_EMAIL", "your@email.com", "User")
[System.Environment]::SetEnvironmentVariable("JIRA_API_TOKEN", "your_atlassian_api_token", "User")
```

### 5. Install runtime dependencies (for run mode)
```bash
pip install playwright pyotp
python -m playwright install chromium
```

### 6. Restart Claude Code

Skills and MCP servers load at startup. After restart, `/qa-agent` is ready.

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
```

For apps behind Microsoft login, add `--sso` (or let run mode auto-detect the redirect). See [SSO Authentication](#sso-authentication).

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

Many enterprise apps sit behind Microsoft Entra ID (Azure AD) with MFA — a wall that normally breaks browser automation. Run mode handles it with a bundled, verified script (`skills/qa-agent/scripts/ms_sso_auth.py`).

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

It enters the email and password, clicks **"I can't use my Microsoft Authenticator app right now"** on the number-match screen, selects **"Use a verification code"**, generates the current TOTP from your test account's secret, and saves the authenticated session. If the session expires mid-run, it re-authenticates automatically.

### Setup (only if you test SSO-protected apps)

Set three environment variables for your **test account** (never a personal account):

Mac/Linux:
```bash
export TEST_EMAIL="testuser@yourcompany.com"
export TEST_PASSWORD="your_test_password"
export TEST_TOTP_SECRET="base32secretfromauthenticator"
```
Windows (PowerShell):
```powershell
[System.Environment]::SetEnvironmentVariable("TEST_EMAIL", "testuser@yourcompany.com", "User")
[System.Environment]::SetEnvironmentVariable("TEST_PASSWORD", "your_test_password", "User")
[System.Environment]::SetEnvironmentVariable("TEST_TOTP_SECRET", "base32secretfromauthenticator", "User")
```

> **`TEST_TOTP_SECRET`** is the Base32 seed shown when you set up the authenticator for the test account. The script uses `pyotp` — RFC 6238, identical to Google Authenticator.

### Verify it standalone
```bash
python skills/qa-agent/scripts/ms_sso_auth.py \
  --url https://your-app --output output/auth/storage_state.json
# add --headed to watch the browser
```
A successful run saves ~22 cookies plus app localStorage to `storage_state.json`. Full details and troubleshooting: `skills/qa-agent/references/run-sso-profile.md`.

---

## Architecture: Orchestrator + Workers

`qa-agent` runs as a **two-tier system** for token efficiency. The dispatcher is the **orchestrator** (run it on a power model like Opus); it keeps the judgment work and delegates everything mechanical to cheaper **worker models (Sonnet)**.

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

**Quality is preserved by an escalation path:** a worker that hits a low-confidence decision flags `needs_orchestrator_review` instead of guessing, and the orchestrator resolves just those cases on the power model.

> **To get the full benefit**, run the qa-agent session on Opus. Delegation happens automatically via the Agent tool's `model` parameter. Details: `skills/qa-agent/references/orchestrator-protocol.md`.

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
Output written to `output/screenshots/{RUN_ID}/` and `output/results/{RUN_ID}/` (`results.json`, `run-report.md`, `pw_runner.py`).

### bug-maester
Standalone bug filer with an audit pass that repairs any existing open bug descriptions before creating new ones.
```
report a bug: description here
/bug-maester TBL-217        ← from a specific Test Execution
/bug-maester all            ← all executions in the project
```

---

## Troubleshooting

**Skills not showing up in Claude Code**
→ Check the skill was copied to `~/.claude/skills/<skill-name>/SKILL.md` and restart Claude Code.

**`mcp__xray__*` tools unavailable**
→ Verify the `xray` entry in `.claude/mcp.json` is exactly `{ "type": "sse", "url": "https://xray-mcp-server.vercel.app/sse" }` and restart Claude Code.

**Prompted to set `XRAY_CLIENT_ID` / `XRAY_CLIENT_SECRET`**
→ You should never need these. The hosted Xray server holds its own credentials. If you see this, either (a) your `xray` entry is pointing at a local/self-hosted server instead of the hosted URL above — fix the config — or (b) the hosted server has lost its credentials and the **maintainer** needs to restore them. It is never a user action.

**`mcp__jira__*` tools unavailable**
→ Verify the `jira` entry is in `.claude/mcp.json`. Run `npx -y @modelcontextprotocol/server-rovo` manually to confirm npm can reach it.

**Playwright errors on form filling**
→ The generic runner uses label-based locators. If the app uses placeholder text instead of `<label>` elements, override with `get_by_placeholder()` or `#id` selectors. See `run-mode.md` in the `qa-agent` references.

**Xray SSE connection timeout**
→ Transient hosted-server cold start; retry. If it persists, contact the maintainer.

---

## Maintainers

The Xray MCP server source and its Vercel deployment live in this repo: `api/index.py` (the hosted SSE server) and `xray-mcp/server.py` (a local stdio variant), with `vercel.json` for the deployment. Hosted credentials (`XRAY_CLIENT_ID` / `XRAY_CLIENT_SECRET`) are stored as Vercel environment variables on the deployment — end users never set these. To rotate them: `vercel login`, then update the Vercel project's environment variables (Production) and run `vercel --prod` to redeploy.
