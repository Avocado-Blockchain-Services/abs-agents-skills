# abs-agents-skills — Design Spec

**Date:** 2026-08-17
**Status:** Approved for implementation
**Owner:** Marco (implementation by the platform team, not the MCP team)

## Overview

`abs-agents-skills` is the public distribution repo for agent skills that teach AI coding
agents (Claude Code, opencode, Cursor, Codex, …) how to onboard a user's project onto the
Persea AI agents platform using the platform's MCP server.

The MCP server already exists in `persea-agents-api` (mounted at `/mcp/lite`) and exposes
onboarding tools (`create_project`, `check_github_connection`, `get_logging_snippet`,
`test_connection`, …) plus a server-side `logcore_setup` MCP prompt. MCP prompts are
user-invoked and unevenly supported across clients, so the industry-standard complement is
a **skill**: a model-discovered SKILL.md that triggers automatically when a user asks to
integrate with the platform. This repo ships that skill, following the same pattern Stripe,
Figma, Supabase, and Auth0 use (skills bundle + per-agent install paths).

This MVP is **skills-only**. It deliberately ships no MCP connection config; MCP-side
changes are follow-ups owned by Cristhian (see "Follow-ups" below).

## Goals

- One public repo installable today by any early tester:
  - Claude Code: `/plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills`
    → `/plugin install perseaai-agents@abs-agents-skills`
  - Any other agent: `npx skills add Avocado-Blockchain-Services/abs-agents-skills`
- One skill, `perseaai-agents-setup`, encoding the 6-phase onboarding playbook.
- Frontmatter that is 100% agentskills.io-spec compliant so the same file serves every
  agent unmodified.

## Non-goals (this iteration)

- Shipping `.mcp.json` / auto-configuring the MCP connection (follow-up, after the MCP
  rebrand).
- Cursor/Codex native plugin manifests, official directory submissions, CI, version
  automation.
- A troubleshooting skill, or per-phase skill splitting.
- Any change to `persea-agents-api` code.

## Naming

| Thing | Name |
|---|---|
| Repo | `Avocado-Blockchain-Services/abs-agents-skills` (public) |
| Skill | `perseaai-agents-setup` |
| Plugin (Claude Code) | `perseaai-agents` |
| Recommended MCP server key (future) | `perseaai-agents` |

Rationale: "logcore" names the logging microservice, not the platform. The customer-facing
brand for the platform integration is **perseaai-agents**. Inside skill content, "logcore"
is still used where it correctly refers to the logging service itself (log schema, sink,
intake endpoints).

## Repo layout

```
abs-agents-skills/
├── .claude-plugin/
│   ├── plugin.json          # name: perseaai-agents, version 0.1.0, skills-only
│   └── marketplace.json     # lists this repo's plugin → repo doubles as its own marketplace
├── skills/
│   └── perseaai-agents-setup/
│       └── SKILL.md
├── docs/superpowers/specs/  # this spec
├── LICENSE                  # Apache-2.0
└── README.md
```

## The skill: `perseaai-agents-setup/SKILL.md`

### Frontmatter

Strictly the agentskills.io contract — required `name` + `description`, optional `license`
and `metadata`. No agent-specific top-level keys (`allowed-tools`,
`disable-model-invocation`, …).

```yaml
---
name: perseaai-agents-setup
description: >-
  Use when the user wants to connect a project or repository to the Persea AI
  agents platform, integrate logcore structured logging, register a service,
  connect their GitHub account to the platform, set up log forwarding
  (stdout/Cloud Logging sink or HTTP), or onboard a new frontend/backend for
  platform log detection. Requires the platform MCP server to be connected.
license: Apache-2.0
metadata:
  author: Avocado Blockchain Services
  version: "0.1.0"
---
```

The description is the highest-leverage text: concrete "use when…" phrasing listing the
user intents that should trigger it.

### Body

Adapted from `LOGCORE_SETUP_PROMPT`
(`persea-agents-api:src/mcp/prompts/logcore_setup.py`, `development` branch as of
2026-08-17). An HTML comment at the top marks the manual-sync relationship:
`<!-- Content adapted from src/mcp/prompts/logcore_setup.py — keep in sync -->`.

