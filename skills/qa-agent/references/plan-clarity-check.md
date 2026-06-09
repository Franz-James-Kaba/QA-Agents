# Story Clarity Check

Decides whether a story has enough detail to write meaningful test cases. If not, the story is flagged with a Jira comment and skipped.

## Locate acceptance criteria

Check in this order; use the first non-empty:

1. `customfield_10016` — the most common Jira AC custom field
2. Any other field whose name contains "acceptance" or "criteria" (case-insensitive) — inspect `issue.names` from a `expand=names` fetch
3. A section headed "Acceptance Criteria" embedded in the description text

Combine the description and the acceptance criteria into a single content block for analysis.

## Clarity check

A story is **too unclear to test** if ANY of the following are true:

- Combined content is empty, null, or under 20 words
- No acceptance criteria found in any location
- Content contains only a generic user story statement with no defined behaviour
- Contradictory requirements within the same story
- Exclusively vague language with no observable outcomes (e.g. "improve", "make it better", "should work well", "enhance performance")

A story passes if it has at least one concrete, observable behaviour to test — even if other parts are vague.

## If unclear — flag and skip

Post a comment on the Jira story using the add-comment operation:

```
🚩 Test Case Generation — Story Flagged

This story was skipped during automated test case generation because it
lacks sufficient detail for effective testing.

Gaps identified:
• <specific gap 1>
• <specific gap 2>
• <specific gap 3 — as many as apply>

Please update the description and acceptance criteria to address the gaps
above, then re-run the test case generator.
```

The comment body can be ADF or markdown depending on what the connected tool accepts — use `content_format: "markdown"` if supported, otherwise build an ADF doc with a paragraph + bullet list.

Add the story to the **Flagged** list (printed in the plan-mode final report) with the gaps. **Do not generate any test cases for this story.** Move to the next.
