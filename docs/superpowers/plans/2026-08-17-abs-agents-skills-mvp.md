# abs-agents-skills MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the public `abs-agents-skills` repo: one spec-compliant skill (`perseaai-agents-setup`) + Claude Code plugin manifests + bundled `.mcp.json`, installable via Claude Code marketplace and `npx skills add`.

**Architecture:** Pure-content repo, no code. The repo is simultaneously (a) an agentskills.io-compliant skills package consumable by `npx skills add`, and (b) its own Claude Code plugin marketplace via `.claude-plugin/`. The bundled `.mcp.json` connects Claude Code plugin users to the platform MCP automatically.

**Tech Stack:** Markdown + YAML frontmatter (agentskills.io spec), Claude Code plugin/marketplace JSON manifests, `skills` CLI (vercel) for verification.

**Spec:** `docs/superpowers/specs/2026-08-17-abs-agents-skills-design.md`

## Global Constraints

- Repo: `Avocado-Blockchain-Services/abs-agents-skills` (public, already exists, branch `main`).
- Working directory: `/home/marco-tamayo/Development/abs_agents/abs-agents-skills`.
- Skill name: `perseaai-agents-setup` — MUST equal its directory name.
- Plugin + MCP server key: `perseaai-agents`.
- SKILL.md frontmatter: ONLY `name`, `description`, `license`, `metadata` — no agent-specific top-level keys.
- `description` must be 1–1024 characters. `name` must be lowercase alphanumeric + hyphens, ≤64 chars.
- Skill body references MCP tools by BARE names (`create_project`, never `mcp__perseaai-agents__create_project`).
- MCP URL, verbatim: `https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp`
- "logcore" appears only where it names the logging microservice (schema, sink, intake), never as the platform/plugin brand.
- Every commit message ends with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Do NOT touch anything in `persea-agents-api`.

---

### Task 1: The skill — `skills/perseaai-agents-setup/SKILL.md`

**Files:**
- Create: `skills/perseaai-agents-setup/SKILL.md`
- Create: `scripts/validate_skill.py` (tiny checker, kept in-repo for future skills)

**Interfaces:**
- Produces: the skill directory `skills/perseaai-agents-setup/` that Task 2's `plugin.json` and Task 3's README refer to by name `perseaai-agents-setup`.

- [ ] **Step 1: Write the validation script (the "failing test")**

Create `scripts/validate_skill.py`:

```python
#!/usr/bin/env python3
"""Validate SKILL.md files against the agentskills.io frontmatter contract."""
import re
import sys
from pathlib import Path

ALLOWED_KEYS = {"name", "description", "license", "metadata"}

def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)

def main(path):
    p = Path(path)
    text = p.read_text()
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        fail("no frontmatter block delimited by --- at start of file")
    try:
        import yaml
        fm = yaml.safe_load(m.group(1))
    except ImportError:
        fail("pyyaml not installed (pip install pyyaml)")
    if not isinstance(fm, dict):
        fail("frontmatter is not a mapping")
    extra = set(fm) - ALLOWED_KEYS
    if extra:
        fail(f"non-spec top-level keys: {extra}")
    name = fm.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or len(name) > 64:
        fail(f"invalid name: {name!r}")
    if name != p.parent.name:
        fail(f"name {name!r} != directory {p.parent.name!r}")
    desc = fm.get("description", "")
    if not (1 <= len(desc) <= 1024):
        fail(f"description length {len(desc)} outside 1..1024")
    body = text[m.end():]
    if "mcp__" in body:
        fail("body references prefixed tool names; use bare names")
    print(f"OK: {path}")

if __name__ == "__main__":
    main(sys.argv[1])
```

- [ ] **Step 2: Run it to verify it fails (no SKILL.md yet)**

