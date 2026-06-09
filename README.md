# QA Agents — Claude Code Skills

Three Claude Code skills that form a complete automated QA pipeline for Jira + Xray Cloud projects.

```
test-case-generator  →  manual-executor  →  bug-maester
     (generate)            (execute)           (report)
```

## Skills

| Skill | Trigger phrase | What it does |
|-------|---------------|--------------|
| `test-case-generator` | "generate test cases" | Generates full Xray test hierarchy (TCs, Test Set, Test Plan, Test Execution) from sprint stories |
| `manual-executor` | "execute test cases" | Runs TCs via Playwright, screenshots every step, vision pass/fail, auto-provisions staging accounts |
| `bug-maester` | "report a bug" | Files structured 6-section Bug tickets from Xray failures or natural language |

## Installation

1. **Copy skill files** to your Claude skills directory:
   ```
   ~/.claude/skills/manual-executor/SKILL.md
   ~/.claude/skills/bug-maester/SKILL.md
   ~/.claude/skills/test-case-generator/SKILL.md
   ```

2. **Connect the Xray MCP server** — choose local or remote:

   **Option A — Local (stdio, per-project)**
   Copy `xray-mcp/server.py` to your project root, then add to `.claude/mcp.json`:
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

   **Option B — Remote via Vercel (SSE, shared across team)**
   Deploy once, connect from any machine — see [Vercel Deployment](#vercel-deployment) below.
   Then add to `~/.claude/mcp.json`:
   ```json
   {
     "mcpServers": {
       "xray": {
         "type": "sse",
         "url": "https://your-deployment.vercel.app/sse"
       }
     }
   }
   ```

3. **Set environment variables:**
   ```
   JIRA_EMAIL=your@email.com
   JIRA_API_TOKEN=your_atlassian_api_token
   ```

4. **Install Playwright** (for `manual-executor`):
   ```bash
   pip install playwright
   python -m playwright install chromium
   ```

See [ONBOARDING.md](ONBOARDING.md) for full usage details.

---

## Vercel Deployment

The `api/index.py` file is a Starlette ASGI app that serves the same 12 Xray tools over SSE transport, making the MCP server accessible remotely without running anything locally.

### Prerequisites
- [Vercel CLI](https://vercel.com/docs/cli): `npm i -g vercel`
- Xray Cloud API key pair from [Xray Global Settings → API Keys](https://docs.getxray.app/display/XRAYCLOUD/Global+Settings%3A+API+Keys)

### Steps

1. **Install Python dependencies locally** (for testing):
   ```bash
   pip install -r requirements.txt
   ```

2. **Deploy to Vercel:**
   ```bash
   vercel --prod
   ```
   On first run, Vercel will prompt you to link or create a project.

3. **Set environment variables** in the Vercel dashboard (or via CLI):
   ```bash
   vercel env add XRAY_CLIENT_ID
   vercel env add XRAY_CLIENT_SECRET
   ```
   Or set them at `https://vercel.com/<your-team>/<project>/settings/environment-variables`.

4. **Redeploy** after setting env vars:
   ```bash
   vercel --prod
   ```

5. **Connect Claude Code** — add to `~/.claude/mcp.json` (user-level, works in any project):
   ```json
   {
     "mcpServers": {
       "xray": {
         "type": "sse",
         "url": "https://your-deployment.vercel.app/sse"
       }
     }
   }
   ```

### MCP endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/sse` | Client connects here — establishes the SSE stream |
| `POST` | `/messages/` | Client sends tool call messages here |

### Tools exposed

| Tool | What it does |
|------|--------------|
| `authenticate` | Verify credentials, return token TTL |
| `add_test_step` | Add a step to a Test issue |
| `update_test_step` | Edit an existing step by ID |
| `remove_test_step` | Delete a step by ID |
| `get_test_steps` | Read all steps on a Test issue |
| `get_test_runs` | Fetch all test runs (with run IDs) from a Test Execution |
| `update_test_run_status` | Set PASS/FAIL/TODO/EXECUTING/ABORTED on a test run |
| `get_test_execution_failures` | Read failed results from a Test Execution |
| `add_tests_to_test_set` | Link Tests into a Test Set |
| `add_tests_to_test_execution` | Link Tests into a Test Execution |
| `add_tests_to_test_plan` | Link Tests into a Test Plan |
| `add_test_executions_to_test_plan` | Link Executions into a Test Plan |

> **Note on Vercel timeouts:** Hobby plan functions time out at 10s; Pro plan at 60s. All Xray GraphQL calls complete well within these limits. The SSE connection itself is re-established per tool invocation by the MCP client.
