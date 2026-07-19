param(
    [int]$PostgresPort = 55432,
    [int]$ApiPort = 9000,
    [int]$WebPort = 4300,
    [int]$HttpsPort = 15443
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Portable-Path.ps1')
. (Join-Path $PSScriptRoot 'Portable-Process.ps1')

$physicalRoot = Get-StevenPortablePhysicalRoot $PSScriptRoot
$operationLock = Enter-StevenPortableOperationLock $physicalRoot
$pathContext = $null

try {
    $pathContext = Get-StevenPortablePathContext $PSScriptRoot
    $packageRoot = $pathContext.RuntimeRoot
    $runtimeRoot = Join-Path $packageRoot 'runtime'
    $physicalRuntimeRoot = Join-Path $pathContext.PhysicalRoot 'runtime'
    $statePath = Join-Path $packageRoot 'data\runtime\portable-processes.json'
    $databaseData = Join-Path $packageRoot 'data\postgresql'
    $pgCtl = Join-Path $runtimeRoot 'postgresql\bin\pg_ctl.exe'
    $apiExecutablePaths = @(
        (Join-Path $runtimeRoot 'python\python.exe'),
        (Join-Path $physicalRuntimeRoot 'python\python.exe')
    ) | Select-Object -Unique
    $webExecutablePaths = @(
        (Join-Path $runtimeRoot 'node\node.exe'),
        (Join-Path $physicalRuntimeRoot 'node\node.exe')
    ) | Select-Object -Unique
    $caddyExecutablePaths = @(
        (Join-Path $runtimeRoot 'caddy\caddy.exe'),
        (Join-Path $physicalRuntimeRoot 'caddy\caddy.exe')
    ) | Select-Object -Unique

    $state = Read-StevenPortableProcessState $statePath
    if ($state) {
        if ($state.postgres_port) { $PostgresPort = [int]$state.postgres_port }
        if ($state.api_port) { $ApiPort = [int]$state.api_port }
        if ($state.web_port) { $WebPort = [int]$state.web_port }
        if ($state.https_port) { $HttpsPort = [int]$state.https_port }
    }

    $groups = @(
        @{ Name = 'Caddy'; Paths = $caddyExecutablePaths; Fragments = @('run','Caddyfile') },
        @{ Name = 'Next.js'; Paths = $webExecutablePaths; Fragments = @('server.js') },
        @{ Name = 'FastAPI'; Paths = $apiExecutablePaths; Fragments = @('uvicorn','app.main:app') }
    )
    foreach ($group in $groups) {
        foreach ($identity in (Find-StevenPortableProcesses $group.Paths $group.Fragments)) {
            Write-Host "Stopping verified $($group.Name) process $($identity.ProcessId)..."
            Stop-Process -Id $identity.ProcessId -Force -ErrorAction Stop
            try { Wait-Process -Id $identity.ProcessId -Timeout 10 -ErrorAction SilentlyContinue } catch {}
        }
    }

    $remainingProcesses = @()
    foreach ($group in $groups) {
        $remainingProcesses += @(Find-StevenPortableProcesses $group.Paths $group.Fragments)
    }
    if ($remainingProcesses.Count -gt 0) {
        throw 'One or more verified portable application processes could not be stopped. The state file and path mapping were kept.'
    }

    if (Test-Path -LiteralPath (Join-Path $databaseData 'PG_VERSION')) {
        & $pgCtl -D $databaseData status *> $null
        if ($LASTEXITCODE -eq 0) {
            & $pgCtl -D $databaseData stop -m fast *> $null
            if ($LASTEXITCODE -ne 0) {
                throw 'Portable PostgreSQL failed to stop. The state file and path mapping were kept.'
            }
        }
    }

    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    Remove-StevenPortablePathMapping $pathContext
    $pathContext = $null
    Write-Host 'Steven portable Demo is stopped. Repeated stop is safe.'
} finally {
    Exit-StevenPortableOperationLock $operationLock
}
