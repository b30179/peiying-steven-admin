param(
    [switch]$NoBrowser,
    [int]$WebPort = 4300,
    [int]$HttpsPort = 15443,
    [switch]$EnableMockProofreading,
    [switch]$EnableDeepSeekProofreading
)

if ($EnableMockProofreading -and $EnableDeepSeekProofreading) {
    throw "Choose only one proofreading provider mode."
}

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$apiRoot = Join-Path $projectRoot "apps\api"
$webRoot = Join-Path $projectRoot "apps\web"
$nextCli = Join-Path $webRoot "node_modules\next\dist\bin\next"
$nextDevCache = Join-Path $webRoot ".next\dev"
$caddy = Join-Path $projectRoot "tools\caddy\caddy.exe"
$caddyConfig = Join-Path $projectRoot "infra\caddy\Caddyfile"
$runtimeRoot = Join-Path $projectRoot "data\runtime"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$runRoot = Join-Path $runtimeRoot "runs\$runId"
$logRoot = Join-Path $runRoot "logs"
$statePath = Join-Path $runtimeRoot "steven-demo-processes.json"
$fileRoot = Join-Path $projectRoot "data\steven-demo-d1"
$caddyStorage = Join-Path $runtimeRoot "caddy-storage"
$caddyRootCertificate = Join-Path $caddyStorage "pki\authorities\local\root.crt"
$pgpass = Join-Path $env:APPDATA "postgresql\pgpass.conf"
$publicOrigin = "https://localhost:$HttpsPort"
$requestedAiEnabled = [bool]($EnableMockProofreading -or $EnableDeepSeekProofreading)
$requestedAiProvider = if ($EnableDeepSeekProofreading) { "deepseek" } else { "mock" }

