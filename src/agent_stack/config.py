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
    """Hold Azure Cosmos DB connection settings."""

    endpoint: str = field(default_factory=lambda: _env("COSMOS_ENDPOINT"))
    key: str = field(default_factory=lambda: _env("COSMOS_KEY"))
    database: str = field(
        default_factory=lambda: _env("COSMOS_DATABASE", "agent-stack")
    )


@dataclass(frozen=True)
class OpenAIConfig:
    """Hold Azure OpenAI endpoint and deployment settings."""

    endpoint: str = field(default_factory=lambda: _env("AZURE_OPENAI_ENDPOINT"))
    deployment: str = field(default_factory=lambda: _env("AZURE_OPENAI_DEPLOYMENT"))


@dataclass(frozen=True)
class StorageConfig:
    """Hold Azure Blob Storage connection settings."""

    connection_string: str = field(
        default_factory=lambda: _env("AZURE_STORAGE_CONNECTION_STRING")
    )
    container: str = field(
        default_factory=lambda: _env("AZURE_STORAGE_CONTAINER", "$web")
    )


@dataclass(frozen=True)
class EntraConfig:
    """Hold Entra ID authentication settings."""

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
        """Return the Entra ID authority URL."""
        return f"https://login.microsoftonline.com/{self.tenant_id}"


@dataclass(frozen=True)
class MonitorConfig:
    """Hold Application Insights connection settings."""

    connection_string: str = field(
        default_factory=lambda: _env("APPLICATIONINSIGHTS_CONNECTION_STRING")
    )


@dataclass(frozen=True)
class AppConfig:
    """Hold general application settings."""

    env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    secret_key: str = field(default_factory=lambda: _env("APP_SECRET_KEY"))
    app_config_endpoint: str = field(
        default_factory=lambda: _env("APP_CONFIG_ENDPOINT")
    )
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    @property
    def is_development(self) -> bool:
        """Return True when running in the development environment."""
        return self.env == "development"


@dataclass(frozen=True)
class Settings:
    """Aggregate all configuration sections into a single settings object."""

    cosmos: CosmosConfig = field(default_factory=CosmosConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    entra: EntraConfig = field(default_factory=EntraConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    app: AppConfig = field(default_factory=AppConfig)


def load_settings() -> Settings:
    """Load settings from environment variables, reading .env in development."""
    env_path = Path.cwd() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    return Settings()
