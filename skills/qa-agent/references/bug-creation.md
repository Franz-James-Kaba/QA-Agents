# Bug Creation

Single source of truth for creating one bug ticket. Used both inline (1 bug) and via the subagent template at the bottom (2+ bugs in parallel).

Steps run in order: Create → Attach → Link → Transition.

## Per-bug inputs

| Field | Source |
|-------|--------|
| `project_key` | from the dispatcher |
| `cloud_id` | resolved once at session start |
| `title` | natural language (manual) or derived from TC summary (auto) |
| `tc_key`, `tc_summary` | optional in manual; required in explicit/auto/all |
| `story_key`, `story_assignee_account_id` | parent Story link + assignee with current-user fallback |
| `priority` | inferred or `Medium` |
| `description` | narrative (1–3 sentences) |
| `steps` | list of strings — Xray-derived or user-supplied |
| `actual_result`, `expected_result` | from results-file enrichment, last Xray step, or user input |
| `env_surface`, `env_known` | for `environment_bullets(surface, **known)` |
| `root_cause` | `"TBD — under investigation"` default |
| `attachments` | optional file paths |

## Step C1 — Create the Bug

Build the ADF using `build_bug_description` from `conventions.md`:

```python
adf = build_bug_description(
    description=description,
    steps=steps,
    actual=actual_result,
    expected=expected_result,
    env_bullets=environment_bullets(env_surface, **env_known),
    root_cause=root_cause,
)
```

Then run the create-issue operation with:

```
cloud_id:    <cloud_id>
project_key: <project_key>
issue_type:  "Bug"
summary:     <title>
description: <adf>
content_format: "adf"
additional_fields:
  priority: {"name": <priority>}
  assignee: {"accountId": <story_assignee_account_id>}
```

**Severity** — do NOT set it unless the user has explicitly confirmed the project has a Severity field. Most projects don't, and setting it returns HTTP 400.

Capture the returned `key` as `bug_key` and the numeric `id` as `bug_id`.

## Step C2 — Upload attachments

If `attachments` is non-empty, upload each file using whichever attachment operation the connected Jira tool exposes. If the tool doesn't expose attachment upload, note this in the final report and tell the user to upload manually — do not fall back to raw HTTP.

## Step C3 — Link the bug

Two links via the create-issue-link operation. Skip either if its target is unknown.

```
Link 1 — Defect:
  type:         "Defect"
  outwardIssue: bug_key
  inwardIssue:  tc_key

Link 2 — Relates:
  type:         "Relates"
  outwardIssue: bug_key
  inwardIssue:  story_key
```

## Step C4 — Transition Bug and Story to In Progress

Use `transition_to_in_progress` from `jira-helpers.md` for both. For the Story, check `get_status_category` first — skip the transition only if it's `"Done"`.

```python
transition_to_in_progress(bug_key, cloud_id)

if story_key:
    if get_status_category(story_key, cloud_id) == "Done":
        story_status = "Done (skipped)"
    else:
        transition_to_in_progress(story_key, cloud_id)
        story_status = "In Progress"
else:
    story_status = "N/A (no story)"
```

---

## Bug Creation Subagent Template

Use one subagent per bug when 2+ bugs are being created in explicit/auto/all sub-mode. Send all subagents in **ONE message**.

```
You are creating one Jira Bug ticket for a failing test. All data is provided below.
Do NOT ask any questions. Execute every task and return the result.

## Required reading (do this first)
Read these files for ADF shape, helper functions, link types, and tool patterns:
- <ABSOLUTE_PATH_TO_SKILL>/references/conventions.md
- <ABSOLUTE_PATH_TO_SKILL>/references/jira-helpers.md

## Access
- Jira and Xray Cloud tooling are connected (the dispatcher verified this).
- Use whichever connected tools are available — pick by intent.
- Do not fall back to raw HTTP.
- Cloud / workspace ID: <CLOUD_ID>

## Pre-resolved shared values
- Project key:           <PROJECT_KEY>
- Assignee account ID:   <ACCOUNT_ID>      (Story's assignee, or current-user fallback)
- Assignee display name: <DISPLAY_NAME>
- Run ID (if any):       <RUN_ID or "n/a">

## This bug's data
- Title:           <TITLE>
- Test Case key:   <TC_KEY>
- TC summary:      <TC_SUMMARY>
- Story key:       <STORY_KEY>
- Priority:        <PRIORITY>
- Description:     <DESCRIPTION_NARRATIVE>
- Steps:           <NUMBERED_STEPS> (Xray-derived; one string per step)
- Actual result:   <ACTUAL_RESULT>
- Expected result: <EXPECTED_RESULT>
- Environment surface:  <mobile | web | backend>
- Environment known:    <JSON object, e.g. {"environment": "staging", "url": "..."}>
- Root cause:      "TBD — under investigation"
- Attachments:     <PATHS or "none">

## Tasks

### Task 1 — Create the Bug
Build ADF using build_bug_description and environment_bullets from conventions.md.
All headings level 2 (never level 3).
Run the create-issue operation with: project_key, issue_type="Bug", summary, priority,
assignee (accountId), description (ADF), content_format="adf".
Do NOT set a Severity field.
Capture the returned key.

### Task 2 — Upload attachments
If attachments != "none", upload each file using the attachment operation if exposed.
If unavailable, note this in the ERROR field and continue.

### Task 3 — Link the bug
Run the create-issue-link operation twice:
  Link 1: type="Defect",  outwardIssue=<BUG_KEY>, inwardIssue=<TC_KEY>
  Link 2: type="Relates", outwardIssue=<BUG_KEY>, inwardIssue=<STORY_KEY>

### Task 4 — Transition Bug and Story to In Progress
Bug — always: use transition_to_in_progress(<BUG_KEY>, <CLOUD_ID>) per jira-helpers.md.
Story — if get_status_category == "Done", skip; otherwise transition.

## Return format
BUG_KEY: <key>
TITLE: <title>
TC: <tc_key>
STORY: <story_key>
STATUS: In Progress
STORY_STATUS: <In Progress | Done (skipped)>
ATTACHMENTS: <N>
ERROR: none
URL: <full Jira browse URL for the bug>
```
