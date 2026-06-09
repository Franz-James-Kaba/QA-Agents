# QA Agents — Onboarding Guide

Welcome. This guide gets you from zero to running your first automated QA session in Claude Code.

---

## What you're installing

Four Claude Code skills that automate the QA loop:

| Skill | What it does |
|-------|--------------|
| `qa-agent` | **Primary skill.** Plan test cases, execute them in a browser, file bugs — all in one skill with three modes. |
| `test-case-generator` | Standalone TC generator |
| `manual-executor` | Standalone Playwright test runner |
| `bug-maester` | Standalone bug filer |

Start with `qa-agent`. The others are specialist tools for when you need finer control.

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/Franz-James-Kaba/QA-Agents.git
cd QA-Agents
```

---

## Step 2 — Install the qa-agent skill

**Mac/Linux:**
```bash
cp -r skills/qa-agent ~/.claude/skills/
```

**Windows (PowerShell):**
```powershell
xcopy /E /I skills\qa-agent "$env:USERPROFILE\.claude\skills\qa-agent"
```

To install all skills at once:

**Mac/Linux:**
```bash
cp -r skills/qa-agent skills/test-case-generator skills/manual-executor skills/bug-maester ~/.claude/skills/
```

**Windows:**
```powershell
foreach ($s in @("qa-agent","test-case-generator","manual-executor","bug-maester")) {
    xcopy /E /I "skills\$s" "$env:USERPROFILE\.claude\skills\$s"
}
```

---

## Step 3 — Connect the MCP servers

Create (or update) `.claude/mcp.json` in your project root:

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

> The Xray MCP server at `https://xray-mcp-server.vercel.app` is pre-deployed with shared credentials. No local Python server needed.

**Requires Node.js** for the Jira MCP (`npm --version` to check).

---

## Step 4 — Set your Atlassian credentials

The skills need your email and API token to create Jira issues.

Get your API token at: https://id.atlassian.com/manage-profile/security/api-tokens

**Mac/Linux** (`~/.bashrc` or `~/.zshrc`):
```bash
export JIRA_EMAIL="you@yourcompany.com"
export JIRA_API_TOKEN="your_token_here"
```

**Windows (PowerShell — persists across sessions):**
```powershell
[System.Environment]::SetEnvironmentVariable("JIRA_EMAIL", "you@yourcompany.com", "User")
[System.Environment]::SetEnvironmentVariable("JIRA_API_TOKEN", "your_token_here", "User")
```

---

## Step 5 — Install Playwright

Required for `qa-agent` run mode and `manual-executor`:

```bash
pip install playwright
python -m playwright install chromium
```

---

## Step 6 — Restart Claude Code

Skills and MCP servers are loaded at startup. Restart after steps 2 and 3.

---

## Step 7 — Run your first session

Open Claude Code in your project folder and try:

```
/plan TBL-123
```

Replace `TBL-123` with a real story key from your Jira board. The skill will:
1. Fetch the story description and acceptance criteria
2. Ask a few clarifying questions about the real implementation
3. Generate positive + negative test cases
4. Create a full Xray hierarchy (Test Cases → Test Set → Test Plan → Test Execution)

Then execute:
```
/run --from-xray TBL-123 --url http://your-staging-url --env staging
```

Then file bugs for any failures:
```
/bug TBL-611
```

---

## Quick reference

| Command | What happens |
|---------|-------------|
| `/plan TBL-123` | Generate TCs for story TBL-123 |
| `/run --from-xray TBL-123 --url <url> --env staging` | Execute all TCs against a URL |
| `/bug TBL-611` | File bugs for failures in Test Execution TBL-611 |
| `/bug all` | File bugs for all open failures in the project |
| `report a bug: <description>` | File a single bug from plain English |

---

## Troubleshooting

**Skills not appearing**
→ Confirm `~/.claude/skills/qa-agent/SKILL.md` exists, then restart Claude Code.

**`mcp__xray__*` tools not available**
→ Check `.claude/mcp.json` has the `xray` entry and restart Claude Code.

**`mcp__jira__*` tools not available**
→ Check the `jira` entry is in `.claude/mcp.json`. Confirm Node.js is installed: `node --version`.

**Browser automation errors**
→ Confirm Playwright is installed: `python -m playwright install chromium`

For more detail, see [README.md](README.md).
