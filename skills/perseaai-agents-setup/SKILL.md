---
name: perseaai-agents-setup
description: >-
  Use when the user wants to connect a project or repository to the Persea AI
  agents platform, integrate logcore structured logging, register a service or
  repo on the platform, connect their GitHub account to the platform, set up
  log forwarding (JSON-to-stdout with a Cloud Logging sink for backends inside
  GCP, or HTTP to the gateway for frontends and for backends hosted anywhere
  else — a VPS, Hetzner, DigitalOcean, AWS, a PaaS), or onboard a new
  frontend/backend so the platform can detect its logs. Requires the platform
  MCP server to be connected.
license: Apache-2.0
metadata:
  author: Avocado Blockchain Services
  version: "0.6.0"
---

<!-- Content adapted from persea-agents-api:src/mcp/prompts/logcore_setup.py
     and src/mcp/tools/logging_snippet.py. The GitHub connection contract is
     organization-scoped and single-step as of 2026-08-21. Keep in sync. -->

# Persea AI Agents Platform — Project Onboarding

Set up logcore logging integration for the user's project by following the
phases below in order.

## Prerequisites

This skill drives tools served by the Persea AI agents platform MCP server:
`list_organizations`, `check_github_connection`, `get_github_connect_url`,
`list_projects`, `create_project`, `add_service`, `set_build_commands`,
`set_service_type`, `set_runtime_image`, `get_runtime_image_status`,
`get_service_config`, `get_logging_snippet`,
`get_infra_setup`, `register_writer_identity`, `validate_setup`, and
`register_pr`.

If these tools are not available in the session, the MCP server is not
connected. Stop and point the user to the installation instructions in this
plugin's README (https://github.com/Avocado-Blockchain-Services/abs-agents-skills)
before continuing.

The optional tool `test_connection` may also be present; Phase 5 uses it only
when available.

## Phase 1: GitHub Connection

1. Call `list_organizations` before checking GitHub. If several Persea
   organizations are available, present them and let the developer select one.
   Keep that `organization_id` for every organization-scoped call below.
2. Call `check_github_connection(organization_id)` for the selected Persea
   organization.
3. If it is not connected, call `get_github_connect_url(organization_id)` and
   ask the developer to open the one returned `connect_url`. GitHub performs
   user authorization and App installation in that interaction.
4. Poll `check_github_connection(organization_id)` until `connected` is true.
   Do not continue merely because the browser window closed.

## Phase 2: Project Setup

1. Detect from the local repository:
   - `repo_full_name`: run `git remote -v` and parse the origin URL
   - `branch`: run `git branch --show-current`
   - `language`: check for package.json (TypeScript/JavaScript),
     requirements.txt/pyproject.toml (Python), go.mod (Go), Cargo.toml (Rust)
   - `framework`: check for next.config (Next.js), fastapi in deps (FastAPI),
     express in deps (Express), etc.
   - `service_type`: **how this service's logs reach logcore**, which is the
     one thing you cannot detect from the repository. Three values:

     | Value | Where it runs | How logs travel |
     |---|---|---|
     | `WEB_APP_FRONTEND` | a browser | HTTP POST to the gateway with an API key |
     | `BACKEND` | Google Cloud (Cloud Run, GKE, GCE, App Engine) | stdout, collected by a Cloud Logging sink |
     | `EXTERNAL_BACKEND` | anywhere else — a VPS, Hetzner, DigitalOcean, AWS, Azure, Fly, Render, Railway, on-prem | HTTP POST to the gateway with an API key |

     It does NOT say what the service is written in — the language is its own
     field, so do not pick a type based on it. `PYTHON_BACKEND` is the legacy
     spelling of `BACKEND`.

     **Ask the developer where a backend runs**: *"Where does this service run
     — Google Cloud, or somewhere else?"* You cannot read a deploy target out
     of source code, and guessing wrong is silent either way. A backend outside
     GCP filed as `BACKEND` is issued **no API key**, so Phase 3 has nothing to
     authenticate with and Phase 4 sends the developer to create a sink in a
     project their service does not run in. The service registers fine and
     reports nothing, forever.
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
     a. Reuse the Persea organization selected in Phase 1.
     b. Ask for a project name and description.
     c. Call `create_project` with the selected `organization_id`. Every entry
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
   - Idempotent means it returns what is already there, **including its
     `service_type`**. A backend registered before `EXTERNAL_BACKEND` existed
     comes back as a plain `BACKEND` no matter what you passed, and therefore
     holds no API key. If the developer says it runs outside GCP, call
     `set_service_type` with `EXTERNAL_BACKEND` to correct it in place and
     issue the key — do not proceed down a path the platform did not record.
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
   env, **service_id** and **transport**.
