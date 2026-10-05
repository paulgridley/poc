#!/usr/bin/env python3
"""Merge compiled Bicep parameters with validated, typed request inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--compiled-parameters", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    resolved: Dict[str, Any] = json.loads(args.resolved.read_text(encoding="utf-8"))
    parameters: Dict[str, Any] = json.loads(args.compiled_parameters.read_text(encoding="utf-8"))
    if not isinstance(parameters.get("parameters"), dict):
        raise ValueError("compiled parameter document has no parameters object")
    for name, value in resolved["bicepParameters"].items():
        parameters["parameters"][name] = {"value": value}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(parameters, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(parameters['parameters'])} typed deployment parameters at {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
