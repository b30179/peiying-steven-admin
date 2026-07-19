param(
    [int]$PostgresPort = 55432,
    [switch]$SkipOperationLock
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
. (Join-Path $PSScriptRoot 'Portable-Path.ps1')

$physicalRoot = Get-StevenPortablePhysicalRoot $PSScriptRoot
$operationLock = if ($SkipOperationLock) { $null } else { Enter-StevenPortableOperationLock $physicalRoot }
$pathContext = $null

try {
    $pathContext = Get-StevenPortablePathContext $PSScriptRoot
    $packageRoot = $pathContext.RuntimeRoot
    $runtimeRoot = Join-Path $packageRoot 'runtime'
    $postgresBin = Join-Path $runtimeRoot 'postgresql\bin'
    $python = Join-Path $runtimeRoot 'python\python.exe'
    $dataRoot = Join-Path $packageRoot 'data'
    $databaseData = Join-Path $dataRoot 'postgresql'
    $databaseBackup = Join-Path $packageRoot 'database\steven_demo.backup'
    $secretRoot = Join-Path $dataRoot 'secrets'
    $secretPath = Join-Path $secretRoot 'postgres-password.dpapi'
    $initializedPath = Join-Path $dataRoot 'initialized.json'
    $logRoot = Join-Path $dataRoot 'logs'
    $initLog = Join-Path $logRoot 'initialize.log'
    $apiRoot = Join-Path $packageRoot 'apps\api'

    function Test-InitializationComplete {
        if (-not (Test-Path -LiteralPath (Join-Path $databaseData 'PG_VERSION'))) { return $false }
        if (-not (Test-Path -LiteralPath $secretPath)) { return $false }
        if (-not (Test-Path -LiteralPath $initializedPath)) { return $false }
        try {
            $state = Get-Content -LiteralPath $initializedPath -Encoding UTF8 -Raw | ConvertFrom-Json
            return $state.database -eq 'puiying_steven_demo' -and [int]$state.account_count -eq 2
        } catch {
            return $false
        }
    }

    function Test-DirectoryHasContent([string]$Path) {
        if (-not (Test-Path -LiteralPath $Path)) { return $false }
        return $null -ne (Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue | Select-Object -First 1)
    }

    function Remove-SafeInitializationDirectory([string]$Path, [bool]$AllowPublishedDatabase = $false) {
        if (-not (Test-Path -LiteralPath $Path)) { return }
        $resolvedDataRoot = [System.IO.Path]::GetFullPath($dataRoot).TrimEnd('\') + '\'
        $resolvedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
        $leaf = Split-Path -Leaf $resolvedPath
        $isStaging = $leaf.StartsWith('postgresql.initializing.', [System.StringComparison]::OrdinalIgnoreCase)
        $isPublishedDatabase = $AllowPublishedDatabase -and
            [string]::Equals($resolvedPath, [System.IO.Path]::GetFullPath($databaseData).TrimEnd('\'), [System.StringComparison]::OrdinalIgnoreCase)
        if (-not $resolvedPath.StartsWith($resolvedDataRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            (-not $isStaging -and -not $isPublishedDatabase)) {
            throw "Refusing to remove an unexpected initialization path: $resolvedPath"
        }
        Remove-Item -LiteralPath $resolvedPath -Recurse -Force
    }

    foreach ($required in @(
        (Join-Path $postgresBin 'initdb.exe'), (Join-Path $postgresBin 'pg_ctl.exe'),
        (Join-Path $postgresBin 'psql.exe'), (Join-Path $postgresBin 'createdb.exe'),
        (Join-Path $postgresBin 'pg_restore.exe'), (Join-Path $postgresBin 'pg_isready.exe'),
        $python, $databaseBackup, (Join-Path $apiRoot 'alembic.ini')
    )) {
        if (-not (Test-Path -LiteralPath $required)) { throw "Portable component is missing: $required" }
    }

    if (Test-InitializationComplete) {
        Write-Host 'Steven portable database is already initialized and its completion marker is valid.'
        return
    }

    if ((Test-DirectoryHasContent $databaseData) -or (Test-Path -LiteralPath $secretPath) -or (Test-Path -LiteralPath $initializedPath)) {
        throw 'Incomplete portable initialization was detected. No existing data was deleted. Keep the package stopped and inspect data\logs\initialize.log before retrying with a clean package copy.'
    }
    if (Get-NetTCPConnection -State Listen -LocalPort $PostgresPort -ErrorAction SilentlyContinue) {
        throw "Port $PostgresPort is already in use. Choose another PostgreSQL port."
    }

    New-Item -ItemType Directory -Path $dataRoot, $secretRoot, $logRoot -Force | Out-Null
    Write-StevenPortableTextAtomic $initLog ("Steven portable initialization started at $([datetimeoffset]::Now.ToString('o')).`r`n")

    $runToken = "$PID.$([guid]::NewGuid().ToString('N'))"
    $stagingDatabaseData = Join-Path $dataRoot "postgresql.initializing.$runToken"
    $stagingSecretPath = Join-Path $secretRoot "postgres-password.initializing.$runToken.dpapi"
    $passwordFile = Join-Path $secretRoot "init-password.$runToken.tmp"
    $roleSqlPath = Join-Path $secretRoot "create-role.$runToken.tmp.sql"
    $passwordBytes = New-Object byte[] 32
    $randomNumberGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $randomNumberGenerator.GetBytes($passwordBytes)
    } finally {
        $randomNumberGenerator.Dispose()
    }
    $databasePassword = ([System.BitConverter]::ToString($passwordBytes)).Replace('-', '').ToLowerInvariant()
    $protectedBytes = [System.Security.Cryptography.ProtectedData]::Protect(
        [System.Text.Encoding]::UTF8.GetBytes($databasePassword),
        $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    [System.IO.File]::WriteAllBytes($stagingSecretPath, $protectedBytes)
    [System.IO.File]::WriteAllText($passwordFile, ($databasePassword + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))

    $postgresStarted = $false
    $databasePublished = $false
    $secretPublished = $false
    $initializationSucceeded = $false
    try {
        & (Join-Path $postgresBin 'initdb.exe') -D $stagingDatabaseData --username=postgres --encoding=UTF8 --locale=C --auth-host=scram-sha-256 --auth-local=scram-sha-256 --pwfile=$passwordFile *>> $initLog
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initdb failed. See data\logs\initialize.log.' }
        $configuration = "`r`n# Steven portable Demo: loopback-only settings`r`nlisten_addresses = '127.0.0.1'`r`nport = $PostgresPort`r`npassword_encryption = 'scram-sha-256'`r`n"
        [System.IO.File]::AppendAllText((Join-Path $stagingDatabaseData 'postgresql.conf'), $configuration, [System.Text.UTF8Encoding]::new($false))
        & (Join-Path $postgresBin 'pg_ctl.exe') -s -D $stagingDatabaseData -l (Join-Path $logRoot 'postgresql.log') start
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to start during initialization.' }
        $postgresStarted = $true
        $env:PGPASSWORD = $databasePassword
        $deadline = (Get-Date).AddSeconds(30)
        do {
            & (Join-Path $postgresBin 'pg_isready.exe') -h 127.0.0.1 -p $PostgresPort -U postgres -d postgres *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL did not become ready during initialization.' }

        [System.IO.File]::WriteAllText($roleSqlPath, "CREATE ROLE puiying_steven_demo_app LOGIN PASSWORD '$databasePassword';", [System.Text.UTF8Encoding]::new($false))
        & (Join-Path $postgresBin 'psql.exe') -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $PostgresPort -U postgres -d postgres -f $roleSqlPath *>> $initLog
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the portable application database role.' }
        & (Join-Path $postgresBin 'createdb.exe') -h 127.0.0.1 -p $PostgresPort -U postgres -O puiying_steven_demo_app puiying_steven_demo *>> $initLog
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the portable Demo database.' }
        & (Join-Path $postgresBin 'pg_restore.exe') -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo --no-owner --no-acl $databaseBackup *>> $initLog
        if ($LASTEXITCODE -ne 0) { throw 'Failed to restore the packaged Demo database.' }

        $env:APP_ENV = 'development'
        $env:AUTH_MODE = 'session'
        $env:DEMO_SEED_ENABLED = 'false'
        $env:DATABASE_URL = "postgresql+psycopg://puiying_steven_demo_app:$databasePassword@127.0.0.1:$PostgresPort/puiying_steven_demo"
        Push-Location $apiRoot
        try {
            & $python -m alembic -c alembic.ini upgrade head *>> $initLog
            if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade failed during initialization.' }
        } finally {
            Pop-Location
        }
        & (Join-Path $postgresBin 'psql.exe') -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo -c 'DELETE FROM auth_sessions;' *>> $initLog
        if ($LASTEXITCODE -ne 0) { throw 'Failed to clear packaged browser sessions.' }
        $accountCheck = & (Join-Path $postgresBin 'psql.exe') -X -A -t -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo -c "SELECT string_agg(username, ',' ORDER BY username), count(*) FROM users;"
        if ($LASTEXITCODE -ne 0 -or $accountCheck.Trim() -ne 'Steven,approve|2') { throw 'Packaged accounts failed verification.' }
        $migrationCheck = & (Join-Path $postgresBin 'psql.exe') -X -A -t -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo -c 'SELECT version_num FROM alembic_version;'
        if ($LASTEXITCODE -ne 0 -or $migrationCheck.Trim() -ne '20260718_0016') { throw 'Packaged Alembic head failed verification.' }

        & (Join-Path $postgresBin 'pg_ctl.exe') -D $stagingDatabaseData stop -m fast *> $null
        if ($LASTEXITCODE -ne 0) { throw 'Portable PostgreSQL failed to stop after initialization.' }
        $postgresStarted = $false

        Move-Item -LiteralPath $stagingSecretPath -Destination $secretPath
        $secretPublished = $true
        Move-Item -LiteralPath $stagingDatabaseData -Destination $databaseData
        $databasePublished = $true
        $initializedState = [ordered]@{
            initialized_at = [datetimeoffset]::Now.ToString('o')
            postgres_port = $PostgresPort
            database = 'puiying_steven_demo'
            account_count = 2
            alembic_head = '20260718_0016'
        }
        Write-StevenPortableTextAtomic $initializedPath (($initializedState | ConvertTo-Json) + [Environment]::NewLine)
        $initializationSucceeded = $true
        Write-Host 'Steven portable Demo initialized successfully.'
        Write-Host 'Database is loopback-only and uses a DPAPI-protected random local password.'
    } finally {
        if ($postgresStarted) {
            & (Join-Path $postgresBin 'pg_ctl.exe') -D $stagingDatabaseData stop -m immediate *> $null
        }
        Remove-Item -LiteralPath $passwordFile, $roleSqlPath, $stagingSecretPath -Force -ErrorAction SilentlyContinue
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
        $databasePassword = $null
        if (-not $initializationSucceeded) {
            if ($databasePublished -and -not (Test-Path -LiteralPath $initializedPath)) {
                Remove-SafeInitializationDirectory $databaseData $true
            } else {
                Remove-SafeInitializationDirectory $stagingDatabaseData
            }
            if ($secretPublished -and -not (Test-Path -LiteralPath $initializedPath)) {
                Remove-Item -LiteralPath $secretPath -Force -ErrorAction SilentlyContinue
            }
        }
    }
} finally {
    if ($pathContext -and $pathContext.MappingCreated) { Remove-StevenPortablePathMapping $pathContext }
    Exit-StevenPortableOperationLock $operationLock
}
