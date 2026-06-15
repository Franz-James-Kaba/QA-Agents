# Plan Mode

Generates a complete Xray test artefact hierarchy for an active sprint: one Test Plan, one Test Set per story, all positive and negative Test Cases with full step detail, one Test Execution per Test Set. Stories without enough detail to test are flagged and skipped.

Run once per sprint per project.

## Invocation

```
/plan <PROJECT_KEY>
/plan <PROJECT_KEY> --board <BOARD_ID>      (optional — see Step P1)
generate test cases for the active sprint in PROJ
```

## Step P0 — Universal setup

Per `conventions.md`:

```
1. Run the Xray authenticate operation.
2. Run the workspace-discovery operation and store the result as `cloud_id`
   (some tools call it the "cloud id", others "workspace id" or similar).
3. Run the current-user operation and store the `accountId` as `current_account_id`.
```

## Step P1 — Resolve the active sprint

Two paths depending on what the connected Jira tool exposes:

**Preferred — JQL on the project**:

```
jql:        project = <PROJECT_KEY> AND sprint in openSprints() AND issuetype = Story
fields:     ["summary", "description", "priority", "assignee", "issuetype", "customfield_10016"]
maxResults: 100
```

`customfield_10016` is the most common Acceptance Criteria field — include it in the fields list, but fall back to scanning the description if it's empty (see `plan-clarity-check.md`).

