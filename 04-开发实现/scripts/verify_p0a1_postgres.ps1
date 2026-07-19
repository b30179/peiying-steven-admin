param(
    [string]$Python = "$PSScriptRoot\..\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$required = @(
    "P0A1_ADMIN_DATABASE_URL",
    "DATABASE_URL",
    "BOOTSTRAP_ADMIN_USERNAME",
    "BOOTSTRAP_ADMIN_DISPLAY_NAME",
    "BOOTSTRAP_ADMIN_PASSWORD"
)
$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_)) })
if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python runtime not found: $Python"
}

& $Python "$PSScriptRoot\verify_p0a1_postgres.py"
if ($LASTEXITCODE -ne 0) {
    throw "P0-A.1 PostgreSQL verification failed with exit code $LASTEXITCODE"
}
