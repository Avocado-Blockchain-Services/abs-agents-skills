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
  version: "0.3.4"
---

<!-- Content adapted from persea-agents-api:src/mcp/prompts/logcore_setup.py
     and src/mcp/tools/logging_snippet.py (development @ 2bf8103, which
     includes the field constraints from PR #31, plus the required build
     commands and `set_build_commands` in PR #32 and the parsed `error.stack`
     in PR #34 — 2026-08-18). Keep in sync. -->

# Persea AI Agents Platform — Project Onboarding

Set up logcore logging integration for the user's project by following the
phases below in order.

## Prerequisites

This skill drives tools served by the Persea AI agents platform MCP server:
`check_github_connection`, `get_github_auth_url`, `list_organizations`,
`list_projects`, `create_project`, `add_service`, `set_build_commands`,
`get_service_config`, `get_logging_snippet`, `get_infra_setup`,
`register_writer_identity`, `validate_setup`, and `register_pr`.

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
   - `setup_command` and `test_command`: what a FRESH CLONE of this repo runs
     to install its dependencies, and to run its test suite. **Read them out of
     the project** — `package.json` scripts, pyproject, Makefile, the README's
     own instructions — rather than assuming. Common pairs:

     | project | `setup_command` | `test_command` |
     |---|---|---|
     | npm | `npm ci` | `npm test` |
     | pnpm | `pnpm install --frozen-lockfile` | `pnpm test` |
     | yarn | `yarn install --frozen-lockfile` | `yarn test` |
     | poetry | `poetry install` | `poetry run pytest` |
     | pip | `pip install -r requirements.txt` | `pytest` |
     | go | `go mod download` | `go test ./...` |

     Both are **required** to register a service, and this is not paperwork.
     The debugger clones the repo, installs it, reproduces the bug and verifies
     its own fix — so a service without them registers fine and is then skipped
     with "has no branch/setup/test command configured", minutes later, in a job
     the developer never sees. If the repo genuinely has no test script, say so
     and agree a command with the developer instead of inventing one that will
     fail on first use.
2. Call `list_projects` to check if a project already exists for this repo.
   - If a project exists with this repo, use it and skip to Phase 3 — but first
     confirm the service still has both build commands. A service registered
     before they were required has neither, and the debugger skips it in
     silence. Call `set_build_commands` with the `service_id` and the pair you
     detected; it fixes the service in place, so there is no need to delete and
     re-register anything.
   - If no project exists:
     a. Call `list_organizations` to get the user's organizations.
     b. If multiple organizations, present them as a list and let the user choose.
     c. Ask for a project name and description.
     d. Call `create_project` with the selected `organization_id`. Every entry
        in `services` needs `setup_command` and `test_command` as well — the
        call is refused if any one of them is missing, and the error names the
        repo that is short.
   - If a project exists without this repo, ask: "Add this repo to project
     '{name}'?" If yes, call `add_service` with the project id, repo, branch,
     service type, `setup_command`, `test_command`, and language.
3. `add_service` is idempotent on `(repo_full_name, branch)`. When a service for
   that pair already exists it returns the existing one with
   `already_existed: true` instead of creating a second. **Read that field and
   report it** — "this repo was already registered, reusing it" — rather than
   telling the developer you created something. Retrying the call is safe.
   - Only the pair is idempotent, not the repo alone: the same repo on two
     branches is a legitimate staging/production pair, and both get their own
     service and their own `service_id`.
   - So pass the branch you actually detected. Passing a different branch than
     the one already registered creates a SECOND service for the same repo,
     which is how a project ends up with two entries that look identical in the
     UI but carry different ids.
4. Ask: "What is your target branch for PRs?" (suggest the detected default
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
   - **`field_patterns` and `field_enums` are the formats the gateway enforces.**
     A value of the right kind but the wrong shape is a **422**, and these are
     the ones that actually bit real integrations:

     | Field | Rule | The mistake it catches |
     |---|---|---|
     | `insert_id` | `^[0-9a-f]{32}$` | A full SHA-256 digest is **64** chars and is rejected. **Truncate to the first 32** — the shipped loggers do (`sha256(...)[:32]` / `.slice(0, 32)`) |
     | `env` | `prod`, `staging`, `dev`, `test`, `local` | It is spelled **`prod`**, not `production` |
     | `service` | `^[a-z0-9][a-z0-9._-]{0,62}$` | Uppercase or spaces in a service name |
     | `source_project` | `^[a-z][a-z0-9-]{4,28}[a-z0-9]$` | Anything under 6 characters, and the empty string |

     `validate_setup` checks these, so Phase 5 catches them before the developer
     does — but only if you run it on the code's REAL output.
   - **`error.stack` is a list of PARSED FRAMES, never the raw traceback
     string.** There is no `stack_trace` field; logcore forbids unknown fields,
     so one fails the whole entry. Each frame is
     `{function, file, line, column, inApp}`:

     ```json
     "error": {
       "type": "TypeError",
       "message": "Cannot read properties of undefined",
       "stack": [
         {"function": "checkout", "file": "app.js", "line": 1,
          "column": 48213, "inApp": true}
       ]
     }
     ```

     Three details decide whether this actually works:

     - **Innermost first.** The frame that threw is index 0. logcore takes the
       first `inApp` frame as the issue's top location, so the wrong order
       groups every error in a service under whatever entry point they share.
       JS `error.stack` is already in this order; Python's
       `traceback.extract_tb` is the reverse and must be flipped.
     - **Follow the exception chain to its root, and put the root first.** A
       wrapped exception's own traceback stops at the `raise` — the line that
       actually broke is not in it. Wrapping is ordinary in a backend (a
       repository tapping a driver error, a service layer relabelling), and
       since logcore keys the issue on the first `inApp` frame, stopping at the
       wrapper collapses every error that layer re-raises into one issue. Every
       language exposes the chain: Python `__cause__`/`__context__`, Java
       `getCause()`, Ruby `cause`, JS `error.cause`, Go `errors.Unwrap`. Honour
       an explicit suppression where the language has one — Python's
       `raise ... from None` is the author saying the context is noise. Keep
       `type` and `message` from the exception actually raised: that is what
       the service reported and what its own logs will say.
     - **`inApp`, not `in_app`.** logcore reads this key off the raw payload
       before validating, so snake_case passes validation and is then never
       seen: every frame counts as not-in-app and the grouping loses the frames
       it works from.
     - **Keep `column`.** A production bundle puts every frame on line 1, so
       the column is the only thing that locates the frame in the source map.

     This is not cosmetic. Symbolication and the fingerprint are both computed
     from these frames, and on a backend the failure is silent: the log is
     accepted and grouped, and the emission to the classifier dies afterwards.
     The error never reaches anyone.
3. Read the project's existing code to understand its patterns and style.
   Locate the extension points you will register with: the entry point, the
   shared HTTP client instance, the middleware chain. You need to know where
   they are before you generate anything.
4. Put the integration LOGIC in new files. You may EDIT existing files, but
   only to register with an extension point — never to restructure what is
   there. Follow this hierarchy, stopping at the first rung that applies:
   a. **Use the extension point the library already provides.** axios exposes
      `interceptors`, Angular has `HttpInterceptor`, Express and FastAPI have
      middleware, Django has middleware. When one exists the edit is ONE line
      at the place the client or app is constructed, and no call site changes.
   b. **If there is none, install from a new module.** `fetch` has no
      interceptor. Patch it from a new file, install it explicitly from the
      entry point, and return an uninstall function. One global effect,
      localized and reversible — or skip HTTP instrumentation entirely and
      rely on the global handlers, which already catch failures that
      propagate.
   c. **Never invent an abstraction.** Do NOT introduce a wrapper, a `request`
      helper, a base client, or any layer that forces call sites to be
      rewritten. Rewriting how the project makes its calls is not integration,
      it is a refactor the developer did not ask for. If instrumenting a call
      path would require touching call sites, do not instrument it — say so
      instead.
   The generated code itself is:
   - For frontends (http — the gateway resolves identity from the API key):
     - A logcore client module (HTTP POST to the logcore endpoint with an
       `x-api-key` header)
     - **The client has to be able to emit WITHOUT an exception**, and to carry
       `labels`, `context` and `fingerprint` — every one of them a valid entry
       field on this transport. A client whose only entry point takes an `Error`
       covers exactly the failures that throw, and the ones that hurt most do
       not: a bug that computes the wrong value raises nothing, so no global
       handler and no error boundary can ever see it. The app itself is the only
       thing positioned to report it, and it needs a call to make. Shape it as
       `log(severity, message, {error, context, labels, fingerprint})` with a
       thin `logError` on top, or as whatever the project's naming calls for —
       the wire format is the contract, the function names are not.
     - An error boundary or global error handler (window.onerror,
       unhandledrejection)
     - An env var example (.env.example or similar) with **all three** variables
       the client module reads, not just the key:

       ```
       <PREFIX>LOGCORE_ENABLED=true
       <PREFIX>LOGCORE_URL=<the `endpoint` from get_service_config>
       <PREFIX>LOGCORE_KEY=<the `api_key` from get_service_config>
       ```

       `<PREFIX>` is whatever the project's bundler requires to expose a
       variable to browser code, and it is **not optional** — an unprefixed
       variable is simply absent at runtime, so the logger silently never sends
       anything:

       | Tooling | Prefix |
       |---|---|
       | Vite | `VITE_` |
       | Next.js | `NEXT_PUBLIC_` |
       | Create React App | `REACT_APP_` |
       | Astro | `PUBLIC_` |
       | Nuxt | `NUXT_PUBLIC_` |

       Detect it from the project (`vite.config`, `next.config`, etc.) rather
       than assuming; if you cannot tell, ask the developer instead of guessing.

       `endpoint` is **logcore's gateway**, a different service from the agents
       API. The client posts to `<PREFIX>LOGCORE_URL` + `/v1/logs`. If
       `endpoint` comes back empty the environment is not configured — say so
       and stop rather than inventing a URL.
     - **The wiring**: install the global handlers and mount the error
       boundary at the entry point. A boundary that wraps nothing and a
       handler nobody installs report nothing, no matter how correct the
       module is.
     - Entry fields stay FLAT: `service`, `env`, `insert_id` are top-level.
       This path never touches Cloud Logging, so nothing is promoted.
     - **The entry is not the request body.** POST an envelope to
       `<LOGCORE_URL>/v1/logs` with the `x-api-key` header:

       ```json
       { "schema_version": 1, "entries": [ /* one or more entries */ ] }
       ```

       A bare `{"entries": [...]}` is rejected with **422** for a missing
       `schema_version`. `wire_shape` and `golden_entry` describe ONE ENTRY —
       see `transport_info.request_envelope` for the wrapper.
     - **Omit `source_project` for a browser app.** It runs in no GCP project,
       and the schema validates the field as a GCP project id whenever it is
       present — so sending `""` is a **422**, while leaving it out is accepted.
       `get_service_config` returns `null` for it on a frontend: pass that
       through as absent, do not coerce it to an empty string.
   - For backends (stdout — the sink can only identify the sender by
     service_id):
     - A structured logger module (JSON to stdout — Cloud Logging captures it)
     - A logging middleware for the framework
     - **The wiring**: register that middleware on the app. Mind the ordering
       semantics of the framework — Express error middleware goes last and
       takes four arguments; FastAPI runs `add_middleware` in reverse order of
       registration. Registered in the wrong position it catches nothing while
       looking installed.
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
3. **Check whether the sink already exists before asking the developer for
   anything.** Run this yourself — it is a read, and it costs one call:

   ```bash
   gcloud logging sinks describe errors-to-logcore \
     --project=<gcp_project_id> --format="value(writerIdentity)"
   ```

   A project onboarded before — or reset between demos — still has its sink:
   what gets lost is the platform-side registration, not the GCP resource. If
   this prints a service account you already have the `writerIdentity`, so skip
   to step 5. Sending the developer to create a sink that exists buys an
   `ALREADY_EXISTS` and a round trip that taught nobody anything.
4. Only when it does not exist: give the developer the create command from
   `get_infra_setup` and ask them to run it. That one writes to their project,
   so it stays theirs to run. Then read the identity back with the describe
   above rather than asking them to copy it out of the output.

   If gcloud is unavailable to you or refuses on their project, say so and ask
   them to paste the `writerIdentity` — but ask because you tried, not instead
   of trying.
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
5. **Verify the wiring, not just the emitter.** Steps 1-3 prove the module
   PRODUCES a correct entry. They do not prove anything CALLS it — a perfectly
   valid module nobody invokes reports exactly nothing, and that failure is
   silent. So also confirm the registration is real: the entry point imports
   and calls the installer, the boundary wraps the component tree, the
   middleware sits in the chain.
6. **Run the project's own build and tests after editing** (`npm run build`,
   `pytest`, `go build`, whatever the repo uses). Adding a file is inert if it
   is wrong; editing an entry point is not — a bad edit breaks the app instead
   of merely failing to log.
   - If it fails, REVERT your edit to that file and report it. Never leave a
     broken entry point behind: an integration that does not log is
     recoverable, an app that does not start is not.
   - If you cannot identify the framework's extension point with confidence,
     do NOT guess. Skip the edit, ship the new modules, and tell the developer
     exactly what to wire and where — the pre-existing behaviour.

## Phase 6: Create PR

1. Create a feature branch: `git checkout -b feat/logcore-integration`
2. Stage all generated files.
3. Commit with message: `feat(logcore): integrate structured logging`
4. Push and create a PR targeting the developer's chosen branch.
5. Call `register_pr` with the service id and PR URL to track the PR on the
   platform.
6. Report the PR URL to the developer.

## Code Quality Checklist

These are the MINIMUM bar, not the ceiling. They are verifiable by reading the
diff — apply them instead of reaching for a named design pattern. The
project's own conventions always win over your personal preference.

Every transport:

- Logging must never break the app. Swallow transport failures; never
  propagate an exception or block the user's flow because a log could not be
  delivered.
- Add NO new runtime dependencies. Use what the project already has.
- The module must be exercisable with the transport stubbed — no network, no
  credentials. Phase 5 depends on this; an untestable module cannot be
  validated.
- Anything installed globally returns its own uninstall/cleanup function.
- Comments explain WHY, not WHAT. A deterministic insert_id earns a line; a
  comment restating the function name is noise.
- Never log PII or secrets: no request bodies, tokens, or auth headers.
- One module, one purpose. Keep the client, the global handlers, and the
  framework adapter in separate files.

http (frontend): never block navigation or the render path — the request is
fire-and-forget and survives page unload.

stdout (backend): never emit at import time; one JSON object per line, no
interleaved partial writes.

## Critical Rules

- **Keep edits to existing code minimal, localized, and justified.** The
  integration logic belongs in new files. Every edit to a file the developer
  already had must be a registration at an extension point — importing and
  calling an installer, adding an interceptor, mounting middleware, wrapping
  the root component. Never restructure, reformat, rename, or refactor code
  you are passing through, and never rewrite call sites. If you cannot express
  the change as "register X at Y", it does not belong in this PR.
- NEVER hardcode API keys in source code. Use environment variables.
- Generate code that fits the project's existing patterns — do not use
  templates.
- **Any language and framework is supported, snippet or not.** The contract is
  `wire_shape` + `golden_entry`, which are language-independent, and Phase 5
  verifies what your code actually emitted. A missing reference snippet is not
  a reason to refuse, to guess, or to substitute another language's example.
- For frontends, all three variables go in the environment with the bundler's
  browser prefix — `<PREFIX>LOGCORE_ENABLED`, `<PREFIX>LOGCORE_URL` and
  `<PREFIX>LOGCORE_KEY`. The key alone is not enough: without the URL the client
  has nowhere to post, and without the prefix none of them reach browser code at
  all. Never hardcode the key in source.
- For backends, no API key is needed in code — Cloud Logging captures stdout
  automatically — but LOGCORE_SERVICE_ID is required, and it is the one field
  without which nothing works: logcore discards a sink-delivered log that
  declares no service_id, because a service NAME is not unique across
  customers.
- At the end, report the wiring you applied — name the files you edited and
  show the diff, so the developer reviews it rather than discovering it.
- If you could not wire it (unknown framework, build failed and you reverted),
  say plainly that **the integration is incomplete and reports nothing yet**,
  and give the exact steps left. Do not describe it as done. A developer who
  believes logging is live and has none is worse off than one who knows it is
  pending.
