param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ResetArguments
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$resetScript = Join-Path $PSScriptRoot "reset_steven_demo_data.py"
$pgpass = Join-Path $env:APPDATA "postgresql\pgpass.conf"
$fileRoot = Join-Path $projectRoot "data\steven-demo-d1"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python environment is missing: .venv"
}
if (-not (Test-Path -LiteralPath $resetScript)) {
    throw "Reset implementation is missing: scripts\reset_steven_demo_data.py"
}
if (-not (Test-Path -LiteralPath $pgpass)) {
    throw "Approved PostgreSQL pgpass file is missing."
}
if (-not (Select-String -LiteralPath $pgpass -Pattern '^127\.0\.0\.1:5432:puiying_steven_demo:puiying_steven_demo_app:' -Quiet)) {
    throw "Approved Demo database credential entry is missing from pgpass.conf."
}

function Ensure-StevenPostgresService {
    $serviceName = "postgresql-x64-18"
    $service = Get-Service -Name $serviceName -ErrorAction Stop
    if ($service.Status -eq "Running") {
        return
    }

    Write-Host "Starting the approved existing PostgreSQL service postgresql-x64-18..."
    try {
        Start-Service -Name $serviceName -ErrorAction Stop
    } catch {
        Write-Host "Windows administrator approval is required only to start the existing PostgreSQL service."
        try {
            $serviceControl = Join-Path $env:SystemRoot "System32\sc.exe"
            $elevated = Start-Process -FilePath $serviceControl `
                -ArgumentList "start", $serviceName `
                -Verb RunAs `
                -WindowStyle Hidden `
                -Wait `
                -PassThru
        } catch {
            throw "PostgreSQL service start was not approved or could not be elevated."
        }
        if ($elevated.ExitCode -ne 0) {
            throw "Elevated PostgreSQL service start failed with exit code $($elevated.ExitCode)."
        }
    }

    $service = Get-Service -Name $serviceName -ErrorAction Stop
    $service.WaitForStatus("Running", [TimeSpan]::FromSeconds(20))
    $service.Refresh()
    if ($service.Status -ne "Running") {
        throw "PostgreSQL service postgresql-x64-18 did not reach Running state."
    }
}

Ensure-StevenPostgresService

$env:APP_ENV = "development"
$env:AUTH_MODE = "session"
$env:DEMO_SEED_ENABLED = "false"
$env:OCR_ENABLED = "false"
$env:AI_STRUCTURING_ENABLED = "false"
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
$env:PGUSER = "puiying_steven_demo_app"
$env:PGDATABASE = "puiying_steven_demo"
$env:FILE_STORAGE_ROOT = $fileRoot

if (-not $ResetArguments -or $ResetArguments.Count -eq 0) {
    $ResetArguments = @("--dry-run")
}

& $python $resetScript @ResetArguments
exit $LASTEXITCODE
