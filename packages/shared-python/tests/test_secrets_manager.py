"""Tests for sk_shared.secrets_manager -- the generic AWS Secrets Manager
loader used by every backend service's src/config.py (see
docs/SECRETS_MANAGER_MIGRATION.md and each service's
_SECRETS_MANAGER_FIELD_MAP / get_settings()).

Uses a minimal fake boto3-shaped client (mirroring the FakeRedis-style
convention in test_rate_limit.py) instead of hitting real AWS -- this suite
must never make a network call.
"""
import json

import pytest

import sk_shared.secrets_manager as secrets_manager_module
from sk_shared.secrets_manager import SecretsManagerLoadError, load_secrets_manager_overrides


class _ResourceNotFoundException(Exception):
    pass


class _FakeExceptions:
    ResourceNotFoundException = _ResourceNotFoundException


class FakeSecretsManagerClient:
    """Minimal stand-in for boto3's Secrets Manager client."""

    def __init__(self, secrets: dict[str, str] | None = None, missing: set[str] | None = None, errors: dict[str, Exception] | None = None):
        self.secrets = secrets or {}
        self.missing = missing or set()
        self.errors = errors or {}
        self.exceptions = _FakeExceptions()
        self.calls: list[str] = []

    def get_secret_value(self, SecretId: str):
        self.calls.append(SecretId)
        if SecretId in self.missing:
            raise self.exceptions.ResourceNotFoundException(SecretId)
        if SecretId in self.errors:
            raise self.errors[SecretId]
        return {"SecretString": self.secrets[SecretId]}


@pytest.fixture(autouse=True)
def clear_client_cache():
    """The real _get_secretsmanager_client is lru_cache'd; each test patches
    it directly (bypassing the cache), but clear it anyway so no test can
    leak a real boto3 client into another via the cache."""
    secrets_manager_module._get_secretsmanager_client.cache_clear()
    yield
    secrets_manager_module._get_secretsmanager_client.cache_clear()


def _patch_client(monkeypatch, fake_client: FakeSecretsManagerClient) -> None:
    monkeypatch.setattr(
        secrets_manager_module,
        "_get_secretsmanager_client",
        lambda region: fake_client,
    )


def test_fetches_each_secret_and_returns_field_name_keyed_dict(monkeypatch):
    fake = FakeSecretsManagerClient(
        secrets={
            "gateway/prod/database-url": "postgresql://real-prod-db",
            "gateway/prod/redis-url": "redis://real-prod-redis",
        }
    )
    _patch_client(monkeypatch, fake)

    result = load_secrets_manager_overrides(
        service_prefix="gateway",
        environment="prod",
        secret_field_map={"database-url": "DATABASE_URL", "redis-url": "REDIS_URL"},
        region="us-east-1",
    )

    assert result == {
        "DATABASE_URL": "postgresql://real-prod-db",
        "REDIS_URL": "redis://real-prod-redis",
    }


def test_secret_name_is_service_prefix_slash_environment_slash_key(monkeypatch):
    fake = FakeSecretsManagerClient(secrets={"ledger-service/staging/internal-api-token": "tok"})
    _patch_client(monkeypatch, fake)

    load_secrets_manager_overrides(
        service_prefix="ledger-service",
        environment="staging",
        secret_field_map={"internal-api-token": "internal_api_token"},
        region="ap-south-1",
    )

    assert fake.calls == ["ledger-service/staging/internal-api-token"]


def test_lowercase_field_names_supported_for_ledger_service_style_settings(monkeypatch):
    """ledger-service's Settings class uses lower_snake field names, unlike
    the other four services' UPPER_SNAKE convention -- the returned dict key
    must match exactly whatever field name the caller asked for."""
    fake = FakeSecretsManagerClient(secrets={"ledger-service/prod/database-url": "postgresql://x"})
    _patch_client(monkeypatch, fake)

    result = load_secrets_manager_overrides(
        service_prefix="ledger-service",
        environment="prod",
        secret_field_map={"database-url": "database_url"},
        region="us-east-1",
    )

    assert result == {"database_url": "postgresql://x"}


