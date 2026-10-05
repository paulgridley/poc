# Azure Bicep validation and self-service catalogue

This repository contains a deliberately small, version-controlled Azure self-service baseline. The GitHub repository was empty when this implementation was created, so the included `shared-observability` and `application-storage` workloads establish the Bicep, Azure Verified Modules (AVM), workload, and Azure DevOps YAML conventions rather than modifying an existing deployment.

The catalogue is the authority for approved workload/environment combinations, Bicep entry points, parameter files, deployment scopes, service connections, ownership boundaries, regions, and permitted sizing choices. Pipeline runtime parameters never accept a subscription, service connection, deployment target, or template path.

## Repository layout

- `catalogue/workloads.json` — approved workloads and controlled targets.
- `workloads/` — subscription-scoped Bicep entry points and per-environment `.bicepparam` files.
- `azure-pipelines/validate.yml` — offline validation plus optional authenticated Azure validation and what-if; it never deploys resources.
- `azure-pipelines/self-service.yml` — manual self-service entry point that validates, runs what-if, and then deploys through a protected Azure DevOps environment.
- `scripts/` — dependency-free catalogue resolution, parameter preparation, Azure operations, and report generation.
- `docs/` — operating guidance and Azure DevOps setup.

## Local validation

Prerequisites: Azure CLI with Bicep installed, Python 3.9+, and network access to the public Bicep registry for AVM module restore.

```bash
python3 scripts/catalogue.py --repo-root . validate
python3 -m unittest discover -s tests -v
python3 scripts/validate_offline.py --output-dir artifacts/offline-validation
```

The last command restores AVM modules, builds and lints every catalogue entry point, builds every referenced `.bicepparam` file, checks file associations, validates the catalogue, and writes an artifact-style JSON report. It does not authenticate to Azure or create resources.

## Pipeline setup

Create two Azure Pipelines from the YAML files, then follow [the Azure DevOps setup guide](docs/azure-devops-setup.md). In particular, configure Azure Repos build-validation branch policy explicitly; `pr:` in YAML does not configure PR validation for Azure Repos.

For catalogue usage, maintenance, request examples, and ownership boundaries, see [the catalogue guide](docs/catalogue.md).