function Test-LoopbackPortAvailable([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

if (-not (Test-LoopbackPortAvailable $WebPort)) {
    if ($PSBoundParameters.ContainsKey('WebPort')) {
        throw "Requested Next.js loopback port is unavailable: $WebPort"
    }

    $preferredFallbackPorts = @(18080..18099) + @(25000..25019)
    $fallbackWebPort = @($preferredFallbackPorts | Where-Object { Test-LoopbackPortAvailable $_ } | Select-Object -First 1)
    if ($fallbackWebPort.Count -eq 0) {
        throw "No approved fallback loopback port is available for Next.js."
    }
    $WebPort = [int]$fallbackWebPort[0]
    $publicOrigin = "https://localhost:$HttpsPort"
    Write-Host "Default Next.js port 4300 is unavailable; using loopback port $WebPort."
}

if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $python)) {
    throw "Project Python environment is missing: .venv"
}
if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $nextCli)) {
    throw "Project Next.js runtime is missing: apps\web\node_modules\next"
}
$nodeCommand = Get-Command "node.exe" -ErrorAction SilentlyContinue
if (-not $nodeCommand) {
    throw "Node.js is not available for the project web runtime."
}
$node = $nodeCommand.Source
if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $caddy)) {
    throw "Project Caddy is missing: tools\caddy\caddy.exe"
}
if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $caddyConfig)) {
    throw "Project Caddyfile is missing: infra\caddy\Caddyfile"
}
if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $pgpass)) {
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
if (Microsoft.PowerShell.Management\Test-Path -LiteralPath $statePath) {
    try {
        $existingState = Get-Content -LiteralPath $statePath -Encoding utf8 | ConvertFrom-Json
    } catch {
        $existingState = $null
    }
    function Get-StatePort([string]$Url, [int]$Fallback) {
        if (-not $Url) {
            return $Fallback
        }
        try {
            return ([uri]$Url).Port
        } catch {
            return $Fallback
        }
    }
    $existingApiPort = Get-StatePort $existingState.api_url 9000
    $existingWebPort = Get-StatePort $existingState.internal_web_url $WebPort
    $existingHttpsPort = Get-StatePort $existingState.https_url $HttpsPort
    $existingPublicOrigin = if ($existingState.https_url) {
        ([string]$existingState.https_url).TrimEnd("/")
    } else {
        $publicOrigin
    }
    $expectedListeners = @(
        @{ Port = $existingApiPort; Pid = $existingState.api_listener_pid },
        @{ Port = $existingWebPort; Pid = $existingState.web_listener_pid },
        @{ Port = $existingHttpsPort; Pid = $existingState.caddy_listener_pid }
    )
    $liveListenerCount = 0
    foreach ($expected in $expectedListeners) {
        if (-not $expected.Pid) {
            continue
        }
        $listener = Get-NetTCPConnection -State Listen -LocalPort $expected.Port -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -eq $expected.Pid } |
            Select-Object -First 1
        if ($listener -and (Get-Process -Id $expected.Pid -ErrorAction SilentlyContinue)) {
            $liveListenerCount += 1
        }
    }
    $existingHealthy = $false
    if ($existingState -and $existingState.phase -eq "ready" -and $liveListenerCount -eq $expectedListeners.Count) {
        try {
            $existingHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$existingApiPort/health" -TimeoutSec 5
            $existingLogin = Invoke-WebRequest -Uri "$existingPublicOrigin/login" -UseBasicParsing -TimeoutSec 5
            $existingHealthy = (
                $existingHealth.data.auth_mode -eq "session" -and
                $existingHealth.data.persistence.mode -eq "postgresql" -and
                $existingHealth.data.persistence.database -eq "puiying_steven_demo" -and
                $existingHealth.data.persistence.inventory_store -eq "postgresql" -and
                $existingHealth.data.ai_enabled -eq $requestedAiEnabled -and
                $existingHealth.data.ai_structuring_provider -eq $requestedAiProvider -and
                $existingLogin.StatusCode -eq 200
            )
        } catch {
            $existingHealthy = $false
        }
    }
    if ($existingHealthy) {
        $startedAt = if ($existingState.started_at) { [datetimeoffset]$existingState.started_at } else { $null }
        $sourceRoots = @(
            (Join-Path $projectRoot "apps\api\app"),
            (Join-Path $projectRoot "apps\web\app"),
            (Join-Path $projectRoot "apps\web\components"),
            (Join-Path $projectRoot "apps\web\lib")
        )
        $newerSource = if ($startedAt) {
            $sourceRoots |
                Where-Object { Test-Path -LiteralPath $_ } |
                ForEach-Object { Get-ChildItem -LiteralPath $_ -Recurse -File -ErrorAction SilentlyContinue } |
                Where-Object { $_.Extension -in @(".py", ".json", ".ts", ".tsx", ".js", ".jsx", ".css") } |
                Where-Object { $_.LastWriteTimeUtc -gt $startedAt.UtcDateTime } |
                Select-Object -First 1
        } else {
            $null
        }
        if (-not $newerSource) {
            Write-Host "Steven Demo is already running and healthy."
            Write-Host "HTTPS: $existingPublicOrigin/login"
            if (-not $NoBrowser) {
                Start-Process "$existingPublicOrigin/login"
            }
            return
        }
        Write-Warning "Project source changed after the current Demo instance started. Restarting the tracked local Demo processes."
        & (Join-Path $PSScriptRoot "stop_steven_demo.ps1")
        $existingState = $null
    }
    if ($existingState) {
        $trackedPids = @(
            $existingState.api_launcher_pid,
            $existingState.api_listener_pid,
            $existingState.web_launcher_pid,
            $existingState.web_listener_pid,
            $existingState.caddy_pid,
            $existingState.caddy_listener_pid
        ) | Where-Object { $_ } | Select-Object -Unique
        $trackedProcessAlive = $trackedPids |
            Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        $relevantPorts = @(
            9000,
            $WebPort,
            $HttpsPort,
            $existingApiPort,
            $existingWebPort,
            $existingHttpsPort
        ) | Select-Object -Unique
        $relevantPortInUse = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -in $relevantPorts } |
            Select-Object -First 1
        if (-not $trackedProcessAlive -and -not $relevantPortInUse) {
            Remove-Item -LiteralPath $statePath -Force
            Write-Warning "Removed a stale Steven Demo state file; no tracked process or project port was active."
        } else {
            throw "An existing Steven Demo instance is running with a different mode or is unhealthy. Run scripts\stop_steven_demo.ps1 before restarting."
        }
    }
}
foreach ($port in 9000, $WebPort, $HttpsPort) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Stop the existing process before starting Steven Demo."
    }
}

