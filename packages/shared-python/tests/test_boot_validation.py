import pytest

from sk_shared.boot_validation import (
    LOCAL_ENVIRONMENT_DEFAULT,
    check_placeholder_credentials,
    raise_if_placeholder_credentials,
)


# --- check_placeholder_credentials -----------------------------------------


def test_local_environment_always_passes_even_with_placeholder_value():
    errors = check_placeholder_credentials(
        [("INTERNAL_SERVICE_TOKEN", "dev-secret-token", "dev-secret-token")],
        environment="local",
    )
    assert errors == []


def test_placeholder_value_in_non_local_environment_produces_error():
    errors = check_placeholder_credentials(
        [("INTERNAL_SERVICE_TOKEN", "dev-secret-token", "dev-secret-token")],
        environment="production",
    )
    assert len(errors) == 1
    assert "INTERNAL_SERVICE_TOKEN" in errors[0]
    assert "dev-secret-token" in errors[0]
    assert "production" in errors[0]
    assert "local" in errors[0]


def test_real_value_in_non_local_environment_passes_cleanly():
    errors = check_placeholder_credentials(
        [("INTERNAL_SERVICE_TOKEN", "a-real-rotated-secret", "dev-secret-token")],
        environment="production",
    )
    assert errors == []


def test_empty_checks_list_returns_no_errors():
    assert check_placeholder_credentials([], environment="production") == []


def test_multiple_checks_only_flags_the_ones_still_at_placeholder():
    errors = check_placeholder_credentials(
        [
            ("KMS_MOCK_KEY_HEX", "0123456789abcdef" * 4, "0123456789abcdef" * 4),
            ("INTERNAL_SERVICE_TOKEN", "a-real-rotated-secret", "dev-secret-token"),
            ("INTERNAL_API_KEY", "test-key", "test-key"),
        ],
        environment="production",
    )
    assert len(errors) == 2
    joined = "\n".join(errors)
    assert "KMS_MOCK_KEY_HEX" in joined
    assert "INTERNAL_API_KEY" in joined
    assert "INTERNAL_SERVICE_TOKEN" not in joined


def test_custom_local_environment_is_respected():
    # A service that treats "dev" (not "local") as its no-validation environment.
    errors = check_placeholder_credentials(
        [("INTERNAL_API_KEY", "test-key", "test-key")],
        environment="dev",
        local_environment="dev",
    )
    assert errors == []

    errors = check_placeholder_credentials(
        [("INTERNAL_API_KEY", "test-key", "test-key")],
        environment="local",
        local_environment="dev",
    )
    assert len(errors) == 1


def test_default_local_environment_constant_matches_default_argument():
    assert LOCAL_ENVIRONMENT_DEFAULT == "local"


def test_settings_obj_with_service_name_prefixes_error_messages():
    class FakeSettings:
        SERVICE_NAME = "gateway"

    errors = check_placeholder_credentials(
        [("INTERNAL_API_KEY", "test-key", "test-key")],
        environment="production",
        settings_obj=FakeSettings(),
    )
    assert len(errors) == 1
    assert errors[0].startswith("gateway: ")


def test_settings_obj_without_service_name_has_no_prefix():
    class FakeSettings:
        pass

    errors = check_placeholder_credentials(
        [("INTERNAL_API_KEY", "test-key", "test-key")],
        environment="production",
        settings_obj=FakeSettings(),
    )
    assert len(errors) == 1
    assert not errors[0].startswith(":")
    assert errors[0].startswith("INTERNAL_API_KEY")


def test_settings_obj_none_has_no_prefix():
    errors = check_placeholder_credentials(
        [("INTERNAL_API_KEY", "test-key", "test-key")],
        environment="production",
        settings_obj=None,
    )
    assert errors[0].startswith("INTERNAL_API_KEY")


def test_non_string_values_are_compared_with_equality():
    # Values need not be strings -- equality comparison should work for any type.
    errors = check_placeholder_credentials(
        [("SOME_FLAG", 0, 0), ("OTHER_FLAG", 1, 0)],
        environment="production",
    )
    assert len(errors) == 1
    assert "SOME_FLAG" in errors[0]


# --- raise_if_placeholder_credentials ---------------------------------------


def test_raise_if_placeholder_credentials_passes_when_no_violations():
    raise_if_placeholder_credentials(
        [("INTERNAL_API_KEY", "a-real-rotated-secret", "test-key")],
        environment="production",
    )  # should not raise


def test_raise_if_placeholder_credentials_passes_in_local_environment():
    raise_if_placeholder_credentials(
        [("INTERNAL_API_KEY", "test-key", "test-key")],
        environment="local",
    )  # should not raise despite the placeholder match


def test_raise_if_placeholder_credentials_raises_runtime_error_with_all_violations():
    with pytest.raises(RuntimeError) as exc_info:
        raise_if_placeholder_credentials(
            [
                ("KMS_MOCK_KEY_HEX", "0123456789abcdef" * 4, "0123456789abcdef" * 4),
                ("INTERNAL_SERVICE_TOKEN", "local-internal-token", "local-internal-token"),
                ("INTERNAL_API_KEY", "a-real-rotated-secret", "test-key"),
            ],
            environment="production",
            error_prefix="PRODUCTION_CONFIG_VALIDATION_FAILED",
        )
    message = str(exc_info.value)
    assert message.startswith("PRODUCTION_CONFIG_VALIDATION_FAILED:")
    assert "KMS_MOCK_KEY_HEX" in message
    assert "INTERNAL_SERVICE_TOKEN" in message
    assert "INTERNAL_API_KEY" not in message


def test_raise_if_placeholder_credentials_default_error_prefix():
    with pytest.raises(RuntimeError) as exc_info:
        raise_if_placeholder_credentials(
            [("INTERNAL_API_KEY", "test-key", "test-key")],
            environment="staging",
        )
    assert str(exc_info.value).startswith("CONFIG_VALIDATION_FAILED:")


def test_raise_if_placeholder_credentials_with_empty_checks_does_not_raise():
    raise_if_placeholder_credentials([], environment="production")  # should not raise
