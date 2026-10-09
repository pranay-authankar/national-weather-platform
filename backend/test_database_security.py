"""
Isolated automated tests for database configuration precedence and credential sanitization (Test 11).

Guarantees:
- Tests environment variable precedence over .env (preventing overwrite).
- Tests credential redaction for PostgreSQL URIs, URI-encoded credentials,
  passwords with punctuation/special characters, configured secrets, and arbitrary URI schemes.
- Verifies non-credential error messages remain intact and useful for debugging.
- Fully isolated; zero network or database connections.
"""

import os
from pathlib import Path
import sys
import unittest.mock as mock

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from database import get_db_config, sanitize_error_message


def test_env_precedence_over_dotenv():
    """Verify process-level environment variables take precedence over .env values."""
    custom_host = "explicit-process-host.internal"
    custom_port = "5439"
    custom_user = "explicit_process_user"
    custom_pass = "explicit_process_secret_pass"
    custom_db = "explicit_process_db"

    env_overrides = {
        "DATABASE_HOST": custom_host,
        "DATABASE_PORT": custom_port,
        "DATABASE_USER": custom_user,
        "DATABASE_PASSWORD": custom_pass,
        "DATABASE_NAME": custom_db,
    }

    with mock.patch.dict(os.environ, env_overrides, clear=False):
        config = get_db_config()
        assert config["host"] == custom_host, "Process DATABASE_HOST must not be overwritten by .env"
        assert config["port"] == 5439, "Process DATABASE_PORT must not be overwritten by .env"
        assert config["user"] == custom_user, "Process DATABASE_USER must not be overwritten by .env"
        assert config["password"] == custom_pass, "Process DATABASE_PASSWORD must not be overwritten by .env"
        assert config["dbname"] == custom_db, "Process DATABASE_NAME must not be overwritten by .env"

    print("  [PASS] 1. Process environment variables take precedence over .env file.")


def test_redact_standard_postgres_uri():
    """Verify postgresql://user:password@host:port/db credentials are redacted."""
    raw_error = "Connection failed: postgresql://test_user:sensitive_password_123@aws-cluster.supabase.com:5432/postgres"
    sanitized = sanitize_error_message(raw_error)
    assert "sensitive_password_123" not in sanitized
    assert "postgresql://test_user:******@aws-cluster.supabase.com:5432/postgres" in sanitized
    print("  [PASS] 2. Standard PostgreSQL connection URI redacted.")


def test_redact_uri_encoded_credentials():
    """Verify URI-encoded usernames and passwords are appropriately sanitized."""
    raw_error = "Connection failed: postgresql://user%3Aname:p%40ss%25word%21@db.example.org:5432/prod_db"
    sanitized = sanitize_error_message(raw_error)
    assert "p%40ss%25word%21" not in sanitized
    assert "postgresql://user%3Aname:******@db.example.org:5432/prod_db" in sanitized
    print("  [PASS] 3. URI-encoded credentials redacted.")


def test_redact_password_with_punctuation_and_special_chars():
    """Verify passwords containing punctuation and symbols are completely redacted."""
    raw_error = "Failed to connect to postgresql://admin:p$ss%20w+rd-_.!~*();=^&#1@localhost:5432/weather"
    sanitized = sanitize_error_message(raw_error)
    assert "p$ss" not in sanitized
    assert "#1" not in sanitized
    assert "postgresql://admin:******@localhost:5432/weather" in sanitized
    print("  [PASS] 4. Passwords with punctuation and special characters redacted.")


def test_redact_configured_password_in_plain_error():
    """Verify connection errors containing the configured database password are redacted."""
    synthetic_pass = "synthetic_super_secret_db_pass_999"
    raw_error = f"FATAL: password authentication failed for user postgres with password {synthetic_pass}"

    with mock.patch("database.get_db_config", return_value={"password": synthetic_pass}):
        sanitized = sanitize_error_message(raw_error)
        assert synthetic_pass not in sanitized
        assert "******" in sanitized
        assert "password authentication failed for user postgres" in sanitized

    print("  [PASS] 5. Configured database password in plain connection errors redacted.")


def test_redact_unexpected_credential_like_uri():
    """Verify unexpected/custom database schemes with credentials are also sanitized."""
    schemes = [
        "redis://admin:super_secret_redis_pass@cache.internal:6379",
        "mongodb://mongouser:mongo_pass_987@mongo.internal:27017/analytics",
        "custom-db://operator:custom_db_token#123@cluster.internal:9999/events",
    ]
    for raw in schemes:
        sanitized = sanitize_error_message(raw)
        assert "super_secret_redis_pass" not in sanitized
        assert "mongo_pass_987" not in sanitized
        assert "custom_db_token#123" not in sanitized
        assert ":******@" in sanitized

    print("  [PASS] 6. Unexpected credential-like URIs across diverse schemes redacted.")


def test_redact_dsn_style_credentials():
    """Verify DSN key-value style credentials (password=... or pwd=...) are redacted."""
    raw_error = "psycopg.OperationalError: host=localhost port=5432 user=postgres password=my_plain_pass dbname=test"
    sanitized = sanitize_error_message(raw_error)
    assert "my_plain_pass" not in sanitized
    assert "password=******" in sanitized
    assert "user=postgres" in sanitized
    assert "host=localhost" in sanitized
    print("  [PASS] 7. DSN key-value credentials redacted.")


def test_preserve_messages_without_credentials():
    """Verify non-credential error messages remain intact and useful for debugging."""
    useful_errors = [
        'FATAL: password authentication failed for user "postgres"',
        'Connection to server at "127.0.0.1", port 5432 failed: Connection refused',
        'psycopg.errors.UndefinedTable: relation "public.nonexistent" does not exist',
        'Operation timed out after 10000ms waiting for connection pooler',
    ]
    for msg in useful_errors:
        sanitized = sanitize_error_message(msg)
        assert sanitized == msg, f"Non-credential error was unnecessarily altered!\nGot:  {sanitized}\nWant: {msg}"

    print("  [PASS] 8. Informative non-credential error messages preserved intact for debugging.")


def test_empty_and_none_handling():
    """Verify sanitize_error_message safely handles empty string or None without exceptions."""
    assert sanitize_error_message("") == ""
    assert sanitize_error_message(None) == ""
    print("  [PASS] 9. Empty and None inputs handled safely.")


def run_all_database_security_tests():
    print("======================================================================")
    print("TEST 11: Database Security & Configuration Precedence Tests")
    print("======================================================================")
    tests = [
        test_env_precedence_over_dotenv,
        test_redact_standard_postgres_uri,
        test_redact_uri_encoded_credentials,
        test_redact_password_with_punctuation_and_special_chars,
        test_redact_configured_password_in_plain_error,
        test_redact_unexpected_credential_like_uri,
        test_redact_dsn_style_credentials,
        test_preserve_messages_without_credentials,
        test_empty_and_none_handling,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {t.__name__}: {exc}")
            failed += 1

    print("======================================================================")
    print(f"DATABASE SECURITY TESTS SUMMARY: Passed {passed} / {len(tests)} (Failed: {failed})")
    print("======================================================================")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_database_security_tests()