**Fallback — Agile board API**: if the connected Jira tool exposes an Agile board / sprint operation, ask the user for the board ID (or detect from the project's sprint custom field), then list active sprints, pick the most recent, and list its stories. If no Agile operations are exposed, fall back to the JQL approach above.

If zero stories → print `No stories found in the active sprint for <PROJECT_KEY>.` and stop.

Otherwise print:

```
Stories in active sprint:
1. <KEY> (<priority>) — <summary>
2. ...
```

## Step P2 — Create or find the sprint Test Plan

Check whether a Test Plan exists for this sprint. Search:

```
jql: project = <PROJECT_KEY> AND issuetype = "Test Plan" AND summary ~ "<Sprint Name>"
```

If found → use its `key` and numeric `id`, print `Test Plan already exists: <key>`, continue.

If not → create one using the create-issue operation, with:

```
cloud_id:    <cloud_id>
project_key: <PROJECT_KEY>
issue_type:  "Test Plan"
summary:     "Test Plan — <Sprint Name> — <YYYY-MM-DD>"
description: short paragraph: "Auto-generated test plan for sprint <Sprint Name>."
```

Capture both the returned `key` and numeric `id`. Store as `TESTPLAN_KEY` and `TESTPLAN_ID` for Step P5.

## Step P3 — Per-story clarity check

For each story, read `plan-clarity-check.md` and run the check. If the story is too unclear to test, the procedure there posts a flag comment to the Jira issue and adds the story to the **Flagged** list (do **not** generate test cases for it). Move on to the next story.

## Step P4 — Per-story implementation dialogue + test case generation

> **Delegation (see `orchestrator-protocol.md`).** The dialogue (P4.1) needs the user and stays with the orchestrator. The actual TC generation (P4.2) is mechanical and is **delegated to a Sonnet worker per story** — see Step P5, which fuses generation + Xray creation into one worker per story. The orchestrator gathers dialogue context for every story first, then fans out.

For each story that passed the clarity check:

1. Read `plan-implementation-dialogue.md` and run the dialogue with the user (orchestrator). This gathers real screen names, field labels, button text, API endpoints, and error messages so test steps reflect the actual app. **Record the gathered context per story** — it is handed to that story's worker.
2. TC generation itself is performed by the story's Sonnet worker in Step P5, using the coverage rules and format below. The orchestrator does NOT write TC steps inline.

### Coverage rules

**Positive test cases — always include:**
- The primary success flow (end-to-end happy path)
- One test per distinct acceptance criterion
- Valid boundary values (max allowed characters, valid date ranges)
- Different valid user roles or permission levels if access control is involved

**Negative test cases — always include:**
- Required fields left empty / null
- Invalid data formats (wrong email format, letters in numeric fields)
- Boundary violations (one above max, one below min)
- Unauthorised access where roles/permissions are involved
- API / network failure response handling where a backend call is involved
- Concurrent or race-condition scenarios where relevant

**Surface-specific extras** — pull from the dialogue. For mobile: back navigation, offline, orientation, app backgrounding. For web: keyboard navigation, browser-back, form-validation timing. For backend: error codes, idempotency, auth header behaviour.

**Minimum per story**: 2 positive + 2 negative. More if the acceptance criteria warrant it.

### Test case format

Produce each test case in this structure:

```
Name: [Concise and specific — e.g. "<STORY_KEY> — Submit registration form with valid data — positive"]
Type: Positive | Negative
Preconditions: [App and data state required before step 1]

Steps:
  1. Action:          [Exact tap / input / gesture / navigation]
     Test Data:       [Specific value — e.g. email: "qa@example.com", name: "Jane Doe"]
     Expected Result: [Exact observable outcome on screen or system]

  2. Action: ...
     Test Data: ...
     Expected Result: ...
```

Rules:

- 3–8 steps per test case
- Each step is atomic — one action only; never bundle multiple actions
- Test data must be concrete values, never placeholders like `<valid email>`
- Expected results must be observable (visible UI state, message text, navigation destination)

## Step P5 — Generate TCs + create Xray artefacts (Sonnet workers)

Once the dialogue (P4.1) is complete for **every** story, fan out. **Strict delegation:** spawn **one Sonnet worker per story** (`model: "sonnet"`), all in a single message — even if there is only one story. Never generate TCs or create artefacts in the orchestrator context.

Each worker:
1. Receives, inline: the story text + acceptance criteria, the **dialogue context** gathered in P4.1, the coverage rules + TC format below, and the pre-resolved `cloud_id` / `TESTPLAN_KEY` / `TESTPLAN_ID` / project key.
2. Reads `plan-xray-artifacts.md` (absolute path) for the artefact-creation flow.
3. Generates the positive + negative TCs (coverage rules + format below), then creates that story's Test Set, Test Cases, and Test Execution, links them, and adds the Execution to the Test Plan.
4. Returns structured output only: story key, TC count (pos/neg), Test Set key, Test Execution key, and `needs_orchestrator_review` + `review_reason` if the ACs and dialogue context conflict.

The orchestrator collects worker outputs for the final report (P6) and resolves any escalated stories itself.

## Step P6 — Final report

After all subagents (or the inline single-story run) complete, collect their results:

```
=== TEST CASE GENERATION — <PROJECT_KEY> — <Sprint Name> ===

Test Plan: <TESTPLAN_KEY>

Stories processed:
✓ <KEY> — <summary>
    Tests: <N> (<X> positive, <Y> negative)
    Test Set:       <TESTSET_KEY>
    Test Execution: <TESTEXEC_KEY>

✓ <KEY> — <summary>
    ...

Flagged stories (skipped — insufficient detail):
🚩 <KEY> — <summary>
    Gaps: <gap 1>, <gap 2>

───────────────────────────────────────────────────
Total stories processed : <N>
Total test cases created: <N> (<X> positive, <Y> negative)
Stories flagged         : <N>
===================================================
```

If any subagent returned non-empty `ERRORS`, list under a `Warnings:` section. If a subagent failed entirely, list under `Failed:`.

## Plan-mode rules

- **Clarity check is non-negotiable** — never generate test cases for a flagged story.
- **Implementation dialogue is mandatory for every story that passes the clarity check** — never fall back to assumptions alone.
- **Both positive AND negative test cases are mandatory** — never omit either.
- **Minimum 2 positive + 2 negative per story** regardless of story size.
- **Each step has concrete Action, concrete Test Data, specific Expected Result.**
- **Phase P4 must complete for all stories before Phase P5 spawns** — never interleave dialogue with artefact creation.
- **Every Test Execution is linked to its Test Set** (Relates link, see `conventions.md`) and **added to the Test Plan** — never skip either.
- **TC generation is always delegated to a Sonnet worker per story** (P5) — the orchestrator never writes TC steps inline, even for a single story. See `orchestrator-protocol.md`.
