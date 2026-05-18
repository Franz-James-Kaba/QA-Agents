---
name: test-case-generator
description: >
  Generates a complete Xray test artefact hierarchy for every story in the active
  AMOB sprint. Run once per sprint. Reads each story's full description and
  acceptance criteria, generates both positive and negative test cases with
  detailed steps (Action / Test Data / Expected Result per step), creates all
  Xray issue types (Test, Test Set, Test Plan, Test Execution) and links them
  correctly. Flags stories with insufficient detail with a Jira comment rather
  than generating weak tests. Triggered by "generate test cases", "create test
  plan", "run test generator", or /test-case-generator.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob, Agent, mcp__jira__*, mcp__xray__*
model: sonnet
---

## Overview

Runs once per sprint against the AMOB project. Produces a complete Xray test
artefact hierarchy — one Test Plan for the sprint, one Test Set per story, all
positive and negative Test Cases with full step detail, one Test Execution per
Test Set. Unclear stories are flagged with a Jira comment and skipped rather
than generating weak tests.

---

## Project constants

| Item | Value |
|------|-------|
| Jira project key | `AMOB` |
| Jira cloud ID | `3521e9d0-86fb-4525-9c87-d0ab1f900e7c` |
| Jira base URL | `https://amali-tech.atlassian.net` |
| Jira email | `franz-james.kaba@amalitech.com` |
| Agile board ID | `3243` |
| Xray GraphQL step mutation | `addTestStep` (see Phase 5a) |
| Xray GraphQL endpoint | `https://xray.cloud.getxray.app/api/v2/graphql` |
| Xray auth endpoint | `https://xray.cloud.getxray.app/api/v2/authenticate` |

Auth for Jira/curl calls: Basic auth — `$JIRA_EMAIL:$JIRA_API_TOKEN` (env vars).
Auth for Xray GraphQL: handled automatically by the **Xray MCP server** — never obtain or pass tokens manually.

---

## Xray MCP Tools

All Xray Cloud operations are performed via the `mcp__xray__*` tools provided by the
project-local MCP server (`xray-mcp/server.py`). The server manages authentication,
token caching, and GraphQL calls internally. Never use raw curl or Python urllib for
Xray operations.

| Operation | MCP Tool | Key Parameters |
|-----------|----------|----------------|
| Verify credentials | `mcp__xray__authenticate` | — |
| Add step to Test Case | `mcp__xray__add_test_step` | `issue_id`, `action`, `data`, `result` |
| Link Tests to Test Set | `mcp__xray__add_tests_to_test_set` | `test_set_issue_id`, `test_issue_ids` |
| Link Tests to Test Execution | `mcp__xray__add_tests_to_test_execution` | `test_exec_issue_id`, `test_issue_ids` |
| Link Tests to Test Plan | `mcp__xray__add_tests_to_test_plan` | `test_plan_issue_id`, `test_issue_ids` |
| Link Executions to Test Plan | `mcp__xray__add_test_executions_to_test_plan` | `test_plan_issue_id`, `test_exec_issue_ids` |
| Fetch Test Case steps | `mcp__xray__get_test_steps` | `issue_id` |
| Fetch failed results | `mcp__xray__get_test_execution_failures` | `issue_id` |

All `issue_id` / `*_issue_id` parameters take the **numeric Jira ID** (e.g. `"113080"`),
not the key (e.g. `"AMOB-131"`). The numeric ID is available in the Jira issue REST
response as `issue["id"]`.

---

## Xray issue types

| Type | Jira name |
|------|-----------|
| Test case | `Test` |
| Test grouping | `Test Set` |
| Sprint container | `Test Plan` |
| Execution record | `Test Execution` |

---

## Xray link types

| Relationship | Link type |
|---|---|
| Story → Test Case | `Test` (Story = outward, Test Case = inward → Story shows "is tested by") |
| Bug → Test Case | `Defect` (resolved dynamically — see bug-maester skill) |

Test Set ↔ Tests, Test Plan ↔ Tests, Test Execution ↔ Tests are managed via
Xray Cloud GraphQL mutations (not standard Jira issue links).

---

## Phase 0 — Authenticate with Xray Cloud API

Call the MCP authenticate tool to verify credentials before doing any Xray work:

```
mcp__xray__authenticate()
```

