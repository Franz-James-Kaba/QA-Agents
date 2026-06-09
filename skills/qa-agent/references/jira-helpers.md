# Jira Helpers

Shared procedures used across modes: duplicate guard, assignee resolution, status transitions. All calls go through whatever Jira tooling is connected — never raw HTTP. The `cloud_id` is resolved once at session start (see `conventions.md`).

The snippets below are **operation pseudocode**, not literal Python. Treat each line that starts with a verb (`get_issue`, `create_link`, etc.) as a placeholder for "perform the corresponding operation using the connected Jira tool."

## Duplicate guard for bugs

Inspect a Test Case's issue links directly. **Do NOT** use `issueFunction` JQL — it's unreliable across projects and Jira versions.

```
def has_open_defect_bug(tc_key, cloud_id):
    """Return True if the TC already has at least one open Defect-linked Bug."""

    # 1. Fetch the TC's issue links via the get-issue operation
    issue = get_issue(cloud_id=cloud_id, key=tc_key, fields=["issuelinks"])

    defect_keys = []
    for link in issue["fields"].get("issuelinks", []):
        if link["type"]["name"] == "Defect":
            for direction in ("inwardIssue", "outwardIssue"):
                if direction in link:
                    defect_keys.append(link[direction]["key"])

    # 2. For each linked key, check if it's an open Bug
    for key in defect_keys:
        linked = get_issue(cloud_id=cloud_id, key=key, fields=["issuetype", "status"])
        is_bug  = linked["fields"]["issuetype"]["name"] == "Bug"
        is_open = linked["fields"]["status"]["statusCategory"]["name"] != "Done"
        if is_bug and is_open:
            return True
    return False
```

Skip any TC where this returns `True`. Report the skip in the final report.

## Assignee resolution

Priority order:

1. If a Story key is known: use the Story's `assignee.accountId` if non-null.
2. Otherwise: use the current user's `accountId` (resolved at session start).
3. Only ask the user explicitly if both fail.

```
def resolve_assignee(cloud_id, story_key=None, current_account_id=None):
    if story_key:
        story = get_issue(cloud_id=cloud_id, key=story_key, fields=["assignee"])
        a = story["fields"].get("assignee")
        if a and a.get("accountId"):
            return a["accountId"], a.get("displayName", "")

    if current_account_id:
        # The dispatcher already called the current-user operation once and
        # passed the account ID through — use it directly.
        return current_account_id, "<current user>"

    return None, None  # caller must ask the user
```

## Status category

```
def get_status_category(issue_key, cloud_id):
    issue = get_issue(cloud_id=cloud_id, key=issue_key, fields=["status"])
    return issue["fields"]["status"]["statusCategory"]["name"]
```

## Transition helper

```
def transition_to_in_progress(issue_key, cloud_id):
    # Fetch the available transitions for this issue
    resp = get_transitions(cloud_id=cloud_id, key=issue_key)
    transitions = resp["transitions"]

    # Find "In Progress" — exact match first, then closest containing "progress"
    target = next(
        (t for t in transitions if t["name"].lower() == "in progress"),
        next((t for t in transitions if "progress" in t["name"].lower()), None),
    )
    if not target:
        return False  # caller logs this

    # Apply the transition
    apply_transition(cloud_id=cloud_id, key=issue_key, transition_id=target["id"])
    return True
```

Always transition the issue regardless of its current state (To Do, In Progress, Code Review, Ready for Testing, Testing). Only skip if the status category is already `Done`.

## Story-to-Test-Case traversal

A Test Case is linked to a Story via the `Test` link, with the Story as outward and the Test as inward.

To find a TC's parent Story:

```
def get_parent_story_key(tc_key, cloud_id):
    issue = get_issue(cloud_id=cloud_id, key=tc_key, fields=["issuelinks"])
    for link in issue["fields"].get("issuelinks", []):
        if link["type"]["name"] == "Test" and "outwardIssue" in link:
            return link["outwardIssue"]["key"]
    return None
```

To find all TCs linked to a Story:

```
def get_test_cases_for_story(story_key, cloud_id):
    issue = get_issue(cloud_id=cloud_id, key=story_key, fields=["issuelinks"])
    return [
        link["inwardIssue"]
        for link in issue["fields"].get("issuelinks", [])
        if link["type"]["name"] == "Test" and "inwardIssue" in link
    ]
```

Each returned dict has `key` and `id` (numeric) — both are needed downstream.
