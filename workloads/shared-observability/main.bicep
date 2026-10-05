targetScope = 'subscription'

@description('Deployment environment represented in resource names and tags.')
@allowed([
  'dev'
  'prod'
])
param environment string

@description('Azure region approved by the catalogue target mapping.')
@allowed([
  'uksouth'
  'ukwest'
  'westeurope'
])
param location string

@description('Short service name used to construct deterministic resource names.')
@minLength(3)
@maxLength(20)
param serviceName string

@description('Team or distribution list accountable for the workload.')
@minLength(3)
@maxLength(64)
param owner string

@description('Finance cost centre applied to all resources.')
@minLength(2)
@maxLength(32)
param costCentre string

@description('Log Analytics data retention period.')
@allowed([
  30
  60
  90
])
param retentionInDays int = 30

var compactServiceName = replace(serviceName, '-', '')
var resourceGroupName = 'rg-${serviceName}-observability-${environment}'
var workspaceName = 'log-${compactServiceName}-${environment}-${uniqueString(subscription().subscriptionId)}'
var commonTags = {
  environment: environment
  owner: owner
  costCentre: costCentre
  managedBy: 'bicep-self-service'
  workload: 'shared-observability'
  ownershipBoundary: 'shared-platform'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
  tags: commonTags
}

module workspace 'br/public:avm/res/operational-insights/workspace:0.16.1' = {
  name: 'deploy-log-analytics-workspace'
  scope: resourceGroup
  params: {
    name: workspaceName
    location: location
    dataRetention: retentionInDays
    tags: commonTags
  }
}

output resourceIds array = [
  resourceGroup.id
  workspace.outputs.resourceId
]
output portalLinks array = [
  'https://portal.azure.com/#@/resource${resourceGroup.id}'
  'https://portal.azure.com/#@/resource${workspace.outputs.resourceId}'
]
output ownershipBoundary string = 'shared-platform'
