@description('Name of the App Configuration store')
param name string

@description('Location for the resource')
param location string

@description('Principal ID for role assignment')
param principalId string

@description('Cosmos DB endpoint')
param cosmosEndpoint string

@description('Cosmos DB database name')
param cosmosDatabase string

@description('Storage account URL')
param storageAccountUrl string

@description('Application Insights connection string')
@secure()
param appInsightsConnectionString string

resource appConfig 'Microsoft.AppConfiguration/configurationStores@2023-03-01' = {
  name: name
  location: location
  sku: {
    name: 'free'
  }
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appConfig.id, principalId, '516239f1-63e1-4d78-a4de-a74fb236a071')
  scope: appConfig
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '516239f1-63e1-4d78-a4de-a74fb236a071')
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource cosmosEndpointKv 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfig
  name: 'COSMOS_ENDPOINT'
  properties: {
    value: cosmosEndpoint
  }
}

resource cosmosDatabaseKv 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfig
  name: 'COSMOS_DATABASE'
  properties: {
    value: cosmosDatabase
  }
}

resource storageAccountUrlKv 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfig
  name: 'AZURE_STORAGE_ACCOUNT_URL'
  properties: {
    value: storageAccountUrl
  }
}

resource appInsightsConnectionKv 'Microsoft.AppConfiguration/configurationStores/keyValues@2023-03-01' = {
  parent: appConfig
  name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
  properties: {
    value: appInsightsConnectionString
  }
}

output endpoint string = appConfig.properties.endpoint
