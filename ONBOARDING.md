# QA Automation Skills — PingMaster

Three Claude Code skills that form a complete automated QA pipeline:
**generate → execute → report bugs**.

---

## Skills Included

| Skill | Trigger | What it does |
|-------|---------|--------------|
| `/test-case-generator` | "generate test cases" | Generates full Xray test hierarchy from sprint stories |
| `/manual-executor` | "execute test cases" | Runs TCs via Playwright, screenshots every step, vision-based pass/fail |
| `/bug-maester` | "report a bug" | Files structured Bug tickets from failures or natural language |

---

## Prerequisites

### Environment variables (required)

| Variable | Purpose |
|----------|---------|
| `JIRA_EMAIL` | Your Atlassian account email |
| `JIRA_API_TOKEN` | Atlassian API token — generate at https://id.atlassian.com/manage-profile/security/api-tokens |

### Xray MCP server (required for all three skills)

The skills use a local Xray Cloud MCP server for GraphQL operations. Add to your `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "xray": {
      "command": "python",
      "args": ["xray-mcp/server.py"]
    }
  }
}
```

The server file (`xray-mcp/server.py`) must exist in your project root. It handles authentication, token caching, and all Xray GraphQL mutations internally.

### Playwright (manual-executor only)

```bash
pip install playwright
python -m playwright install chromium
```

### Optional — test account credentials (manual-executor)

If not set, fresh accounts are **auto-provisioned** via the signup API on staging/UAT:

| Variable | Purpose |
|----------|---------|
| `QA_USERNAME` / `QA_PASSWORD` | Primary player test account |
| `QA_USERNAME_2` / `QA_PASSWORD_2` | Secondary player (multi-player TCs) |
| `QA_ADMIN_USERNAME` / `QA_ADMIN_PASSWORD` | Admin test account |

---

## /test-case-generator

Reads every story in the active sprint, analyses the description and acceptance criteria, and generates a complete Xray test artefact hierarchy — ready to execute.

**What it creates per story:**
- Positive and negative Test Cases with full Action / Test Data / Expected Result steps
- Test Set grouping all TCs for the story
- Test Execution record
- Test Plan for the sprint
- Correct Xray issuelinks between all artefacts
- Jira comment on stories that are too vague (skips them instead of generating weak tests)

**Invoke:**
```
/test-case-generator
```
or type: `generate test cases`, `create test plan`, `run test generator`

**Output:** All issues created in your configured Jira/Xray project with steps populated.

---

## /manual-executor

Executes test cases step by step in a real Chromium browser. Takes a screenshot before and after every step, uses Claude's vision to assess pass/fail, and fires `/bug-maester` in the background for any failure.

**What it does:**
- Pulls TCs directly from Xray (`--from-xray`) or reads a local JSON file
- Spawns parallel browser sessions by user role (player vs admin)
- Auto-provisions fresh test accounts on staging — no `reset-db` endpoint needed
- Captures screenshots to `output/screenshots/{RUN_ID}/`
- Writes `results.json` + `run-report.md` to `output/results/{RUN_ID}/`
- Uploads final results to the Xray Test Execution on completion

**Invocation forms:**

```bash
# Pull TCs directly from Xray (recommended)
/manual-executor --from-xray TBL-XXX --url http://your-staging-url --env staging

# Use a local JSON file
/manual-executor --input output/test-cases/TBL-XXX.json --url http://localhost:4200 --env local

# Resume from a specific TC (skips all earlier ones)
/manual-executor --from-xray TBL-XXX --url http://... --env staging --skip-to AMOB-YYY
```

or type: `execute test cases`, `run manual tests`, `start test execution`

**Output structure:**
```
output/
  screenshots/{RUN_ID}/        ← one PNG per step
  results/{RUN_ID}/
    results.json               ← per-TC status + step details
    run-report.md              ← markdown summary table
    pw_runner.py               ← the generated Playwright script
```

---

## /bug-maester

Reports bugs against Jira in two modes. Every invocation first audits and repairs any existing open bug descriptions before creating new ones.

### Mode 1 — Natural language intake

Describe the bug in plain English. The skill infers as many fields as possible and asks only for what is genuinely missing:

```
report a bug: the Accept button on the challenge card disappears after page refresh
```

### Mode 2 — Auto-fill from Test Execution

Fetches all FAILED TCs from an Xray execution, reads the test steps to populate Steps to Reproduce, and creates one Bug ticket per failure in parallel:

```bash
/bug-maester AMOB-217          # specific execution
/bug-maester all               # all executions in the project
```

**Bug ticket format (6 sections):**
1. Summary
2. Environment (URL, browser, build)
3. Steps to Reproduce (pulled from Xray TC steps)
4. Expected Result
5. Actual Result
6. Logs / Screenshots

**Invoke:** `report a bug`, `log a bug`, `create bug`, `/bug-maester`, `/bug-maester <EXEC_KEY>`

---

## Typical workflow

```
1. /test-case-generator          → TCs + Test Set + Execution created in Xray
2. /manual-executor --from-xray TBL-XXX --url <staging> --env staging
                                 → Browser runs all TCs, screenshots every step
3. /bug-maester <EXEC_KEY>       → Bug tickets filed for any failures
```
