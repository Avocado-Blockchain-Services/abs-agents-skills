# Polyglot runtime for the debugger — Design Spec

**Date:** 2026-08-26
**Status:** Approved for implementation
**Owner:** Reylan
**Channel:** `development` branch (plugin `perseaai-agents-dev`, MCP `perseaai-agents-dev`)
**Repos touched:** `abs_agent_debugger`, `persea-agents-api`, `abs-agents-skills`, `abs-agents-terraform`

## Overview

`abs_agent_debugger` can only fix bugs in Python projects. The cause is not the agent — it is that the
`agent-worker` image (`Dockerfile.worker`: `python:3.12-slim` + Node + poetry + pnpm + opencode) does two
incompatible jobs at once.

It is the **brain**: opencode, git, the TDD gate, PR creation, the GitHub App token, the service account. And it
is the **workshop**: where the customer repo is cloned and where `setup_command` / `test_command` run as
`subprocess` (`adapters/git_clone.py:463`) in the same process space.

While those live together, every new stack has to fit inside the same image as the agent. That does not scale to
Rust, .NET, Laravel, Java, C++ or COBOL, and it breaks on the first customer who needs Alpine or RHEL.

**What changes:** each repo declares its own Dockerfile, versioned alongside its code. The debugger runs it as a
sibling container where dependencies are installed, the project is compiled if the language needs it, and the
tests run. The agent stays outside with the credentials. The image is built once and reused.

## The problem in one sentence

*"What toolchain does this project need?"* and *"what runtime does the agent need?"* were never the same question,
and the whole system was built as if they were.

## Decisions

