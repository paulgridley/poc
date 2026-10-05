# Self-service catalogue

`catalogue/workloads.json` is reviewed configuration, not user input. It resolves every requested workload/environment pair to its Bicep entry point, `.bicepparam` file, Azure deployment scope, target location, Azure DevOps environment, and Azure Resource Manager service connection.

## Approved workloads

| Workload | Owner boundary | Environments | Scope | Sizing |
| --- | --- | --- | --- | --- |
| `shared-observability` | Shared platform | `dev`, `prod` | Subscription | Log retention: 30, 60, or 90 days |
| `application-storage` | Application | `dev`, `test`, `prod` | Subscription | `Standard_LRS`, `Standard_GRS`, or `Standard_ZRS` |

Both workloads allow `uksouth`, `ukwest`, and `westeurope`; the currently controlled targets use `uksouth`. The platform workload creates and tags its own shared resource group and Log Analytics workspace. The application workload creates and tags an application resource group and storage account. They do not share ownership: the application workload merely records its dependency on the platform workload in the catalogue.

Every request requires an accountable `owner`, `costCentre`, and `serviceName`, plus its workload-specific sizing input. The resolver validates types and patterns and writes typed values into the final ARM parameter document; for example, `retentionInDays` is an integer rather than a quoted string.

## Example requests

Run `azure-pipelines/self-service.yml` manually in Azure DevOps:

| Scenario | Workload | Environment | Inputs |
| --- | --- | --- | --- |
| Development storage | `application-storage` | `dev` | `owner=payments@example.com`, `costCentre=PAY001`, `serviceName=payments`, `storageSku=Standard_LRS` |
| Production shared logging | `shared-observability` | `prod` | `owner=platform@example.com`, `costCentre=PLATFORM`, `serviceName=platform`, `retentionInDays=90` |

Selecting `shared-observability` with `test`, an unknown SKU, malformed service name, or an additional field such as `serviceConnection` fails in the resolver before an Azure task runs.

## Adding a workload

1. Add a deployable Bicep entry point under `workloads/<id>/main.bicep` and use pinned AVM module versions where a module exists.
2. Add one `.bicepparam` file per supported environment under `workloads/<id>/parameters/`. Each must `using` that entry point and set `environment`, `location`, and every required request-mapped parameter.
3. Add the workload to `catalogue/workloads.json`. Set the actual Bicep target scope, allowed regions, sizing choices, required input types, ownership boundary and tags, dependencies, and only controlled target identifiers.
4. Reuse an existing target only when its scope and ownership boundary are appropriate. Adding a target requires an explicitly named Azure Resource Manager service connection; never add a subscription ID, secret, or arbitrary path parameter.
5. Run the local commands in the root README. Add tests for each new unsupported combination or input rule.
6. Update the `workload` runtime parameter allow-list in both top-level pipeline YAML files. Azure DevOps runtime parameter value lists are static, so this small duplication is deliberate and is checked in review alongside the catalogue change.

The catalogue validator rejects missing files, path traversal, incorrect `.bicepparam` associations, nonexistent dependencies, scope mismatches, target locations outside the workload allow-list, ownership-boundary crossings, missing required ownership tags, and Bicep parameter mappings that do not exist.

## Operational flow

```text
Request parameters
      |
      v
Catalogue resolver -> controlled target + typed Bicep values -> compile template/parameters
      |                                                        |
      |                                                        v
      |                                             Azure validate + what-if
      |                                                        |
      |                         protected Azure DevOps environment approval / lock
      |                                                        |
      +--------------------------------------------------> deployment create
                                                               |
                                                               v
                                                  resource IDs + portal links artifact
```

The validation pipeline ends after the Azure validate/what-if branch and cannot execute `az deployment ... create`.
