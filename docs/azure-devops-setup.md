# Azure DevOps pipeline and security setup

The YAML files are safe to commit before any Azure configuration exists. The four service-connection names in the catalogue are intentional placeholders because this repository contained no existing service connections:

| Catalogue target | Required Azure Resource Manager service connection |
| --- | --- |
| `platform-nonprod` | `sc-azure-platform-nonprod-wif` |
| `platform-prod` | `sc-azure-platform-prod-wif` |
| `application-nonprod` | `sc-azure-application-nonprod-wif` |
| `application-prod` | `sc-azure-application-prod-wif` |

Create each as an Azure Resource Manager connection using workload identity federation (WIF), then authorize only the two pipeline definitions that require it. Do not select **Grant access permission to all pipelines**. Use separate identities/scopes for platform and application ownership boundaries and for production/non-production. The validation identity needs the Azure permissions required by template validation and what-if at its controlled scope; the deployment identity additionally needs only the resource actions required to create and update the approved workload. Avoid role-assignment permissions unless a workload genuinely manages role assignments.

For WIF, use the Azure DevOps-generated issuer and subject for the specific service connection, add the federated credential to the app registration or user-assigned managed identity, then grant the scoped Azure role and verify/save the connection. Microsoft’s current guidance is [Azure Resource Manager service connections with workload identity federation](https://learn.microsoft.com/en-us/azure/devops/pipelines/library/connect-to-azure) and [manual WIF setup](https://learn.microsoft.com/en-us/azure/devops/pipelines/release/configure-workload-identity). No subscription IDs, tenants, client secrets, or credentials belong in this repository.

## Create the pipelines

1. Create an Azure Pipeline using `azure-pipelines/validate.yml`; name it **Bicep validation**.
2. Create a manual Azure Pipeline using `azure-pipelines/self-service.yml`; name it **Approved workload self-service**.
3. Authorize only the controlled service connections shown above. The pipeline resolves their names from the reviewed catalogue; queue-time users cannot supply another connection.
4. Create Azure DevOps environments named `azure-nonproduction` and `azure-production`.
5. On `azure-production`, require one or more platform approvers and enable an **Exclusive lock** check. Use the same lock on `azure-nonproduction` if concurrent changes to a subscription need serialization. The self-service YAML also requests sequential lock behavior.
6. Limit who may queue the self-service pipeline and who may administer environments/service connections. Require a review for changes under `catalogue/`, `workloads/`, and `azure-pipelines/`.

The self-service pipeline always runs offline validation, Azure validation, and what-if before a deployment job reaches its protected environment. It publishes the compiled request, Azure validate output, what-if output, deployment result, and a Markdown summary with resource IDs and portal links when the template returns those outputs.

## Azure Repos branch policy

Azure Repos does not use YAML `pr:` triggers for pull request validation; build validation is a branch policy. The supplied validation YAML explicitly uses `trigger: none` and `pr: none` so it is only queued by the policy or manually.

After the **Bicep validation** pipeline exists, configure `main` in **Repos > Branches > Branch policies**:

1. Add **Build validation** and select **Bicep validation**.
2. Set Trigger to **Automatic**, Policy requirement to **Required**, and queue-on-source-update-only as appropriate for the team.
3. Set build expiration according to the rate of updates on `main`; immediate expiry is safest for a low-churn infrastructure repository.
4. Add minimum-reviewer, comment-resolution, and path-based reviewer policies according to your governance model.

For Azure CLI automation, fill in your own Azure DevOps organization, project, repository ID, and pipeline definition ID; these values are intentionally not guessed:

```bash
az repos policy build create \
  --blocking true \
  --branch main \
  --build-definition-id <validation-pipeline-definition-id> \
  --display-name "Bicep validation" \
  --enabled true \
  --manual-queue-only false \
  --queue-on-source-update-only true \
  --repository-id <azure-repos-repository-id> \
  --valid-duration 0 \
  --org https://dev.azure.com/<organization> \
  --project <project>
```

The source repository is currently GitHub-hosted. If it remains on GitHub, configure the equivalent required status check/branch protection there instead; the Azure Repos policy instructions are provided for the requested Azure Repos scenario.

## Authenticated validation without deployment

Queue **Bicep validation** manually with `runAzureValidation=true`, an approved workload/environment pair, and valid inputs. Its Azure stage invokes only `az deployment {sub|group|mg|tenant} validate` and `what-if`; it never invokes `create`. It has no deployment job and does not target a protected environment.

Queue **Approved workload self-service** for an approved request when a deployment is intended. Its deployment stage uses the catalogue-selected protected environment, re-resolves the request to guard against YAML/catalogue drift, and calls `create` only after the preceding validation/what-if stage has passed and the environment checks approve it. It does not repeat an interactive CLI prompt; the protected Azure DevOps environment is the approval gate.
