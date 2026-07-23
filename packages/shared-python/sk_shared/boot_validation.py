"""Shared boot-time "still at a placeholder default" credential validator.

Every service has grown its own ad hoc version of the same check:

- ``apps/gateway/src/config.py::validate_critical_settings()`` -- a
  standalone function (called from ``main.py`` at startup) that, when
  ``ENVIRONMENT == "production"``, compares several settings against their
  known-insecure defaults (``KMS_MOCK_KEY_HEX``, ``INTERNAL_SERVICE_TOKEN``,
  ``INTERNAL_API_KEY``, ...) and raises ``RuntimeError`` with all violations
  joined into one message if any still match.
- ``apps/product-service/src/config.py`` -- a pydantic
  ``@model_validator(mode="after")`` that raises ``ValueError`` if
  ``ENVIRONMENT != "local"`` and ``INTERNAL_SERVICE_TOKEN == "dev-secret-token"``.
- ``apps/notification-service/src/config.py`` -- the same pattern, guarding
  ``INTERNAL_API_KEY == "test-key"`` when ``ENVIRONMENT != "local"``.

All three encode the identical rule ("if this setting is still equal to its
known placeholder value, and we are not in a local/dev environment, that is a
boot-time configuration error") with different plumbing. This module extracts
that rule once.

Usage
-----
::

    from sk_shared.boot_validation import check_placeholder_credentials, raise_if_placeholder_credentials

    # Return-list style (e.g. inside a pydantic `@model_validator`, or to log
    # every problem before deciding whether to raise):
    errors = check_placeholder_credentials(
        [
            ("INTERNAL_SERVICE_TOKEN", settings.INTERNAL_SERVICE_TOKEN, "dev-secret-token"),
        ],
        environment=settings.ENVIRONMENT,
    )
    if errors:
        raise ValueError(errors[0])

    # Raise-directly style (mirrors gateway's `validate_critical_settings()`,
    # called once from `main.py` at startup, collecting *all* violations into
    # one RuntimeError instead of failing on the first):
    def validate_critical_settings() -> None:
        raise_if_placeholder_credentials(
            [
                ("KMS_MOCK_KEY_HEX", settings.KMS_MOCK_KEY_HEX, "0123456789abcdef" * 4),
                ("INTERNAL_SERVICE_TOKEN", settings.INTERNAL_SERVICE_TOKEN, "local-internal-token"),
                ("INTERNAL_API_KEY", settings.INTERNAL_API_KEY, "test-key"),
            ],
            environment=settings.ENVIRONMENT,
            error_prefix="PRODUCTION_CONFIG_VALIDATION_FAILED",
        )

Each service's existing ``validate_critical_settings()``-style function (or
pydantic validator) becomes a thin wrapper that builds its own list of
``(name, current_value, placeholder_value)`` tuples and delegates here, rather
than reimplementing the "raise if still default outside local" logic anew.
Wiring this into any individual service's `main.py`/`config.py` is a separate
Phase 2 step, one service at a time -- this module only builds and tests the
shared helper itself.

Note on ``environment`` semantics: this helper treats *any* non-local
environment (``environment != local_environment``, default local_environment
``"local"``) as requiring real credentials -- matching product-service and
notification-service. Gateway's existing check is narrower (it only checks in
``"production"``, not e.g. ``"staging"``); a future gateway wrapper can either
adopt the stricter "not local" behavior or pre-filter its own checks list
before calling this helper if it wants to preserve the old, narrower scope.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, Tuple

PlaceholderCheck = Tuple[str, Any, Any]

LOCAL_ENVIRONMENT_DEFAULT = "local"


def check_placeholder_credentials(
    checks: Iterable[PlaceholderCheck],
    environment: str,
    *,
    local_environment: str = LOCAL_ENVIRONMENT_DEFAULT,
    settings_obj: Optional[Any] = None,
) -> list[str]:
    """Return human-readable errors for any setting still at its placeholder value.

    Args:
        checks: an iterable of ``(setting_name, current_value, placeholder_value)``
            tuples. ``setting_name`` is used only for the error message;
            ``current_value`` is compared with ``==`` against
            ``placeholder_value``.
        environment: the service's current ``ENVIRONMENT`` (e.g. "local",
            "test", "staging", "production").
        local_environment: the environment value that skips validation
            entirely (default ``"local"``, matching every service's
            existing convention).
        settings_obj: optional -- if provided and it has a ``SERVICE_NAME``
            attribute, error messages are prefixed with it (useful when
            aggregating errors from multiple services, e.g. in a shared
            startup script).

    Returns:
        A list of human-readable error strings, one per setting still equal
        to its placeholder value. Empty (``[]``) when ``environment ==
        local_environment`` or when every setting has been changed from its
        placeholder.
    """
    if environment == local_environment:
        return []

    service_name = getattr(settings_obj, "SERVICE_NAME", None) if settings_obj is not None else None
    prefix = f"{service_name}: " if service_name else ""

    errors: list[str] = []
    for name, current_value, placeholder_value in checks:
        if current_value == placeholder_value:
            errors.append(
                f"{prefix}{name} is still set to its default placeholder value "
                f"({placeholder_value!r}) -- it must be changed outside the "
                f"'{local_environment}' environment (current environment: '{environment}')"
            )
    return errors


def raise_if_placeholder_credentials(
    checks: Sequence[PlaceholderCheck],
    environment: str,
    *,
    local_environment: str = LOCAL_ENVIRONMENT_DEFAULT,
    settings_obj: Optional[Any] = None,
    error_prefix: str = "CONFIG_VALIDATION_FAILED",
) -> None:
    """Raise ``RuntimeError`` listing every placeholder-value violation, if any.

    Convenience wrapper around :func:`check_placeholder_credentials` for
    services (like gateway) that call a single ``validate_critical_settings()``
    function at startup and want one combined error covering every violation,
    rather than failing on the first.
    """
    errors = check_placeholder_credentials(
        checks,
        environment,
        local_environment=local_environment,
        settings_obj=settings_obj,
    )
    if errors:
        raise RuntimeError(f"{error_prefix}:\n" + "\n".join(f"  - {e}" for e in errors))