Expected response: `{"status": "ok", "token_length": <N>, "expires_in_seconds": <N>}`.

If the tool raises → print the error message and stop. The MCP server manages the
Bearer token internally; no `XRAY_TOKEN` variable is needed in this skill.

---

## Phase 1 — Fetch active sprint stories

Use the Agile REST API (the JQL search endpoint has permission restrictions):

```bash
# Step 1: Get active sprint ID
SPRINT_ID=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "https://amali-tech.atlassian.net/rest/agile/1.0/board/3243/sprint?state=active" \
  -H "Accept: application/json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
sprint = data['values'][0]
print(sprint['id'])
")

SPRINT_NAME=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "https://amali-tech.atlassian.net/rest/agile/1.0/board/3243/sprint?state=active" \
  -H "Accept: application/json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['values'][0]['name'])
")

# Step 2: Get all stories in the active sprint
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "https://amali-tech.atlassian.net/rest/agile/1.0/board/3243/sprint/$SPRINT_ID/issue?maxResults=100&fields=summary,description,priority,assignee,issuetype" \
  -H "Accept: application/json"
```

Filter to `issuetype = Story` only. If zero stories → print
`No stories found in the active AMOB sprint.` and stop.

Print a numbered list before proceeding:
```
Stories in active sprint (<SPRINT_NAME>):
1. AMOB-001 (High)   — <summary>
2. AMOB-002 (Medium) — <summary>
...
```

---

## Phase 2 — Create the sprint Test Plan

Check for an existing Test Plan using the Agile API on the active sprint first.
If one already exists → use it and its numeric `id`, print `Test Plan already exists: <key>` and continue.

If none exists → create a Jira issue and capture both `key` and numeric `id`:
```bash
TESTPLAN_RESPONSE=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issue" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "AMOB"},
      "issuetype": {"name": "Test Plan"},
      "summary": "Test Plan — <Sprint Name> — <YYYY-MM-DD>",
      "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Auto-generated test plan for sprint <Sprint Name>."}]}]}
    }
  }')

TESTPLAN_KEY=$(echo $TESTPLAN_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
TESTPLAN_ID=$(echo $TESTPLAN_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

Store both `TESTPLAN_KEY` and `TESTPLAN_ID` for Phase 5e.

---

## Phase 3 — Assess each story

For each story, fetch the full issue:
```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  "https://amali-tech.atlassian.net/rest/api/3/issue/<STORY_KEY>" \
  -H "Accept: application/json"
```

### Locate acceptance criteria

Check the following in order and use whichever is non-empty:
1. `customfield_10016` — the most common Jira AC field
2. Any field whose name contains "acceptance" or "criteria" (case-insensitive)
3. A section headed "Acceptance Criteria" embedded in the description text

Combine the description and acceptance criteria into a single content block for analysis.

### Clarity check

A story is **too unclear to test** if ANY of the following are true:
- Combined content is empty, null, or under 20 words
- No acceptance criteria found in any location
- Content contains only a generic user story statement with no defined behaviour
- Contradictory requirements within the same story
- Exclusively vague language with no observable outcomes:
  "improve", "make it better", "should work well", "enhance performance"

### If unclear — flag and skip

1. Post a comment on the Jira story in ADF format:

```
🚩 Test Case Generation — Story Flagged

This story was skipped during automated test case generation because it
lacks sufficient detail for effective testing.

Gaps identified:
• [specific gap 1]
• [specific gap 2]
• [specific gap 3 — as many as apply]

Please update the description and acceptance criteria to address the gaps
above, then re-run /test-case-generator.
```

2. Add the story to the **Flagged** list (printed in the Phase 6 report).
3. **Do not generate any test cases for this story.** Move to the next story.

---

## Phase 3b — Implementation Dialogue

Runs for every story that **passed** the clarity check — before any test cases are written.
The goal is to capture the real implementation detail so test steps use exact screen names,
field labels, button text, API endpoints, and error messages rather than inferred placeholders.

### Step 1 — Classify the story type

Read the story summary and description and assign one or more types:
- **Form/input** — user fills fields and submits (e.g. create request, search, login)
- **Data display** — app fetches and renders a list or detail screen
- **Authentication/biometric** — login, biometric enrolment, session management
- **Connectivity/state** — VPN check, offline mode, background/foreground transitions
- **Navigation** — multi-step flow, back navigation, deep links
- **Settings/toggle** — user enables or disables a feature

### Step 2 — Ask the user targeted questions

Print the block below verbatim (substituting the story key and summary), then wait:

```
Implementation flow for <STORY_KEY> — <story summary>
──────────────────────────────────────────────────────
Please answer the following so test cases reflect the real app:

