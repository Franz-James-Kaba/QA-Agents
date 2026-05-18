---
name: bug-maester
description: >
  Reports bugs for the AMOB Jira project in two ways: (1) natural language intake —
  user describes a bug conversationally and the skill creates a full 6-section Bug
  ticket; (2) auto-fill — fetches failing tests from a Test Execution (or all
  executions) via Xray Cloud GraphQL, uses the Test Case steps to populate the
  description, and creates tickets in parallel. Every invocation first audits and
  repairs all open bug descriptions (Phase 0). Triggered by "report a bug",
  "log a bug", "create bug", "bug found in AMOB-XXX", /bug-maester,
  /bug-maester <EXEC_KEY>, or /bug-maester all.
allowed-tools: Bash, Read, Write, Agent, mcp__jira__*, mcp__xray__*
model: sonnet
---

## Overview

Two objectives:

1. **Natural language intake (manual mode)** — user describes a bug in plain text;
   skill parses the description, infers as many fields as possible, asks only for
   what is genuinely missing, and creates a full 6-section Bug ticket.

2. **Auto-fill from Test Executions (auto / all mode)** — skill fetches FAILED tests
   from one or all Test Executions via Xray Cloud GraphQL, reads the Test Case's
   Xray steps to populate Steps to Reproduce and Expected Result, runs the duplicate
   guard, and creates bug tickets in parallel (one subagent per bug).

**Every invocation starts with Phase 0.** Phase 0 audits all open Bug descriptions,
fetches Xray steps for any non-compliant bug that has a linked Test Case, and repairs
descriptions in parallel before any new bug work begins.

---

## Project constants

| Item | Value |
|------|-------|
| Jira cloud ID | `3521e9d0-86fb-4525-9c87-d0ab1f900e7c` |
| Jira base URL | `https://amali-tech.atlassian.net` |
| Xray Cloud GraphQL | `https://xray.cloud.getxray.app/api/v2/graphql` |
| Xray auth endpoint | `https://xray.cloud.getxray.app/api/v2/authenticate` |
| Jira email | `franz-james.kaba@amalitech.com` |
| Bug issue type | `Bug` |
| Defect link type | `Defect` (Bug=outwardIssue, TC=inwardIssue) |
| Target status | `In Progress` |

Auth for Jira: Basic auth — `$JIRA_EMAIL:$JIRA_API_TOKEN` (env vars).
Auth for Xray GraphQL: handled automatically by the **Xray MCP server** — never obtain or pass tokens manually.

### Project detection

Determine `PROJECT_KEY` at the start of Mode detection, before any Jira calls:

```python
# Determine project from argument or TC key
# Argument examples: "TBL-1236 --tcs TBL-1193,TBL-1198" / "TBL-1236" / "AMOB-123" / "all"
import re

raw_arg = "<USER_ARGUMENT>"   # the string passed to /bug-maester

if re.search(r'\bTBL-\d+', raw_arg, re.IGNORECASE):
    PROJECT_KEY = "TBL"
    # TBL-specific: no Severity field
    STAGING_URL = "http://ttl-app-alb-1081216351.eu-west-1.elb.amazonaws.com"
else:
    PROJECT_KEY = "AMOB"
    STAGING_URL = None
    # AMOB has no Severity custom field — never attempt to set it
```

Use `PROJECT_KEY` everywhere a project key is referenced (`"project": {"key": PROJECT_KEY}`).
Both projects share the same `CLOUD_ID`, `BASE`, and Jira credentials.

---

## Xray MCP Tools

All Xray Cloud operations use the `mcp__xray__*` tools provided by the project-local
MCP server (`xray-mcp/server.py`). Never use raw curl or urllib.request for Xray calls.

| Operation | MCP Tool | Key Parameters |
|-----------|----------|----------------|
| Verify credentials | `mcp__xray__authenticate` | — |
| Fetch Test Case steps | `mcp__xray__get_test_steps` | `issue_id` (numeric) |
| Fetch failed results | `mcp__xray__get_test_execution_failures` | `issue_id` (numeric) |

All `issue_id` parameters take the **numeric Jira ID** (e.g. `"113080"`), not the key.

---

## Phase 0 — Audit and repair existing bug descriptions

Runs **every invocation** before any new bug work or user dialogue.

### Step 0a — Authenticate with Xray Cloud

```
mcp__xray__authenticate()
```

Expected: `{"status": "ok", ...}`. If the tool raises → print the error and stop.

### Step 0b — Fetch all open bugs

