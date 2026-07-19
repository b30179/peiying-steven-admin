param(
    [switch]$NoBrowser,
    [int]$PostgresPort = 55432,
    [int]$ApiPort = 9000,
    [int]$WebPort = 4300,
    [int]$HttpsPort = 15443,
    [switch]$SkipOperationLock
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
. (Join-Path $PSScriptRoot 'Portable-Path.ps1')
. (Join-Path $PSScriptRoot 'Portable-Process.ps1')

$physicalRoot = Get-StevenPortablePhysicalRoot $PSScriptRoot
$operationLock = if ($SkipOperationLock) { $null } else { Enter-StevenPortableOperationLock $physicalRoot }
$pathContext = $null
$startupSucceeded = $false

try {
    $pathContext = Get-StevenPortablePathContext $PSScriptRoot
    $packageRoot = $pathContext.RuntimeRoot
    $runtimeRoot = Join-Path $packageRoot 'runtime'
    $physicalRuntimeRoot = Join-Path $pathContext.PhysicalRoot 'runtime'
    $python = Join-Path $runtimeRoot 'python\python.exe'
    $node = Join-Path $runtimeRoot 'node\node.exe'
    $postgresBin = Join-Path $runtimeRoot 'postgresql\bin'
    $caddyExe = Join-Path $runtimeRoot 'caddy\caddy.exe'
    $caddyConfig = Join-Path $packageRoot 'config\Caddyfile'
    $apiRoot = Join-Path $packageRoot 'apps\api'
    $webRoot = Join-Path $packageRoot 'apps\web\standalone\apps\web'
    $webServer = Join-Path $webRoot 'server.js'
    $dataRoot = Join-Path $packageRoot 'data'
    $databaseData = Join-Path $dataRoot 'postgresql'
    $secretPath = Join-Path $dataRoot 'secrets\postgres-password.dpapi'
    $initializedPath = Join-Path $dataRoot 'initialized.json'
    $aiConfigPath = Join-Path $dataRoot 'secrets\ai-provider.json'
    $aiSecretPath = Join-Path $dataRoot 'secrets\deepseek-api-key.dpapi'
    $fileRoot = Join-Path $dataRoot 'steven-demo-d1'
    $runtimeData = Join-Path $dataRoot 'runtime'
    $logRoot = Join-Path $runtimeData 'logs'
    $statePath = Join-Path $runtimeData 'portable-processes.json'
    $caddyStorage = Join-Path $runtimeData 'caddy-storage'
    $publicOrigin = "https://localhost:$HttpsPort"
    $pgCtl = Join-Path $postgresBin 'pg_ctl.exe'

    $apiExecutablePaths = @($python, (Join-Path $physicalRuntimeRoot 'python\python.exe')) | Select-Object -Unique
    $webExecutablePaths = @($node, (Join-Path $physicalRuntimeRoot 'node\node.exe')) | Select-Object -Unique
    $caddyExecutablePaths = @($caddyExe, (Join-Path $physicalRuntimeRoot 'caddy\caddy.exe')) | Select-Object -Unique

    function Get-ProtectedSecret([string]$Path) {
        $protectedBytes = [System.IO.File]::ReadAllBytes($Path)
        $plainBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $protectedBytes,
            $null,
            [System.Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        return [System.Text.Encoding]::UTF8.GetString($plainBytes)
    }

    function Wait-Http([string]$Url, [int]$Seconds = 60) {
        $deadline = (Get-Date).AddSeconds($Seconds)
        do {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3 -MaximumRedirection 0
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return }
            } catch {
                if ($_.Exception.Response) {
                    $statusCode = [int]$_.Exception.Response.StatusCode
                    if ($statusCode -ge 200 -and $statusCode -lt 500) { return }
                }
            }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)
        throw "Timed out waiting for $Url"
    }

    function Test-HttpNow([string]$Url) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5 -MaximumRedirection 0
            return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
        } catch {
            if ($_.Exception.Response) {
                $statusCode = [int]$_.Exception.Response.StatusCode
                return $statusCode -ge 200 -and $statusCode -lt 500
            }
            return $false
        }
    }

    function Test-PostgresRunning {
        if (-not (Test-Path -LiteralPath (Join-Path $databaseData 'PG_VERSION'))) { return $false }
        & $pgCtl -D $databaseData status *> $null
        return $LASTEXITCODE -eq 0
    }

    function Stop-PortablePostgresIfRunning {
        if (Test-PostgresRunning) {
            & $pgCtl -D $databaseData stop -m fast *> $null
            if ($LASTEXITCODE -ne 0) { throw 'Portable PostgreSQL failed to stop during startup recovery.' }
        }
    }

    function Stop-KnownPortableApplicationProcesses {
        $groups = @(
            @{ Paths = $caddyExecutablePaths; Fragments = @('run', 'Caddyfile') },
            @{ Paths = $webExecutablePaths; Fragments = @('server.js') },
            @{ Paths = $apiExecutablePaths; Fragments = @('uvicorn', 'app.main:app') }
        )
        foreach ($group in $groups) {
            foreach ($identity in (Find-StevenPortableProcesses $group.Paths $group.Fragments)) {
                Stop-Process -Id $identity.ProcessId -Force -ErrorAction SilentlyContinue
                try { Wait-Process -Id $identity.ProcessId -Timeout 10 -ErrorAction SilentlyContinue } catch {}
            }
        }
    }

    function Test-StateProcessIdentities($State) {
        if (-not $State) { return $false }
        foreach ($property in @('api_pid','web_pid','caddy_pid','api_port','web_port','https_port')) {
            if (-not $State.PSObject.Properties.Name.Contains($property) -or [int]$State.$property -le 0) { return $false }
        }
        return (Test-StevenPortableProcessIdentity ([int]$State.api_pid) $apiExecutablePaths @('uvicorn','app.main:app') ([int]$State.api_port)) -and
            (Test-StevenPortableProcessIdentity ([int]$State.web_pid) $webExecutablePaths @('server.js') ([int]$State.web_port)) -and
            (Test-StevenPortableProcessIdentity ([int]$State.caddy_pid) $caddyExecutablePaths @('run','Caddyfile') ([int]$State.https_port))
    }

    foreach ($required in @(
        $python, $node, $pgCtl, (Join-Path $postgresBin 'pg_isready.exe'),
        $caddyExe, $caddyConfig, $webServer, (Join-Path $PSScriptRoot 'Initialize-StevenPortable.ps1')
    )) {
        if (-not (Test-Path -LiteralPath $required)) { throw "Portable component is missing: $required" }
    }

    & (Join-Path $PSScriptRoot 'Initialize-StevenPortable.ps1') -PostgresPort $PostgresPort -SkipOperationLock
    if (-not (Test-Path -LiteralPath $secretPath) -or -not (Test-Path -LiteralPath $initializedPath)) {
        throw 'Portable database initialization is incomplete.'
    }

    $existingState = Read-StevenPortableProcessState $statePath
    if ($existingState -and (Test-StateProcessIdentities $existingState)) {
        $existingOrigin = if ($existingState.public_origin) { [string]$existingState.public_origin } else { "https://localhost:$($existingState.https_port)" }
        if (-not (Test-PostgresRunning) -or
            -not (Test-HttpNow "http://127.0.0.1:$($existingState.api_port)/health") -or
            -not (Test-HttpNow "http://127.0.0.1:$($existingState.web_port)/login")) {
            throw 'Steven portable Demo processes are present but unhealthy. Run the stop script, then start again.'
        }
        Write-Host "Steven portable Demo is already running: $existingOrigin/login"
        if (-not $NoBrowser) { Start-Process "$existingOrigin/login" }
        $startupSucceeded = $true
        return
    }

    if (Test-Path -LiteralPath $statePath) {
        Write-Host 'A stale portable process state was found; cleaning only verified package-owned processes.'
    }
    Stop-KnownPortableApplicationProcesses
    Stop-PortablePostgresIfRunning
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue

    foreach ($port in @($PostgresPort, $ApiPort, $WebPort, $HttpsPort)) {
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
            throw "Port $port is already in use by a process that is not owned by this portable package."
        }
    }

    New-Item -ItemType Directory -Path $logRoot, $caddyStorage, $fileRoot -Force | Out-Null
    $databasePassword = Get-ProtectedSecret $secretPath
    $deepSeekApiKey = $null
    $api = $null
    $web = $null
    $caddyProcess = $null
    try {
        $env:PGPASSWORD = $databasePassword
        & $pgCtl -s -D $databaseData -l (Join-Path $logRoot 'postgresql.log') start -o "-p $PostgresPort -h 127.0.0.1"
        if ($LASTEXITCODE -ne 0) { throw 'Portable PostgreSQL failed to start.' }
        $deadline = (Get-Date).AddSeconds(30)
        do {
            & (Join-Path $postgresBin 'pg_isready.exe') -h 127.0.0.1 -p $PostgresPort -U puiying_steven_demo_app -d puiying_steven_demo *> $null
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)
        if ($LASTEXITCODE -ne 0) { throw 'Portable PostgreSQL did not become ready.' }

        $env:APP_ENV = 'development'
        $env:AUTH_MODE = 'session'
        $env:DEMO_SEED_ENABLED = 'false'
        $env:DATABASE_URL = "postgresql+psycopg://puiying_steven_demo_app:$databasePassword@127.0.0.1:$PostgresPort/puiying_steven_demo"
        $env:FILE_STORAGE_ROOT = $fileRoot
        $env:ALLOWED_ORIGINS = $publicOrigin
        $env:RATE_LIMIT_MODE = 'memory'
        $env:SESSION_COOKIE_SECURE = 'true'
        $env:DEMO_PROFILE_ENABLED = 'true'
        $env:OCR_ENABLED = 'true'
        $env:OCR_PROVIDER = 'paddle'
        $env:PADDLE_PDX_CACHE_HOME = Join-Path $apiRoot 'models\ocr'
        $env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK = 'True'
        $env:AI_STRUCTURING_ENABLED = 'true'
        $env:AI_STRUCTURING_PROVIDER = 'mock'
        $env:AI_STRUCTURING_ENDPOINT = ''
        $env:AI_STRUCTURING_MODEL = 'mock-structured-demo'
        $aiModeMessage = 'AI uses an explicit local Mock.'

        if (Test-Path -LiteralPath $aiConfigPath) {
            $aiConfig = Get-Content -LiteralPath $aiConfigPath -Encoding UTF8 -Raw | ConvertFrom-Json
            if ($aiConfig.enabled -eq $true) {
                if ($aiConfig.provider -ne 'deepseek') { throw 'Unsupported portable AI provider. Run the AI configuration tool again.' }
                if ([string]::IsNullOrWhiteSpace($aiConfig.endpoint) -or
                    -not $aiConfig.endpoint.StartsWith('https://', [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw 'The configured AI endpoint must use HTTPS.'
                }
                if ([string]::IsNullOrWhiteSpace($aiConfig.model)) { throw 'The configured AI model is empty.' }
                if (-not (Test-Path -LiteralPath $aiSecretPath)) {
                    throw 'DeepSeek is enabled but its protected API key is missing. Run Configure Steven AI API.'
                }
                $deepSeekApiKey = Get-ProtectedSecret $aiSecretPath
                if ([string]::IsNullOrWhiteSpace($deepSeekApiKey)) { throw 'The protected DeepSeek API key is empty.' }
                $env:AI_STRUCTURING_PROVIDER = 'deepseek'
                $env:AI_STRUCTURING_ENDPOINT = $aiConfig.endpoint.TrimEnd('/')
                $env:AI_STRUCTURING_MODEL = $aiConfig.model.Trim()
                $env:DEEPSEEK_API_KEY = $deepSeekApiKey
                $aiModeMessage = 'DeepSeek online AI is enabled with a locally protected API key.'
            }
        }

        $env:STEVEN_API_BASE_URL = "http://127.0.0.1:$ApiPort"
        $env:STEVEN_PUBLIC_ORIGIN = $publicOrigin
        $env:HOSTNAME = '127.0.0.1'
        $env:PORT = "$WebPort"
        $env:STEVEN_WEB_PORT = "$WebPort"
        $env:CADDY_HTTPS_PORT = "$HttpsPort"
        $env:NODE_PATH = Join-Path $packageRoot 'apps\web\standalone\node_modules\.pnpm\node_modules'
        $env:CADDY_STORAGE = $caddyStorage -replace '\\','/'
        $env:PYTHONUNBUFFERED = '1'

        $api = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$ApiPort" -WorkingDirectory $apiRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'api.out.log') -RedirectStandardError (Join-Path $logRoot 'api.err.log')
        Wait-Http "http://127.0.0.1:$ApiPort/health" 90
        $web = Start-Process -FilePath $node -ArgumentList $webServer -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'web.out.log') -RedirectStandardError (Join-Path $logRoot 'web.err.log')
        Wait-Http "http://127.0.0.1:$WebPort/login" 90
        $caddyProcess = Start-Process -FilePath $caddyExe -ArgumentList 'run','--config',$caddyConfig,'--adapter','caddyfile' -WorkingDirectory $packageRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'caddy.out.log') -RedirectStandardError (Join-Path $logRoot 'caddy.err.log')

        $certificatePath = Join-Path $caddyStorage 'pki\authorities\local\root.crt'
        $deadline = (Get-Date).AddSeconds(60)
        $httpsReady = $false
        do {
            if ($caddyProcess.HasExited) { throw 'Caddy exited before HTTPS became ready.' }
            if (Test-Path -LiteralPath $certificatePath) {
                $probe = "import ssl,urllib.request; c=ssl.create_default_context(cafile=r'''$certificatePath'''); print(urllib.request.urlopen('$publicOrigin/login',context=c,timeout=3).status)"
                & $python -c $probe *> $null
                if ($LASTEXITCODE -eq 0) { $httpsReady = $true; break }
            }
            Start-Sleep -Milliseconds 500
        } while ((Get-Date) -lt $deadline)
        if (-not $httpsReady) { throw 'Portable HTTPS endpoint did not become ready.' }

        $state = [ordered]@{
            started_at = [datetimeoffset]::Now.ToString('o')
            postgres_port = $PostgresPort
            api_port = $ApiPort
            web_port = $WebPort
            https_port = $HttpsPort
            api_pid = $api.Id
            web_pid = $web.Id
            caddy_pid = $caddyProcess.Id
            public_origin = $publicOrigin
            certificate = $certificatePath
            path_drive = $pathContext.Drive
        }
        Write-StevenPortableTextAtomic $statePath (($state | ConvertTo-Json) + [Environment]::NewLine)
        Write-Host "Steven portable Demo is ready: $publicOrigin/login"
        Write-Host "PaddleOCR is offline and enabled. $aiModeMessage"
        if (-not $NoBrowser) { Start-Process "$publicOrigin/login" }
        $startupSucceeded = $true
    } catch {
        foreach ($process in @($caddyProcess, $web, $api)) {
            if ($process -and -not $process.HasExited) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            }
        }
        Stop-KnownPortableApplicationProcesses
        Stop-PortablePostgresIfRunning
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
        Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
        $databasePassword = $null
        $deepSeekApiKey = $null
    }
} finally {
    if (-not $startupSucceeded -and $pathContext -and $pathContext.MappingCreated) {
        Remove-StevenPortablePathMapping $pathContext
    }
    Exit-StevenPortableOperationLock $operationLock
}