Structure:

1. **Prerequisites** — the platform MCP server must be connected. Tools are referenced by
   **bare names** (`check_github_connection`, `create_project`, …) because the MCP
   registration key — and therefore any `mcp__<key>__` prefix — is user-controlled and
   not shipped by this repo. If the tools are unavailable, direct the user to the README's
   connection instructions.
2. **Phase 1: GitHub connection** — `check_github_connection`; if absent,
   `get_github_auth_url` → user installs the GitHub App in browser → poll until connected.
3. **Phase 2: Project setup** — detect repo/branch/language/framework/service_type
   locally; `list_projects` / `list_organizations` / `create_project` / `add_service`;
   ask for the PR target branch.
4. **Phase 3: Code generation** — `get_service_config` + `get_logging_snippet`; generate
   integration code as **new files only**, matching project conventions (frontend: HTTP
   client + error boundary; backend: structured JSON-to-stdout logger + middleware).
5. **Phase 4: GCP infrastructure (backend only)** — `get_infra_setup` → user runs gcloud
   commands → `register_writer_identity`.
6. **Phase 5: Validate** — `validate_setup` on a sample entry; `test_connection` for E2E.
7. **Phase 6: PR** — open the integration PR; `register_pr`.

## Claude Code plugin manifests

`.claude-plugin/plugin.json`:

```json
{
  "name": "perseaai-agents",
  "version": "0.1.0",
  "description": "Onboard projects onto the Persea AI agents platform (logcore logging integration)."
}
```

`.claude-plugin/marketplace.json` lists the single plugin with source `"./"` so the repo
is its own marketplace — no separate marketplace repo, no infrastructure.

## README

Three install sections plus a stage notice:

1. **Claude Code** — the two `/plugin` commands.
2. **Other agents** — `npx skills add Avocado-Blockchain-Services/abs-agents-skills`
   (with `--agent opencode`, `-g`, `--copy` examples and where files land per scope).
3. **Connecting the MCP server** — documentation-only manual config snippet (current dev
   Cloud Run URL, `type: http`, OAuth), explicitly marked **temporary** until the MCP
   rebrand lands; nothing is auto-installed by this repo.
4. Early-stage notice: dev endpoint, URL and server naming will change.

## Verification (manual, no CI)

1. `npx skills add` this repo with `--agent opencode` and `--agent claude-code`; confirm
   the skill appears in each agent's skill list (project and `-g` scopes).
2. Fresh Claude Code session: add marketplace, install plugin, confirm the skill loads
   and triggers on a natural request ("connect this repo to the platform").
3. One live onboarding run against a scratch repo (reuse the AMPS docs-scribe-test harness
   pattern) driving the skill end-to-end through at least Phases 1–3 against the dev MCP.

## Follow-ups (owned by Cristhian — MCP side, later)

1. **Rebrand the MCP server** from "logcore" to **perseaai-agents**: FastMCP server
   name, the server `instructions` field (currently one line — should summarize the
   onboarding flow), and the recommended client registration key. "logcore" remains the
   name of the logging microservice only.
2. **After the rebrand:** add `.mcp.json` to this repo's plugin so Claude Code users get
   the MCP connection + skill in a single install (the full vendor-bundle pattern).
3. **On merge of `feat/mcp-service-id-emitter`:** re-sync the skill body with the new
   contract (language-agnostic wire contract, `service_id` in stdout transport, Cloud Run
   label promotion) in one coordinated pass with the server prompt.

## Decisions log

- Skills-only MVP; MCP config excluded by explicit decision (Marco, 2026-08-17).
- Content based on `development` contract, not the in-flight branch.
- Hand-authored skill (Approach A) over generated-from-prompt (B) or thin wrapper (C):
  duplication accepted for MVP; sync is manual with a marker comment.
- Bare tool names over `mcp__<key>__` prefixes: portable across agents and registration
  keys.
- Dev Cloud Run URL in docs for now; stable domain later.
