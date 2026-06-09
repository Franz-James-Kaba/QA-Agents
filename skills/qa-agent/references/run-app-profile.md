# App Profile (Optional)

Without a profile, the runner uses accessibility-first locators (`get_by_role`, `get_by_label`, `get_by_text`) plus quoted-text and testid heuristics. That works for most modern web apps.

If your app has selectors that don't follow accessibility conventions — or repeated CSS classes the test cases reference — write a profile so the runner can use them directly.

A profile is a single markdown file with a YAML front-matter block. Pass it with `--profile <path>`.

## Profile schema

```yaml
---
name: "Example App"
url_default: "https://staging.example.com"

# Roles map test-case "user" values to environment variables.
roles:
  player:
    username_env: "PLAYER_USERNAME"
    password_env: "PLAYER_PASSWORD"
  admin:
    username_env: "ADMIN_USERNAME"
    password_env: "ADMIN_PASSWORD"

# Login recipes per role. The runner uses these in do_login().
login:
  default:
    url: "/login"
    fields:
      - { selector: '[data-cy="login-username-input"]', env: "PLAYER_USERNAME" }
      - { selector: '[data-cy="login-password-input"]', env: "PLAYER_PASSWORD" }
    submit: '[data-cy="login-submit-btn"]'
    success_pattern: '(?!.*/login)'
  admin:
    url: "/admin/login"
    fields:
      - { selector: '[name="username"]', env: "ADMIN_USERNAME" }
      - { selector: '[name="password"]', env: "ADMIN_PASSWORD" }
    submit: 'button[type="submit"]'

# Selectors map keywords-in-action to CSS selectors.
# When a step's action contains one of `keywords` (word-boundary, case-insensitive),
# the runner uses `selector` instead of generic resolution.
selectors:
  - keywords: ["accept", "accept button"]
    selector: ".btn-accept"
    kind: click
  - keywords: ["contest", "contest button"]
    selector: ".btn-contest"
    kind: click
  - keywords: ["contest textarea", "contest reason"]
    selector: ".contest-textarea"
    kind: fill
  - keywords: ["force confirm"]
    selector: ".btn-force-confirm"
    kind: click

# Optional pre-TC hooks. Run before each TC unless preserveSession=true.
# Each hook is a free-form prose instruction the execution subagent interprets.
hooks:
  before_each_tc:
    - "Reset state: clear all PENDING matches via DELETE /api/test/reset."
  after_login:
    - "Wait for the dashboard heading to appear."
---

# Human-readable notes (optional)

Anything below the front-matter is for humans — the runner ignores it.
Use this section to document app quirks, test-data conventions, known
flaky areas, etc.
```

## What the runner reads from the profile

- `roles` — maps a TC's `user` value to credential env var names.
- `login.<role>.url` / `fields` / `submit` / `success_pattern` — used by `do_login` for re-authentication mid-run.
- `selectors[]` — `match_profile_selector` checks this list first inside `click_element` and `fill_element`. The first entry whose `keywords` match the action wins.
- `hooks.before_each_tc` — free-form instructions run by the execution subagent before each TC (unless `preserveSession: true`).
- `hooks.after_login` — free-form instructions run once after each login.

## Hook semantics

Hooks are interpreted by the execution subagent, not executed as code. A hook like `"Reset state: clear all PENDING matches via DELETE /api/test/reset"` tells the subagent to make that HTTP call before each TC. The subagent uses its judgment — it can decline a hook that looks unsafe (writing to production, deleting unrelated data).

If your team's hooks need to be code, put them in a separate Python module in your repo and reference it from a hook line: `"Run scripts/qa_hooks.py::reset_state(base_url, admin_token) before each TC"`.

## How profiles are loaded

```python
import yaml, re, os

def load_profile(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return None
    return yaml.safe_load(m.group(1))
```

## Where to keep profiles

In your repo, alongside your tests:

```
your-repo/
├── qa/
│   ├── profiles/
│   │   ├── staging.md
│   │   ├── production.md
│   │   └── local.md
│   └── test-data/...
```

Then `/run --from-xray PROJ-100 --url https://staging --profile qa/profiles/staging.md`.
