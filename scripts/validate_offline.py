#!/usr/bin/env python3
"""Run deterministic, unauthenticated catalogue and Bicep validation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from catalogue import load_catalogue, validate_catalogue


def _run(command: Sequence[str]) -> Dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return {
        "command": list(command),
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, default=Path("catalogue/workloads.json"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/offline-validation"))
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_catalogue(args.catalogue)
    errors = validate_catalogue(data, root)
    results: Dict[str, Any] = {"catalogueErrors": errors, "commands": []}

    if not errors:
        for workload in data["workloads"]:
            workload_dir = output_dir / workload["id"]
            workload_dir.mkdir(parents=True, exist_ok=True)
            entry = root / workload["entryPoint"]
            results["commands"].append(_run(["az", "bicep", "restore", "--file", str(entry), "--force"]))
            results["commands"].append(
                _run(["az", "bicep", "build", "--file", str(entry), "--outfile", str(workload_dir / "template.json")])
            )
            for environment, config in workload["environments"].items():
                parameter_file = root / config["parameterFile"]
                results["commands"].append(
                    _run(
                        [
                            "az", "bicep", "build-params", "--file", str(parameter_file),
                            "--outfile", str(workload_dir / f"{environment}.parameters.json"),
                        ]
                    )
                )

    test_result = _run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"])
    results["commands"].append(test_result)
    report_path = output_dir / "validation-report.json"
    report_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    failures = errors or [item for item in results["commands"] if item["exitCode"] != 0]
    for item in results["commands"]:
        command = " ".join(item["command"])
        print(f"[{item['exitCode']}] {command}")
        if item["stdout"]:
            print(item["stdout"], end="")
        if item["stderr"]:
            print(item["stderr"], end="", file=sys.stderr)
    if failures:
        print(f"Offline validation failed. Report: {report_path}", file=sys.stderr)
        return 1
    print(f"Offline validation passed. Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
