from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
CONSTRAINTS = (
    "fk_steven_quote_approvals_submitted_by",
    "fk_steven_quote_approvals_decided_by",
)


def emit(step: str, status: str, **details: object) -> None:
    print(json.dumps({"step": step, "status": status, **details}, ensure_ascii=False))


def orphan_report(connection) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(text("""
        SELECT actor_field, actor_id, count(*) AS approval_count
          FROM (
                SELECT 'submitted_by' AS actor_field, submitted_by AS actor_id
                  FROM steven_quote_approvals approvals
                 WHERE submitted_by IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM users WHERE users.id=approvals.submitted_by)
                UNION ALL
                SELECT 'decided_by', decided_by
                  FROM steven_quote_approvals approvals
                 WHERE decided_by IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM users WHERE users.id=approvals.decided_by)
          ) orphaned
         GROUP BY actor_field, actor_id
         ORDER BY actor_field, actor_id
    """)).mappings()]


def constraint_report(connection) -> list[dict[str, object]]:
    return [dict(row) for row in connection.execute(text("""
        SELECT conname, convalidated
          FROM pg_constraint
         WHERE conname = ANY(:constraints)
         ORDER BY conname
    """), {"constraints": list(CONSTRAINTS)}).mappings()]


def apply_mapping(connection, mapping: dict[str, str]) -> int:
    changed = 0
    for source, target in mapping.items():
        if not connection.execute(text("SELECT 1 FROM users WHERE id=:target"), {"target": target}).first():
            raise RuntimeError(f"Approved target user does not exist: {target}")
        for field in ("submitted_by", "decided_by"):
            result = connection.execute(
                text(f"UPDATE steven_quote_approvals SET {field}=:target WHERE {field}=:source"),
                {"source": source, "target": target},
            )
            changed += result.rowcount or 0
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Report and explicitly govern orphan S2 approval actors.")
    parser.add_argument("--mapping-file", type=Path)
    parser.add_argument("--apply-approved-mapping", action="store_true")
    parser.add_argument("--validate", action="store_true")
    arguments = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        emit("configuration", "failed", reason="DATABASE_URL is required")
        return 2
    mutating = arguments.apply_approved_mapping or arguments.validate
    if mutating and os.getenv("P0B1_ACTOR_GOVERNANCE_APPROVED") != "true":
        emit("configuration", "failed", reason="P0B1_ACTOR_GOVERNANCE_APPROVED=true is required for changes")
        return 2
    if arguments.apply_approved_mapping and not arguments.mapping_file:
        emit("configuration", "failed", reason="--mapping-file is required for approved mapping")
        return 2

    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as connection:
            before = orphan_report(connection)
            constraints = constraint_report(connection)
            emit("actor_governance_report", "passed", orphans=before, constraints=constraints)
            if arguments.apply_approved_mapping:
                mapping = json.loads(arguments.mapping_file.read_text(encoding="utf-8"))
                if not isinstance(mapping, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()):
                    raise RuntimeError("Mapping file must be a JSON object of source_actor_id to approved_user_id")
                changed = apply_mapping(connection, mapping)
                emit("approved_mapping", "passed", changed_rows=changed)
            remaining = orphan_report(connection)
            if arguments.validate:
                if remaining:
                    raise RuntimeError("Orphan actors remain; constraints were not validated")
                for constraint in CONSTRAINTS:
                    connection.execute(text(f"ALTER TABLE steven_quote_approvals VALIDATE CONSTRAINT {constraint}"))
                emit("validate_constraints", "passed", constraints=list(CONSTRAINTS))
            elif mutating:
                emit("validation", "skipped", reason="Use --validate only after reviewing the post-mapping report", remaining_orphans=remaining)
    except Exception as error:
        emit("actor_governance", "failed", error=type(error).__name__, message=str(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(API_ROOT))
    raise SystemExit(main())