1. What is the exact screen name (class name or route name) where this feature lives?
2. Describe the user journey step by step — what does the user tap/see from entry to completion?
3. What are the exact labels of any buttons, tabs, or navigation items the user interacts with?
4. Are there loading states, empty states, or skeleton screens shown while data loads?
5. What happens on success? (navigation destination, snackbar/toast text, state change)
6. What error messages or states are shown when something goes wrong?
```

Then append the relevant type-specific questions:

**Form/input stories — add:**
```
7. List every field with its type (text, dropdown, date picker, etc.) and whether it is required.
8. When is inline validation shown — on blur, on submit, or real-time?
9. What API endpoint and HTTP method does the submit action call?
```

**Data display stories — add:**
```
7. What API endpoint and HTTP method fetches the data?
8. What fields or columns are shown per item in the list/detail?
9. Is there pull-to-refresh, pagination, or auto-refresh behaviour?
```

**Authentication/biometric stories — add:**
```
7. What triggers the biometric prompt — app launch, return from background, or explicit user action?
8. What is the fallback when biometric fails or is unavailable?
9. How many failed attempts are allowed before the fallback is forced?
```

**Connectivity/state stories — add:**
```
7. What conditions are checked — internet only, VPN required, or both?
8. How often is the check re-run — on app open, on every API call, or on foreground resume?
9. What is the exact on-screen message when connectivity is insufficient?
```

### Step 3 — Wait for the user's answers

Do **not** proceed to Phase 4 until the user has replied. If any critical answer is missing
or ambiguous (e.g. "the form has some fields"), ask one targeted follow-up question and wait
again before continuing.

### Step 4 — Store as the Implementation Context for this story

Hold the answers in memory as **Implementation Context: <STORY_KEY>**. Phase 4 reads this
context to:
- Use the real screen name, field labels, and button text in every action step
- Use the real API endpoint in negative test cases ("Mock POST /api/leave to return 500")
- Use the real error message text in expected results
- Use the real navigation destination in success expected results
- Use the real field list (with required flags) in form-validation test cases

If a detail was not provided by the user, make the best inference from the story description
but mark it with `[ASSUMED]` in the step text so it can be corrected after review.

---

## Phase 4 — Generate test cases

For each clear story, produce a full set of positive and negative test cases
from the combined description + acceptance criteria content.

> **Use the Implementation Context from Phase 3b.** Every action must reference the exact
> screen name, field label, button label, and navigation destination the user provided.
> Every expected result for an error must use the exact error text the user provided.
> Every negative test case that involves an API call must name the real endpoint.
> Mark anything not confirmed by the user with `[ASSUMED]`.

### Coverage rules

**Positive test cases — always include:**
- The primary success flow (end-to-end happy path)
- One test per distinct acceptance criterion
- Valid boundary values (e.g. max allowed characters, valid date ranges)
- Different valid user roles or permission levels if the story involves access control

**Negative test cases — always include:**
- Required fields left empty / null
- Invalid data formats (wrong email format, letters in numeric fields, etc.)
- Boundary violations (one above maximum, one below minimum)
- Unauthorised access where the story involves roles or permissions
- API / network failure response handling where the story calls a backend
- Concurrent or race condition scenarios where relevant

**Flutter mobile — always consider for both types:**
- Back navigation behaviour mid-flow
- Offline / no-connectivity handling where the story involves network calls
- Portrait and landscape orientation if the story involves layout
- Form inline validation feedback (error text, snackbars, toast messages)
- App state restoration after backgrounding

**Minimum per story:** 2 positive + 2 negative. More if the acceptance criteria
warrant additional coverage.

### Test case format

Produce each test case in this structure:

```
Name: [Concise and specific — e.g. "AMOB-12 — Submit registration form with valid data — positive"]
Type: Positive / Negative
Preconditions: [App and data state required before step 1]

