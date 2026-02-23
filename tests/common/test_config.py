"""Tests for configuration module."""

import pytest

from curate_common.config import (
    AppConfig,
    CosmosConfig,
    EntraConfig,
    FoundryConfig,
    ServiceBusConfig,
    Settings,
    StorageConfig,
    _env,
)


def test_env_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify env returns value."""
    monkeypatch.setenv("TEST_KEY", "hello")
    assert _env("TEST_KEY") == "hello"


def test_env_returns_default_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify env returns default when missing."""
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert _env("TEST_KEY", "fallback") == "fallback"


def test_env_returns_empty_string_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify env returns empty string default."""
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert _env("TEST_KEY") == ""


def test_entra_authority() -> None:
    """Verify entra authority."""
    config = EntraConfig.__new__(EntraConfig)
    object.__setattr__(config, "tenant_id", "my-tenant")
    assert config.authority == "https://login.microsoftonline.com/my-tenant"


def test_app_config_is_development_true() -> None:
    """Verify app config is development true."""
    config = AppConfig.__new__(AppConfig)
    object.__setattr__(config, "env", "development")
    assert config.is_development is True


def test_app_config_is_development_false() -> None:
    """Verify app config is development false."""
    config = AppConfig.__new__(AppConfig)
    object.__setattr__(config, "env", "production")
    assert config.is_development is False


def test_cosmos_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify cosmos config defaults."""
    monkeypatch.setenv("AZURE_COSMOS_ENDPOINT", "https://cosmos.example.com")
    monkeypatch.delenv("AZURE_COSMOS_DATABASE", raising=False)
    config = CosmosConfig()
    assert config.endpoint == "https://cosmos.example.com"
    assert config.database == "curate"


def test_foundry_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Foundry config reads env vars."""
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://test.services.ai.azure.com")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-4.1")
    config = FoundryConfig()
    assert config.project_endpoint == "https://test.services.ai.azure.com"
    assert config.model == "gpt-4.1"


def test_storage_config_default_container(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify storage config default container."""
    monkeypatch.setenv(
        "AZURE_STORAGE_ACCOUNT_URL", "https://test.blob.core.windows.net"
    )
    monkeypatch.delenv("AZURE_STORAGE_CONTAINER", raising=False)
    config = StorageConfig()
    assert config.container == "$web"


def test_settings_creates_all_sub_configs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings creates all sub configs."""
    for key in [
        "AZURE_COSMOS_ENDPOINT",
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL",
        "AZURE_STORAGE_ACCOUNT_URL",
        "ENTRA_TENANT_ID",
        "ENTRA_CLIENT_ID",
        "ENTRA_CLIENT_SECRET",
    ]:
        monkeypatch.setenv(key, "test")
    settings = Settings()
    assert isinstance(settings.cosmos, CosmosConfig)
    assert isinstance(settings.foundry, FoundryConfig)
    assert isinstance(settings.storage, StorageConfig)
    assert isinstance(settings.entra, EntraConfig)
    assert isinstance(settings.app, AppConfig)


def test_servicebus_names_ignore_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Service Bus names are centrally defined and not env-overridable."""
    monkeypatch.setenv("AZURE_SERVICEBUS_CONNECTION_STRING", "Endpoint=sb://test")
    monkeypatch.setenv("AZURE_SERVICEBUS_TOPIC_NAME", "legacy-topic")
    monkeypatch.setenv("AZURE_SERVICEBUS_COMMAND_TOPIC_NAME", "override-commands")
    monkeypatch.setenv("AZURE_SERVICEBUS_EVENT_TOPIC_NAME", "override-events")
    monkeypatch.setenv("AZURE_SERVICEBUS_SUBSCRIPTION_NAME", "override-web")
    monkeypatch.setenv("AZURE_SERVICEBUS_WORKER_SUBSCRIPTION_NAME", "override-worker")

    config = ServiceBusConfig()

    assert config.topic_name == "pipeline-events"
    assert config.command_topic_name == "pipeline-commands"
    assert config.event_topic_name == "pipeline-events"
    assert config.subscription_name == "web-consumer"
    assert config.worker_subscription_name == "worker-consumer"


def test_servicebus_connection_string_reads_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Service Bus connection string remains env-configurable."""
    monkeypatch.setenv("AZURE_SERVICEBUS_CONNECTION_STRING", "Endpoint=sb://test")

    config = ServiceBusConfig()

    assert config.connection_string == "Endpoint=sb://test"
