# Test scenario — bug mode

End-to-end check for `/bug` natural-language intake. This is the smallest exercise of the skill and should pass first.

## Setup

The tester needs:
- Jira tooling connected, with at least one writable project
- (Optional) Xray Cloud tooling connected — not required for this scenario
- A project key the tester is comfortable writing throwaway bugs into (e.g. a sandbox project)

## Invocation

```
I found a bug in PROJ. The login button on the staging app doesn't work — when I click it
nothing happens, no error toast, the URL stays on /login. I'm on Chrome 138 on macOS.
This is blocking smoke testing.
```

(Substitute `PROJ` for your sandbox project key.)

## Expected behaviour

The skill should:

1. **Detect mode** as `bug` (user said "bug").
2. **Resolve project key** as `PROJ` from the mention.
3. **Verify Jira tooling** is connected. (Xray tooling is not required for manual bug filing.)
4. **Run the description audit** (`audit.md`) against `PROJ`. Print the audit summary block (could be 0/0/0/0 in a fresh project — that's fine).
5. **Parse the natural-language input** and pre-populate:
   - Title: something concise like "Login button does nothing on staging"
   - Priority: `High` or `Highest` (user said "blocking")
   - Environment: web surface, environment=staging, browser=Chrome 138, OS=macOS
   - Description: synthesised from the user's text
   - Steps to Reproduce: derived ("Navigate to /login on staging", "Click the Login button", "Observe no response")
   - Actual: "Nothing happens; no error toast; URL stays on /login"
   - Expected: derived (probably "User is authenticated and redirected" — flag as inferred)
6. **Show the pre-populated summary** and ask the user to confirm before creating.
7. **On confirm**, create the Bug ticket with a 6-section ADF description, all h2 headings level 2. Capture the returned key and numeric id.
8. **Transition the Bug to In Progress** (no Story or TC linked in this scenario, so no Story transition).
9. **Print the final report** block with the Bug key, URL, links section showing "none — no TC linked" and "none — no story linked".

## What to verify after the run

- The created Bug ticket exists in Jira.
- Opening the ticket shows the 6 expected h2 sections in order: Description, Steps to Reproduce, Actual Result, Expected Result, Environment, Root Cause Analysis.
- No h3 (level 3) headings anywhere.
- Priority is `High` or `Highest`.
- Assignee is the current user.
- Status is `In Progress`.
- No `Severity` field was set.

## Common ways this can go wrong

- **Skill creates the bug without confirming first.** Manual sub-mode must have the confirmation gate.
- **Description uses level-3 headings.** The audit's compliance rule says no level 3. The builder in `conventions.md` must produce level 2.
- **Severity field is set.** Must never set Severity unless user explicitly confirms.
- **Skill tries to use raw HTTP.** Should use the connected Jira tooling.
- **Skill asks for project key even though `PROJ-` is in the message.** Step 1 of the dispatcher should have captured it.

## Cleanup

The created bug is throwaway — delete it (or mark Done) after verifying.