Steps:
  1. Action:          [Exact tap / input / gesture / navigation]
     Test Data:       [Specific value — e.g. email: "qa@example.com", name: "Jane Doe"]
     Expected Result: [Exact observable outcome on screen or system]

  2. Action:          ...
     Test Data:       ...
     Expected Result: ...
  ...
```

Rules:
- 3–8 steps per test case
- Each step is atomic — one action only
- Never bundle multiple actions into one step
- Test data must be concrete values, never placeholders like `<valid email>`
- Expected results must be observable (visible UI state, message text, navigation destination)

---

## Phase 5 — Create Xray artefacts (parallel via subagents)

After Phase 4 is complete for **ALL** stories (i.e., every story has passed
Phase 3b dialogue and Phase 4 test case generation), proceed as follows:

1. The Xray MCP server (`mcp__xray__*`) handles authentication automatically —
   no token variable is needed. All Xray calls in steps 5a–5f use MCP tools.

2. If there is only **ONE** story to process → run steps 5a–5f directly in the
   main context (no subagent needed).

3. If there are **TWO OR MORE** stories → spawn one subagent per story in a
   **single message** (all `Agent` tool calls in one turn = parallel execution).
   Each subagent independently executes steps 5a–5f for its story and returns a
   structured result (see Phase 5 Subagent Prompt Template below).
   Do NOT wait for one subagent before launching the next.

4. After all subagents complete, collect their structured results and run Phase 6
   (final report) in the main context. Parse each subagent's `STORY`,
   `TCS_CREATED`, `TC_KEYS`, `TESTSET`, `TESTEXEC`, and `ERRORS` fields.
   Any subagent that returned non-empty `ERRORS` is added to the Warnings list.

---

## Phase 5 Subagent Prompt Template

Use this template for each story's Phase 5 subagent. Substitute all `<PLACEHOLDERS>`
before spawning. Send all subagents in **ONE message** so they run in parallel.

```
You are creating all Jira and Xray test artefacts for one story in the AMOB project.
All required data is provided below — do NOT ask the user any questions.
Execute every task and return the structured result at the end.

## Credentials and endpoints
- Jira base URL: https://amali-tech.atlassian.net
- Jira auth: Basic auth with env vars $JIRA_EMAIL and $JIRA_API_TOKEN
- Xray operations: use mcp__xray__* tools (authentication is handled automatically)

## Story
- Key: <STORY_KEY>
- Summary: <STORY_SUMMARY>
- Test Plan ID (numeric): <TESTPLAN_ID>
- Test Plan Key: <TESTPLAN_KEY>

## Test cases to create
<PASTE FULL LIST: one block per TC with Name, Type, Preconditions, and all Steps>

Format for each TC:
  Name: <name>
  Type: Positive / Negative
  Preconditions: <preconditions>
  Steps:
    1. Action: <action> | Data: <data> | Expected: <expected>
    2. …

## Tasks to execute in order

### Task 5a — Create Test Case Jira issues + add Xray steps
For each test case above:
1. POST to /rest/api/3/issue (issuetype: Test, project: AMOB, summary: <name>)
2. Capture key AND numeric id from response
3. For each step: call mcp__xray__add_test_step(issue_id, action, data, result)
   using the numeric TC ID (not the key).
4. Store key and numeric id for subsequent tasks

### Task 5b — Create Test Set
POST to /rest/api/3/issue (issuetype: Test Set,
  summary: "[<STORY_KEY>] Test Set — <STORY_SUMMARY>")
Capture key and numeric id.
Call mcp__xray__add_tests_to_test_set(test_set_issue_id: <TESTSET_ID>, test_issue_ids: [...all TC ids...])

### Task 5c — Link Test Cases to Story
For each TC key: POST to /rest/api/3/issueLink
  type: "Test", outwardIssue: <STORY_KEY>, inwardIssue: <TC_KEY>
Expected HTTP 201 for each link.

### Task 5d — Create Test Execution
POST to /rest/api/3/issue (issuetype: Test Execution,
  summary: "[<STORY_KEY>] Test Execution — <STORY_SUMMARY>")
Capture key and numeric id.
Call mcp__xray__add_tests_to_test_execution(test_exec_issue_id: <TESTEXEC_ID>, test_issue_ids: [...all TC ids...])

### Task 5e — Link Test Execution to Test Set
POST to /rest/api/3/issueLink
  type: "Relates", outwardIssue: <TESTSET_KEY>, inwardIssue: <TESTEXEC_KEY>

