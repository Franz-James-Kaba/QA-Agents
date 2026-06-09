# Bug Description Audit

Runs at the start of every **bug-mode** invocation. Ensures all open bugs in the active project conform to the 6-section h2 ADF format defined in `conventions.md`.

The audit is fast — it's a single search call plus per-bug ADF inspection. It's mandatory because a project gradually accumulates malformed descriptions over time, and any new bug created in a malformed project still has to match the convention.

## Step A1 — Authenticate Xray (if available)

Run the Xray authenticate operation.

If Xray isn't connected but the user is only doing manual bug filing, print a one-line note and continue. The audit itself doesn't require Xray.

## Step A2 — Fetch all open bugs in PROJECT_KEY

Run the JQL search operation with:

```
jql:        project = <PROJECT_KEY> AND issuetype = Bug AND statusCategory != Done
fields:     ["summary", "description", "issuelinks"]
maxResults: 100
responseContentFormat: "adf"
```

Setting `responseContentFormat: "adf"` ensures the description comes back as a raw ADF tree (not markdown), which the compliance check inspects directly.

## Step A3 — Compliance check

A description is **compliant** only when ALL of these hold:

1. `description` is not null.
2. The ADF `content` has an h2 heading for each of the 6 required section names (case-insensitive): `Description`, `Steps to Reproduce`, `Actual Result`, `Expected Result`, `Environment`, `Root Cause Analysis`.
3. No heading uses `"level": 3`.

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

## Step A4 — Resolve TC steps for non-compliant bugs

For each non-compliant bug, scan its `issuelinks` for a `Defect`-type link to a Test Case. If found and Xray is available, fetch the TC's Xray steps to use as the basis for repair.

```python
def get_tc_from_links(issuelinks):
    for link in issuelinks:
        if link["type"]["name"] == "Defect":
            for direction in ("inwardIssue", "outwardIssue"):
                if direction in link:
                    return link[direction]["key"], link[direction]["id"]
    return None, None
```

Then run the Xray get-test-steps operation with `issue_id=tc_id` for each — fire all in parallel if there are several.

Collect one repair job per non-compliant bug, containing: `key`, `summary`, current ADF, `tc_key`, `xray_steps`.

## Step A5 — Repair dispatch

- **1 non-compliant bug** → repair in main context, using the strategy table below (no subagent).
- **2+ non-compliant bugs** → spawn one repair subagent per bug in a **single message** so they run in parallel. Use the Repair Subagent Template at the bottom of this file.

## Step A6 — Print the audit summary

```
=== DESCRIPTION AUDIT ===
Bugs checked:      <N>
Already compliant: <X>
Repaired:          <Y>
  PROJ-XXX — xray-steps   (TC steps used to populate all sections)
  PROJ-YYY — strategy-a   (table extracted to 6-section h2)
  PROJ-ZZZ — strategy-c   (existing content wrapped + placeholders added)
Errors:            <E>
=========================
```

After printing, proceed to bug-mode dispatch.

## Repair strategies

Pick the first one that fits the bug:

### xray-steps — Xray steps were fetched
- Description:        narrative from the bug summary — explain what is broken and its impact
- Steps to Reproduce: orderedList — each step is `"{action}"` plus `" — {data}"` if data is non-empty and not `"-"`
- Expected Result:    the `result` field of the last Xray step that is non-empty
- Actual Result:      any existing actual-result text from the current description, else `"TBD"`
- Environment:        bulletList — use real values from the current description if present, else placeholders per `conventions.md`
- Root Cause Analysis: `"TBD — under investigation"`

### strategy-a — current description contains a table node
- Extract the Action + Data columns as numbered steps
- Take the last non-dash Expected Result and Actual Result column values
- Description = narrative from the bug summary

### strategy-b — current description has headings but some/all use level 3
- Walk the ADF and set every heading node to level 2
- Append placeholder nodes for any of the 6 sections still missing

### strategy-c — current description has no heading structure
- Wrap ALL existing content nodes under a `Description` h2 heading
- Append the other 5 sections as placeholders

### strategy-d — description is null or empty
- Build the full 6-section template using the bug summary as the Description paragraph
- All other sections get placeholder values

## Repair Subagent Template

```
You are repairing one Jira Bug description to conform to a required 6-section h2 format.
All data is provided below. Do NOT ask any questions. Execute the repair and return the result.

## Required reading (do this first)
Read these files for ADF helpers and tool patterns:
- <ABSOLUTE_PATH_TO_SKILL>/references/conventions.md

## Access
- Jira tooling is connected (the dispatcher verified this).
- Use whichever connected Jira tool is available — pick by intent.
- Cloud / workspace ID: <CLOUD_ID>

## Bug to repair
- Project key:        <PROJECT_KEY>
- Bug key:            <BUG_KEY>
- Summary:            <BUG_SUMMARY>
- Linked TC key:      <TC_KEY or "none">
- Xray steps:         <JSON array of {action, data, result} objects, or []>
- Current description ADF: <CURRENT_ADF_JSON>

## Strategy
Pick the first one that fits (see audit.md):
  xray-steps | strategy-a | strategy-b | strategy-c | strategy-d

Build the repaired ADF using build_bug_description(...) from conventions.md.
All headings must be level 2.

## Update the issue
Call the edit-issue operation with:
  cloudId:      <CLOUD_ID>
  issueIdOrKey: <BUG_KEY>
  fields:       {"description": <repaired_adf>}
  contentFormat: "adf"

## Return format (required)
KEY: <BUG_KEY>
STRATEGY: <xray-steps | strategy-a | strategy-b | strategy-c | strategy-d>
STATUS: ok
ERROR: none
```