| Topic | Decision |
|---|---|
| Architecture | Two containers per run: `agent` (ours) and `runtime` (the customer's), sharing `/workspace` |
| Platform | Cloud Run Jobs — multi-container is **GA** since 2025-04-02 |
| Job lifecycle | **One ephemeral job per execution**: `create` → `run` → `delete` |
| Image contract | Minimal: `/bin/sh`, repo at `/workspace`, commands run there. Nothing else |
| Commands | Remain server-side authority (`setup_command` / `test_command`), never the repo's |
| Dockerfile path | Default `.persea/Dockerfile`, overridable per service (monorepos) |
| Build | Persea rebuilds from the committed Dockerfile and pins by digest |
| Cache | First-order requirement: rebuild only when the Dockerfile or lockfiles change |
| Sidecar surface | setup, build, test **and the agent's bash** |
| Resources | Default 2 vCPU / 4 GiB, overridable per service |
| Migration | Dockerfile **mandatory**; existing services migrated in one directed batch |
| Egress allowlist | **Out of scope** (explicit decision) |

### Why ephemeral jobs rather than one persistent job per service

Cloud Run does not let you choose the image at execution time. `ContainerOverride` exposes only `name`, `args`,
`env` and `clearArgs`; per-execution overrides cover args, env vars, task count and timeout — **never the image**.
`gcloud run jobs execute` has no `--image`. The image is part of the resource, so a fixed definition can only ever
run the image it was created with.

That leaves two options, and the ephemeral one wins on both counts that matter:

- **Agent updates.** With one persistent definition per customer, every new agent release would require patching
  hundreds of definitions against a 180 writes/60s quota — minutes of partial rollout with some customers on the
  new version and some on the old. An ephemeral job declares the current agent image at creation, so a release
  applies on the next run with no fan-out. Cloud Build goes back to doing only build + push.
- **Concurrency.** Patching a shared definition before each run is a race: run B's patch changes the image in the
  window before run A starts, and A executes against the wrong toolchain. Per-execution definitions have no
  shared resource to clobber.

It also removes the 1000-jobs ceiling as a limit on how many customers can be onboarded.

**Accepted cost:** 3 Admin API writes per run (create + run + delete) against 180/60s per region → a ceiling of
~60 executions per minute, shared with any other deploy in the project. That quota is adjustable on request.

### Discarded alternatives

**GKE Autopilot.** The gap is ~$32/month at the 750h ceiling, and **at low volume it inverts**: at 5 runs/day
(50h/month) Cloud Run costs $2.97 and Autopilot $5.43, because Cloud Run's free tier (~31h/month) covers 62% of
the consumption while Autopilot has no pod free tier — its credit is cluster management. Spot drops it to $1.90,
a $1.07/month saving in exchange for 25-second eviction notices: with 20-30 minute runs and `max_retries = 0`,
losing one mid-flight throws away the agent's work, which is the expensive part (model tokens, not CPU seconds).
Its one differentiating advantage was FQDN egress, which is alpha and out of scope anyway.

**Cloud Build.** Every step is a command frozen at submit time. The debugger improvises commands *during*
execution — the agent decides what to run after reading the code. Incompatible by design, not by price (and it is
also 2.3× the cost).

**Cloud Batch.** Its runnables execute **in sequence**, not as concurrent sidecars, so it does not reproduce the
agent+runtime pattern.

## Architecture

### 1 · The image contract

Deliberately minimal, so that `gnucobol` on Debian and `mcr.microsoft.com/dotnet/sdk` satisfy the same contract
without knowing it exists:

- Provides `/bin/sh`.
- The repo will be mounted at `/workspace`; commands run with that `cwd`.
- Does not need to know about opencode, persea, or the agent.
- Carries no mounted credentials: neither the git token nor the worker's `DEBUGGER_*` env vars.

Everything else — which commands to run — stays server-side, as today.

**Security caveat, verified.** The customer container *does* reach the metadata server, and therefore the job's
service account. In Cloud Run the service account is attached **per instance, not per container**
(`abs-agent-debugger-setup.tf:755` declares it as a sibling of `containers`; `Container` has no `serviceAccount`
field in v2) and the **network namespace is shared** (documented for jobs). A separate container yields a
different uid and a different filesystem namespace, **not a different identity**.

What this refactor does close is the mounted-credential vector: the git token and the `DEBUGGER_*` env vars are
absent from the container where hostile code runs, and the worker's `/proc/1/environ` sits in a different PID
namespace. Closing the ADC path is separate infrastructure work — removing `secretAccessor` from the runtime SA
and moving token minting behind agents-api — tracked in the capability-containment line and orthogonal to this
change.

### 2 · The execution channel

The insertion point is already clean: `run_test_command_capture` (`adapters/git_clone.py:463`) returns
`(exit_code, combined_output)`.

- **New** `ports/command_runner.py` with that exact signature.
- The current `subprocess` implementation is extracted from `git_clone.py` into a `LocalCommandRunner`, preserving
  behaviour for tests and local development.
- **New** `adapters/sidecar_exec.py`, which runs the command in the sibling container.
- `worker/stage_orchestrator.py`, `worker/tdd_check.py` and the guardrails **do not change** — they consume the port.
- opencode's bash (`domain/opencode_config.py`) is routed through the same channel.

The two containers share two things, and each solves half the problem:

| Shared resource | Used for |
|---|---|
| Network namespace (`localhost`) | Control channel: execution request, stdout/stderr streaming, exit code |
| In-memory volume (`/workspace`) | Data: the repo clone, which the agent reads and edits from its own container |

The channel is **HTTP over 127.0.0.1**, not a file protocol: native streaming, no polling, no file races, clean
exit-code propagation. It serves `setup`/`test` and the agent's bash alike.

**Who listens in the sidecar.** The customer image cannot ship the server — that would mean asking them to
install our runtime. The job definition **overrides the sidecar's `command`/`args`** with a static binary of ours
(Go, `CGO_ENABLED=0`, runs on Debian/Alpine/RHEL without glibc). The customer's Dockerfile still promises only
`/bin/sh` and its toolchain, and its own entrypoint never runs: this is not an app to start, it is an environment
to execute in.

**Debt this retires:** today `_split_command` uses `shlex.split` with no shell, so `pip install -r req.txt &&
pytest` is impossible to configure. Going through `sh -c` inside the customer container removes that limitation.

### 3 · Build and image cache

- Cache key: `hash(Dockerfile + relevant build context + lockfiles)`.
- Rebuild **only** when that key changes. Source code never enters the image — it arrives via `/workspace`, so
  editing it invalidates nothing.
- Build in Cloud Build → Artifact Registry, pinned by digest; the resolved digest is stored on the service.
- **Artifact Registry retention policy, mandatory from day one.** It is the only cost that grows on its own
  (~$0.10/GiB-month, 0.5 GiB free tier per billing account, no egress on same-region pulls from Cloud Run). With
  20 images of ~1.5 GB that is ~$3/month; without cleanup it grows linearly forever. Rule: **keep the in-use
  version plus one previous** per repo for immediate rollback, delete the rest, and never delete a digest a job
  might be using. Repository in the **same region** as the jobs so pulls pay no transfer.
- Second cache layer for what does not fit in the image: package-manager caches (`~/.cargo`, `~/.nuget`, `~/.m2`,
  `vendor/`) when the repo is ahead of the image.

**Simplification.** `worker/deps_archive.py` loses most of its reason to exist. Today `.venv` is only cacheable
because the clone path is stable and shebangs are absolute (see the comment at `deps_archive.py:31-46`). With a
per-repo container and `/workspace` fixed by construction, dependencies become image layers — immutable and
digest-versioned. What remains is the package-manager cache.

### 4 · Update flow

Detection is **lazy, at dispatch time**: `hash(Dockerfile + lockfiles)` is computed over the commit being fixed
and compared against the key the current image was built from, together with the current agent digest.

- **Match** (the common case) → create the job with the registered digests and run.
- **Mismatch** → build in Cloud Build, register the new digest, then create and run.

Lazy rather than webhook-driven because it does not depend on an event arriving: **a run never executes against an
image that does not match the code.** A push webhook on top is a latency optimisation, not a correctness one.

| Changed in the repo | Rebuild? | Cost of the next run |
|---|---|---|
| Source code only | no | none — it arrives via `/workspace` |
| A lockfile | yes | dependency layers; the toolchain is reused |
| The `Dockerfile` | yes | full build |
| Service resources | no | none |
| A new version of **our** agent | no | none — declared at job creation |

**If the build fails, the run is aborted.** Continuing with the previous image is tempting and wrong: if the
lockfile changed because a dependency was added, the old image will fail the tests, and the verifier would read
that red as a broken fix. Better to report that the environment could not be built.

### 5 · Launch (`abs_agent_debugger`)

`WorkerLauncherPort` (`ports/worker_launcher.py:40`) is a single-operation port, so the change is contained in
`adapters/cloud_run_jobs.py`:

```
jobs.create  debugger-run-<uuid>   --container agent   --image <agent-digest>
                                   --container runtime --image <client-digest>
jobs.run
   ... the execution runs ...
jobs.delete  debugger-run-<uuid>
```

`gcloud run jobs deploy ... --execute-now` fuses create and run into one invocation (*"Execute the job immediately
after the creation or update completes"*; `--container` is repeatable on the **GA** track of `jobs deploy`).

**Name constraints:** maximum **49 characters**, unique per region and project. `debugger-run-` (13) + hex UUID
without dashes (32) = 45, within margin; with dashes it would be exactly 49, too close to the limit. The permitted
charset is not documented for jobs — validate with `validateOnly=true` before assuming it. `jobs.delete` accepts
`etag` and `validateOnly`; there is **no `force`**. `create`, `run` and `delete` are all async (LRO).

**Lifecycle and cleanup — the part that must be done right.** There is no TTL or automatic deletion
(`expireTime`/`deleteTime` are `Output only` and describe the soft-delete window *after* a Delete has been issued;
there is no equivalent of Kubernetes' `ttlSecondsAfterFinished`). There is no completion event either: Eventarc
does not list `run.googleapis.com` as a source, and audit logs only record invoked actions (`CreateJob`,
`DeleteJob`, `RunJob`, `CancelExecution`, `DeleteExecution`) — an execution finishing is not an API call.
Therefore:

1. **Inline deletion:** the worker deletes its own job when it finishes. Order matters — *"Deleting a job
   terminates all the job executions in progress and all running container instances"* — so the delete comes
   **after** the execution ends, never before.
2. **Backstop sweep (not optional):** a periodic reconciler lists jobs prefixed `debugger-run-` whose execution
   ended more than N minutes ago and deletes them. It covers the case where the worker dies mid-flight, which is
   exactly when inline deletion fails. The repo already has a reconciler (`Dockerfile.reconciler`) to host it.
3. **Logs survive deletion** (*"its logs continue to be available in Cloud Logging"*), so cleanup loses no run
   traceability.

Terraform (`abs-agents-terraform/.../abs-agent-debugger-setup.tf:753+`): the static worker job definition goes
away. What remains is the dispatcher SA's permission to create, run and delete jobs, plus the Artifact Registry.

### 6 · Data model (`persea-agents-api`)

New columns on `services` (`src/orm/models/service.py`) plus an Alembic migration, following the pattern of
`d5a91f3c7b60_add_external_backend_service_type.py`:

- `dockerfile_path` (default `.persea/Dockerfile`)
- `build_context` (default repo root)
- `runtime_image_digest` — the built, pinned image
- `runtime_image_key` — the cache key it was built from
- `runtime_cpu`, `runtime_memory` — per-service overrides

Exposed through `src/schemas/service_config.py` and `src/api/internal/service_config.py`, which the debugger
already consumes. A new MCP tool sets them (following `set_build_commands` / `set_service_type` in
`src/mcp/lite.py`).

### 7 · Onboarding (`abs-agents-skills`)

A new phase in `skills/perseaai-agents-setup/SKILL.md`, honouring the repo's conventions (single SKILL.md, no
subdirectories, tool names without the `mcp__` prefix, `## Prerequisites` kept in sync — enforced by
`scripts/validate_skill.py` and `scripts/validate_tool_references.py`):

1. Analyse the repo and determine the real stack.
2. Generate `.persea/Dockerfile` satisfying the minimal contract.
3. **Build it locally and verify the build works.**
4. Run `setup_command` and `test_command` inside the image to prove the contract holds.
5. Audit the Dockerfile: no secrets, no `curl | sh` from unpinned sources, base pinned by tag or digest.
6. Commit it and register the path via the new MCP tool.

**Quarantine interaction:** `worker/repo_workspace.py:62-93` renames customer instruction files (`.opencode`,
`AGENTS.md`, …). `.persea/` must be declared explicitly as trusted configuration data, never as instructions.

### 8 · Migration

The Dockerfile becomes mandatory. Existing services are migrated in one batch before the new runtime is enabled;
two live execution paths are not maintained.

## Spike evidence

Run in `persea-dev-2` / `us-east4` with two `alpine` containers, deleted afterwards (verified: zero jobs left in
the project).

| Question | Result |
|---|---|
| Does the job finish while the sidecar is still alive? | **Yes.** `Execution completed successfully in 32.84s`, `succeededCount: 1`, with the sidecar in a `while true` loop. It does not wait for sidecars or burn the task timeout. |
| Shared in-memory volume? | **Yes.** The sidecar wrote `/workspace/from-side.txt`; the main container read it. |
| `localhost` between containers? | **Yes.** `nc 127.0.0.1 8080` returned the sidecar's payload. |
| 1 vCPU per container? | **Yes**, 2 vCPU total — the intended default. |

**Measured latency:** `jobs create` 6s · image import 2.5s · startup to execution 23s → **~29s overhead per
execution** (~3% of a 15-minute run).

**Consequence:** the design does not need the sidecar shutdown handshake that had been planned as a mitigation.
The worker exits and the execution ends.

## Verification

1. **Execution port:** unit tests for `LocalCommandRunner` and `SidecarCommandRunner` against the same contract
   suite — same signature, same behaviour for exit codes, combined output and timeouts.
2. **Image contract:** test repos in at least three distinct stacks (one compiled — Rust or .NET; one interpreted
   non-Python — Laravel or Node; one exotic — COBOL), each with its Dockerfile, verifying `setup` and `test` run
   and the exit code propagates.
3. **Cache:** two consecutive runs without touching the Dockerfile or lockfiles trigger no build; touching the
   Dockerfile does; touching only source code does not.
4. **Isolation:** confirm from inside the sidecar that there is no git token and no `DEBUGGER_*` env vars, and
   that the worker's `/proc/1/environ` is unreadable from there. Do **not** expect the metadata server to be
   unreachable — it will not be; that closure belongs to capability-containment.
5. **Cleanup:** after a successful run, no `debugger-run-*` job remains. After a run killed mid-flight, the sweep
   removes the orphan.
6. **Concurrency:** two simultaneous runs on services with different images, each starting with its own.
7. **End-to-end:** a real issue against a non-Python repo, through to the PR, with the TDD gate and the full suite
   running in the customer container.
8. **Regression:** existing Python repos still work with their migrated Dockerfile.

## Risks and open items

- **Orphan-sweep reliability** — the piece the ephemeral model rests on. With no TTL and no completion event, a
  worker that dies mid-flight leaves an unswept job. Define the sweep interval and the age threshold.
- **~29s startup overhead per execution** — measured, inherent to the ephemeral model. Worth watching if runs get
  shorter.
- **Container dependencies are BETA** — `depends_on` requires `run.googleapis.com/launch-stage: BETA`, which
  Google documents as having *"no SLA or technical support obligations"*. Multi-container itself is GA. The spike
  worked without `depends_on`; a startup probe on the sidecar is the production-grade alternative.
- **The sidecar exec-agent** — a new static Go binary plus its client adapter. The largest piece of new code,
  though HTTP-over-localhost keeps the design conventional.
- **TDD gate outside Python** — it does not break: without narrowing to the added tests, `tdd_check.py:403-416`
  runs the full suite, which still proves the error reproduces. It loses precision, not correctness. Structured
  reports (junit/TAP) to recover that precision are a later phase, out of scope here.
- **Linters and formatters** — there is no quality gate today (the only gates are test-based). The agent runs
  them itself, and the bash channel to the sidecar allows that with no new machinery.

## Out of scope

- Egress allowlist for the customer container (explicit decision).
- Closing the ADC / metadata-server path — capability-containment work, orthogonal to this change.
- Structured test reports (junit/TAP) to restore red-check precision on non-pytest runners.
- A quality gate for linters and formatters.
