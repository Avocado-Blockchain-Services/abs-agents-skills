"""Host-specific OAuth configuration contracts for the development MCP."""

import json
from pathlib import Path
import unittest


MCP_NAME = "perseaai-agents-dev"
MCP_URL = "https://agents-api-dev-352942961463.us-east4.run.app/mcp/lite/mcp"
CLIENT_ID = "OwSOkAnm6fyS7igs8nKQI2btOo5IRm9X"
SCOPES = ["openid", "profile", "email", "offline_access"]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    with (REPOSITORY_ROOT / relative_path).open(encoding="utf-8") as config_file:
        return json.load(config_file)


class McpConfigurationContractTests(unittest.TestCase):
    def test_readme_documents_the_development_codex_marketplace_command(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn(
            "codex plugin marketplace add "
            "Avocado-Blockchain-Services/abs-agents-skills --ref development",
            readme,
        )

    def test_claude_root_config_uses_its_host_specific_oauth_contract(self) -> None:
        """Claude Code's `oauth` block carries the static client id and string scopes.

        The Auth0 development tenant has dynamic client registration disabled
        (its metadata still advertises /oidc/register -- advertising is not
        enablement), so Claude Code must be handed the shared public client id
        via `oauth.clientId`, the documented "pre-configured OAuth credentials"
        path. No secret: it is a public PKCE client.

        `oauth.scopes` must be a SINGLE SPACE-SEPARATED STRING (RFC 6749 §3.3).
        An array here fails Claude Code's config schema and the whole server
        entry is dropped at parse time -- silently: absent from `/mcp`, not
        "needs authentication", no error. That array is how 0.5.0 shipped
        broken, and misreading the drop as "clientId is unsupported" is how
        0.5.1 removed the client id and stranded Claude Code on the rejected
        DCR path. Verified against Claude Code 2.1.246: array scopes -> entry
        dropped; string scopes + clientId -> accepted ("client_id configured").

        Scopes are pinned explicitly because Claude Code (v2.1.196+) no longer
        requests the discovered `scopes_supported` catalog and the dev
        protected-resource metadata advertises no scopes; unpinned, the
        authorize request would carry no scope and yield no refresh token.

        Codex reads a different file with its own schema (top-level scopes
        array) -- see the test below; neither contract constrains the other.
        """
        server = load_json(".mcp.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "type": "http",
                "url": MCP_URL,
                "oauth": {
                    "clientId": CLIENT_ID,
                    "callbackPort": 29352,
                    "scopes": " ".join(SCOPES),
                },
            },
        )

    def test_codex_config_uses_its_host_specific_oauth_contract(self) -> None:
        config_path = REPOSITORY_ROOT / ".codex-plugin/mcp.json"
        self.assertTrue(config_path.is_file(), "Codex-specific MCP configuration is missing")
        if not config_path.is_file():
            return

        server = load_json(".codex-plugin/mcp.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "type": "http",
                "url": MCP_URL,
                "scopes": SCOPES,
                "oauth": {
                    "clientId": CLIENT_ID,
                    "callbackPort": 29352,
                },
            },
        )

    def test_antigravity_root_config_uses_its_host_specific_oauth_contract(self) -> None:
        """Antigravity (agy) reads root `mcp_config.json`: `serverUrl` plus clientId only.

        The remote-server key is `serverUrl` -- agy does not accept the `url` /
        `httpUrl` spellings the other hosts use. The oauth block carries just the
        shared public client id: there is no secret (public PKCE client), and no
        scopes on purpose -- agy 1.1.21 sends no scope parameter and silently
        ignores a `scopes` key in this block, so tokens come back scope-less with
        the exact-resource audience (agy does send RFC 8707 `resource`) and NO
        refresh token. Antigravity users therefore re-authenticate daily until agy
        grows a scope lever or the API advertises `scopes_supported` in its
        protected-resource metadata.

        Verified live 2026-08-26 against agy 1.1.21: the authorize request carried
        client_id, PKCE S256, redirect https://antigravity.google/oauth-callback
        (the fixed hosted callback registered on the Auth0 client in terraform)
        and resource=<MCP URL>; the minted token's `aud` was the exact endpoint.
        """
        server = load_json("mcp_config.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "serverUrl": MCP_URL,
                "oauth": {
                    "clientId": CLIENT_ID,
                },
            },
        )

    def test_antigravity_plugin_manifest_declares_the_google_schema(self) -> None:
        manifest = load_json("plugin.json")

        self.assertEqual(
            manifest["$schema"], "https://antigravity.google/schemas/v1/plugin.json"
        )
        self.assertEqual(manifest["name"], MCP_NAME)
        self.assertTrue(manifest["description"])

    def test_plugin_manifests_reference_the_expected_mcp_configs_at_version_0100(self) -> None:
        # The version is the plugin cache key: Claude Code stores an installed
        # build under `cache/<marketplace>/<plugin>/<version>/` and reuses it
        # rather than re-copying. Shipping a config fix without bumping this
        # leaves every existing install on the old build, which is how the
        # broken 0.5.0 kept coming back after the source was already correct.
        #
        # Las tres se afirman contra el MISMO literal porque el README manda
        # subirlas juntas. Este test estuvo en rojo desde que .claude-plugin
        # pasó a 0.7.0 en solitario: los otros dos se quedaron en 0.6.0 y nadie
        # lo miró. Si vuelve a fallar, la respuesta es alinear los manifiestos,
        # no aflojar la aserción.
        claude_manifest = load_json(".claude-plugin/plugin.json")
        codex_manifest = load_json(".codex-plugin/plugin.json")
        antigravity_manifest = load_json("plugin.json")

        self.assertEqual(claude_manifest["version"], "0.10.0")
        self.assertEqual(codex_manifest["version"], "0.10.0")
        self.assertEqual(antigravity_manifest["version"], "0.10.0")
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-plugin/mcp.json")


if __name__ == "__main__":
    unittest.main()
