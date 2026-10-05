#!/usr/bin/env python3
"""Create a concise Markdown deployment summary from Azure deployment output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _output_value(outputs: Dict[str, Any], name: str) -> Any:
    value = outputs.get(name, {})
    return value.get("value") if isinstance(value, dict) else None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--deployment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    resolved = json.loads(args.resolved.read_text(encoding="utf-8"))
    deployment = json.loads(args.deployment.read_text(encoding="utf-8"))
    properties = deployment.get("properties", {})
    outputs = properties.get("outputs", {}) if isinstance(properties, dict) else {}
    resource_ids = _output_value(outputs, "resourceIds") or []
    portal_links = _output_value(outputs, "portalLinks") or []
    lines: List[str] = [
        "# Deployment summary",
        "",
        f"- Workload: `{resolved['workload']}`",
        f"- Environment: `{resolved['environment']}`",
        f"- Target: `{resolved['targetName']}`",
        f"- Scope: `{resolved['deploymentScope']}`",
        f"- Ownership boundary: `{resolved['ownership']['boundary']}`",
        f"- Provisioning state: `{properties.get('provisioningState', 'unknown')}`",
        "",
        "## Resources",
        "",
    ]
    if resource_ids:
        for index, resource_id in enumerate(resource_ids):
            if index < len(portal_links):
                lines.append(f"- [`{resource_id}`]({portal_links[index]})")
            else:
                lines.append(f"- `{resource_id}`")
    else:
        lines.append("No `resourceIds` output was returned by the workload template.")
    lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Deployment summary written to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