if (Microsoft.PowerShell.Management\Test-Path -LiteralPath $nextDevCache) {
    $resolvedWebRoot = [System.IO.Path]::GetFullPath($webRoot).TrimEnd("\")
    $resolvedNextDevCache = [System.IO.Path]::GetFullPath($nextDevCache)
    $expectedCachePrefix = $resolvedWebRoot + "\"
    if (-not $resolvedNextDevCache.StartsWith($expectedCachePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear a Next.js cache outside the project web directory."
    }
    [System.IO.Directory]::Delete($resolvedNextDevCache, $true)
    Write-Host "Cleared the generated Next.js development cache before startup."
}

New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
New-Item -ItemType Directory -Path $fileRoot -Force | Out-Null
New-Item -ItemType Directory -Path $caddyStorage -Force | Out-Null

$env:APP_ENV = "development"
$env:AUTH_MODE = "session"
$env:DEMO_SEED_ENABLED = "false"
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
$env:PGUSER = "puiying_steven_demo_app"
$env:PGDATABASE = "puiying_steven_demo"
$env:DATABASE_URL = "postgresql+psycopg://$($env:PGUSER)@$($env:PGHOST):$($env:PGPORT)/$($env:PGDATABASE)"
$env:FILE_STORAGE_ROOT = $fileRoot
$env:ALLOWED_ORIGINS = $publicOrigin
$env:RATE_LIMIT_MODE = "memory"
$env:SESSION_COOKIE_SECURE = "true"
$env:DEMO_PROFILE_ENABLED = "true"
$env:OCR_ENABLED = "true"
$env:OCR_PROVIDER = "paddle"
$env:PADDLE_PDX_CACHE_HOME = "models/ocr"
$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = "True"
$env:AI_STRUCTURING_ENABLED = if ($requestedAiEnabled) { "true" } else { "false" }
$env:AI_STRUCTURING_PROVIDER = $requestedAiProvider
$env:AI_STRUCTURING_ENDPOINT = "https://api.deepseek.com/v1"
$env:AI_STRUCTURING_MODEL = "deepseek-chat"
$env:STEVEN_API_BASE_URL = "http://127.0.0.1:9000"
$env:STEVEN_PUBLIC_ORIGIN = $publicOrigin
$env:STEVEN_WEB_PORT = "$WebPort"
$env:CADDY_HTTPS_PORT = "$HttpsPort"
$env:CADDY_STORAGE = ($caddyStorage -replace "\\", "/")
$env:PYTHONUNBUFFERED = "1"

$apiOut = Join-Path $logRoot "api.out.log"
$apiErr = Join-Path $logRoot "api.err.log"
$webOut = Join-Path $logRoot "web.out.log"
$webErr = Join-Path $logRoot "web.err.log"
$caddyOut = Join-Path $logRoot "caddy.out.log"
$caddyErr = Join-Path $logRoot "caddy.err.log"

& $caddy validate --config $caddyConfig --adapter caddyfile
if ($LASTEXITCODE -ne 0) {
    throw "Caddy configuration validation failed."
}

$api = Start-Process -FilePath $python `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "9000" `
    -WorkingDirectory $apiRoot `
    -RedirectStandardOutput $apiOut `
    -RedirectStandardError $apiErr `
    -WindowStyle Hidden `
    -PassThru

$inheritedNodeTlsRejectUnauthorized = [Environment]::GetEnvironmentVariable(
    "NODE_TLS_REJECT_UNAUTHORIZED",
    [EnvironmentVariableTarget]::Process
)
try {
    Remove-Item Env:NODE_TLS_REJECT_UNAUTHORIZED -ErrorAction SilentlyContinue
    $web = Start-Process -FilePath $node `
        -ArgumentList $nextCli, "dev", "--hostname", "127.0.0.1", "--port", "$WebPort" `
        -WorkingDirectory $webRoot `
        -RedirectStandardOutput $webOut `
        -RedirectStandardError $webErr `
        -WindowStyle Hidden `
        -PassThru
} finally {
    if ($null -eq $inheritedNodeTlsRejectUnauthorized) {
        Remove-Item Env:NODE_TLS_REJECT_UNAUTHORIZED -ErrorAction SilentlyContinue
    } else {
        $env:NODE_TLS_REJECT_UNAUTHORIZED = $inheritedNodeTlsRejectUnauthorized
    }
}

function Wait-Http([string]$Url, [int]$Seconds, [System.Diagnostics.Process]$Process, [hashtable]$Headers = @{}) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            throw "Process exited before $Url became ready (exit code $($Process.ExitCode))."
        }
        try {
            $response = Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 750
        }
    }
    throw "Timed out waiting for $Url"
}

