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

    def test_claude_root_config_uses_the_shared_oauth_contract(self) -> None:
        server = load_json(".mcp.json")["mcpServers"][MCP_NAME]

        self.assertEqual(
            server,
            {
                "type": "http",
                "url": MCP_URL,
                "oauth": {
                    "clientId": CLIENT_ID,
                    "callbackPort": 29352,
                    "scopes": SCOPES,
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

    def test_plugin_manifests_reference_the_expected_mcp_configs_at_version_050(self) -> None:
        claude_manifest = load_json(".claude-plugin/plugin.json")
        codex_manifest = load_json(".codex-plugin/plugin.json")

        self.assertEqual(claude_manifest["version"], "0.5.0")
        self.assertEqual(codex_manifest["version"], "0.5.0")
        self.assertEqual(codex_manifest["mcpServers"], "./.codex-plugin/mcp.json")


if __name__ == "__main__":
    unittest.main()