```python
import urllib.request, json, os, base64

EMAIL = os.environ["JIRA_EMAIL"]
TOKEN = os.environ["JIRA_API_TOKEN"]
creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
HEADERS = {"Authorization": f"Basic {creds}", "Accept": "application/json"}
BASE = "https://amali-tech.atlassian.net"

body = json.dumps({
    "jql": "project = AMOB AND issuetype = Bug AND statusCategory != Done",
    "fields": ["summary", "description", "issuelinks"],
    "maxResults": 100
}).encode()
req = urllib.request.Request(
    f"{BASE}/rest/api/3/search/jql",
    data=body,
    headers={**HEADERS, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read())

bugs = [
    {
        "key": i["key"],
        "summary": i["fields"]["summary"],
        "description": i["fields"]["description"],
        "issuelinks": i["fields"].get("issuelinks", []),
    }
    for i in data["issues"]
]
```

### Step 0c — Compliance check

A description is **compliant** only when ALL hold:
1. `description` is not null
2. ADF `content` has an h2 heading for each of the 6 required section names (case-insensitive):
   `Description`, `Steps to Reproduce`, `Actual Result`, `Expected Result`, `Environment`, `Root Cause Analysis`
3. No heading uses `"level": 3`

```python
REQUIRED = {
    "description", "steps to reproduce", "actual result",
    "expected result", "environment", "root cause analysis",
}

def is_compliant(adf):
    if not adf:
        return False
    h2_found = set()
    for node in adf.get("content", []):
        if node.get("type") != "heading":
            continue
        level = node.get("attrs", {}).get("level")
        if level == 3:
            return False
        if level == 2:
            text = "".join(
                c.get("text", "") for c in node.get("content", [])
                if c.get("type") == "text"
            ).lower().strip()
            h2_found.add(text)
    return REQUIRED.issubset(h2_found)
```

Collect all bugs where `is_compliant()` returns `False`.

### Step 0d — Resolve TC steps for non-compliant bugs

For each non-compliant bug, check its `issuelinks` for a `Defect`-type link to a Test Case.
If found, fetch the TC's Xray steps via GraphQL:

```python
def get_tc_key_from_links(issuelinks):
    for link in issuelinks:
        if link["type"]["name"] == "Defect":
            for direction in ["inwardIssue", "outwardIssue"]:
                if direction in link:
                    return link[direction]["key"], link[direction]["id"]
    return None, None

```

Build the repair context for each non-compliant bug using the Xray MCP tool:
```python
repair_jobs = []
for bug in non_compliant:
    tc_key, tc_id = get_tc_key_from_links(bug["issuelinks"])
    # Call mcp__xray__get_test_steps(issue_id=tc_id) if tc_id is not None
    steps = mcp__xray__get_test_steps(issue_id=tc_id) if tc_id else []
    repair_jobs.append({
        "key": bug["key"],
        "summary": bug["summary"],
        "description": bug["description"],
        "tc_key": tc_key,     # None if no TC linked
        "xray_steps": steps,  # [] if no TC or no steps
    })
```

### Step 0e — Repair dispatch

**1 non-compliant bug** → repair in main context using the logic in the Repair Subagent Template below.

**2+ non-compliant bugs** → spawn one repair subagent per bug in a **single message**
(all `Agent` tool calls in one turn = parallel execution). Pass each bug's full
repair context in the subagent prompt.

### Step 0f — Collect results and print audit summary

```
=== DESCRIPTION AUDIT ===
Bugs checked:      <N>
Already compliant: <X>
Repaired:          <Y>
  AMOB-XXX — xray-steps  (TC steps used to populate all sections)
  AMOB-YYY — strategy-a  (table → 6-section h2)
  AMOB-ZZZ — strategy-c  (existing content wrapped + placeholders added)
Errors:            <E>
=========================
```

After printing, proceed to Mode detection.

---

## Phase 0 Repair Subagent Template

Use this template verbatim for each repair subagent in Step 0e, substituting every
`<PLACEHOLDER>`. Send all subagents in **ONE message**.

