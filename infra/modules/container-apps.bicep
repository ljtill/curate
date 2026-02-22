@description('Name of the container app')
param name string

@description('Location for the resource')
param location string

@description('User-assigned managed identity resource ID')
param identityId string

@description('ACR login server')
param acrLoginServer string

@description('Container image tag')
param imageTag string

@description('Log Analytics workspace customer ID')
param logAnalyticsCustomerId string

@description('Log Analytics workspace shared key')
@secure()
param logAnalyticsSharedKey string

@description('Application Insights connection string')
@secure()
param appInsightsConnectionString string

@description('Microsoft Foundry project endpoint for memory service')
param foundryProjectEndpoint string = ''

@description('Foundry Memory store name')
param foundryMemoryStoreName string = 'editorial-memory'

@description('Foundry embedding model deployment name')
param foundryEmbeddingModel string = 'text-embedding-3-small'

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: '${name}-env'
  location: location
  properties: {
    zoneRedundant: false
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2025-07-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'agent-stack'
          image: '${acrLoginServer}/agent-stack:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'AZURE_APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsightsConnectionString
            }
            {
              name: 'FOUNDRY_PROJECT_ENDPOINT'
              value: foundryProjectEndpoint
            }
            {
              name: 'FOUNDRY_MEMORY_STORE_NAME'
              value: foundryMemoryStoreName
            }
            {
              name: 'FOUNDRY_EMBEDDING_MODEL'
              value: foundryEmbeddingModel
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-requests'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
