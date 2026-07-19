from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import create_engine, text


def emit(step: str, status: str, **details: object) -> None:
    print(json.dumps({"step": step, "status": status, **details}, ensure_ascii=False))


def inspect_candidate(root: Path, row: dict[str, object]) -> dict[str, object]:
    storage_key = str(row["storage_key"])
    path = (root / storage_key).resolve()
    if root != path and root not in path.parents:
        return {**row, "candidate": "manual_review", "reason": "storage_key_escaped_root"}
    if not path.is_file():
        return {**row, "candidate": "failed_candidate", "reason": "published_file_missing"}
    try:
        load_workbook(path, read_only=True).close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {**row, "candidate": "ready_candidate", "sha256": digest, "size_bytes": path.stat().st_size}
    except Exception as error:
        return {**row, "candidate": "failed_candidate", "reason": f"invalid_xlsx:{type(error).__name__}"}


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    root_value = os.getenv("FILE_STORAGE_ROOT", "").strip()
    if not database_url or not root_value:
        emit("configuration", "failed", reason="DATABASE_URL and FILE_STORAGE_ROOT are required")
        return 2
    root = Path(root_value).resolve()
    threshold_minutes = int(os.getenv("P0B1_RESERVED_ALERT_MINUTES", "30"))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
    try:
        engine = create_engine(database_url, future=True)
        with engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(text("""
                SELECT id,quote_job_id,version_number,filename,storage_key,created_at
                  FROM steven_quote_versions
                 WHERE status='reserved' AND created_at <= :cutoff
                 ORDER BY created_at,id
            """), {"cutoff": cutoff}).mappings()]
        candidates = [inspect_candidate(root, row) for row in rows]
        emit("reserved_export_scan", "passed", threshold_minutes=threshold_minutes, count=len(candidates), candidates=candidates)
    except Exception as error:
        emit("reserved_export_scan", "failed", error=type(error).__name__, message=str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
