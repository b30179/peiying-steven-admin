from __future__ import annotations

import json
import os
import sys

from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.db.session import create_postgres_engine
from app.modules.accounts.repository import PostgresAuthRepository


def bootstrap_admin() -> int:
    settings = Settings.from_env()
    settings.validate()
    if settings.auth_mode != "session":
        print(json.dumps({"status": "rejected", "code": "session_auth_required"}), file=sys.stderr)
        return 2
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    display_name = os.getenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not display_name or len(password) < 12:
        print(json.dumps({"status": "rejected", "code": "bootstrap_environment_invalid"}), file=sys.stderr)
        return 2
    repository = PostgresAuthRepository(create_postgres_engine(settings))
    try:
        account = repository.bootstrap_admin(username, display_name, password)
    except ValueError as error:
        print(json.dumps({"status": "rejected", "code": str(error)}), file=sys.stderr)
        return 3
    except Exception:
        print(json.dumps({"status": "failed", "code": "bootstrap_failed"}), file=sys.stderr)
        return 4
    print(json.dumps({"status": "created", "user_id": account["id"], "username": account["username"], "roles": account["roles"]}, ensure_ascii=False))
    return 0


def reset_demo_passwords() -> int:
    settings = Settings.from_env()
    settings.validate()
    database_name = make_url(settings.database_url).database if settings.database_url else None
    confirmation = os.getenv("DEMO_PASSWORD_RESET_CONFIRM", "")
    usernames = [
        username.strip()
        for username in os.getenv("DEMO_PASSWORD_RESET_USERNAMES", "").split(",")
        if username.strip()
    ]
    password = os.getenv("DEMO_PASSWORD_RESET_PASSWORD", "")
    if (
        settings.app_env != "development"
        or settings.auth_mode != "session"
        or database_name != "puiying_steven_demo"
        or confirmation != "RESET_LOCAL_DEMO_ONLY"
        or not usernames
        or len(password) < 6
    ):
        print(json.dumps({"status": "rejected", "code": "demo_password_reset_environment_invalid"}), file=sys.stderr)
        return 2
    repository = PostgresAuthRepository(create_postgres_engine(settings))
    try:
        accounts = repository.reset_demo_passwords(usernames, password)
    except ValueError as error:
        print(json.dumps({"status": "rejected", "code": str(error)}), file=sys.stderr)
        return 3
    except Exception:
        print(json.dumps({"status": "failed", "code": "demo_password_reset_failed"}), file=sys.stderr)
        return 4
    print(
        json.dumps(
            {
                "status": "reset",
                "accounts": [
                    {"username": account["username"], "sessions_revoked": account["sessions_revoked"]}
                    for account in accounts
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def sync_demo_accounts() -> int:
    settings = Settings.from_env()
    settings.validate()
    database_url = make_url(settings.database_url) if settings.database_url else None
    confirmation = os.getenv("DEMO_ACCOUNT_SYNC_CONFIRM", "")
    password = os.getenv("DEMO_ACCOUNT_SYNC_PASSWORD", "")
    if (
        settings.app_env != "development"
        or settings.auth_mode != "session"
        or database_url is None
        or database_url.database != "puiying_steven_demo"
        or database_url.username != "puiying_steven_demo_app"
        or confirmation != "SYNC_LOCAL_REDACTED_DEMO_ONLY"
        or len(password) < 6
    ):
        print(json.dumps({"status": "rejected", "code": "demo_account_sync_environment_invalid"}), file=sys.stderr)
        return 2
    repository = PostgresAuthRepository(create_postgres_engine(settings))
    try:
        result = repository.sync_demo_accounts(password)
    except ValueError as error:
        print(json.dumps({"status": "rejected", "code": str(error)}), file=sys.stderr)
        return 3
    except Exception:
        print(json.dumps({"status": "failed", "code": "demo_account_sync_failed"}), file=sys.stderr)
        return 4
    print(
        json.dumps(
            {
                "status": "synchronized",
                "previous_user_count": result["previous_user_count"],
                "current_user_count": result["current_user_count"],
                "users_removed": result.get("users_removed", 0),
                "sessions_revoked": result["sessions_revoked"],
                "accounts": [
                    {
                        "username": account["username"],
                        "display_name": account["display_name"],
                        "roles": account["roles"],
                    }
                    for account in result["accounts"]
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    if sys.argv[1:] == ["bootstrap-admin"]:
        return bootstrap_admin()
    if sys.argv[1:] == ["reset-demo-passwords"]:
        return reset_demo_passwords()
    if sys.argv[1:] == ["sync-demo-accounts"]:
        return sync_demo_accounts()
    print("Usage: python -m app.cli bootstrap-admin|reset-demo-passwords|sync-demo-accounts", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
