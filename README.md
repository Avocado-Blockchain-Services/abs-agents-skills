# abs-agents-skills

Agent skills for the **Persea AI agents platform** by Avocado Blockchain
Services. Ships the `perseaai-agents-setup` skill, which teaches AI coding
agents (Claude Code, Codex, opencode, Cursor, …) how to onboard a project onto
the platform: connect GitHub, register the repo as a service, integrate
logcore structured logging, and open the integration PR.

> ⚠️ **Early stage.** The MCP endpoints below point at pre-production
> environments; URLs will move to a stable domain before general availability.

## Channels

| Channel | Plugin | Branch | MCP endpoint |
|---|---|---|---|
| **Stable** | `perseaai-agents` | `main` | staging API (`agents-api-…`) |
| **Dev** | `perseaai-agents-dev` | `development` | dev API (`agents-api-dev-…`) |

Both channels are served by this same marketplace. Install **one per
workspace** — they ship the same skill and would double-trigger side by side.
Skill changes land on `development` first, get dogfooded by the team against
the dev API, and are promoted to `main` with a version bump.

### Development OAuth

The development MCP uses a shared public OAuth client: its client ID is public
and is not a secret. Auth0 is the authorization server. After installing the
plugin, start a new host session before using the MCP so the host loads its
configuration and begins a fresh authorization flow.

**Promoting `development` → `main`:** merge, then re-assert the STABLE
identity inside the channel-owned files while keeping development's shape and
version. Checking out main's copies wholesale no longer works — the files'
shapes evolve on `development` (e.g. `.codex-plugin/mcp.json` splitting off in
0.5.x). The channel identity is three values — plugin/server name
(`perseaai-agents`, no `-dev`), MCP URL (`agents-api-…`, not
`agents-api-dev-…`) and OAuth client id (staging `qzjTYaG…`, not dev
`OwSOkAnm…`) — carried by:

- `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `plugin.json`
  (name, version, description)
- `.mcp.json`, `.codex-plugin/mcp.json`, `mcp_config.json` (server key, URL,
  client id)
- `tests/test_mcp_configs.py` (the `MCP_NAME` / `MCP_URL` / `CLIENT_ID`
  constants), plus this README's channel-primary install sections

Run `python -m unittest discover tests` afterwards — the contract tests pin
each host's exact config shape.

**Testing an unmerged PR branch** needs no channel at all — a marketplace can
be a local checkout:

```
/plugin marketplace add /path/to/your/abs-agents-skills   # on the PR branch
/plugin install perseaai-agents-dev@abs-agents-skills
```

## Install

### Claude Code (recommended — one step gets tools + skill)

```
/plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills
/plugin install perseaai-agents@abs-agents-skills
```

(Team members testing pre-release content: `/plugin install
perseaai-agents-dev@abs-agents-skills` instead.)

This also configures the platform MCP server (key `perseaai-agents`) via the
bundled `.mcp.json`; an OAuth browser window will open on first use.

### Codex (native plugin: tools + skill)

```sh
codex plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills
codex plugin add perseaai-agents@abs-agents-skills
```

(Team members testing pre-release content install the dev channel instead:
`codex plugin marketplace add Avocado-Blockchain-Services/abs-agents-skills --ref development`.)

Start a new Codex session in the repository after installation so it loads the
bundled MCP server and onboarding skill.

### Antigravity CLI (plugin: tools + skills)

The repository root is also an Antigravity plugin (`plugin.json` +
`mcp_config.json`). `agy plugin install` takes a local directory; install the
stable channel from a checkout of `main` (the default branch), or the dev
channel from a checkout of `development`:

```sh
git clone git@github.com:Avocado-Blockchain-Services/abs-agents-skills.git
agy plugin install ./abs-agents-skills
```

Sign-in uses the same shared public OAuth client through a Google-hosted
callback page — paste the authorization code back into the CLI. Note that
Antigravity requests no scopes and Auth0 therefore issues no refresh token:
expect to re-authenticate about once a day until agy grows a scope
configuration or the API advertises `scopes_supported`.

`agy plugin install` copies the checkout into `~/.gemini/config/plugins/`, so
to pick up plugin updates pull the branch and run the install again.

> ⚠️ The git-URL form (`agy plugin install https://github.com/...abs-agents-skills.git`)
> only ever installs the repository's **default branch** (`main`, the stable
> channel) — since 0.6.0 main carries the Antigravity manifests, so that form
> now works for stable. It can never install the dev channel: for that, use a
> local checkout of `development` as shown above. (On a branch without the
> manifests agy does not fail — it synthesizes a plugin from the Claude Code
> files and mangles the HTTP MCP server into a broken empty-stdio entry,
> verified on agy 1.1.21.)

