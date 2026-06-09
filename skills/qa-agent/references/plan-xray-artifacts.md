# Xray Artefact Creation (Plan Mode — Step P5)

After all stories have completed clarity check, dialogue, and test case generation, create the Xray hierarchy. Single-story → main context. Multi-story → one subagent per story in a single message.

The Test Plan (`TESTPLAN_KEY`, `TESTPLAN_ID`) was already created in plan-mode Step P2.

The snippets below are **operation pseudocode**, not literal Python. Each call describes what the agent does using whatever Jira and Xray tooling is connected.

## Per-story tasks (5a–5f)

Run in this order for each story:

### 5a — Create Test Case Jira issues and add Xray steps

For each generated test case:

1. Create the issue (issue type `Test`):
   ```
   resp = create_issue(
       cloud_id      = <cloud_id>,
       project_key   = <PROJECT_KEY>,
       issue_type    = "Test",
       summary       = "[<STORY_KEY>] <test case name>",
       description   = build_test_case_description(test_type, preconditions),  # from conventions.md
       content_format = "adf",
   )
   tc_key = resp["key"]
   tc_id  = resp["id"]
   ```

2. For each step in the test case, add it to Xray using the add-step operation (one call per step). Use the **numeric** TC id:
   ```
   xray_add_test_step(
       issue_id = tc_id,
       action   = step.action,
       data     = step.data or "-",
       result   = step.expected,
   )
   ```
   The add-step operation returns the UUID of the created step. If a call fails, print the error and continue to the next step — don't abort the whole test case for one bad step.

Collect all Test Case keys (for issue links) and numeric IDs (for Xray operations) into parallel lists.

### 5b — Create the Test Set

```
resp = create_issue(
    cloud_id    = <cloud_id>,
    project_key = <PROJECT_KEY>,
    issue_type  = "Test Set",
    summary     = "[<STORY_KEY>] Test Set — <story summary>",
)
TESTSET_KEY = resp["key"]
TESTSET_ID  = resp["id"]
```

Then add all Test Cases to the Test Set:

```
xray_add_tests_to_test_set(
    test_set_issue_id = TESTSET_ID,
    test_issue_ids    = [TC_ID_1, TC_ID_2, ...],
)
```

Expected response: `{"addedTests": [...], "warning": null}`. If `warning` is non-empty, log it and add the story to the Warnings list.

### 5c — Link Test Cases to the Story

For each Test Case key, create an issue link:

```
create_issue_link(
    cloud_id      = <cloud_id>,
    type          = "Test",
    outward_issue = <STORY_KEY>,
    inward_issue  = <TEST_CASE_KEY>,
)
```

This causes the Story to display **"is tested by"** in its Linked Work Items. Direction matters — Story is outward, Test is inward. Do not swap.

### 5d — Create the Test Execution

```
resp = create_issue(
    cloud_id    = <cloud_id>,
    project_key = <PROJECT_KEY>,
    issue_type  = "Test Execution",
    summary     = "[<STORY_KEY>] Test Execution — <story summary>",
)
TESTEXEC_KEY = resp["key"]
TESTEXEC_ID  = resp["id"]
```

Then add all Test Cases to it:

```
xray_add_tests_to_test_execution(
    test_exec_issue_id = TESTEXEC_ID,
    test_issue_ids     = [TC_ID_1, TC_ID_2, ...],
)
```

### 5e — Link the Test Execution to its Test Set

Xray Cloud has no native Test Set ↔ Test Execution relationship, so use a Jira `Relates` link:

```
create_issue_link(
    cloud_id      = <cloud_id>,
    type          = "Relates",
    outward_issue = TESTSET_KEY,
    inward_issue  = TESTEXEC_KEY,
)
```

### 5f — Add Test Cases and Test Execution to the Test Plan

Both calls — Test Plans contain Test Cases directly **and** track Test Executions:

```
xray_add_tests_to_test_plan(
    test_plan_issue_id = TESTPLAN_ID,
    test_issue_ids     = [TC_ID_1, TC_ID_2, ...],
)

xray_add_test_executions_to_test_plan(
    test_plan_issue_id  = TESTPLAN_ID,
    test_exec_issue_ids = [TESTEXEC_ID],
)
```

Both must succeed. Expected responses have non-empty `addedTests` / `addedTestExecutions` and null `warning`.

---

## Plan Mode Subagent Template

Use one subagent per story when 2+ stories need processing. Send all in **ONE message**.

```
You are creating all Jira and Xray test artefacts for one story.
All data is provided below. Do NOT ask any questions. Execute every task and return the result.

## Required reading (do this first)
Read these files for ADF helpers, link types, and operation patterns:
- <ABSOLUTE_PATH_TO_SKILL>/references/conventions.md
- <ABSOLUTE_PATH_TO_SKILL>/references/plan-xray-artifacts.md

## Access
- Jira and Xray Cloud tooling are connected (the dispatcher verified this).
- Use whichever connected tools the agent has — pick by intent, not by name.
- Do not fall back to raw HTTP.
- Cloud / workspace identifier: <CLOUD_ID>

## Story
- Project key:    <PROJECT_KEY>
- Story key:      <STORY_KEY>
- Story summary:  <STORY_SUMMARY>
- Test Plan ID:   <TESTPLAN_ID> (numeric)
- Test Plan key:  <TESTPLAN_KEY>

## Test cases to create
<PASTE FULL LIST: one block per TC with Name, Type, Preconditions, and all Steps>

Format per TC:
  Name: <name>
  Type: Positive | Negative
  Preconditions: <preconditions>
  Steps:
    1. Action: <action> | Data: <data> | Expected: <expected>
    2. ...

## Tasks (in order)
Run tasks 5a → 5f as documented in plan-xray-artifacts.md.

## Return format
STORY:    <STORY_KEY>
TCS_CREATED: <N>
TC_KEYS:  <KEY-1>, <KEY-2>, ...
TESTSET:  <TESTSET_KEY>
TESTEXEC: <TESTEXEC_KEY>
ERRORS:   none (or list errors with task and message)
```