### Task 5f — Add TCs and Test Execution to Test Plan
Call mcp__xray__add_tests_to_test_plan(test_plan_issue_id: <TESTPLAN_ID>, test_issue_ids: [...all TC ids...])
Call mcp__xray__add_test_executions_to_test_plan(test_plan_issue_id: <TESTPLAN_ID>, test_exec_issue_ids: [<TESTEXEC_ID>])

## Return format (required — use exactly this structure)
STORY: <STORY_KEY>
TCS_CREATED: <N>
TC_KEYS: AMOB-X, AMOB-Y, ...
TESTSET: <TESTSET_KEY>
TESTEXEC: <TESTEXEC_KEY>
ERRORS: none (or list any errors with task and message)
```

---

When running Phase 5 directly (single story, no subagent), follow steps 5a–5f below.

### 5a — Create Test Case issues

For each generated test case, create a Jira issue and capture both `key` and
numeric `id` from the response:

```bash
TC_RESPONSE=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issue" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "AMOB"},
      "issuetype": {"name": "Test"},
      "summary": "[AMOB-XXX] <test case name>",
      "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Type: <Positive/Negative>\n\nPreconditions: <preconditions>"}]}]}
    }
  }')

TC_KEY=$(echo $TC_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
TC_ID=$(echo $TC_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

After the issue is created, add each step via the Xray MCP tool (one call per step).
Use the numeric `TC_ID`, NOT the key:

```
mcp__xray__add_test_step(
  issue_id = "<TC_ID>",
  action   = "<action text>",
  data     = "<test data or '-' if none>",
  result   = "<expected result>"
)
```

Returns the UUID of the created step. If the tool raises, print the error and
continue to the next step.

Collect all created Test Case **keys** (for issue links) and **numeric IDs**
(for all GraphQL mutations including steps) into two parallel lists.

### 5b — Create the Test Set

Create a Jira issue and capture both `key` and numeric `id`:

```bash
TS_RESPONSE=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issue" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "AMOB"},
      "issuetype": {"name": "Test Set"},
      "summary": "[AMOB-XXX] Test Set — <story summary>"
    }
  }')

TESTSET_KEY=$(echo $TS_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
TESTSET_ID=$(echo $TS_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

Add all Test Case numeric IDs to this Test Set via the Xray MCP tool:

```
mcp__xray__add_tests_to_test_set(
  test_set_issue_id = "<TESTSET_ID>",
  test_issue_ids    = ["<TC_ID_1>", "<TC_ID_2>", ...]
)
```

Expected response: `{"addedTests": [...], "warning": null}`.

### 5c — Link Test Cases to the Story

For each Test Case key, create an issue link via the Jira REST API. The Story
must be the **outward** issue and the Test Case must be the **inward** issue —
this causes the Story to display **"is tested by"** in its Linked Work Items
section. Do NOT swap these values.

```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issueLink" \
  -H "Content-Type: application/json" \
  -d '{
    "type": {"name": "Test"},
    "outwardIssue": {"key": "<STORY_KEY>"},
    "inwardIssue":  {"key": "<TEST_CASE_KEY>"}
  }'
```

Expected HTTP response: `201 Created`.

### 5d — Create the Test Execution

Create a Jira issue and capture both `key` and numeric `id`:

```bash
TE_RESPONSE=$(curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issue" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "AMOB"},
      "issuetype": {"name": "Test Execution"},
      "summary": "[AMOB-XXX] Test Execution — <story summary>"
    }
  }')

