from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from catalogue import CatalogueError, load_catalogue, resolve_request, validate_catalogue  # noqa: E402


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = load_catalogue(ROOT / "catalogue/workloads.json")

    def test_repository_catalogue_is_valid(self) -> None:
        self.assertEqual(validate_catalogue(self.catalogue, ROOT), [])

    def test_application_request_resolves_controlled_target_and_typed_input(self) -> None:
        resolved = resolve_request(
            self.catalogue,
            "application-storage",
            "prod",
            {
                "owner": "payments@example.com",
                "costCentre": "PAY001",
                "serviceName": "payments",
                "storageSku": "Standard_ZRS",
            },
        )
        self.assertEqual(resolved["targetName"], "application-prod")
        self.assertEqual(resolved["target"]["serviceConnection"], "sc-azure-application-prod-wif")
        self.assertEqual(resolved["target"]["ownershipBoundary"], "application")
        self.assertEqual(resolved["bicepParameters"]["environment"], "prod")
        self.assertEqual(resolved["bicepParameters"]["location"], "uksouth")

    def test_integer_input_reaches_bicep_as_integer(self) -> None:
        resolved = resolve_request(
            self.catalogue,
            "shared-observability",
            "dev",
            {
                "owner": "platform@example.com",
                "costCentre": "PLATFORM",
                "serviceName": "platform",
                "retentionInDays": "60",
            },
        )
        self.assertEqual(resolved["bicepParameters"]["retentionInDays"], 60)
        self.assertIsInstance(resolved["bicepParameters"]["retentionInDays"], int)

    def test_unsupported_environment_is_rejected_before_azure(self) -> None:
        with self.assertRaisesRegex(CatalogueError, "environment test is not supported"):
            resolve_request(
                self.catalogue,
                "shared-observability",
                "test",
                {
                    "owner": "platform@example.com",
                    "costCentre": "PLATFORM",
                    "serviceName": "platform",
                    "retentionInDays": "30",
                },
            )

    def test_unapproved_sizing_is_rejected(self) -> None:
        with self.assertRaisesRegex(CatalogueError, "storageSku must be one of"):
            resolve_request(
                self.catalogue,
                "application-storage",
                "dev",
                {
                    "owner": "app@example.com",
                    "costCentre": "APP001",
                    "serviceName": "sampleapp",
                    "storageSku": "Premium_LRS",
                },
            )

    def test_missing_and_arbitrary_inputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(CatalogueError, "missing required inputs"):
            resolve_request(self.catalogue, "application-storage", "dev", {"owner": "app@example.com"})
        with self.assertRaisesRegex(CatalogueError, "unsupported inputs"):
            resolve_request(
                self.catalogue,
                "application-storage",
                "dev",
                {
                    "owner": "app@example.com",
                    "costCentre": "APP001",
                    "serviceName": "sampleapp",
                    "storageSku": "Standard_LRS",
                    "serviceConnection": "attacker-controlled",
                },
            )

    def test_scope_and_ownership_boundary_mismatch_is_invalid(self) -> None:
        changed = copy.deepcopy(self.catalogue)
        changed["targets"]["application-nonprod"]["ownershipBoundary"] = "shared-platform"
        errors = validate_catalogue(changed, ROOT)
        self.assertTrue(errors)
        self.assertIn("crosses the declared ownership boundary", errors[0])

    def test_repository_escape_is_invalid(self) -> None:
        changed = copy.deepcopy(self.catalogue)
        changed["workloads"][0]["entryPoint"] = "../outside.bicep"
        errors = validate_catalogue(changed, ROOT)
        self.assertTrue(errors)
        self.assertIn("escapes the repository", errors[0])

    def test_parameter_environment_mismatch_is_invalid(self) -> None:
        changed = copy.deepcopy(self.catalogue)
        parameter_file = ROOT / changed["workloads"][0]["environments"]["dev"]["parameterFile"]
        original = parameter_file.read_text(encoding="utf-8")
        try:
            parameter_file.write_text(original.replace("param environment = 'dev'", "param environment = 'prod'"), encoding="utf-8")
            errors = validate_catalogue(changed, ROOT)
        finally:
            parameter_file.write_text(original, encoding="utf-8")
        self.assertTrue(errors)
        self.assertIn("must set environment to 'dev'", errors[0])


if __name__ == "__main__":
    unittest.main()
