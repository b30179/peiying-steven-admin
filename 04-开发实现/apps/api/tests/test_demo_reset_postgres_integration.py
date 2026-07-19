from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "reset_steven_demo_data.py"


def load_module():
    spec = importlib.util.spec_from_file_location("reset_steven_demo_data_integration", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.skipif(
    os.environ.get("STEVEN_RUN_DEMO_RESET_INTEGRATION") != "1",
    reason="Requires the approved stopped local PostgreSQL Demo runtime.",
)


def test_real_postgres_reset_success_concurrency_and_precommit_rollback(monkeypatch):
    module = load_module()
    database_url = module.database_url_from_environment()
    module.validate_runtime_environment(database_url)
    file_root = module.validate_file_root()
    engine = create_engine(database_url, pool_pre_ping=True)

    with engine.connect() as connection:
        module.database_identity(connection)
        initial_plan = module.build_plan(connection, file_root)
    initial_hash = module.calculate_plan_hash(initial_plan)

    successful = module.apply_reset(engine, initial_plan, initial_hash, file_root)
    assert successful["journal_warning"] is None
    assert successful["verified"]["statuses"] == {
        "s2": "exported",
        "s1": "approved",
        "s3": "approved",
    }
    assert successful["verified"]["totals"] == {
        "SUP-C": "2583.00",
        "SUP-A": "2605.00",
        "SUP-B": "2622.00",
    }

    with engine.connect() as connection:
        stable_plan = module.build_plan(connection, file_root)
    stable_hash = module.calculate_plan_hash(stable_plan)

    lock_connection = engine.connect()
    try:
        lock_connection.execute(
            text("SELECT pg_advisory_lock(:key)"),
            {"key": module.ADVISORY_LOCK_KEY},
        )
        with pytest.raises(module.ResetBlocked, match="already running"):
            module.apply_reset(engine, stable_plan, stable_hash, file_root)
    finally:
        lock_connection.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": module.ADVISORY_LOCK_KEY},
        )
        lock_connection.close()

    original_verify = module.verify_switched_demo

    def fail_after_switch(connection, seeded, root):
        original_verify(connection, seeded, root)
        raise module.ResetBlocked("forced precommit verification failure")

    monkeypatch.setattr(module, "verify_switched_demo", fail_after_switch)
    with pytest.raises(module.ResetBlocked, match="forced precommit"):
        module.apply_reset(engine, stable_plan, stable_hash, file_root)

    with engine.connect() as connection:
        recovered_plan = module.build_plan(connection, file_root)
    assert module.calculate_plan_hash(recovered_plan) == stable_hash
    recovered = module.verify_standard_demo(engine, file_root)
    assert recovered["totals"] == successful["verified"]["totals"]
    assert recovered["ready_versions"] == {"s2": 3, "s1": 3, "s3": 3}
