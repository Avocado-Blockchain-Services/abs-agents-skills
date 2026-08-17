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
`validate_setup`, and `register_pr`.

If these tools are not available in the session, the MCP server is not
connected. Stop and point the user to the installation instructions in this
plugin's README (https://github.com/Avocado-Blockchain-Services/abs-agents-skills)
before continuing.

The optional tool `test_connection` may also be present; Phase 5 uses it only when available.

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
