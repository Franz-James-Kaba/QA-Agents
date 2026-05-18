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

2. **Copy the Xray MCP server** to your project root:
   ```
   xray-mcp/server.py
   ```
   Then add to `.claude/mcp.json`:
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
   Update `CLIENT_ID` and `CLIENT_SECRET` in `server.py` with your Xray Cloud credentials.

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
