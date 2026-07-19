param()

$plan = [ordered]@{
    mode = "plan-only"
    execution_allowed = $false
    generated_on = "2026-07-17"
    service = "postgresql-x64-18"
    proposed_database = "puiying_steven_demo"
    proposed_role = "puiying_steven_demo_app"
    boundaries = @(
        "This script does not start or stop PostgreSQL services.",
        "This script does not create roles or databases.",
        "This script does not connect to PostgreSQL.",
        "Credentials must be supplied later through approved secret storage."
    )
    approved_stage_sequence = @(
        "Verify the native PostgreSQL 18 service and approved maintenance window.",
        "Create a dedicated least-privilege login role and puiying_steven_demo database.",
        "Set APP_ENV=development, AUTH_MODE=session, DEMO_PROFILE_ENABLED=true, and environment-specific storage root.",
        "Run alembic upgrade head and verify alembic current is 20260717_0007.",
        "Run the controlled first-admin bootstrap without echoing the password.",
        "Load only the fully sanitized Steven D0 fixtures.",
        "Verify login, Cookie, CSRF, RBAC, platform audit, request_id linkage, and role-change session revocation.",
        "Confirm 3 suppliers x 5 items, candidate review confirmation, restart recovery, unique constraints, and audit persistence.",
        "Run concurrent import confirmation and 10-way versioned export smoke; verify unique versions, SHA-256, append-only files, and recovery scan.",
        "Record rollback point, backup evidence, logs with secrets removed, and final go/no-go decision."
    )
}

$plan | ConvertTo-Json -Depth 5
