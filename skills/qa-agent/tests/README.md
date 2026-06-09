# Test Scenarios

Three end-to-end test scenarios — one per mode. Each scenario describes:

- What the tester needs to set up
- The exact invocation
- The expected behaviour at every phase
- What to verify after the run
- Common ways the skill can fail this scenario
- How to clean up

## Recommended order

Run these in this order. Each one is more expensive (and slower) than the previous.

1. **`test-bug-mode.md`** — smallest. Tests dispatcher routing, the audit, and the manual bug-filing flow with a natural-language input. Roughly 1 minute.
2. **`test-plan-mode.md`** — medium. Tests sprint resolution, the clarity check, the implementation dialogue, test case generation, and the full Xray hierarchy creation. Requires a Jira project with at least 2 stories (one clear, one vague) in an active sprint. Roughly 5–10 minutes including dialogue.
3. **`test-run-mode.md`** — largest. Tests the Playwright runner, screenshot capture, vision-based pass/fail, and the failure→bug chain. Requires Playwright installed and a running web app with linked Test Cases. Roughly 10–15 minutes.

Each scenario is self-contained — you don't have to run the previous ones first. But if you have a sandbox Jira project, running plan → run → bug in that order also exercises the cross-mode chain (plan creates TCs, run executes and fails some, run triggers bug filings).

## What "passing" looks like

A scenario passes if:

- Every step in **Expected behaviour** happens in the right order.
- Every check in **What to verify after the run** is satisfied.
- None of the **Common ways this can go wrong** symptoms appear.

If something in the skill drifts from the documented behaviour, capture the discrepancy and feed it back into the skill's references — that's the eval loop the skill-creator process recommends.
