"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class CosmosConfig:
    """Hold Microsoft Azure Cosmos DB connection settings."""

    endpoint: str = field(default_factory=lambda: _env("AZURE_COSMOS_ENDPOINT"))
    database: str = field(
        default_factory=lambda: _env("AZURE_COSMOS_DATABASE", "curate")
    )


@dataclass(frozen=True)
class FoundryConfig:
    """Hold Microsoft Foundry project and model settings."""

    project_endpoint: str = field(
        default_factory=lambda: _env("FOUNDRY_PROJECT_ENDPOINT")
    )
    model: str = field(default_factory=lambda: _env("FOUNDRY_MODEL"))
    provider: str = field(default_factory=lambda: _env("FOUNDRY_PROVIDER", "cloud"))
    local_model: str = field(
        default_factory=lambda: _env("FOUNDRY_LOCAL_MODEL", "phi-4-mini")
    )

    @property
    def is_local(self) -> bool:
        """Return True when using Foundry Local for on-device inference."""
        return self.provider == "local"


@dataclass(frozen=True)
class StorageConfig:
    """Hold Microsoft Azure Blob Storage connection settings."""

    account_url: str = field(default_factory=lambda: _env("AZURE_STORAGE_ACCOUNT_URL"))
    container: str = field(
        default_factory=lambda: _env("AZURE_STORAGE_CONTAINER", "$web")
    )


@dataclass(frozen=True)
class EntraConfig:
    """Hold Microsoft Entra ID authentication settings."""

    tenant_id: str = field(default_factory=lambda: _env("ENTRA_TENANT_ID"))
    client_id: str = field(default_factory=lambda: _env("ENTRA_CLIENT_ID"))
    client_secret: str = field(default_factory=lambda: _env("ENTRA_CLIENT_SECRET"))
    redirect_uri: str = field(
        default_factory=lambda: _env(
            "ENTRA_REDIRECT_URI", "http://localhost:8000/auth/callback"
        )
    )

    @property
    def authority(self) -> str:
        """Return the Microsoft Entra ID authority URL."""
        return f"https://login.microsoftonline.com/{self.tenant_id}"


@dataclass(frozen=True)
class MonitorConfig:
    """Hold Application Insights connection settings."""

    connection_string: str = field(
        default_factory=lambda: _env("AZURE_APPLICATIONINSIGHTS_CONNECTION_STRING")
    )


@dataclass(frozen=True)
class FoundryMemoryConfig:
    """Hold Microsoft Foundry Memory settings."""

    memory_store_name: str = field(
        default_factory=lambda: _env("FOUNDRY_MEMORY_STORE_NAME", "editorial-memory")
    )
    chat_model: str = field(
        default_factory=lambda: _env("FOUNDRY_CHAT_MODEL", "gpt-4.1-mini")
    )
    embedding_model: str = field(
        default_factory=lambda: _env(
            "FOUNDRY_EMBEDDING_MODEL", "text-embedding-3-small"
        )
    )
    enabled: bool = field(
        default_factory=lambda: _env("FOUNDRY_MEMORY_ENABLED", "true").lower() == "true"
    )


@dataclass(frozen=True)
class ServiceBusConfig:
    """Hold Azure Service Bus connection settings."""

    connection_string: str = field(
        default_factory=lambda: _env("AZURE_SERVICEBUS_CONNECTION_STRING")
    )
    topic_name: str = field(
        default_factory=lambda: _env("AZURE_SERVICEBUS_TOPIC_NAME", "pipeline-events")
    )
    subscription_name: str = field(
        default_factory=lambda: _env(
            "AZURE_SERVICEBUS_SUBSCRIPTION_NAME", "web-consumer"
        )
    )


@dataclass(frozen=True)
class AppConfig:
    """Hold general application settings."""

    env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    secret_key: str = field(default_factory=lambda: _env("APP_SECRET_KEY"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    slow_request_ms: int = field(
        default_factory=lambda: int(_env("APP_SLOW_REQUEST_MS", "800"))
    )
    slow_repository_ms: int = field(
        default_factory=lambda: int(_env("APP_SLOW_REPOSITORY_MS", "250"))
    )

    @property
    def is_development(self) -> bool:
        """Return True when running in the development environment."""
        return self.env == "development"


@dataclass(frozen=True)
class Settings:
    """Aggregate all configuration sections into a single settings object."""

    cosmos: CosmosConfig = field(default_factory=CosmosConfig)
    foundry: FoundryConfig = field(default_factory=FoundryConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    entra: EntraConfig = field(default_factory=EntraConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    memory: FoundryMemoryConfig = field(default_factory=FoundryMemoryConfig)
    servicebus: ServiceBusConfig = field(default_factory=ServiceBusConfig)
    app: AppConfig = field(default_factory=AppConfig)


def load_settings() -> Settings:
    """Load settings from environment variables, reading .env in development."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    return Settings()
