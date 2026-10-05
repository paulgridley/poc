from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from azure_operation import build_command  # noqa: E402


class AzureOperationTests(unittest.TestCase):
    def test_subscription_validation_never_uses_create(self) -> None:
        resolved = {
            "deploymentScope": "subscription",
            "target": {"location": "uksouth"},
        }
        command = build_command(
            resolved, "validate", Path("template.json"), Path("parameters.json"), "validation-name"
        )
        self.assertEqual(command[:4], ["az", "deployment", "sub", "validate"])
        self.assertNotIn("create", command)
        self.assertIn("--location", command)

    def test_resource_group_target_is_controlled(self) -> None:
        resolved = {
            "deploymentScope": "resourceGroup",
            "target": {"location": "uksouth", "resourceGroup": "rg-controlled"},
        }
        command = build_command(
            resolved, "what-if", Path("template.json"), Path("parameters.json"), "what-if-name"
        )
        self.assertEqual(command[:4], ["az", "deployment", "group", "what-if"])
        self.assertEqual(command[command.index("--resource-group") + 1], "rg-controlled")
        self.assertNotIn("--location", command)

    def test_deploy_is_the_only_action_that_uses_create(self) -> None:
        resolved = {
            "deploymentScope": "tenant",
            "target": {"location": "uksouth"},
        }
        command = build_command(
            resolved, "deploy", Path("template.json"), Path("parameters.json"), "deployment-name"
        )
        self.assertEqual(command[:4], ["az", "deployment", "tenant", "create"])
        self.assertNotIn("--confirm-with-what-if", command)


if __name__ == "__main__":
    unittest.main()
