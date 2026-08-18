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
  version: "0.2.0"
---

<!-- Content adapted from persea-agents-api:src/mcp/prompts/logcore_setup.py
     (development branch @ e5bda30, 2026-08-17) — keep in sync. -->

# Persea AI Agents Platform — Project Onboarding

Set up logcore logging integration for the user's project by following the
phases below in order.

## Prerequisites

This skill drives tools served by the Persea AI agents platform MCP server:
`check_github_connection`, `get_github_auth_url`, `list_organizations`,
`list_projects`, `create_project`, `add_service`, `get_service_config`,
`get_logging_snippet`, `get_infra_setup`, `register_writer_identity`,
`validate_setup`, and `register_pr`.

If these tools are not available in the session, the MCP server is not
connected. Stop and point the user to the installation instructions in this
plugin's README (https://github.com/Avocado-Blockchain-Services/abs-agents-skills)
before continuing.

The optional tool `test_connection` may also be present; Phase 5 uses it only
when available.

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
   - `service_type`: WEB_APP_FRONTEND for frontends, BACKEND for anything
     server-side. The type says how logs reach logcore (gateway vs sink), NOT
     what the service is written in — the language is its own field, so do not
     pick a type based on it. PYTHON_BACKEND is the legacy spelling of BACKEND.
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
   env, and **service_id**.
2. Call `get_logging_snippet` with the language, framework, and transport to
   get the contract. Transport is `stdout` for backends, `http` for frontends.
   - **The contract is `transport_info.wire_shape` and
     `transport_info.golden_entry`, not the example code.** `wire_shape`
     declares which fields are top-level, which are nested and under which
     key, and which must use a promoted name. `golden_entry` is the literal
     JSON a correct emitter produces — in ANY language. Build to those two and
     the language does not matter.
   - `example` is a reference implementation and exists only for some
     languages. If `has_reference_snippet` is false there is NO snippet for
     this language: that is expected, not a blocker. Do NOT improvise the wire
     format and do NOT fall back to another language's transport — build from
     `wire_shape`.
   - Its `required_fields` is transport-aware: obey it exactly. The two paths
     identify the sender differently, and getting it wrong is silent.
3. Read the project's existing code to understand its patterns and style.
4. Generate logcore integration code by ONLY CREATING NEW FILES:
   - For frontends (http — the gateway resolves identity from the API key):
     - A logcore client module (HTTP POST to the logcore endpoint with an
       `x-api-key` header)
     - An error boundary or global error handler (window.onerror,
       unhandledrejection)
     - An env var example (.env.example or similar) with the API key variable
     - Entry fields stay FLAT: `service`, `env`, `source_project`, `insert_id`
       are top-level. This path never touches Cloud Logging, so nothing is
       promoted.
   - For backends (stdout — the sink can only identify the sender by
     service_id):
     - A structured logger module (JSON to stdout — Cloud Logging captures it)
     - A logging middleware for the framework
     - An env var example declaring **LOGCORE_SERVICE_ID**, whose value is the
       `service_id` from `get_service_config`. Read it from the environment;
       do NOT hardcode it, because a re-created service is issued a new id and
       an env var is fixed at deploy time rather than by editing committed
       code.
     - Cloud Run promotes ONLY `logging.googleapis.com/*` keys out of a
       structured log line. So `env`, `source_project` and `trace_id` go
       nested inside `logging.googleapis.com/labels`, and the insert id goes
       in `logging.googleapis.com/insertId`. Anything left at the top level
       stays inside jsonPayload where logcore does not read it: a top-level
       `env` silently makes every issue record env="unknown".
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
6. Remind the developer to set **LOGCORE_SERVICE_ID** on the deployed service
   (e.g. `gcloud run services update <svc> --update-env-vars
   LOGCORE_SERVICE_ID=<id>`). Without it the logger cannot declare an identity
   and logcore discards every log the sink delivers — the service will look
   configured and report nothing.

## Phase 5: Validate what your code actually emits

**Validate real output, never a hand-written sample.** A sample you compose
yourself proves only that you can write correct JSON by hand; it says nothing
about the module you just generated. This step is what makes the integration
verifiable in a language the platform ships no snippet for.

1. Run the generated logger once and capture ONE emitted line:
   - backends (stdout): execute a small script that imports the module and
     logs an error, then take the line it printed to stdout.
   - frontends (http): call the module's log function with the network call
     stubbed, and take the JSON body it would have posted.
   If it cannot be executed (no toolchain, no deps installed), say so plainly
   and validate the exact literal your code builds — then tell the developer
   the emitter was not run.
2. Parse that line and call `validate_setup` with the entry AND the SAME
   transport used in Phase 3. It defaults to "stdout", so omitting it while
   validating a frontend entry reports failures that do not apply to that
   path.
3. Errors mean logcore would reject or misattribute the log; fix the generated
   code and re-run step 1. Warnings mean it is accepted but degraded — read
   them out to the developer with what each one costs, rather than dismissing
   them.
4. If available, call `test_connection` with the service id for an E2E test.
   Read its `tested_path` and `covers_production_logs`: for a backend this
   only exercises the gateway, NOT the sink its real logs travel through, so
   a green result there does not prove production logs arrive.

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
- **Any language and framework is supported, snippet or not.** The contract is
  `wire_shape` + `golden_entry`, which are language-independent, and Phase 5
  verifies what your code actually emitted. A missing reference snippet is not
  a reason to refuse, to guess, or to substitute another language's example.
- For frontends, the API key goes in an environment variable (e.g.,
  VITE_LOGCORE_KEY, NEXT_PUBLIC_LOGCORE_KEY).
- For backends, no API key is needed in code — Cloud Logging captures stdout
  automatically — but LOGCORE_SERVICE_ID is required, and it is the one field
  without which nothing works: logcore discards a sink-delivered log that
  declares no service_id, because a service NAME is not unique across
  customers.
- At the end, briefly tell the user how to wire the generated code into their
  app (e.g., "wrap your App component with LogcoreErrorBoundary in main.jsx").
