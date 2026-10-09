"""
Database connection module for PostgreSQL via Supabase Session Pooler.
Reads connection parameters securely from environment variables.
"""

import os
from pathlib import Path
import re
from typing import Dict, Any
from dotenv import load_dotenv
import psycopg

# Path to backend/.env
env_file_path = Path(__file__).resolve().parent / ".env"


def get_db_config() -> Dict[str, Any]:
    """
    Load environment variables from backend/.env and return database configuration.
    Uses override=False so process-level environment variables take precedence.
    """
    load_dotenv(dotenv_path=env_file_path, override=False)
    return {
        "host": os.getenv("DATABASE_HOST", "aws-0-ap-south-1.pooler.supabase.com"),
        "port": int(os.getenv("DATABASE_PORT", "5432")),
        "dbname": os.getenv("DATABASE_NAME", "postgres"),
        "user": os.getenv("DATABASE_USER", "postgres"),
        "password": os.getenv("DATABASE_PASSWORD", ""),
        "sslmode": os.getenv("DATABASE_SSLMODE", "require"),
    }


def get_db_connection() -> psycopg.Connection:
    """
    Establish and return a reusable connection to PostgreSQL.
    
    Raises:
        ValueError: If DATABASE_PASSWORD is not set.
        psycopg.Error: If the connection fails.
    """
    config = get_db_config()
    if not config["password"]:
        raise ValueError(
            "DATABASE_PASSWORD is not set. Please add your database password to backend/.env"
        )

    return psycopg.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["dbname"],
        user=config["user"],
        password=config["password"],
        sslmode=config["sslmode"],
        connect_timeout=10,
    )


def sanitize_error_message(message: str) -> str:
    """
    Sanitize error message to ensure database passwords, credentials embedded in URIs,
    and sensitive credentials/API keys are never leaked in exception messages or API responses.
    """
    if not message:
        return ""

    # 1. Redact credentials embedded in connection URIs (e.g. postgresql://user:password@host:port/db)
    # Handles user:password, :password, URI-encoded or punctuation-rich passwords before @
    uri_pattern = re.compile(
        r'(\b[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^:\s/@]*:)?)([^@\s/]+)(@(?=[a-zA-Z0-9_.-]+(?::\d+)?(?:[/?:#\s]|$)))'
    )
    message = uri_pattern.sub(r'\g<1>******\3', message)

    # 2. Redact key-value DSN style credentials (e.g. password=... or pwd=...)
    dsn_pattern = re.compile(r'(?i)\b(password|pwd)\s*=\s*(?:\'[^\']*\'|"[^"]*"|\S+)')
    message = dsn_pattern.sub(r'\1=******', message)

    # 3. Redact explicit configured secrets
    try:
        config = get_db_config()
        password = config.get("password")
        if password and len(str(password)) >= 3 and str(password) in message:
            message = message.replace(str(password), "******")
        data_gov_key = os.getenv("DATA_GOV_API_KEY")
        if data_gov_key and len(str(data_gov_key)) >= 3 and str(data_gov_key) in message:
            message = message.replace(str(data_gov_key), "******")
        admin_key = os.getenv("ADMIN_API_KEY")
        if admin_key and len(str(admin_key)) >= 3 and str(admin_key) in message:
            message = message.replace(str(admin_key), "******")
    except Exception:
        pass

    return message


def check_database_connection() -> bool:
    """
    Test the PostgreSQL connection by executing a lightweight 'SELECT 1' query.
    
    Returns:
        bool: True if connection and query succeed.
        
    Raises:
        ValueError: If credentials are missing.
        RuntimeError: If connection or query execution fails (without leaking secrets).
    """
    config = get_db_config()
    password = config["password"]

    if not password:
        raise ValueError(
            "DATABASE_PASSWORD is not configured. Please fill in DATABASE_PASSWORD in backend/.env"
        )

    try:
        with psycopg.connect(
            host=config["host"],
            port=config["port"],
            dbname=config["dbname"],
            user=config["user"],
            password=password,
            sslmode=config["sslmode"],
            connect_timeout=10,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                result = cur.fetchone()
                return bool(result and result[0] == 1)

    except psycopg.Error as exc:
        sanitized_error = sanitize_error_message(str(exc))
        raise RuntimeError(f"Database connection failed: {sanitized_error}") from None
    except Exception as exc:
        sanitized_error = sanitize_error_message(str(exc))
        raise RuntimeError(f"Database error: {sanitized_error}") from None

