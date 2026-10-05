targetScope = 'subscription'

@description('Deployment environment represented in resource names and tags.')
@allowed([
  'dev'
  'test'
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

@description('Approved storage redundancy and performance option.')
@allowed([
  'Standard_LRS'
  'Standard_GRS'
  'Standard_ZRS'
])
param storageSku string = 'Standard_LRS'

var compactServiceName = replace(serviceName, '-', '')
var resourceGroupName = 'rg-${serviceName}-${environment}'
var storageNamePrefix = take(compactServiceName, 5)
var storageAccountName = 'st${storageNamePrefix}${environment}${uniqueString(subscription().subscriptionId, serviceName)}'
var commonTags = {
  environment: environment
  owner: owner
  costCentre: costCentre
  managedBy: 'bicep-self-service'
  workload: 'application-storage'
  ownershipBoundary: 'application'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
  tags: commonTags
}

module storageAccount 'br/public:avm/res/storage/storage-account:0.33.1' = {
  name: 'deploy-storage-account'
  scope: resourceGroup
  params: {
    name: storageAccountName
    location: location
    kind: 'StorageV2'
    skuName: storageSku
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    tags: commonTags
  }
}

output resourceIds array = [
  resourceGroup.id
  storageAccount.outputs.resourceId
]
output portalLinks array = [
  'https://portal.azure.com/#@/resource${resourceGroup.id}'
  'https://portal.azure.com/#@/resource${storageAccount.outputs.resourceId}'
]
output ownershipBoundary string = 'application'