2. Call `get_logging_snippet` with the language, framework, and transport to
   get the contract. **Use the `transport` that `get_service_config` returned**
   rather than deriving it: `stdout` for a `BACKEND`, `http` for a
   `WEB_APP_FRONTEND` and for an `EXTERNAL_BACKEND`. So `http` covers both a
   browser and a backend hosted outside GCP, and the three cases in step 4
   differ in what they send, not in how they reach us.
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
   - For backends running OUTSIDE GCP (http — `EXTERNAL_BACKEND`):
     There is no sink on that host, so the service ships its own errors. This
     is the same wire and the same key model as the frontend, but a backend is
     long-lived and fails in bursts, so the transport itself has rules the
     browser client does not need. `transport_info.backend_delivery_rules`
     carries them; they are the contract, not suggestions.
     - **The service keeps writing stdout exactly as it does today.** HTTP
       replaces one hop — how an error reaches the platform — and nothing else.
       The host's own logs stay whole, and only `ERROR` and above leave it.
     - A logcore client module: POST an envelope to `<endpoint>/v1/logs` with
       the `x-api-key` header, the same
       `{"schema_version": 1, "entries": [...]}` wrapper the frontend uses.
     - **Send no identity fields.** No `service_id` — that is how the sink path
       names a sender, and this path has no sink. No `source_project` — the
       process runs in no GCP project, and an empty string is a **422** while
       absent is accepted. The gateway resolves `repo`, `service_id` and
       `project_id` from the key and overrides whatever the payload claims,
       which is also why spoofing them buys nothing.
     - Entry fields stay FLAT. Nothing is nested under
       `logging.googleapis.com/*`: that is Cloud Run promotion, and this path
       never touches Cloud Logging.
     - **`insert_id` is derived, never random.** Compute it at capture as
       `sha256(timestamp | service | severity | message | canonical_json(context))`
       truncated to the first 32 hex chars. A random id passes the format check
       and still breaks this path specifically: the transport retries, so a
       batch the server accepted but whose response was lost arrives twice, and
       only a deterministic id lets logcore recognise the second copy instead of
       counting the error again. It is also what deduplicates a service that
       reaches the platform both ways during a migration.
     - **The transport rules.** A logger that blocks the request path or
       retries forever is worse than no logging:

       | Rule | What to build |
       |---|---|
       | Severity floor | `ERROR` by default, configurable. Below it, nothing is buffered and nothing is sent |
       | Batching | Flush at 20 buffered entries or every 5s, whichever comes first; at most 200 entries per request |
       | Never block | Sending happens off the calling thread or task. The log call returns immediately |
       | Retry | Network error, 5xx, 429 → exponential backoff `2**attempt × 250ms`, up to 3 retries |
       | Permanent rejection | Any other 4xx is NOT retried. Drop the batch and **echo the server's reason to stderr** — a 400 names the offending field, and without that line a schema mismatch looks exactly like a healthy silent transport |
       | Buffer cap | 1000 entries; when full, drop the OLDEST |
       | Circuit breaker | After 10 consecutive failed flushes, stop sending and empty the buffer. A successful flush resets the streak |
       | Shutdown and crash | Flush on clean exit, and best-effort from the unhandled-exception hook after the crash itself is logged |
       | Self-exclusion | Expose the transport's own ingest URL so HTTP instrumentation never logs the transport's own failed POST — that is the loop that takes a process down |
       | Clamps | `message` ≤ 65 536 chars, ≤ 32 labels of ≤ 1 024 chars, ≤ 50 frames. Clamp before sending rather than letting the server reject the batch |

       **Never report the transport's own failures through the logging tree it
       ships.** It would feed itself: one failed flush logs an error, which
       buffers, which fails, which logs. stderr, or a callback, and nothing else.
     - **The trace, on both ends.** Forward `traceparent` on outgoing HTTP
       calls and bind the incoming one in middleware. Without it a request that
       crosses three services is three unrelated incidents instead of one — and
       that correlation is most of what the platform does with a backend error.
       Install it the same way as any other instrumentation: the framework's
       extension point first (see the hierarchy in step 4), never at call sites.
     - An env var example declaring what the module reads. Same names as the
       frontend uses, minus the bundler prefix — this is server code, and an
       unprefixed variable is exactly what it needs:

       ```
       LOGCORE_SERVICE=<the service name>
       LOGCORE_ENV=<prod|staging|dev|test|local>
       LOGCORE_URL=<the `endpoint` from get_service_config>
       LOGCORE_KEY=<the `api_key` from get_service_config>
       LOGCORE_MIN_SEVERITY=ERROR
       ```

       **This key is a server secret**, unlike the frontend's, which ships in a
       bundle by design. It goes in the deployment's environment or its secret
       manager — never in committed code, and **never** in a browser-prefixed
       variable: a `VITE_`/`NEXT_PUBLIC_` prefix would ship a server key to
       every visitor. If `api_key` comes back null the service was registered
       as a plain `BACKEND`: call `set_service_type` with `EXTERNAL_BACKEND` to
       issue one, rather than working around it.
     - **The wiring**: register the middleware, install the crash hooks, and
       make sure something flushes on exit. A transport nobody calls and a
       middleware nobody registers report exactly nothing.
   - For backends running IN GCP (stdout — `BACKEND`, and the sink can only
     identify the sender by service_id):
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