def test_json_object_secret_merges_its_own_keys_instead_of_field_name(monkeypatch):
    fake = FakeSecretsManagerClient(
        secrets={"payment-orchestrator/prod/db-credentials": json.dumps({"DATABASE_URL": "postgresql://combo", "DB_USER": "svc"})}
    )
    _patch_client(monkeypatch, fake)

    result = load_secrets_manager_overrides(
        service_prefix="payment-orchestrator",
        environment="prod",
        secret_field_map={"db-credentials": "DATABASE_URL"},
        region="us-east-1",
    )

    assert result == {"DATABASE_URL": "postgresql://combo", "DB_USER": "svc"}


def test_json_array_secret_falls_back_to_raw_string(monkeypatch):
    """A secret that happens to parse as JSON but isn't an object (e.g. a
    plain string that looks like a number, or a JSON array) is treated as an
    opaque string value under the mapped field name, not merged."""
    fake = FakeSecretsManagerClient(secrets={"gateway/prod/jwt-private-key": "12345"})
    _patch_client(monkeypatch, fake)

    result = load_secrets_manager_overrides(
        service_prefix="gateway",
        environment="prod",
        secret_field_map={"jwt-private-key": "JWT_PRIVATE_KEY"},
        region="us-east-1",
    )

    assert result == {"JWT_PRIVATE_KEY": "12345"}


def test_missing_secret_raises_secrets_manager_load_error(monkeypatch):
    fake = FakeSecretsManagerClient(missing={"gateway/prod/database-url"})
    _patch_client(monkeypatch, fake)

    with pytest.raises(SecretsManagerLoadError) as exc_info:
        load_secrets_manager_overrides(
            service_prefix="gateway",
            environment="prod",
            secret_field_map={"database-url": "DATABASE_URL"},
            region="us-east-1",
        )

    assert "database-url" in str(exc_info.value)
    assert "gateway/prod" in str(exc_info.value)


def test_secrets_manager_load_error_is_a_value_error():
    """docs/SECRETS_MANAGER_MIGRATION.md documents callers doing
    `except ValueError` around the Secrets Manager load step -- this must
    keep working."""
    assert issubclass(SecretsManagerLoadError, ValueError)


def test_missing_secret_is_all_or_nothing_not_partial(monkeypatch):
    """One missing secret must fail the whole batch -- callers fall back to
    Settings() (plain env vars/.env) entirely rather than merging a partial
    override on top of defaults."""
    fake = FakeSecretsManagerClient(
        secrets={"gateway/prod/redis-url": "redis://ok"},
        missing={"gateway/prod/database-url"},
    )
    _patch_client(monkeypatch, fake)

    with pytest.raises(SecretsManagerLoadError):
        load_secrets_manager_overrides(
            service_prefix="gateway",
            environment="prod",
            secret_field_map={"database-url": "DATABASE_URL", "redis-url": "REDIS_URL"},
            region="us-east-1",
        )


def test_other_aws_errors_are_wrapped_as_secrets_manager_load_error(monkeypatch):
    fake = FakeSecretsManagerClient(errors={"gateway/prod/database-url": RuntimeError("AccessDeniedException")})
    _patch_client(monkeypatch, fake)

    with pytest.raises(SecretsManagerLoadError) as exc_info:
        load_secrets_manager_overrides(
            service_prefix="gateway",
            environment="prod",
            secret_field_map={"database-url": "DATABASE_URL"},
            region="us-east-1",
        )

    assert "AccessDeniedException" in str(exc_info.value)


def test_empty_secret_field_map_returns_empty_dict_without_any_client_call(monkeypatch):
    def _fail_if_called(region):
        raise AssertionError("client should never be constructed for an empty secret_field_map")

    monkeypatch.setattr(secrets_manager_module, "_get_secretsmanager_client", _fail_if_called)

    result = load_secrets_manager_overrides(
        service_prefix="gateway",
        environment="prod",
        secret_field_map={},
        region="us-east-1",
    )

    assert result == {}