Run: `python3 scripts/validate_skill.py skills/perseaai-agents-setup/SKILL.md`
Expected: `FileNotFoundError` (skill doesn't exist yet).

- [ ] **Step 3: Write the skill**

Create `skills/perseaai-agents-setup/SKILL.md` with exactly this content:

````markdown
---
name: perseaai-agents-setup
description: >-
  Use when the user wants to connect a project or repository to the Persea AI
  agents platform, integrate logcore structured logging, register a service or
  repo on the platform, connect their GitHub account to the platform, set up
  log forwarding (JSON-to-stdout with a Cloud Logging sink, or HTTP for
  frontends), or onboard a new frontend/backend so the platform can detect its
  logs. Requires the platform MCP server to be connected.
license: Apache-2.0
metadata:
  author: Avocado Blockchain Services
  version: "0.1.0"
---

<!-- Content adapted from persea-agents-api:src/mcp/prompts/logcore_setup.py
     (development branch, 2026-08-17) — keep in sync. -->

# Persea AI Agents Platform — Project Onboarding

Set up logcore logging integration for the user's project by following the
phases below in order.

## Prerequisites

This skill drives tools served by the Persea AI agents platform MCP server:
`check_github_connection`, `get_github_auth_url`, `list_organizations`,
`list_projects`, `create_project`, `add_service`, `get_service_config`,
`get_logging_snippet`, `get_infra_setup`, `register_writer_identity`,
`validate_setup`, `test_connection`, and `register_pr`.

If these tools are not available in the session, the MCP server is not
connected. Stop and point the user to the installation instructions in this
plugin's README (https://github.com/Avocado-Blockchain-Services/abs-agents-skills)
before continuing.

## Phase 1: GitHub Connection

1. Call `check_github_connection` to verify GitHub is connected.
2. If not connected, call `get_github_auth_url` and ask the developer to open
   the returned `install_url` in their browser to install the GitHub App.
3. Poll `check_github_connection` until `connected` is true.

## Phase 2: Project Setup

1. Detect from the local repository:
   - `repo_full_name`: run `git remote -v` and parse the origin URL
   - `branch`: run `git branch --show-current`
   - `language`: check for package.json (TypeScript/JavaScript),
     requirements.txt/pyproject.toml (Python), go.mod (Go), Cargo.toml (Rust)
   - `framework`: check for next.config (Next.js), fastapi in deps (FastAPI),
     express in deps (Express), etc.
   - `service_type`: WEB_APP_FRONTEND for frontends, PYTHON_BACKEND for backends
2. Call `list_projects` to check if a project already exists for this repo.
   - If a project exists with this repo, use it and skip to Phase 3.
   - If no project exists:
     a. Call `list_organizations` to get the user's organizations.
     b. If multiple organizations, present them as a list and let the user choose.
     c. Ask for a project name and description.
     d. Call `create_project` with the selected `organization_id`.
   - If a project exists without this repo, ask: "Add this repo to project
     '{name}'?" If yes, call `add_service` with the project id, repo, branch,
     service type, and language.
3. Ask: "What is your target branch for PRs?" (suggest the detected default
   branch)

## Phase 3: Code Generation

1. Call `get_service_config` with the service id to get the API key, endpoint,
   and env.
2. Call `get_logging_snippet` with the language, framework, and transport to
   get the log-entry schema reference. Transport is `stdout` for backends,
   `http` for frontends.
3. Read the project's existing code to understand its patterns and style.
4. Generate logcore integration code by ONLY CREATING NEW FILES:
   - For frontends:
     - A logcore client module (HTTP POST to the logcore endpoint with an
       `x-api-key` header)
     - An error boundary or global error handler (window.onerror,
       unhandledrejection)
     - An env var example (.env.example or similar)
   - For backends:
     - A structured logger module (JSON to stdout — Cloud Logging captures it)
     - A logging middleware for the framework
   - Match the project's code style, directory structure, and conventions.

## Phase 4: GCP Infrastructure (Backend Only)

Skip this phase for frontend services (http transport).

1. Ask for the developer's GCP Project ID.
2. Call `get_infra_setup` with the service id and GCP project id to get the
   gcloud commands.
3. Tell the developer to run the gcloud command in their terminal.
4. Ask them to paste the `writerIdentity` from the output.
5. Call `register_writer_identity` with the service id, GCP project id, and
   writer identity.

## Phase 5: Validate

1. Generate a sample log entry matching the schema.
2. Call `validate_setup` with the test log to verify it's correct.
3. If available, call `test_connection` with the service id for an end-to-end
   test.

## Phase 6: Create PR

1. Create a feature branch: `git checkout -b feat/logcore-integration`
2. Stage all generated files.
3. Commit with message: `feat(logcore): integrate structured logging`
4. Push and create a PR targeting the developer's chosen branch.
5. Call `register_pr` with the service id and PR URL to track the PR on the
   platform.
6. Report the PR URL to the developer.

## Critical Rules

- **ONLY ADD NEW FILES. NEVER modify, refactor, or wrap the user's existing
  code.** The integration must be purely additive. Users want zero changes to
  their source code. Create standalone modules that the user can wire into
  their app themselves.
- NEVER hardcode API keys in source code. Use environment variables.
- Generate code that fits the project's existing patterns — do not use
  templates.
- For frontends, the API key goes in an environment variable (e.g.,
  VITE_LOGCORE_KEY, NEXT_PUBLIC_LOGCORE_KEY).
- For backends, no API key is needed in code — Cloud Logging captures stdout
  automatically.
- At the end, briefly tell the user how to wire the generated code into their
  app (e.g., "wrap your App component with LogcoreErrorBoundary in main.jsx").
````

- [ ] **Step 4: Run the validator to verify it passes**

Run: `python3 scripts/validate_skill.py skills/perseaai-agents-setup/SKILL.md`
Expected: `OK: skills/perseaai-agents-setup/SKILL.md`
(If pyyaml is missing: `pip install --user pyyaml` first.)

- [ ] **Step 5: Commit**

```bash
git add skills/ scripts/
git commit -m "feat: add perseaai-agents-setup skill

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Plugin manifests + bundled MCP config

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `.mcp.json`

**Interfaces:**
- Consumes: skill directory name `perseaai-agents-setup` from Task 1.
- Produces: plugin name `perseaai-agents` and marketplace name `abs-agents-skills` that Task 3's README install commands reference.

- [ ] **Step 1: Write `.claude-plugin/plugin.json`**

```json
{
  "name": "perseaai-agents",
  "version": "0.1.0",
  "description": "Onboard projects onto the Persea AI agents platform: connect GitHub, register services, and integrate logcore structured logging.",
  "author": {
    "name": "Avocado Blockchain Services",
    "email": "support@avocadoblock.com"
  }
}
```

(Claude Code auto-discovers `skills/` and `.mcp.json` at the plugin root; they are not declared in plugin.json.)

- [ ] **Step 2: Write `.claude-plugin/marketplace.json`**

```json
{
  "name": "abs-agents-skills",
  "description": "Agent skills for the Persea AI agents platform by Avocado Blockchain Services",
  "owner": {
    "name": "Avocado Blockchain Services",
    "email": "support@avocadoblock.com"
  },
  "plugins": [
    {
      "name": "perseaai-agents",
      "source": "./",
      "description": "Onboard projects onto the Persea AI agents platform: connect GitHub, register services, and integrate logcore structured logging."
    }
  ]
}
```

- [ ] **Step 3: Write `.mcp.json`**

```json
{
  "mcpServers": {
    "perseaai-agents": {
      "type": "http",
      "url": "https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp",
      "oauth": {}
    }
  }
}
```

- [ ] **Step 4: Validate all three parse as JSON**

Run: `python3 -m json.tool .claude-plugin/plugin.json && python3 -m json.tool .claude-plugin/marketplace.json && python3 -m json.tool .mcp.json`
Expected: each file echoed back, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add .claude-plugin/ .mcp.json
git commit -m "feat: add Claude Code plugin manifests and bundled MCP config

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: LICENSE + README

**Files:**
- Create: `LICENSE`
- Create: `README.md`

**Interfaces:**
- Consumes: marketplace name `abs-agents-skills`, plugin name `perseaai-agents`, skill name `perseaai-agents-setup`, MCP URL (Global Constraints).

- [ ] **Step 1: Fetch the Apache-2.0 license text**

Run: `curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE`
Then verify: `head -2 LICENSE` → expected to contain "Apache License".

- [ ] **Step 2: Write `README.md`**

````markdown
# abs-agents-skills

Agent skills for the **Persea AI agents platform** by Avocado Blockchain
Services. Ships the `perseaai-agents-setup` skill, which teaches AI coding
agents (Claude Code, opencode, Cursor, Codex, …) how to onboard a project onto
the platform: connect GitHub, register the repo as a service, integrate
logcore structured logging, and open the integration PR.

> ⚠️ **Early stage.** The MCP endpoint below points at our dev environment;
> the URL and server naming will change before general availability.

## Install

### Claude Code (recommended — one step gets tools + skill)

```
/plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills
/plugin install perseaai-agents@abs-agents-skills
```

This also configures the platform MCP server (key `perseaai-agents`) via the
bundled `.mcp.json`; an OAuth browser window will open on first use.

### Any other agent (opencode, Cursor, Codex, …)

Install the skill:

```
npx skills add Avocado-Blockchain-Services/abs-agents-skills
```

Useful flags: `--agent opencode` to target one agent, `-g` for user-level
instead of project-level scope, `--copy` to copy files instead of symlinking.

Then connect the MCP server manually (streamable HTTP + OAuth):

- **URL:** `https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp`
- **opencode** — add to `opencode.json`:

  ```json
  {
    "mcp": {
      "perseaai-agents": {
        "type": "remote",
        "url": "https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp"
      }
    }
  }
  ```

- **Cursor / Codex** — register a remote (streamable HTTP) MCP server named
  `perseaai-agents` with the URL above, using each client's MCP settings.

### Zero-install fallback

Connect the MCP URL above directly in any MCP client — the server itself
exposes a `logcore_setup` prompt covering the same onboarding flow.

## Usage

With the MCP connected and the skill installed, just ask your agent:

> "Connect this repo to the Persea agents platform"

The `perseaai-agents-setup` skill triggers automatically and walks through
GitHub connection → project registration → logging integration → validation
→ PR.

## Repository layout

- `skills/perseaai-agents-setup/SKILL.md` — the onboarding skill
  ([agentskills.io](https://agentskills.io) format)
- `.claude-plugin/` — Claude Code plugin + self-hosted marketplace manifests
- `.mcp.json` — bundled MCP connection for Claude Code plugin installs
- `docs/superpowers/` — design spec and implementation plan

## License

Apache-2.0
````

- [ ] **Step 3: Re-run the skill validator (regression) and commit**

Run: `python3 scripts/validate_skill.py skills/perseaai-agents-setup/SKILL.md`
Expected: `OK`. Then:

```bash
git add LICENSE README.md
git commit -m "docs: README with per-agent install matrix + Apache-2.0 license

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Publish + distribution verification

**Files:**
- Modify: none (push + verify only)

**Interfaces:**
- Consumes: everything above, pushed to `main`.

- [ ] **Step 1: Push**

```bash
git push
```

- [ ] **Step 2: Verify `npx skills` can see the skill remotely**

Run: `npx -y skills add Avocado-Blockchain-Services/abs-agents-skills -l`
Expected: listing includes `perseaai-agents-setup`. (This lists without installing.)

- [ ] **Step 3: Verify a real opencode-targeted install into a scratch project**

```bash
mkdir -p /tmp/claude-1000/-home-marco-tamayo-Development-abs-agents/b55f3f8d-364e-455b-96de-f9ef89468cf3/scratchpad/skills-install-test
cd /tmp/claude-1000/-home-marco-tamayo-Development-abs-agents/b55f3f8d-364e-455b-96de-f9ef89468cf3/scratchpad/skills-install-test
git init -q
npx -y skills add Avocado-Blockchain-Services/abs-agents-skills --agent opencode -y
ls .agents/skills/
```

Expected: `.agents/skills/` contains `perseaai-agents-setup` (symlink or dir).

- [ ] **Step 4: Manual checks for Marco (report, don't automate)**

These need an interactive session; list them for Marco instead of running them:

1. Fresh Claude Code session → `/plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills` → `/plugin install perseaai-agents@abs-agents-skills`.
2. Confirm OAuth completes and tools appear as `mcp__perseaai-agents__*`.
3. Ask "connect this repo to the Persea agents platform" in a scratch repo and confirm the skill triggers (Phases 1–3 minimum, per the spec's verification section).

- [ ] **Step 5: Commit any doc fixes found during verification, push**

```bash
git add -A
git commit -m "fix: adjustments from distribution verification

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" || echo "nothing to fix"
git push
```