## Phase 3b: Runtime image

The debugger runs this service's setup, build and tests inside a container built
from a Dockerfile in this repository. Without one it cannot run the suite at all,
so this phase is not optional.

**What the image has to be.** An environment, not an application. It provides the
project's own toolchain — compiler, package manager, test runner — and a POSIX
shell at `/bin/sh`. Nothing else is required: it does not need to know about
Persea, and it never runs its own `ENTRYPOINT` or `CMD`. Tell the developer this
explicitly if their Dockerfile does setup work in an entrypoint, because that
work will silently never happen.

1. **Read the repository and determine the real stack.** The language, the
   version it pins, the package manager, any system libraries the build needs.
   Do not guess from the file extensions alone — a `pyproject.toml` with a
   `[tool.poetry]` section and one with `[project]` install differently.

2. **Write `.persea/Dockerfile`.**

   - Pin the base image by tag or digest, never `latest`. An image that changes
     under the service turns a passing suite red for reasons nobody changed.
   - Order the layers so the toolchain installs before the dependencies: the
     dependencies change far more often, and this is what makes a rebuild cheap.
   - `WORKDIR /workspace`. The repository is mounted there at run time.
   - No secrets, no credentials, no tokens. This image is built by the platform
     and stored; anything baked into it is stored with it.
   - No `curl … | sh` from an unpinned source. If a tool has no package, fetch a
     pinned release and verify it.
   - Do not `COPY` the source. The code arrives through the mounted workspace, and
     copying it in would make every commit invalidate the image.

3. **Build it locally and prove it works.**

   ```bash
   docker build -f .persea/Dockerfile -t persea-runtime-check .
   docker run --rm -v "$PWD:/workspace" -w /workspace persea-runtime-check \
     sh -c '<setup_command>'
   docker run --rm -v "$PWD:/workspace" -w /workspace persea-runtime-check \
     sh -c '<test_command>'
   ```

   Both must succeed. A Dockerfile that has never been built is a guess, and the
   first place it would fail is a real customer run.

4. **Audit it before committing.** Read it once more against the rules above —
   pinned base, no secrets, no unpinned downloads, no copied source. You are
   about to commit an environment that will execute this repository's code.

