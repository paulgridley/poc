#!/usr/bin/env python3
"""Run a controlled Azure validation, what-if, or deployment at catalogue scope."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _base_command(scope: str, action: str) -> List[str]:
    scope_commands = {
        "resourceGroup": ["az", "deployment", "group"],
        "subscription": ["az", "deployment", "sub"],
        "managementGroup": ["az", "deployment", "mg"],
        "tenant": ["az", "deployment", "tenant"],
    }
    if scope not in scope_commands:
        raise ValueError(f"unsupported deployment scope: {scope}")
    verb = "create" if action == "deploy" else action
    return scope_commands[scope] + [verb]


def build_command(
    resolved: Dict[str, Any], action: str, template: Path, parameters: Path, deployment_name: str
) -> List[str]:
    scope = resolved["deploymentScope"]
    target = resolved["target"]
    command = _base_command(scope, action)
    if scope == "resourceGroup":
        command.extend(["--resource-group", target["resourceGroup"]])
    elif scope == "managementGroup":
        command.extend(["--management-group-id", target["managementGroupId"]])
    if scope != "resourceGroup":
        command.extend(["--location", target["location"]])
    command.extend(
        [
            "--name", deployment_name,
            "--template-file", str(template),
            "--parameters", f"@{parameters}",
            "--output", "json",
        ]
    )
    if action == "what-if":
        command.extend(["--result-format", "FullResourcePayloads", "--no-pretty-print"])
    return command


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["validate", "what-if", "deploy"], required=True)
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-name")
    args = parser.parse_args(argv)

    resolved: Dict[str, Any] = json.loads(args.resolved.read_text(encoding="utf-8"))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base_name = re.sub(r"[^A-Za-z0-9-]", "-", f"{resolved['workload']}-{resolved['environment']}")
    deployment_name = args.deployment_name or f"{base_name}-{timestamp}"
    command = build_command(resolved, args.action, args.template, args.parameters, deployment_name)
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if completed.stdout.strip():
        try:
            content = json.loads(completed.stdout)
            args.output.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        except json.JSONDecodeError:
            args.output.write_text(completed.stdout, encoding="utf-8")
    else:
        args.output.write_text("{}\n", encoding="utf-8")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        print(f"Azure {args.action} failed; partial output is available at {args.output}.")
        return completed.returncode
    print(f"Azure {args.action} completed at {resolved['deploymentScope']} scope; result: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
