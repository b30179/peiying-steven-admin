$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $projectRoot "data\runtime\steven-demo-processes.json"
$caddy = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "tools\caddy\caddy.exe"))
$python = [System.IO.Path]::GetFullPath((Join-Path $projectRoot ".venv\Scripts\python.exe"))
$nextCli = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "apps\web\node_modules\next\dist\bin\next"))
$caddyConfig = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "infra\caddy\Caddyfile"))

if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $statePath)) {
    Write-Host "No Steven Demo process state file was found."
    return
}

try {
    $state = Get-Content -LiteralPath $statePath -Encoding utf8 | ConvertFrom-Json
} catch {
    $activeDefaultPort = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in @(9000, 4300, 15443) } |
        Select-Object -First 1
    if ($activeDefaultPort) {
        throw "Steven Demo state file is invalid while a project port is active. Refusing to stop an unverified process."
    }
    Remove-Item -LiteralPath $statePath -Force
    Write-Warning "Removed an invalid stale Steven Demo state file; no project port was active."
    return
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

function Test-ProjectProcess([string]$Name, [int]$ProcessId, [datetimeoffset]$StartedAt) {
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    $identity = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $process -or -not $identity -or -not $StartedAt) {
        return $false
    }
    $startDelta = [math]::Abs((([datetimeoffset]$process.StartTime) - $StartedAt).TotalMinutes)
    if ($startDelta -gt 5) {
        return $false
    }
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    $executablePath = if ($identity.ExecutablePath) { [System.IO.Path]::GetFullPath([string]$identity.ExecutablePath) } else { "" }
    $commandLine = [string]$identity.CommandLine
    switch ($Name) {
        "FastAPI" {
            return $commandLine.IndexOf("-m uvicorn app.main:app", $comparison) -ge 0 -and
                $commandLine.IndexOf("--host 127.0.0.1", $comparison) -ge 0
        }
        "Next.js" {
            $nextListenerMarker = Join-Path $projectRoot "node_modules"
            return $commandLine.IndexOf($nextCli, $comparison) -ge 0 -or
                ($commandLine.IndexOf($nextListenerMarker, $comparison) -ge 0 -and
                    $commandLine.IndexOf("next\dist\server\lib\start-server.js", $comparison) -ge 0)
        }
        "Caddy" { return $executablePath.Equals($caddy, $comparison) -and $commandLine.IndexOf($caddyConfig, $comparison) -ge 0 }
        default { return $false }
    }
}

$apiPort = Get-StatePort $state.api_url 9000
$webPort = Get-StatePort $state.internal_web_url 4300
$httpsPort = Get-StatePort $state.https_url 15443
$listenerTargets = @(
    @{ Name = "FastAPI"; Port = $apiPort; Pid = $state.api_listener_pid },
    @{ Name = "Next.js"; Port = $webPort; Pid = $state.web_listener_pid },
    @{ Name = "Caddy"; Port = $httpsPort; Pid = $state.caddy_listener_pid }
)

$stopErrors = @()
$identityWarnings = @()
$startedAt = if ($state.started_at) { [datetimeoffset]$state.started_at } else { $null }

foreach ($target in $listenerTargets) {
    if (-not $target.Pid) {
        continue
    }
    $listener = Get-NetTCPConnection -State Listen -LocalPort $target.Port -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -eq $target.Pid } |
        Select-Object -First 1
    if ($listener -and (Get-Process -Id $target.Pid -ErrorAction SilentlyContinue)) {
        if (Test-ProjectProcess $target.Name $target.Pid $startedAt) {
            Stop-Process -Id $target.Pid -Force -ErrorAction SilentlyContinue
        } else {
            $identityWarnings += "$($target.Name) listener identity could not be verified; it was not terminated directly."
        }
    }
}

foreach ($launcherPid in @($state.api_launcher_pid, $state.web_launcher_pid, $state.caddy_pid) | Where-Object { $_ } | Select-Object -Unique) {
    $launcher = Get-Process -Id $launcherPid -ErrorAction SilentlyContinue
    if (-not $launcher -or -not $startedAt) {
        continue
    }
    $launcherName = if ($launcherPid -eq $state.api_launcher_pid) { "FastAPI" } elseif ($launcherPid -eq $state.web_launcher_pid) { "Next.js" } else { "Caddy" }
    if (Test-ProjectProcess $launcherName $launcherPid $startedAt) {
        Stop-Process -Id $launcherPid -Force -ErrorAction SilentlyContinue
    } else {
        $identityWarnings += "$launcherName launcher identity could not be verified; it was not terminated."
    }
}

$deadline = (Get-Date).AddSeconds(10)
do {
    $remainingListeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in @($apiPort, $webPort, $httpsPort) }
    if (-not $remainingListeners) {
        break
    }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

foreach ($port in @($apiPort, $webPort, $httpsPort) | Select-Object -Unique) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        $stopErrors += "Port $port is still listening."
    }
}
$identityWarnings | ForEach-Object { Write-Warning $_ }
if ($stopErrors.Count -gt 0) {
    $stopErrors | ForEach-Object { Write-Warning $_ }
    throw "Steven Demo stop verification failed; state file was retained."
}
Remove-Item -LiteralPath $statePath -Force
Write-Host "Steven Demo HTTPS, web and API processes stopped. PostgreSQL service was not changed."