5. **Commit `.persea/Dockerfile`** on the integration branch alongside the rest of
   the work.

6. **Register it** by calling `set_runtime_image` with the service id and
   `.persea/Dockerfile`. Confirm it landed with `get_runtime_image_status`:
   `dockerfile_path` should now be the path you registered. `built` will be `false`
   until the platform's first build of it succeeds, which is expected at this point. Pass `build_context` only when the Dockerfile is not
   built from the repository root — a monorepo service, typically. Pass
   `runtime_cpu` and `runtime_memory` only when the build genuinely needs more
   than the default; a compiled Rust or .NET project sometimes does, and most
   projects do not.

**If the developer already has a Dockerfile** that satisfies the rules above, use
it: point `set_runtime_image` at its path instead of writing a second one. A
production image usually will not fit — it tends to be a slim runtime without the
test runner or the compiler — but check rather than assume.

## Phase 4: GCP Infrastructure (backends inside GCP only)

Skip this phase for anything delivered through the gateway — every frontend,
and every `EXTERNAL_BACKEND`. There is no sink to create: those services carry
their identity in the API key, and `get_infra_setup` says so itself, returning
`applicable: false` instead of gcloud commands.

Sending the developer of a VPS-hosted service to create a sink is not a wasted
round trip, it is an impossible one — the commands name a GCP project their
service does not run in.

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
   - anything on the gateway (http) — a frontend, or a backend outside GCP:
     call the module's log function with the network call stubbed, and take
     the JSON body it would have posted. For a backend, stub it at the send
     boundary rather than waiting on the buffer: the transport batches, so a
     single ERROR may not leave for five seconds.
   If it cannot be executed (no toolchain, no deps installed), say so plainly
   and validate the exact literal your code builds — then tell the developer
   the emitter was not run.
2. Parse that line and call `validate_setup` with the entry AND the SAME
   transport used in Phase 3. It defaults to "stdout", so omitting it while
   validating an entry from either gateway path — a frontend, or a backend
   outside GCP — reports failures that do not apply to it.
3. Errors mean logcore would reject or misattribute the log; fix the generated
   code and re-run step 1. Warnings mean it is accepted but degraded — read
   them out to the developer with what each one costs, rather than dismissing
   them.
4. If available, call `test_connection` with the service id for an E2E test.
   Read its `tested_path` and `covers_production_logs` rather than assuming
   what a green result means. It always posts to the gateway, so:
   - for a frontend, and for a backend outside GCP, that IS the production
     path and `covers_production_logs` comes back true;
   - for a backend inside GCP it is not — its real logs travel through the
     sink, which cannot be exercised from here — so a green result proves the
     key and the network path, and nothing about production logs arriving.
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

http (backend outside GCP): never send from the calling thread or task, and
never report the transport's own failures through the logging tree it ships —
that is the loop that takes a process down. Keep writing stdout as before: the
host's own logs are not yours to replace.

stdout (backend inside GCP): never emit at import time; one JSON object per
line, no interleaved partial writes.

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
- **For backends, which of the two paths applies is decided by where the
  service runs, and you cannot read that from the repository — ask.**
  - Inside GCP, no API key is needed in code — Cloud Logging captures stdout
    automatically — but LOGCORE_SERVICE_ID is required, and it is the one field
    without which nothing works: logcore discards a sink-delivered log that
    declares no service_id, because a service NAME is not unique across
    customers.
  - Outside GCP it is the reverse: there is no sink and no service_id to
    declare, and the API key is what identifies the service. It is a server
    secret — environment or secret manager, never committed, never in a
    browser-prefixed variable.
  - Getting this wrong is silent in both directions. A service that ships to
    the gateway while registered as SINK holds no key and is rejected; one that
    writes only stdout on a host with no sink is writing to nobody.
- At the end, report the wiring you applied — name the files you edited and
  show the diff, so the developer reviews it rather than discovering it.
- If you could not wire it (unknown framework, build failed and you reverted),
  say plainly that **the integration is incomplete and reports nothing yet**,
  and give the exact steps left. Do not describe it as done. A developer who
  believes logging is live and has none is worse off than one who knows it is
  pending.