### Any other agent (opencode, Cursor, …)

Install the skill:

```
npx skills add Avocado-Blockchain-Services/abs-agents-skills
```

Useful flags: `--agent opencode` to target one agent, `-g` for user-level
instead of project-level scope, `--copy` to copy files instead of symlinking.

Then connect the MCP server manually (streamable HTTP + OAuth):

- **URL (stable / staging API):**
  `https://agents-api-352942961463.us-east4.run.app/mcp/lite/mcp`
- **URL (dev channel):**
  `https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp`
- **opencode** — add to `opencode.json`:

  ```json
  {
    "mcp": {
      "perseaai-agents": {
        "type": "remote",
        "url": "https://agents-api-352942961463.us-east4.run.app/mcp/lite/mcp"
      }
    }
  }
  ```

- **Cursor** — register a remote (streamable HTTP) MCP server named
  `perseaai-agents` with the URL above, using Cursor's MCP settings.

### Zero-install fallback

Connect the MCP URL above directly in any MCP client — the server itself
exposes a `logcore_setup` prompt covering the same onboarding flow.

## Usage

With the MCP connected and the skill installed, just ask your agent:

> "Connect this repo to the Persea agents platform"

The `perseaai-agents-setup` skill triggers automatically and walks through
GitHub connection → project registration → logging integration → validation
→ PR.

The GitHub connection is organization-scoped and uses one browser interaction:

1. The agent lists the Persea organizations and asks which one to configure.
2. It calls `check_github_connection(organization_id)`.
3. If needed, it calls `get_github_connect_url(organization_id)` and opens the
   single returned `connect_url`.
4. It polls the same organization until the API confirms the installation.

The connection URL combines GitHub App installation and user authorization.
There are no separate authorization and installation URLs, and closing the
browser window is not treated as success.

### GitHub MCP tools

| Tool | Contract |
|---|---|
| `list_organizations()` | Select the Persea organization before connecting GitHub. |
| `check_github_connection(organization_id)` | Report whether that organization has a verified GitHub App installation. |
| `get_github_connect_url(organization_id)` | Return one `connect_url` for an organization owner to open. |

Una vez integrado el proyecto, para saber si está funcionando:

> "¿Está llegando algo a la plataforma desde este repo?"
> "¿Cómo va mi proyecto?"

La skill `perseaai-agents-status` se dispara sola: diagnostica el pipeline
cuando todavía no hay datos, y reporta logs, veredictos del classifier, runs
del debugger y PRs esperando review cuando sí los hay.

## Repository layout

- `skills/perseaai-agents-setup/SKILL.md` — the onboarding skill
  ([agentskills.io](https://agentskills.io) format)
- `skills/perseaai-agents-status/SKILL.md` — la skill de monitoreo post-setup
- `.claude-plugin/` — Claude Code plugin + self-hosted marketplace manifests
- `.codex-plugin/` — Codex plugin manifest
- `.agents/plugins/marketplace.json` — native Codex marketplace catalog
- `.mcp.json` — bundled MCP connection for Claude Code installs
- `.codex-plugin/mcp.json` — bundled MCP connection for Codex plugin installs
- `plugin.json` + `mcp_config.json` — Antigravity (agy) plugin manifest and its
  bundled MCP connection; the repository root is the installable plugin
- `docs/superpowers/` — design spec and implementation plan

## License

Apache-2.0
