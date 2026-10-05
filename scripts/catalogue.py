#!/usr/bin/env python3
"""Validate and resolve the version-controlled self-service workload catalogue."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


VALID_SCOPES = {"resourceGroup", "subscription", "managementGroup", "tenant"}
REQUIRED_OWNERSHIP_TAGS = {"environment", "owner", "costCentre", "managedBy", "workload"}
PARAM_DECLARATION = re.compile(r"^\s*param\s+([A-Za-z][A-Za-z0-9]*)\s+", re.MULTILINE)
PARAM_ASSIGNMENT = re.compile(r"^\s*param\s+([A-Za-z][A-Za-z0-9]*)\s*=", re.MULTILINE)
STRING_PARAM_ASSIGNMENT = re.compile(
    r"^\s*param\s+([A-Za-z][A-Za-z0-9]*)\s*=\s*['\"]([^'\"]+)['\"]\s*$", re.MULTILINE
)
USING_DECLARATION = re.compile(r"^\s*using\s+['\"]([^'\"]+)['\"]", re.MULTILINE)


class CatalogueError(ValueError):
    """Raised when catalogue configuration or a request is invalid."""


def load_catalogue(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogueError(f"catalogue does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogueError(f"catalogue is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CatalogueError("catalogue root must be an object")
    return data


def _safe_repo_path(repo_root: Path, value: Any, label: str, suffix: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise CatalogueError(f"{label} must be a non-empty repository-relative path")
    if not value.endswith(suffix):
        raise CatalogueError(f"{label} must end in {suffix}")
    root = repo_root.resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CatalogueError(f"{label} escapes the repository: {value}") from exc
    if not candidate.is_file():
        raise CatalogueError(f"{label} does not exist: {value}")
    return candidate


def _require_string(mapping: Mapping[str, Any], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogueError(f"{label}.{key} must be a non-empty string")
    return value


def _require_keys(mapping: Mapping[str, Any], keys: Iterable[str], label: str) -> None:
    missing = sorted(set(keys) - set(mapping))
    if missing:
        raise CatalogueError(f"{label} is missing required fields: {', '.join(missing)}")


def validate_catalogue(data: Mapping[str, Any], repo_root: Path) -> List[str]:
    errors: List[str] = []

    def check() -> None:
        _require_keys(data, {"schemaVersion", "targets", "workloads"}, "catalogue")
        if data.get("schemaVersion") != 1:
            raise CatalogueError("catalogue.schemaVersion must be 1")
        targets = data.get("targets")
        workloads = data.get("workloads")
        if not isinstance(targets, dict) or not targets:
            raise CatalogueError("catalogue.targets must be a non-empty object")
        if not isinstance(workloads, list) or not workloads:
            raise CatalogueError("catalogue.workloads must be a non-empty array")

        for target_name, target in targets.items():
            label = f"target {target_name}"
            if not re.fullmatch(r"[a-z][a-z0-9-]+", target_name):
                raise CatalogueError(f"invalid target identifier: {target_name}")
            if not isinstance(target, dict):
                raise CatalogueError(f"{label} must be an object")
            _require_keys(
                target,
                {"serviceConnection", "deploymentScope", "location", "azureDevOpsEnvironment", "ownershipBoundary"},
                label,
            )
            for field in ("serviceConnection", "location", "azureDevOpsEnvironment"):
                _require_string(target, field, label)
            if target["deploymentScope"] not in VALID_SCOPES:
                raise CatalogueError(f"{label}.deploymentScope is invalid")
            if target["ownershipBoundary"] not in {"shared-platform", "application"}:
                raise CatalogueError(f"{label}.ownershipBoundary is invalid")
            if target["deploymentScope"] == "resourceGroup":
                _require_string(target, "resourceGroup", label)
            if target["deploymentScope"] == "managementGroup":
                _require_string(target, "managementGroupId", label)

        seen_ids: set[str] = set()
        entries: Dict[str, Mapping[str, Any]] = {}
        for index, workload in enumerate(workloads):
            label = f"workloads[{index}]"
            if not isinstance(workload, dict):
                raise CatalogueError(f"{label} must be an object")
            _require_keys(
                workload,
                {
                    "id", "description", "entryPoint", "deploymentScope", "ownership",
                    "allowedRegions", "sizingOptions", "requiredInputs", "dependencies", "environments",
                },
                label,
            )
            workload_id = _require_string(workload, "id", label)
            if not re.fullmatch(r"[a-z][a-z0-9-]+", workload_id):
                raise CatalogueError(f"{label}.id is invalid: {workload_id}")
            if workload_id in seen_ids:
                raise CatalogueError(f"duplicate workload id: {workload_id}")
            seen_ids.add(workload_id)
            entries[workload_id] = workload

        for workload_id, workload in entries.items():
            label = f"workload {workload_id}"
            _require_string(workload, "description", label)
            scope = workload.get("deploymentScope")
            if scope not in VALID_SCOPES:
                raise CatalogueError(f"{label}.deploymentScope is invalid")
            entry_path = _safe_repo_path(repo_root, workload.get("entryPoint"), f"{label}.entryPoint", ".bicep")
            entry_text = entry_path.read_text(encoding="utf-8")
            declared_parameters = set(PARAM_DECLARATION.findall(entry_text))

            ownership = workload.get("ownership")
            if not isinstance(ownership, dict):
                raise CatalogueError(f"{label}.ownership must be an object")
            boundary = ownership.get("boundary")
            if boundary not in {"shared-platform", "application"}:
                raise CatalogueError(f"{label}.ownership.boundary is invalid")
            tags = ownership.get("requiredTags")
            if not isinstance(tags, list) or not REQUIRED_OWNERSHIP_TAGS.issubset(set(tags)):
                raise CatalogueError(f"{label} must require ownership tags: {', '.join(sorted(REQUIRED_OWNERSHIP_TAGS))}")

            regions = workload.get("allowedRegions")
            if not isinstance(regions, list) or not regions or not all(isinstance(x, str) and x for x in regions):
                raise CatalogueError(f"{label}.allowedRegions must be a non-empty string array")
            if len(regions) != len(set(regions)):
                raise CatalogueError(f"{label}.allowedRegions contains duplicates")

            inputs = workload.get("requiredInputs")
            if not isinstance(inputs, list) or not inputs:
                raise CatalogueError(f"{label}.requiredInputs must be a non-empty array")
            input_names: set[str] = set()
            bicep_names: set[str] = set()
            for item in inputs:
                if not isinstance(item, dict):
                    raise CatalogueError(f"{label}.requiredInputs entries must be objects")
                _require_keys(item, {"name", "bicepParameter", "type"}, f"{label} input")
                name = _require_string(item, "name", f"{label} input")
                bicep_name = _require_string(item, "bicepParameter", f"{label} input {name}")
                if name in input_names or bicep_name in bicep_names:
                    raise CatalogueError(f"{label} has duplicate input or Bicep parameter mapping")
                input_names.add(name)
                bicep_names.add(bicep_name)
                if bicep_name not in declared_parameters:
                    raise CatalogueError(f"{label} input {name} references undeclared Bicep parameter {bicep_name}")
                if item.get("type") not in {"string", "integer", "boolean"}:
                    raise CatalogueError(f"{label} input {name} has unsupported type")
                if "pattern" in item:
                    try:
                        re.compile(item["pattern"])
                    except (re.error, TypeError) as exc:
                        raise CatalogueError(f"{label} input {name} has invalid pattern") from exc
                if "allowedValues" in item and (not isinstance(item["allowedValues"], list) or not item["allowedValues"]):
                    raise CatalogueError(f"{label} input {name}.allowedValues must be a non-empty array")

            sizing_options = workload.get("sizingOptions")
            if not isinstance(sizing_options, dict):
                raise CatalogueError(f"{label}.sizingOptions must be an object")
            input_by_name = {item["name"]: item for item in inputs}
            for option_name, values in sizing_options.items():
                if option_name not in input_by_name:
                    raise CatalogueError(f"{label} sizing option {option_name} is not a required input")
                if values != input_by_name[option_name].get("allowedValues"):
                    raise CatalogueError(f"{label} sizing option {option_name} must match input allowedValues")

            environments = workload.get("environments")
            if not isinstance(environments, dict) or not environments:
                raise CatalogueError(f"{label}.environments must be a non-empty object")
            for environment, config in environments.items():
                env_label = f"{label} environment {environment}"
                if not re.fullmatch(r"[a-z][a-z0-9-]+", environment) or not isinstance(config, dict):
                    raise CatalogueError(f"{env_label} is invalid")
                _require_keys(config, {"parameterFile", "target"}, env_label)
                parameter_path = _safe_repo_path(
                    repo_root, config.get("parameterFile"), f"{env_label}.parameterFile", ".bicepparam"
                )
                target_name = _require_string(config, "target", env_label)
                if target_name not in targets:
                    raise CatalogueError(f"{env_label} references unknown target {target_name}")
                target = targets[target_name]
                if target["deploymentScope"] != scope:
                    raise CatalogueError(f"{env_label} deployment scope does not match its target")
                if target["ownershipBoundary"] != boundary:
                    raise CatalogueError(f"{env_label} crosses the declared ownership boundary")
                if target["location"] not in regions:
                    raise CatalogueError(f"{env_label} target location is not allowed")

                parameter_text = parameter_path.read_text(encoding="utf-8")
                using_match = USING_DECLARATION.search(parameter_text)
                if not using_match:
                    raise CatalogueError(f"{env_label} has no using declaration")
                associated_template = (parameter_path.parent / using_match.group(1)).resolve()
                if associated_template != entry_path.resolve():
                    raise CatalogueError(f"{env_label} is associated with the wrong Bicep entry point")
                assigned = set(PARAM_ASSIGNMENT.findall(parameter_text))
                required_parameter_names = bicep_names | {"environment", "location"}
                missing_parameters = sorted(required_parameter_names - assigned)
                if missing_parameters:
                    raise CatalogueError(
                        f"{env_label} does not assign required parameters: {', '.join(missing_parameters)}"
                    )
                literal_values = dict(STRING_PARAM_ASSIGNMENT.findall(parameter_text))
                if literal_values.get("environment") != environment:
                    raise CatalogueError(f"{env_label} must set environment to '{environment}'")
                if literal_values.get("location") != target["location"]:
                    raise CatalogueError(
                        f"{env_label} must set location to its controlled target location '{target['location']}'"
                    )

            dependencies = workload.get("dependencies")
            if not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies):
                raise CatalogueError(f"{label}.dependencies must be a string array")
            for dependency in dependencies:
                if dependency == workload_id or dependency not in entries:
                    raise CatalogueError(f"{label} has invalid dependency {dependency}")

    try:
        check()
    except CatalogueError as exc:
        errors.append(str(exc))
    return errors


def _convert_input(spec: Mapping[str, Any], raw_value: str) -> Any:
    input_type = spec["type"]
    name = spec["name"]
    if input_type == "string":
        value: Any = raw_value
        min_length = spec.get("minLength")
        max_length = spec.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise CatalogueError(f"input {name} must contain at least {min_length} characters")
        if isinstance(max_length, int) and len(value) > max_length:
            raise CatalogueError(f"input {name} must contain no more than {max_length} characters")
        pattern = spec.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            raise CatalogueError(f"input {name} does not match the required format")
    elif input_type == "integer":
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise CatalogueError(f"input {name} must be an integer") from exc
    elif input_type == "boolean":
        normalized = raw_value.lower()
        if normalized not in {"true", "false"}:
            raise CatalogueError(f"input {name} must be true or false")
        value = normalized == "true"
    else:
        raise CatalogueError(f"input {name} has unsupported type {input_type}")
    if "allowedValues" in spec and value not in spec["allowedValues"]:
        allowed = ", ".join(str(item) for item in spec["allowedValues"])
        raise CatalogueError(f"input {name} must be one of: {allowed}")
    return value


def resolve_request(
    data: Mapping[str, Any], workload_id: str, environment: str, raw_inputs: Mapping[str, str]
) -> Dict[str, Any]:
    workloads = {item["id"]: item for item in data["workloads"]}
    if workload_id not in workloads:
        raise CatalogueError(f"workload is not approved: {workload_id}")
    workload = workloads[workload_id]
    if environment not in workload["environments"]:
        supported = ", ".join(sorted(workload["environments"]))
        raise CatalogueError(f"environment {environment} is not supported for {workload_id}; choose: {supported}")
    specs = {item["name"]: item for item in workload["requiredInputs"]}
    missing = sorted(set(specs) - set(raw_inputs))
    extra = sorted(set(raw_inputs) - set(specs))
    if missing:
        raise CatalogueError(f"missing required inputs: {', '.join(missing)}")
    if extra:
        raise CatalogueError(f"unsupported inputs: {', '.join(extra)}")
    converted = {name: _convert_input(specs[name], raw_inputs[name]) for name in specs}
    bicep_parameters = {specs[name]["bicepParameter"]: converted[name] for name in specs}
    environment_config = workload["environments"][environment]
    target_name = environment_config["target"]
    target = data["targets"][target_name]
    bicep_parameters["environment"] = environment
    bicep_parameters["location"] = target["location"]
    return {
        "catalogueSchemaVersion": data["schemaVersion"],
        "workload": workload_id,
        "description": workload["description"],
        "environment": environment,
        "entryPoint": workload["entryPoint"],
        "parameterFile": environment_config["parameterFile"],
        "deploymentScope": workload["deploymentScope"],
        "ownership": workload["ownership"],
        "dependencies": workload["dependencies"],
        "targetName": target_name,
        "target": target,
        "inputs": converted,
        "bicepParameters": bicep_parameters,
    }


def _parse_inputs(items: Sequence[str]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise CatalogueError(f"input must use name=value syntax: {item}")
        name, value = item.split("=", 1)
        if not name or name in values:
            raise CatalogueError(f"input name is empty or duplicated: {name}")
        values[name] = value
    return values


def _emit_azure_devops_variables(resolved: Mapping[str, Any]) -> None:
    variables = {
        "catalogueWorkload": resolved["workload"],
        "catalogueEnvironment": resolved["environment"],
        "entryPoint": resolved["entryPoint"],
        "parameterFile": resolved["parameterFile"],
        "deploymentScope": resolved["deploymentScope"],
        "targetName": resolved["targetName"],
        "targetLocation": resolved["target"]["location"],
        "azureServiceConnection": resolved["target"]["serviceConnection"],
        "azureDevOpsEnvironment": resolved["target"]["azureDevOpsEnvironment"],
    }
    for name, value in variables.items():
        print(f"##vso[task.setvariable variable={name}]{value}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalogue", type=Path, default=Path("catalogue/workloads.json"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--workload", required=True)
    resolve_parser.add_argument("--environment", required=True)
    resolve_parser.add_argument("--input", action="append", default=[])
    resolve_parser.add_argument("--output", type=Path, required=True)
    resolve_parser.add_argument("--azure-devops", action="store_true")
    args = parser.parse_args(argv)

    try:
        data = load_catalogue(args.catalogue)
        errors = validate_catalogue(data, args.repo_root)
        if errors:
            raise CatalogueError("; ".join(errors))
        if args.command == "validate":
            print(f"Validated {len(data['workloads'])} workloads and {len(data['targets'])} controlled targets.")
            return 0
        resolved = resolve_request(data, args.workload, args.environment, _parse_inputs(args.input))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(resolved, indent=2) + "\n", encoding="utf-8")
        if args.azure_devops:
            _emit_azure_devops_variables(resolved)
        print(f"Resolved approved request {args.workload}/{args.environment} to {args.output}.")
        return 0
    except CatalogueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
