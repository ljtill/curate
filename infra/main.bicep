targetScope = 'resourceGroup'

@description('Environment name (dev or prod)')
param environment string

@description('Primary location for all resources')
param location string = resourceGroup().location

@description('Base name for resources')
param baseName string = 'agentstack'

@description('Container image tag')
param imageTag string = 'latest'

module identity 'modules/managed-identity.bicep' = {
  name: 'identity'
  params: {
    name: '${baseName}-${environment}-id'
    location: location
  }
}

module cosmosDb 'modules/cosmos-db.bicep' = {
  name: 'cosmos-db'
  params: {
    name: '${baseName}-${environment}-cosmos'
    location: location
    principalId: identity.outputs.principalId
  }
}

module storage 'modules/storage-account.bicep' = {
  name: 'storage-account'
  params: {
    name: replace('${baseName}${environment}sa', '-', '')
    location: location
    principalId: identity.outputs.principalId
  }
}

module appConfig 'modules/app-configuration.bicep' = {
  name: 'app-configuration'
  params: {
    name: '${baseName}-${environment}-appconfig'
    location: location
    principalId: identity.outputs.principalId
    cosmosEndpoint: cosmosDb.outputs.endpoint
    cosmosDatabase: cosmosDb.outputs.databaseName
    storageAccountUrl: storage.outputs.accountUrl
    appInsightsConnectionString: appInsights.outputs.connectionString
  }
}

module acr 'modules/container-registry.bicep' = {
  name: 'container-registry'
  params: {
    name: replace('${baseName}${environment}acr', '-', '')
    location: location
    principalId: identity.outputs.principalId
  }
}

module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    name: '${baseName}-${environment}-app'
    location: location
    identityId: identity.outputs.id
    acrLoginServer: acr.outputs.loginServer
    imageTag: imageTag
    logAnalyticsCustomerId: logAnalytics.outputs.customerId
    logAnalyticsSharedKey: logAnalytics.outputs.sharedKey
    appInsightsConnectionString: appInsights.outputs.connectionString
  }
}

module staticWebApp 'modules/static-web-apps.bicep' = {
  name: 'static-web-apps'
  params: {
    name: '${baseName}-${environment}-swa'
    location: location
  }
}

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  params: {
    name: '${baseName}-${environment}-law'
    location: location
    retentionInDays: environment == 'prod' ? 90 : 30
  }
}

module appInsights 'modules/app-insights.bicep' = {
  name: 'app-insights'
  params: {
    name: '${baseName}-${environment}-appi'
    location: location
    workspaceId: logAnalytics.outputs.id
  }
}

output cosmosEndpoint string = cosmosDb.outputs.endpoint
output storageAccountName string = storage.outputs.name
output acrLoginServer string = acr.outputs.loginServer
output containerAppUrl string = containerApps.outputs.url
output staticWebAppUrl string = staticWebApp.outputs.url
