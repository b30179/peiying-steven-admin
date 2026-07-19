param(
    [int]$PostgresPort = 55432,
    [int]$ApiPort = 9000,
    [int]$WebPort = 4300,
    [int]$HttpsPort = 15443
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
. (Join-Path $PSScriptRoot 'Portable-Path.ps1')

$physicalRoot = Get-StevenPortablePhysicalRoot $PSScriptRoot
$operationLock = Enter-StevenPortableOperationLock $physicalRoot
$pathContext = $null
$keepPathMapping = $false

try {
    $pathContext = Get-StevenPortablePathContext $PSScriptRoot
    $packageRoot = $pathContext.RuntimeRoot
    $python = Join-Path $packageRoot 'runtime\python\python.exe'
    $psql = Join-Path $packageRoot 'runtime\postgresql\bin\psql.exe'
    $secretPath = Join-Path $packageRoot 'data\secrets\postgres-password.dpapi'
    $statePath = Join-Path $packageRoot 'data\runtime\portable-processes.json'

    & (Join-Path $PSScriptRoot 'Start-StevenPortable.ps1') -NoBrowser -PostgresPort $PostgresPort -ApiPort $ApiPort -WebPort $WebPort -HttpsPort $HttpsPort -SkipOperationLock
    if (-not (Test-Path -LiteralPath $statePath)) { throw 'Portable process state is missing after startup.' }
    $keepPathMapping = $true
    $state = Get-Content -LiteralPath $statePath -Encoding UTF8 -Raw | ConvertFrom-Json
    $PostgresPort = [int]$state.postgres_port
    $ApiPort = [int]$state.api_port
    $WebPort = [int]$state.web_port
    $HttpsPort = [int]$state.https_port

    $protected = [System.IO.File]::ReadAllBytes($secretPath)
    $plain = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $protected,
        $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    $databasePassword = [System.Text.Encoding]::UTF8.GetString($plain)
    $env:PGPASSWORD = $databasePassword
    try {
        $healthResponse = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 10
        $health = if ($healthResponse.data) { $healthResponse.data } else { $healthResponse }
        if ($health.auth_mode -ne 'session' -or
            $health.persistence.mode -ne 'postgresql' -or
            $health.ocr_provider -ne 'paddle' -or
            $health.ai_provider -notin @('mock','deepseek')) {
            throw 'Health boundary verification failed.'
        }
        $accounts = & $psql -X -A -t -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo -c "SELECT string_agg(username, ',' ORDER BY username), count(*) FROM users;"
        if ($LASTEXITCODE -ne 0 -or $accounts.Trim() -ne 'Steven,approve|2') { throw 'Application account verification failed.' }
        $migration = & $psql -X -A -t -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo -c 'SELECT version_num FROM alembic_version;'
        if ($LASTEXITCODE -ne 0 -or $migration.Trim() -ne '20260718_0016') {
            throw "Alembic head verification failed: $($migration.Trim())"
        }
        $certificate = [string]$state.certificate
        if (-not (Test-Path -LiteralPath $certificate)) { throw 'Portable HTTPS certificate is missing.' }
        $probe = "import ssl,urllib.request; c=ssl.create_default_context(cafile=r'''$certificate'''); urls=['https://localhost:$HttpsPort/login','https://localhost:$HttpsPort/dashboard/steven/tenders','https://localhost:$HttpsPort/dashboard/steven/quotes','https://localhost:$HttpsPort/dashboard/steven/inventory']; print([urllib.request.urlopen(u,context=c,timeout=10).status for u in urls])"
        $codes = & $python -c $probe
        if ($LASTEXITCODE -ne 0) { throw 'HTTPS verification failed.' }
        & $python -c "import fastapi,psycopg,paddle,paddleocr,docx,openpyxl; print('Portable Python imports: OK')"
        if ($LASTEXITCODE -ne 0) { throw 'Portable Python dependency verification failed.' }
        Write-Host 'Health: session + PostgreSQL + PaddleOCR'
        Write-Host "AI provider: $($health.ai_provider)"
        Write-Host 'Accounts: Steven and approve only'
        Write-Host 'Alembic: 20260718_0016'
        Write-Host "HTTPS pages: $codes"
        Write-Host 'Portable verification passed.'
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        $databasePassword = $null
    }
} finally {
    if (-not $keepPathMapping -and $pathContext -and $pathContext.MappingCreated) {
        Remove-StevenPortablePathMapping $pathContext
    }
    Exit-StevenPortableOperationLock $operationLock
}