$caddyProcess = $null
try {
    Wait-Http "http://127.0.0.1:9000/health" 30 $api
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:9000/health" -TimeoutSec 5
    if (
        $health.data.auth_mode -ne "session" -or
        $health.data.persistence.mode -ne "postgresql" -or
        $health.data.persistence.database -ne "puiying_steven_demo" -or
        $health.data.persistence.inventory_store -ne "postgresql" -or
        $health.data.demo_seed_enabled -ne $false -or
        $health.data.ai_enabled -ne $requestedAiEnabled -or
        $health.data.ai_structuring_provider -ne $requestedAiProvider
    ) {
        throw "API health response does not match the approved PostgreSQL Session profile."
    }
    Write-Host "Waiting for the first Next.js /login compilation; slow local filesystems can require more than 60 seconds."
    Wait-Http "http://127.0.0.1:$WebPort/login" 180 $web @{ "X-Forwarded-Proto" = "https" }

    $caddyProcess = Start-Process -FilePath $caddy `
        -ArgumentList "run", "--config", $caddyConfig, "--adapter", "caddyfile" `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $caddyOut `
        -RedirectStandardError $caddyErr `
        -WindowStyle Hidden `
        -PassThru

    $deadline = (Get-Date).AddSeconds(30)
    $httpsReady = $false
    while ((Get-Date) -lt $deadline) {
        if ($caddyProcess.HasExited) {
            throw "Caddy exited before HTTPS became ready (exit code $($caddyProcess.ExitCode))."
        }
        if (Microsoft.PowerShell.Management\Test-Path -LiteralPath $caddyRootCertificate) {
            $probe = "import ssl, urllib.request; context = ssl.create_default_context(cafile=r'''$caddyRootCertificate'''); print(urllib.request.urlopen('$publicOrigin/login', context=context, timeout=3).status)"
            $statusCode = & $python -c $probe 2>$null
            if ($LASTEXITCODE -eq 0 -and $statusCode -eq "200") {
                $httpsReady = $true
                break
            }
        }
        Start-Sleep -Milliseconds 750
    }
    if (-not $httpsReady) {
        throw "Timed out waiting for the verified HTTPS entry."
    }

    $apiListener = Get-NetTCPConnection -State Listen -LocalPort 9000 -ErrorAction Stop | Select-Object -First 1
    $webListener = Get-NetTCPConnection -State Listen -LocalPort $WebPort -ErrorAction Stop | Select-Object -First 1
    $caddyListener = Get-NetTCPConnection -State Listen -LocalPort $HttpsPort -ErrorAction Stop | Select-Object -First 1
    $state = @{
        phase = "ready"
        run_id = $runId
        run_root = $runRoot
        api_launcher_pid = $api.Id
        api_listener_pid = $apiListener.OwningProcess
        web_launcher_pid = $web.Id
        web_listener_pid = $webListener.OwningProcess
        caddy_pid = $caddyProcess.Id
        caddy_listener_pid = $caddyListener.OwningProcess
        started_at = (Get-Date).ToString("o")
        api_url = "http://127.0.0.1:9000"
        internal_web_url = "http://127.0.0.1:$WebPort"
        https_url = $publicOrigin
        caddy_root_certificate = $caddyRootCertificate
        ai_enabled = $requestedAiEnabled
        ai_provider = $requestedAiProvider
    }
    [System.IO.File]::WriteAllText($statePath, ($state | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
} catch {
    foreach ($process in $caddyProcess, $web, $api) {
        if ($null -eq $process) {
            continue
        }
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    $rootProcessIds = @($caddyProcess, $web, $api) |
        Where-Object { $null -ne $_ } |
        ForEach-Object { $_.Id } |
        Select-Object -Unique
    $allProcesses = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    $ownedProcessIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($processId in $rootProcessIds) {
        [void]$ownedProcessIds.Add([int]$processId)
    }
    do {
        $addedChild = $false
        foreach ($process in $allProcesses) {
            if ($ownedProcessIds.Contains([int]$process.ParentProcessId) -and -not $ownedProcessIds.Contains([int]$process.ProcessId)) {
                [void]$ownedProcessIds.Add([int]$process.ProcessId)
                $addedChild = $true
            }
        }
    } while ($addedChild)
    foreach ($processId in @($ownedProcessIds) | Sort-Object -Descending) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host "Steven Demo started."
Write-Host "API: http://127.0.0.1:9000/health"
Write-Host "HTTPS: $publicOrigin/login"
Write-Host "Caddy only listens on 127.0.0.1:$HttpsPort; its admin API is disabled."
$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($caddyRootCertificate)
$trusted = Microsoft.PowerShell.Management\Test-Path -LiteralPath "Cert:\CurrentUser\Root\$($certificate.Thumbprint)"
if ($trusted -and -not $NoBrowser) {
    Start-Process "$publicOrigin/login"
} elseif (-not $trusted) {
    Write-Warning "The project Caddy root CA is not trusted by the current Windows user. Browser trust requires separate project-owner approval."
}