TESTEXEC_KEY=$(echo $TE_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
TESTEXEC_ID=$(echo $TE_RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
```

Add all Test Case numeric IDs to this Test Execution via the Xray MCP tool:

```
mcp__xray__add_tests_to_test_execution(
  test_exec_issue_id = "<TESTEXEC_ID>",
  test_issue_ids     = ["<TC_ID_1>", "<TC_ID_2>", ...]
)
```

Expected response: `{"addedTests": [...], "warning": null}`.

### 5e — Link the Test Execution to its Test Set

Link the Test Execution back to its Test Set via a Jira "relates to" issue link.
This is the correct association since Xray Cloud has no native Test Set ↔ Test
Execution GraphQL relationship — the Jira link makes the connection visible in
both issues' Linked Work Items sections:

```bash
curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://amali-tech.atlassian.net/rest/api/3/issueLink" \
  -H "Content-Type: application/json" \
  -d '{
    "type": {"name": "Relates"},
    "outwardIssue": {"key": "<TESTSET_KEY>"},
    "inwardIssue":  {"key": "<TESTEXEC_KEY>"}
  }'
```

Expected HTTP response: `201 Created`.

### 5f — Add Test Cases and Test Execution to the Test Plan

**Add the Test Cases** to the sprint Test Plan:

```
mcp__xray__add_tests_to_test_plan(
  test_plan_issue_id = "<TESTPLAN_ID>",
  test_issue_ids     = ["<TC_ID_1>", "<TC_ID_2>", ...]
)
```

**Also add the Test Execution** to the sprint Test Plan so the Test Plan shows
all execution records across the entire sprint:

```
mcp__xray__add_test_executions_to_test_plan(
  test_plan_issue_id  = "<TESTPLAN_ID>",
  test_exec_issue_ids = ["<TESTEXEC_ID>"]
)
```

Both calls must succeed. Expected response: respective `addedTests` /
`addedTestExecutions` arrays contain the IDs, `warning` is null.

Note: Xray Test Plans contain individual Test Cases directly. The Test Set
organises tests per story for readability; the Test Plan aggregates all test
keys and all execution records across all stories for the sprint.


---

## Phase 6 — Final report

After all Phase 5 subagents (or the direct Phase 5 run) complete, collect
structured results. For each subagent, parse: `STORY`, `TCS_CREATED`, `TC_KEYS`,
`TESTSET`, `TESTEXEC`, `ERRORS`. Stories where `ERRORS` is non-empty are added to
the Warnings list. Stories where the subagent itself failed to return a result are
added to the Failed list.

Print a complete summary after all stories are processed:

```
=== TEST CASE GENERATION — AMOB — <Sprint Name> ===

Test Plan: <TESTPLAN_KEY>

Stories processed:
✓ AMOB-001 — <summary>
    Tests: <N> (<X> positive, <Y> negative)
    Test Set:       <TESTSET_KEY>
    Test Execution: <TESTEXEC_KEY>

✓ AMOB-002 — <summary>
    Tests: <N> (<X> positive, <Y> negative)
    Test Set:       <TESTSET_KEY>
    Test Execution: <TESTEXEC_KEY>

Flagged stories (skipped — insufficient detail):
🚩 AMOB-003 — <summary>
    Gaps: <gap 1>, <gap 2>

🚩 AMOB-004 — <summary>
    Gaps: <gap 1>

───────────────────────────────────────────────────
Total stories processed : <N>
Total test cases created: <N> (<X> positive, <Y> negative)
Stories flagged         : <N>
===================================================
```

---

## Hard rules

- Never generate test cases for a flagged story — post the gap comment and skip
- Phase 3b dialogue MUST complete for every story that passes the clarity check — never skip it and fall back to assumptions alone
- Never create a duplicate Test Plan — check via Agile API before creating
- Every Test Case must have all steps added via `mcp__xray__add_test_step` before moving on
- Both positive AND negative test cases are mandatory — never omit either type
- Minimum 2 positive + 2 negative per story regardless of story size
- Each step must have a concrete Action, concrete Test Data, and a specific Expected Result
- Always capture both `key` AND numeric `id` from every issue create response — the key is used for issue links, the numeric ID is used for all GraphQL mutations (including steps)
- Use `mcp__xray__*` tools for ALL Xray operations — NEVER use raw curl or urllib.request for Xray GraphQL calls. The MCP server handles auth and encoding.
- Complete Phase 3b dialogue and Phase 4 test case generation for ALL stories first, then spawn Phase 5 subagents in parallel (one per story) in a single message — never interleave artefact creation with dialogue
- Every Test Execution MUST be linked to its Test Set via a Jira "relates to" link (step 5e) — never skip this
- Every Test Execution MUST be added to the Test Plan via `mcp__xray__add_test_executions_to_test_plan` (step 5f) — never skip this
- If any GraphQL mutation returns a non-empty `warning` or an `errors` field, print it and add the story to a "Warnings" list in the report
- If any API call fails entirely, print the error, skip that story, add it to a separate "Failed" list in the report, and continue