```
You are repairing one Jira Bug description to conform to the required 6-section h2 format.
All data is provided below. Do NOT ask any questions. Execute the repair and return the result.

## Bug to repair
- Key: <BUG_KEY>
- Summary: <BUG_SUMMARY>
- Linked TC key: <TC_KEY or "none">
- Xray steps: <JSON array of {action, data, result} objects, or []>
- Current description ADF: <CURRENT_ADF_JSON>

## Repair rules

### When Xray steps are provided (preferred strategy)
Build the 6-section ADF using:
- Description:          Narrative synthesised from the bug summary — explain what is broken and its impact
- Steps to Reproduce:   orderedList — each step = "{action}" + " — {data}" if data is non-empty and not "-"
- Expected Result:      The `result` field of the LAST Xray step that is non-empty
- Actual Result:        Any existing text found in the current description, else "TBD"
- Environment:          bulletList — use real values if found in current description, else:
                        ["OS: unknown", "Device: unknown", "App version: unknown",
                         "Build type: unknown", "Flutter version: unknown"]
- Root Cause Analysis:  "TBD — under investigation"
Strategy label to return: "xray-steps"

### When no Xray steps (no TC linked) — choose based on current description format
**Strategy A — current description contains a table node:**
- Extract Action + Data columns as numbered steps
- Take last non-dash Expected Result and Actual Result column values
- Description = narrative from bug summary
Strategy label: "strategy-a"

**Strategy B — current description has headings but some/all use level 3:**
- Walk ADF and set every heading node to level 2
- Append placeholder nodes for any of the 6 sections still missing
Strategy label: "strategy-b"

**Strategy C — current description has no heading structure:**
- Wrap ALL existing content nodes under a Description h2 heading
- Append the other 5 sections as placeholders
Strategy label: "strategy-c"

**Strategy D — description is null or empty:**
- Build full 6-section template using bug summary as Description paragraph
- All other sections get placeholder values
Strategy label: "strategy-d"

## ADF builder pattern (use for all strategies)

```python
import urllib.request, json, os, base64

