from __future__ import annotations

import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"

sys.path.insert(0, str(API_ROOT))


def main() -> int:
    if os.environ.get("APP_ENV", "development").strip().lower() == "production":
        print("Refusing to seed S1 Demo data in production.", file=sys.stderr)
        return 2
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is required.", file=sys.stderr)
        return 2
    parsed = make_url(database_url)
    if parsed.database != "puiying_steven_demo":
        print("Refusing to seed a database other than puiying_steven_demo.", file=sys.stderr)
        return 2

    from app.modules.steven.postgres_tender_repository import PostgresTenderRepository

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        actor = connection.execute(
            text("""
                SELECT u.id
                  FROM users u
                  JOIN user_roles ur ON ur.user_id=u.id
                  JOIN roles r ON r.id=ur.role_id
                 WHERE r.code='operator'
                   AND r.status='active'
                   AND u.status='active'
                 ORDER BY u.created_at,u.id
                 LIMIT 1
            """)
        ).scalar_one_or_none()
        if actor is None:
            print("No active Steven user is available for controlled Demo template ownership.", file=sys.stderr)
            return 3
        templates = PostgresTenderRepository(connection).ensure_demo_templates(actor)
    print(f"S1 Demo templates ready: {len(templates)}")
    for template in templates:
        print(f"- {template.code} v{template.version} ({template.document_type})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
