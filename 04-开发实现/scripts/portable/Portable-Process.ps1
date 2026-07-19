function Get-StevenPortableProcess([int]$ProcessId) {
    if ($ProcessId -le 0) { return $null }
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Test-StevenPortableExecutablePath([string]$ActualPath, [string[]]$ExpectedPaths) {
    if ([string]::IsNullOrWhiteSpace($ActualPath)) { return $false }
    foreach ($expectedPath in $ExpectedPaths) {
        if (-not [string]::IsNullOrWhiteSpace($expectedPath) -and
            [string]::Equals($ActualPath, $expectedPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Get-StevenPortablePortOwnerIds([int]$Port) {
    if ($Port -le 0) { return @() }
    return @(
        Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}

function Test-StevenPortableProcessIdentity(
    [int]$ProcessId,
    [string[]]$ExpectedExecutablePaths,
    [string[]]$RequiredCommandFragments = @(),
    [int]$ListeningPort = 0
) {
    $identity = Get-StevenPortableProcess $ProcessId
    if (-not $identity) { return $false }
    if (-not (Test-StevenPortableExecutablePath ([string]$identity.ExecutablePath) $ExpectedExecutablePaths)) { return $false }
    $commandLine = [string]$identity.CommandLine
    foreach ($fragment in $RequiredCommandFragments) {
        if (-not [string]::IsNullOrWhiteSpace($fragment) -and
            $commandLine.IndexOf($fragment, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            return $false
        }
    }
    if ($ListeningPort -gt 0 -and $ProcessId -notin (Get-StevenPortablePortOwnerIds $ListeningPort)) { return $false }
    return $true
}

function Find-StevenPortableProcesses(
    [string[]]$ExpectedExecutablePaths,
    [string[]]$RequiredCommandFragments = @()
) {
    $matches = @()
    foreach ($identity in (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)) {
        if (-not (Test-StevenPortableExecutablePath ([string]$identity.ExecutablePath) $ExpectedExecutablePaths)) { continue }
        $commandLine = [string]$identity.CommandLine
        $matchesAll = $true
        foreach ($fragment in $RequiredCommandFragments) {
            if (-not [string]::IsNullOrWhiteSpace($fragment) -and
                $commandLine.IndexOf($fragment, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
                $matchesAll = $false
                break
            }
        }
        if ($matchesAll) { $matches += $identity }
    }
    return $matches
}

function Stop-StevenPortableVerifiedProcess(
    [int]$ProcessId,
    [string[]]$ExpectedExecutablePaths,
    [string[]]$RequiredCommandFragments = @(),
    [int]$ListeningPort = 0
) {
    if (-not (Test-StevenPortableProcessIdentity $ProcessId $ExpectedExecutablePaths $RequiredCommandFragments $ListeningPort)) {
        return $false
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
    try { Wait-Process -Id $ProcessId -Timeout 10 -ErrorAction SilentlyContinue } catch {}
    return $true
}

function Wait-StevenPortablePortReleased([int]$Port, [int]$Seconds = 15) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) { return $true }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Read-StevenPortableProcessState([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}