def h2(text):
    return {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": text}]}
def para(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}
def ordered_list(items):
    return {"type": "orderedList",
            "content": [{"type": "listItem", "content": [para(i)]} for i in items]}
def bullet_list(items):
    return {"type": "bulletList",
            "content": [{"type": "listItem", "content": [para(i)]} for i in items]}

repaired_adf = {
    "type": "doc", "version": 1,
    "content": [
        h2("Description"),        para("<description>"),
        h2("Steps to Reproduce"), ordered_list(["<step 1>", "<step 2>"]),
        h2("Actual Result"),      para("<actual>"),
        h2("Expected Result"),    para("<expected>"),
        h2("Environment"),        bullet_list(["OS: ...", "Device: ...",
                                               "App version: ...", "Build type: ...",
                                               "Flutter version: ..."]),
        h2("Root Cause Analysis"), para("TBD — under investigation"),
    ]
}

EMAIL = os.environ["JIRA_EMAIL"]
TOKEN = os.environ["JIRA_API_TOKEN"]
creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
body = json.dumps({"fields": {"description": repaired_adf}}).encode()
req = urllib.request.Request(
    "https://amali-tech.atlassian.net/rest/api/3/issue/<BUG_KEY>",
    data=body,
    headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
    method="PUT",
)
with urllib.request.urlopen(req) as r:
    pass  # HTTP 204 = success
```

## Return format (required)
KEY: <BUG_KEY>
STRATEGY: <xray-steps | strategy-a | strategy-b | strategy-c | strategy-d>
STATUS: ok
ERROR: none
```

---

## Mode detection

After Phase 0, determine which of the three modes applies:

---

### Manual mode — no argument provided

User invoked `/bug-maester` with no key, or described a bug in natural language
without specifying an execution key.

→ Proceed directly to **Phase 1**.

---

### Explicit mode — execution key + `--tcs` list provided

User invoked `/bug-maester <EXEC_KEY> --tcs TC-KEY1,TC-KEY2,...`

Use this mode when the caller already knows which failures are genuine product bugs
(vs runner/test-data issues). It bypasses Xray failure detection entirely.

1. Parse `--tcs` value: split on commas, strip whitespace → list of TC keys.

2. For each TC key, resolve its numeric ID and summary:
   ```bash
   curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
     "https://amali-tech.atlassian.net/rest/api/3/issue/<TC_KEY>?fields=summary,issuelinks" \
     -H "Accept: application/json"
   ```
   Capture `id` (numeric), `key`, `fields.summary`, `fields.issuelinks`.

3. For each TC, resolve parent Story key + Story assignee from `issuelinks`
   (type `"Test"`, `outwardIssue` → Story key; then fetch Story for assignee).

4. Fetch Xray steps for each TC:
   ```
   mcp__xray__get_test_steps(issue_id="<TC_NUMERIC_ID>")
   ```

5. **Load results.json enrichment** (see "results.json enrichment" section below).

6. Run duplicate guard (Phase 3) for each TC. Skip any that already have an open
   Defect-linked Bug.

7. Print a visible audit list and proceed immediately (no user gate):
   ```
   Creating <N> bug(s) from <EXEC_KEY> --tcs:
     <TC_KEY> — <tc summary> → story <STORY_KEY> → assignee <name>
     ...
   Proceeding...
   ```

8. **1 bug** → run Phase 4–7 in main context.
   **2+ bugs** → spawn one creation subagent per bug in a **single message**.

9. Collect results → Phase 8 final report.

---

### Auto mode — single Test Execution key provided

User invoked `/bug-maester <EXEC_KEY>` (no `--tcs`) where EXEC_KEY is a Test Execution issue.

1. Xray credentials are managed by the MCP server — no token variable needed.

2. Fetch the execution's numeric ID:
   ```bash
   curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
     "https://amali-tech.atlassian.net/rest/api/3/issue/<EXEC_KEY>" \
     -H "Accept: application/json" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'])"
   ```

3. Fetch all FAILED test numeric IDs from the execution via the Xray MCP tool:
   ```
   mcp__xray__get_test_execution_failures(issue_id="<EXEC_NUMERIC_ID>")
   ```
   Returns a list of `{"issueId": str, "status": "FAILED"}` dicts.

4. For each failing TC numeric ID, resolve key + summary + issuelinks:
   ```python
   body = json.dumps({
       "jql": f"id = {tc_numeric_id}",
       "fields": ["summary", "issuelinks"],
       "maxResults": 1
   }).encode()
   req = urllib.request.Request(
       "https://amali-tech.atlassian.net/rest/api/3/search/jql",
       data=body,
       headers={**JIRA_HEADERS, "Content-Type": "application/json"},
       method="POST",
   )
   ```

5. For each failing TC, resolve parent Story key and Story assignee:
   ```python
   # From issuelinks: type.name == "Test" and "outwardIssue" present → Story key
   # Then fetch Story: GET /rest/api/3/issue/<STORY_KEY>?fields=assignee,summary
   # Story assignee accountId → use as bug assignee
   # If story has no assignee → fall back to $JIRA_EMAIL
   ```

6. Fetch Xray steps for each failing TC:
   ```
   mcp__xray__get_test_steps(issue_id="<TC_NUMERIC_ID>")
   ```
   Returns a list of `{"action": str, "data": str, "result": str}` dicts.

7. Run duplicate guard (Phase 3) for each failing TC. Skip TCs that already
   have an open Defect-linked Bug.

8. Print the list of bugs to be created — no confirmation required, proceed immediately:
   ```
   Creating <N> bug(s):
     AMOB-XXX — <tc summary> → story <STORY_KEY> → assignee <name>
     ...
   ```

9. **1 bug to create** → run Phase 4–7 in main context.
   **2+ bugs to create** → spawn one creation subagent per bug in a **single message**.

10. Collect results → Phase 8 final report.

---

### All mode — "all" argument provided

User invoked `/bug-maester all` or said "go through all executions".

1. Xray credentials are managed by the MCP server — no token variable needed.

2. Fetch all Test Execution issues in AMOB:
   ```python
   body = json.dumps({
       "jql": "project = AMOB AND issuetype = 'Test Execution'",
       "fields": ["summary", "id"],
       "maxResults": 100
   }).encode()
   # POST /rest/api/3/search/jql
   ```

3. For each execution, fetch FAILED test numeric IDs via the Xray MCP tool:
   ```
   mcp__xray__get_test_execution_failures(issue_id="<EXEC_NUMERIC_ID>")
   ```

4. Deduplicate across executions — a TC can fail in multiple executions;
   keep it only once (first occurrence wins).

5. For each unique failing TC: resolve key, summary, issuelinks, Story key,
   Story assignee, Xray steps (same as Auto mode steps 4–6).

6. Run duplicate guard (Phase 3) for each TC. Collect only those without
   an existing open Bug.

7. Print pending list and proceed immediately (no confirmation gate):
   ```
   Scanning <E> executions → <F> unique failing TCs → <N> new bugs to create
     AMOB-XXX — <tc summary> → story <STORY_KEY> → assignee <name>
     ...
   ```

8. **1 bug** → main context. **2+ bugs** → parallel subagents (one per bug, single message).

9. Collect results → Phase 8 final report.

---

## Bug Creation Subagent Template

Use for each bug in auto or all mode (2+ bugs). Substitute every `<PLACEHOLDER>`.
Send all subagents in **ONE message**.

```
You are creating one Jira Bug ticket for a failing test in the AMOB project.
All data is provided — do NOT ask questions. Execute every task and return the result.

## Project constants
- Jira base URL: https://amali-tech.atlassian.net
- Auth: Basic auth with env vars $JIRA_EMAIL and $JIRA_API_TOKEN
- AMOB has NO Severity custom field — do not set it

## Pre-resolved shared values
- Project key:       <PROJECT_KEY>   (TBL or AMOB)
- Assignee account ID:   <ACCOUNT_ID>   (from Story's assignee, or $JIRA_EMAIL fallback)
- Assignee display name: <DISPLAY_NAME>
- Run ID:            <RUN_ID or "unknown">

## This bug's data
- Title:           <TITLE>
- Test Case key:   <TC_KEY>
- TC summary:      <TC_SUMMARY>
- Story key:       <STORY_KEY>
- Priority:        <PRIORITY>
- Description:     <DESCRIPTION_NARRATIVE>
- Steps (from Xray): <NUMBERED_STEPS>
- Actual result:   <ACTUAL_RESULT>   (from results.json FAIL step, or Xray step, or TBD)
- Expected result: <EXPECTED_RESULT> (from results.json FAIL step expected field)
- Environment:     <ENV_LIST>        (TBL: staging bullets; AMOB: Flutter bullets)
- Root cause:      TBD — under investigation
- Attachments:     <PATHS or "none">

## Tasks

### Task 1 — Create the Bug issue
POST https://amali-tech.atlassian.net/rest/api/3/issue
Fields: project=<PROJECT_KEY>, issuetype=Bug, summary, priority, assignee (accountId), description (ADF).
Do NOT set severity (neither TBL nor AMOB has a Severity custom field).

ADF MUST have 6 h2 sections in order:
1. Description       (paragraph)
2. Steps to Reproduce (orderedList)
3. Actual Result     (paragraph)
4. Expected Result   (paragraph)
5. Environment       (bulletList: OS, Device, App version, Build type, Flutter version)
6. Root Cause Analysis (paragraph)

All headings: {"type": "heading", "attrs": {"level": 2}, ...}  — NEVER level 3.
Use Python json.dumps() — never string-interpolate JSON.
Capture the returned key (AMOB-XXX).

### Task 2 — Upload attachments
POST /rest/api/3/issue/<BUG_KEY>/attachments  with X-Atlassian-Token: no-check
Skip silently if attachments = "none".

### Task 3 — Link the bug
POST /rest/api/3/issueLink twice:
  Link 1: type="Defect",  outwardIssue=<BUG_KEY>, inwardIssue=<TC_KEY>
  Link 2: type="Relates", outwardIssue=<BUG_KEY>, inwardIssue=<STORY_KEY>

### Task 4 — Transition Bug and Story to In Progress

Bug:
  GET  /rest/api/3/issue/<BUG_KEY>/transitions
  Find transition whose name is "In Progress" (or closest match).
  POST /rest/api/3/issue/<BUG_KEY>/transitions  body: {"transition": {"id": "<ID>"}}

Story:
  GET  /rest/api/3/issue/<STORY_KEY>?fields=status
  If status category is "Done" → skip.
  Otherwise:
    GET  /rest/api/3/issue/<STORY_KEY>/transitions
    Find "In Progress" transition.
    POST /rest/api/3/issue/<STORY_KEY>/transitions  body: {"transition": {"id": "<ID>"}}

## Return format
BUG_KEY: <key>
TITLE: <title>
TC: <tc_key>
STORY: <story_key>
STATUS: In Progress
STORY_STATUS: <In Progress | Done (skipped)>
ATTACHMENTS: <N>
ERROR: none
URL: https://amali-tech.atlassian.net/browse/<key>
```

---

## results.json enrichment (explicit and auto mode)

After resolving TC keys and before running Phase 4 / spawning subagents, attempt to
load the Playwright results file for richer "Actual Result" and "Expected Result" data.

### Step R1 — Locate results.json

Check for the file at `output/results/<RUN_ID>/results.json` where `RUN_ID` is:
1. Extracted from the execution ticket summary (e.g. `RUN-20260513-003` if present in summary)
2. Or: the most recently modified folder inside `output/results/` (sorted by mtime)
3. Or: skip enrichment entirely if `output/results/` doesn't exist

```python
import os, json, glob

# Try to find the results file
results_map = {}   # tc_key -> result dict
candidates = []

# Strategy 1: check execution summary for RUN-ID pattern
import re
run_id_match = re.search(r'RUN-\d{8}-\d{3}', exec_summary or "")
if run_id_match:
    path = f"output/results/{run_id_match.group()}/results.json"
    if os.path.exists(path):
        candidates.append(path)

# Strategy 2: latest folder
if not candidates:
    folders = sorted(glob.glob("output/results/RUN-*/results.json"),
                     key=os.path.getmtime, reverse=True)
    candidates = folders[:1]

if candidates:
    with open(candidates[0], encoding="utf-8") as f:
        raw = json.load(f)
    for entry in raw:
        if "tcId" in entry:
            results_map[entry["tcId"]] = entry
    print(f"  Loaded results.json from {candidates[0]} ({len(results_map)} TCs)")
else:
    print("  results.json not found — Actual/Expected Result will use Xray step data")
```

### Step R2 — Extract per-TC actual/expected/notes

For each TC key being reported:

```python
def get_enrichment(tc_key, results_map, xray_steps):
    """
    Returns (actual_result, expected_result, description_notes).
    Prefers results.json data; falls back to last Xray step result.
    """
    entry = results_map.get(tc_key, {})
    
    # Find the first FAIL step
    fail_step = next(
        (s for s in entry.get("steps", []) if s.get("status") in ("FAIL", "ERROR")),
        None
    )
    
    if fail_step:
        actual   = fail_step.get("actual", "").strip() or "See runner output"
        expected = fail_step.get("expected", "").strip() or "See test case"
    elif xray_steps:
        # Fallback: last xray step result
        actual   = "TBD — see screenshots"
        expected = (xray_steps[-1].get("result") or "").strip() or "See test case"
    else:
        actual   = "TBD"
        expected = "TBD"
    
    notes = " | ".join(n for n in entry.get("notes", []) if n)
    description_suffix = f"\n\nRunner notes: {notes}" if notes else ""
    
    return actual, expected, description_suffix
```

Pass `actual_result`, `expected_result`, and `description_suffix` into Phase 4 / the
Bug Creation Subagent Template for each TC.

---

## Phase 1 — Natural language intake (manual mode)

### Step 1a — Parse the user's input

Read the user's full message and extract every field that is present or inferable:

| Signal in user text | Maps to |
|---------------------|---------|
| Core problem described | Title (shorten to ≤10 words) + Description narrative |
| "on iOS / Android", device name, version number | Environment OS + Device |
| "TestFlight", "debug build", "release" | Environment Build type |
| An AMOB-XXX key mentioned | TC key or Story key |
| "blocking", "can't proceed", "crash", "app is unusable" | Priority → High or Highest |
| "wrong", "incorrect", "doesn't show", "empty" | Priority → Medium |
| "cosmetic", "typo", "minor", "small" | Priority → Low |
| VPN state, network condition | Steps context |

Pre-populate all extractable fields before asking for anything.

### Step 1b — Ask only for what is missing

Show the pre-populated fields and ask **only** for fields where no value could be inferred.

Minimum required to create the ticket:
- Title
- Description (what is broken + impact)
- Steps to Reproduce
- Actual Result
- Expected Result

The following all have fallbacks — **never block creation waiting for them:**
- TC key → optional; skip linking if not provided
- Story key → optional; skip Story link and Story transition if not provided
- Assignee → default to Story assignee if story known, else `$JIRA_EMAIL`
- Priority → default to `Medium` if cannot be inferred
- Environment → default to `["OS: unknown", "Device: unknown", "App version: unknown", "Build type: unknown", "Flutter version: unknown"]`

### Step 1c — Confirm before creating

Once all mandatory fields are present, show a final summary and wait for user approval
before creating the ticket. (Manual mode only — auto/all modes skip this gate.)

---

## Phase 2 — Resolve the assignee account ID

Priority order:
1. If a Story key is known: `GET /rest/api/3/issue/<STORY_KEY>?fields=assignee` →
   use `fields.assignee.accountId` if non-null
2. If no story or story has no assignee: use `$JIRA_EMAIL` as the assignee →
   resolve its accountId via `GET /rest/api/3/user/search?query=<JIRA_EMAIL>`
3. Only ask the user explicitly if both of the above fail

```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "https://amali-tech.atlassian.net/rest/api/3/user/search?query=<email>" \
  -H "Accept: application/json" | python3 -c "
import sys, json
u = json.load(sys.stdin)[0]
print(u['accountId'], u['displayName'])
"
```

---

## Phase 3 — Duplicate guard

Inspect the TC's issue links directly — do NOT use `issueFunction` JQL.

```python
# Step 1: get all Defect links on the TC
req = urllib.request.Request(
    f"https://amali-tech.atlassian.net/rest/api/3/issue/{tc_key}?fields=issuelinks",
    headers=JIRA_HEADERS,
)
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read())

defect_keys = []
for link in d["fields"].get("issuelinks", []):
    if link["type"]["name"] == "Defect":
        for direction in ["inwardIssue", "outwardIssue"]:
            if direction in link:
                defect_keys.append(link[direction]["key"])

# Step 2: check each linked key is an open Bug
for key in defect_keys:
    req = urllib.request.Request(
        f"https://amali-tech.atlassian.net/rest/api/3/issue/{key}?fields=issuetype,status",
        headers=JIRA_HEADERS,
    )
    with urllib.request.urlopen(req) as r:
        d = json.loads(r.read())
    if (d["fields"]["issuetype"]["name"] == "Bug"
            and d["fields"]["status"]["statusCategory"]["name"] != "Done"):
        print(f"OPEN BUG EXISTS: {key} — skipping {tc_key}")
        # skip this TC
```

If an open Bug is found → skip creation for this TC. Report it in Phase 8.

---

## Phase 4 — Create the Bug ticket

```python
PYTHONIOENCODING=utf-8 python3 << 'EOF'
import urllib.request, json, os, base64

EMAIL = os.environ["JIRA_EMAIL"]
TOKEN = os.environ["JIRA_API_TOKEN"]
creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
HEADERS = {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

def h2(text):
    return {"type": "heading", "attrs": {"level": 2},
            "content": [{"type": "text", "text": text}]}
def para(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}
def ordered_list(items):
    return {"type": "orderedList",
            "content": [{"type": "listItem", "content": [para(i)]} for i in items]}
def bullet_list(items):
    return {"type": "bulletList",
            "content": [{"type": "listItem", "content": [para(i)]} for i in items]}

adf = {
    "type": "doc", "version": 1,
    "content": [
        h2("Description"),        para("<description>"),
        h2("Steps to Reproduce"), ordered_list(["<step 1>", "<step 2>"]),
        h2("Actual Result"),      para("<actual>"),
        h2("Expected Result"),    para("<expected>"),
        # Environment bullets differ by project
        h2("Environment"),        bullet_list(
            # TBL project — web/staging
            [
                "Environment: staging",
                f"URL: {STAGING_URL}",
                "Browser: Chromium headless (Playwright Python)",
                f"Run ID: {run_id or 'see results.json'}",
                "Angular version: 20.x",
            ] if PROJECT_KEY == "TBL" else
            # AMOB project — mobile Flutter (unchanged)
            [
                "OS: <name and version>",
                "Device: <manufacturer and model>",
                "App version: <version>",
                "Build type: <debug/release/profile>",
                "Flutter version: <version or unknown>",
            ]
        ),
        h2("Root Cause Analysis"), para("<root cause or TBD — under investigation>"),
    ]
}

body = json.dumps({
    "fields": {
        "project":     {"key": "AMOB"},
        "issuetype":   {"name": "Bug"},
        "summary":     "<title>",
        "priority":    {"name": "<priority>"},
        "assignee":    {"accountId": "<account_id>"},
        "description": adf,
    }
}).encode()

req = urllib.request.Request(
    "https://amali-tech.atlassian.net/rest/api/3/issue",
    data=body, headers=HEADERS, method="POST"
)
with urllib.request.urlopen(req) as r:
    resp = json.loads(r.read())
    print("Created:", resp["key"])
EOF
```

**Never set a Severity field — AMOB does not have one.**

---

## Phase 5 — Upload attachments

```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issue/<BUG_KEY>/attachments" \
  -H "X-Atlassian-Token: no-check" \
  -F "file=@<absolute_file_path>"
```

Skip silently if no attachments provided.

---

## Phase 6 — Link the bug

```bash
# Link 1: Bug → Test Case (Defect) — skip if no TC key available
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issueLink" \
  -H "Content-Type: application/json" \
  -d '{"type":{"name":"Defect"},"outwardIssue":{"key":"<BUG_KEY>"},"inwardIssue":{"key":"<TC_KEY>"}}'

# Link 2: Bug → Story (Relates) — skip if no Story key available
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issueLink" \
  -H "Content-Type: application/json" \
  -d '{"type":{"name":"Relates"},"outwardIssue":{"key":"<BUG_KEY>"},"inwardIssue":{"key":"<STORY_KEY>"}}'
```

Expected: `201 Created` for each call made.

---

## Phase 7 — Transition Bug and Story to In Progress

**Bug:**
```python
import urllib.request, json, os, base64

creds = base64.b64encode(f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()).decode()
HEADERS = {"Authorization": f"Basic {creds}", "Content-Type": "application/json", "Accept": "application/json"}
BASE = "https://amali-tech.atlassian.net"

def transition_to_in_progress(issue_key):
    # 1. Fetch available transitions
    req = urllib.request.Request(f"{BASE}/rest/api/3/issue/{issue_key}/transitions", headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        transitions = json.loads(r.read())["transitions"]

    # 2. Find "In Progress" (exact match first, then closest)
    target = next(
        (t for t in transitions if t["name"].lower() == "in progress"),
        next((t for t in transitions if "progress" in t["name"].lower()), None)
    )
    if not target:
        print(f"  No In Progress transition found for {issue_key}")
        return

    # 3. Apply transition
    body = json.dumps({"transition": {"id": target["id"]}}).encode()
    req = urllib.request.Request(
        f"{BASE}/rest/api/3/issue/{issue_key}/transitions",
        data=body, headers=HEADERS, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        pass  # HTTP 204 = success
    print(f"  ✓ {issue_key} → In Progress")
```

**Story:**
```python
# Fetch current status first
req = urllib.request.Request(
    f"{BASE}/rest/api/3/issue/{story_key}?fields=status",
    headers=HEADERS
)
with urllib.request.urlopen(req) as r:
    d = json.loads(r.read())
status_category = d["fields"]["status"]["statusCategory"]["name"]

if status_category == "Done":
    print(f"  {story_key} is Done — skipping transition")
else:
    transition_to_in_progress(story_key)
```

Transition the story regardless of current state (To Do, In Progress, Code Review,
Ready for Testing, Testing). Only skip if `statusCategory.name == "Done"`.

---

## Phase 8 — Final report

Collect all subagent return blocks (auto/all mode) or the single result (manual/single mode).

For each bug created, print:

```
=== BUG REPORTED ===
Key:          <BUG_KEY>
Title:        <title>
Priority:     <priority>
Assigned to:  <assignee display name>
Bug status:   In Progress
Story status: <In Progress | Done (skipped) | N/A (no story)>
Links:
  Defect of:  <TC_KEY> — <tc summary>   (or "none — no TC linked")
  Relates to: <STORY_KEY> — <summary>   (or "none — no story linked")
Attachments:  <N> file(s) uploaded
URL:          https://amali-tech.atlassian.net/browse/<BUG_KEY>
====================
```

For auto/all mode, end with a totals line:
```
Total bugs created: <N>   Skipped (existing): <S>   Failed: <F>
```

If any subagent returned a non-empty ERROR field:
```
⚠ Failed:
  <TC_KEY> — <error message>
```

---

## Hard rules

- **TC is required in auto/all mode** (fetched automatically from the execution). **TC is optional in manual mode** — create the bug without a Defect link if no TC is provided; note it in the report
- **Assignee always has a fallback** — inherit from Story's assignee, then `$JIRA_EMAIL`; never block creation waiting for an assignee
- **Priority always has a fallback** — infer from language, default `Medium`; never block creation
- Never set a Severity field — AMOB has none; including it causes HTTP 400
- Never create a bug without Steps to Reproduce — ask the user if they cannot be derived from the Xray steps or natural language description
- Root cause defaults to `TBD — under investigation` when unknown — never leave it blank
- Always transition BOTH Bug and Story to In Progress after creation; skip Story only if its status category is `Done`
- In auto/all mode, create one bug per failing test — never merge multiple failures into one ticket
- Never use Xray's Raven REST API (`/rest/raven/1.0/...`) — it is the server-side plugin API and returns 404 in Xray Cloud; always use `mcp__xray__*` tools
- Never use raw curl or urllib.request for Xray GraphQL — always use `mcp__xray__*` tools; the MCP server manages auth automatically
- Never use `issueFunction` JQL for duplicate checks — unreliable in this project; always inspect TC issue links directly (Phase 3)
- Never re-create a bug for a TC that already has an open Defect-linked Bug — Phase 3 duplicate guard must run first
