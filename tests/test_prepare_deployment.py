from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_deployment import main  # noqa: E402


class PrepareDeploymentTests(unittest.TestCase):
    def test_typed_resolved_values_override_parameter_file_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            resolved = directory / "resolved.json"
            compiled = directory / "compiled.json"
            output = directory / "prepared.json"
            resolved.write_text(
                json.dumps(
                    {
                        "bicepParameters": {
                            "environment": "dev",
                            "owner": "platform@example.com",
                            "retentionInDays": 60,
                        }
                    }
                ),
                encoding="utf-8",
            )
            compiled.write_text(
                json.dumps(
                    {
                        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
                        "contentVersion": "1.0.0.0",
                        "parameters": {
                            "environment": {"value": "placeholder"},
                            "owner": {"value": "placeholder@example.com"},
                            "retentionInDays": {"value": 30},
                        },
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                main(
                    [
                        "--resolved", str(resolved),
                        "--compiled-parameters", str(compiled),
                        "--output", str(output),
                    ]
                ),
                0,
            )
            prepared = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(prepared["parameters"]["environment"]["value"], "dev")
            self.assertEqual(prepared["parameters"]["retentionInDays"]["value"], 60)
            self.assertIsInstance(prepared["parameters"]["retentionInDays"]["value"], int)


if __name__ == "__main__":
    unittest.main()
