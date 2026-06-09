# Conventions

The shared conventions every mode uses: the operations needed, link types, ADF shapes, and helper functions.

The skill describes operations by **intent** rather than by tool name. Use whichever Jira and Xray Cloud tools are connected — the agent picks the right one for each operation.

## Jira operations needed

The skill needs the ability to perform these operations against Jira. Pick whichever connected tool does each:

| Operation | What it does |
|-----------|--------------|
| Discover workspace / cloud | Get the cloud / workspace identifier. Call once per session and reuse. |
| Get current user | For assignee fallback. Returns at minimum an `accountId` and `displayName`. |
| Get an issue | Fetch fields like `summary`, `description`, `issuelinks`, `status`, `assignee`. Many tools accept a `fields=[...]` filter to limit payload — use it where possible. |
| Search issues | Run JQL queries against the project. |
| Create an issue | Returns both the key (e.g. `PROJ-123`) and the numeric `id`. Capture both. |
| Edit an issue | Update the description (for audit repairs) or other fields. |
| Add a comment | Used by the plan-mode clarity check to flag unclear stories. |
| Get available transitions | List the statuses an issue can transition to from its current state. |
| Apply a transition | Move an issue to a new status (e.g. In Progress). |
| Create an issue link | Used for Defect, Relates, and Test links between issues. |
| Upload an attachment (optional) | Used in bug mode if the user provides attachments. If the connected tool doesn't expose this, the skill notes it in the report and asks the user to upload manually. |

If a connected tool exposes the description / content in **Atlassian Document Format (ADF)**, prefer ADF for description fields. Most modern Jira tools support specifying a content format — use ADF.

## Xray Cloud operations needed

| Operation | What it does | Key parameter shape |
|-----------|--------------|--------------------|
| Authenticate | Verify Xray Cloud credentials before any Xray call. | — |
| Fetch Test Case steps | Returns an array of `{action, data, result}` for a Test issue. | `issue_id` (numeric) |
| Add a step to a Test Case | Append a single `{action, data, result}` step to a Test. One call per step. | `issue_id`, `action`, `data`, `result` |
| Link Tests to a Test Set | Add multiple Test Cases to a Test Set. | `test_set_issue_id`, `test_issue_ids[]` |
| Link Tests to a Test Execution | Add multiple Test Cases to a Test Execution. | `test_exec_issue_id`, `test_issue_ids[]` |
| Link Tests to a Test Plan | Add multiple Test Cases to a Test Plan. | `test_plan_issue_id`, `test_issue_ids[]` |
| Link Test Executions to a Test Plan | Add Test Executions to a Test Plan. | `test_plan_issue_id`, `test_exec_issue_ids[]` |
| Fetch failed results from an execution | List FAILED tests in a Test Execution. Returns `[{issueId, status: "FAILED"}, ...]`. | `issue_id` (numeric) |

**Every Xray `issue_id` parameter takes the numeric Jira ID**, not the issue key. Capture both from create responses.

The Xray tooling handles auth and token caching. Never pass tokens manually in any operation.

## Xray issue types

| What it represents | Jira issue type name |
|---|---|
| A single test case | `Test` |
| A group of tests (per story) | `Test Set` |
| Sprint-wide container | `Test Plan` |
| One execution record (per build/env) | `Test Execution` |

## Link types

Use these exact `type.name` values when creating issue links:

| Relationship | Type name | Direction (outward → inward) |
|---|---|---|
| Story → Test Case (Story "is tested by" Test) | `Test` | Story = outward, Test = inward |
| Bug → Test Case (Bug is a defect found by Test) | `Defect` | Bug = outward, Test = inward |
| Bug → Story | `Relates` | Bug = outward, Story = inward |
| Test Execution → Test Set | `Relates` | Test Set = outward, Test Execution = inward |

Direction matters — swapping it changes which side displays which label in Jira's Linked Work Items panel.

## The 6-section Bug ADF

Every bug description is an ADF doc with exactly these six h2 headings, in order:

1. **Description** — paragraph
2. **Steps to Reproduce** — `orderedList`
3. **Actual Result** — paragraph
4. **Expected Result** — paragraph
5. **Environment** — `bulletList`
6. **Root Cause Analysis** — paragraph (default `TBD — under investigation`)

All headings must use `"attrs": {"level": 2}` — **never level 3**. This is the rule the audit (see `audit.md`) enforces and repairs.

## The Test Case ADF

A Test Case description is simpler:

1. A paragraph with `Type: <Positive | Negative>`
2. A paragraph with `Preconditions: <text>`

The actual Test Case **steps** are not in the description — they're stored in Xray (one step at a time, via the "Add a step to a Test Case" operation).

## ADF builder helpers

Use these helpers in any context that builds ADF. Pass content through `json.dumps()` — never string-interpolate JSON.

```python
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

def build_bug_description(description, steps, actual, expected, env_bullets, root_cause):
    """The 6-section bug ADF — see top of this file."""
    return {
        "type": "doc", "version": 1,
        "content": [
            h2("Description"),        para(description),
            h2("Steps to Reproduce"), ordered_list(steps),
            h2("Actual Result"),      para(actual),
            h2("Expected Result"),    para(expected),
            h2("Environment"),        bullet_list(env_bullets),
            h2("Root Cause Analysis"), para(root_cause or "TBD — under investigation"),
        ],
    }

def build_test_case_description(test_type, preconditions):
    """Lightweight ADF for a Test Case issue. Steps go to Xray separately."""
    return {
        "type": "doc", "version": 1,
        "content": [
            para(f"Type: {test_type}"),
            para(f"Preconditions: {preconditions or 'None'}"),
        ],
    }
```

## Environment bullets

The bug Environment section's bullets describe the build / runtime / device. No single shape is universal — derive what you can from context and leave placeholders for the rest.

Common shapes:

**Mobile (native or Flutter)**:
```
OS: <name and version>
Device: <manufacturer and model>
App version: <version>
Build type: <debug/release/profile>
Framework: <Flutter / RN / native — and version>
```

**Web**:
```
Environment: <staging/production/local>
URL: <full URL>
Browser: <Chrome 138 / Firefox / Chromium headless (Playwright)>
Run ID: <CI run id, or "manual">
Framework: <Angular 20 / React 19 / Vue 3 — if known>
```

**Backend / API**:
```
Environment: <staging/production>
Service: <name and version>
Endpoint: <path>
Region: <if multi-region>
```

```python
def environment_bullets(surface, **known):
    """surface: 'mobile' | 'web' | 'backend'. Pass any known values as kwargs."""
    templates = {
        "mobile":  ["OS", "Device", "App version", "Build type", "Framework"],
        "web":     ["Environment", "URL", "Browser", "Run ID", "Framework"],
        "backend": ["Environment", "Service", "Endpoint", "Region"],
    }
    fields = templates.get(surface, templates["web"])
    return [
        f"{f}: {known.get(f.lower().replace(' ', '_'), f'<{f.lower()}>')}"
        for f in fields
    ]
```

If you can't infer the surface, default to `web` — it's the most common.

## Universal session setup

At the start of any mode, after tooling check passes:

```
1. Authenticate Xray Cloud (if this mode needs Xray).
2. Resolve the cloud / workspace identifier using whichever Jira tool exposes it.
   Store it as `cloud_id` and pass into every subsequent Jira call that needs it.
3. Resolve the current user via the current-user operation. Store the `accountId`
   as `current_account_id` for assignee fallback.
```

Pass `cloud_id` and `current_account_id` into every subsequent call that needs them.
