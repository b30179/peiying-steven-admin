from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

HBA_PATH = Path(r"D:\ZM\PostgreSQL\18\data\pg_hba.conf")
ROLE = "puiying_steven_demo_app"
DATABASE = "puiying_steven_demo"
MARKER_BEGIN = "# BEGIN Steven Demo D1 role-only localhost isolation (2026-07-17)"
MARKER_END = "# END Steven Demo D1 role-only localhost isolation"
ANCHOR = "# IPv4 local connections:\n"
RULES = (
    f"{MARKER_BEGIN}\n"
    f"# Allow only the approved Demo database for this fixed Demo role.\n"
    f"host    {DATABASE}    {ROLE}    127.0.0.1/32    scram-sha-256\n"
    f"host    {DATABASE}    {ROLE}    ::1/128         scram-sha-256\n"
    f"# Explicitly reject every other database for this role from localhost.\n"
    f"host    all           {ROLE}    127.0.0.1/32    reject\n"
    f"host    all           {ROLE}    ::1/128         reject\n"
    f"{MARKER_END}\n\n"
)


def unique_backup_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = HBA_PATH.with_name(f"pg_hba.conf.d1-p0-1-backup-{stamp}")
    sequence = 1
    while candidate.exists():
        candidate = HBA_PATH.with_name(f"pg_hba.conf.d1-p0-1-backup-{stamp}-{sequence}")
        sequence += 1
    return candidate


def main() -> int:
    if not HBA_PATH.is_file():
        raise RuntimeError(f"Actual hba file is unavailable: {HBA_PATH}")
    original = HBA_PATH.read_text(encoding="utf-8")
    if MARKER_BEGIN in original or MARKER_END in original:
        raise RuntimeError("D1 P0-1 marker already exists; refusing to duplicate or overwrite rules")
    if ANCHOR not in original:
        raise RuntimeError("Expected insertion anchor is missing; refusing to alter pg_hba.conf")
    backup = unique_backup_path()
    shutil.copy2(HBA_PATH, backup)
    if backup.read_bytes() != HBA_PATH.read_bytes():
        raise RuntimeError("Backup byte comparison failed; pg_hba.conf was not modified")
    updated = original.replace(ANCHOR, RULES + ANCHOR, 1)
    HBA_PATH.write_text(updated, encoding="utf-8", newline="")
    print(f"backup={backup}")
    print(f"hba={HBA_PATH}")
    print("rules_inserted=4")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error={type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
