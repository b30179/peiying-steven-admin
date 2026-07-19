function Get-StevenPortablePhysicalRoot([string]$ScriptRoot) {
    return [System.IO.Path]::GetFullPath((Split-Path -Parent $ScriptRoot)).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
}

function Get-StevenPortableMutexName([string]$PhysicalRoot) {
    $normalizedRoot = [System.IO.Path]::GetFullPath($PhysicalRoot).TrimEnd('\').ToLowerInvariant()
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedRoot))
    } finally {
        $sha256.Dispose()
    }
    $token = ([System.BitConverter]::ToString($hash)).Replace('-', '').Substring(0, 24)
    return "Local\StevenPortable-$token"
}

function Enter-StevenPortableOperationLock([string]$PhysicalRoot, [int]$TimeoutSeconds = 180) {
    $mutex = [System.Threading.Mutex]::new($false, (Get-StevenPortableMutexName $PhysicalRoot))
    $acquired = $false
    try {
        try {
            $acquired = $mutex.WaitOne([TimeSpan]::FromSeconds($TimeoutSeconds))
        } catch [System.Threading.AbandonedMutexException] {
            $acquired = $true
        }
        if (-not $acquired) {
            throw 'Another Steven portable operation is still running. Wait for it to finish, then retry.'
        }
        return [pscustomobject]@{ Mutex = $mutex; Acquired = $true }
    } catch {
        if (-not $acquired) { $mutex.Dispose() }
        throw
    }
}

function Exit-StevenPortableOperationLock($LockHandle) {
    if (-not $LockHandle -or -not $LockHandle.Acquired) { return }
    try {
        $LockHandle.Mutex.ReleaseMutex()
    } finally {
        $LockHandle.Mutex.Dispose()
    }
}

function Write-StevenPortableTextAtomic([string]$Path, [string]$Value) {
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = "$Path.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    try {
        [System.IO.File]::WriteAllText($temporaryPath, $Value, [System.Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    } finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}

function Write-StevenPortableBytesAtomic([string]$Path, [byte[]]$Value) {
    $directory = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporaryPath = "$Path.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
    try {
        [System.IO.File]::WriteAllBytes($temporaryPath, $Value)
        Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    } finally {
        Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    }
}

function Read-StevenPortablePathMarker([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json } catch { return $null }
}

function Test-StevenPortablePathMapping([string]$Drive, [string]$PhysicalRoot) {
    if ([string]::IsNullOrWhiteSpace($Drive) -or -not (Test-Path -LiteralPath ($Drive + '\'))) { return $false }
    $physicalMarkerPath = Join-Path $PhysicalRoot 'data\runtime\portable-path-map.json'
    $mappedMarkerPath = Join-Path ($Drive + '\') 'data\runtime\portable-path-map.json'
    $physicalMarker = Read-StevenPortablePathMarker $physicalMarkerPath
    $mappedMarker = Read-StevenPortablePathMarker $mappedMarkerPath
    if (-not $physicalMarker -or -not $mappedMarker) { return $false }
    return ([string]$physicalMarker.drive -eq $Drive) -and
        ([string]$mappedMarker.drive -eq $Drive) -and
        (-not [string]::IsNullOrWhiteSpace([string]$physicalMarker.token)) -and
        ([string]$physicalMarker.token -eq [string]$mappedMarker.token)
}

function Get-StevenPortablePathContext([string]$ScriptRoot) {
    $physicalRoot = Get-StevenPortablePhysicalRoot $ScriptRoot
    if ($physicalRoot -notmatch '[^\x00-\x7F]') {
        return [pscustomobject]@{
            PhysicalRoot = $physicalRoot
            RuntimeRoot = $physicalRoot
            Drive = $null
            MappingCreated = $false
        }
    }

    $stateRoot = Join-Path $physicalRoot 'data\runtime'
    $mappingPath = Join-Path $stateRoot 'portable-path-map.json'
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    $existingMarker = Read-StevenPortablePathMarker $mappingPath
    $preferredDrive = if ($existingMarker) { $existingMarker.drive } else { $null }
    $candidates = @($preferredDrive, 'S:', 'T:', 'U:', 'V:', 'W:', 'X:', 'Y:', 'Z:', 'R:', 'Q:', 'P:') |
        Where-Object { $_ } |
        Select-Object -Unique

    foreach ($drive in $candidates) {
        $normalizedDrive = ([string]$drive).Substring(0, 1).ToUpperInvariant() + ':'
        if (Test-StevenPortablePathMapping $normalizedDrive $physicalRoot) {
            return [pscustomobject]@{
                PhysicalRoot = $physicalRoot
                RuntimeRoot = ($normalizedDrive + '\')
                Drive = $normalizedDrive
                MappingCreated = $false
            }
        }
        if (Test-Path -LiteralPath ($normalizedDrive + '\')) { continue }
        $mapping = @{
            drive = $normalizedDrive
            token = [guid]::NewGuid().ToString('N')
            updated_at = [datetimeoffset]::Now.ToString('o')
        }
        Write-StevenPortableTextAtomic $mappingPath (($mapping | ConvertTo-Json) + [Environment]::NewLine)
        & subst.exe $normalizedDrive $physicalRoot
        if ($LASTEXITCODE -eq 0 -and (Test-StevenPortablePathMapping $normalizedDrive $physicalRoot)) {
            Write-Host "Portable path contains non-ASCII characters; using temporary drive $normalizedDrive for PostgreSQL."
            return [pscustomobject]@{
                PhysicalRoot = $physicalRoot
                RuntimeRoot = ($normalizedDrive + '\')
                Drive = $normalizedDrive
                MappingCreated = $true
            }
        }
        if (Test-Path -LiteralPath ($normalizedDrive + '\')) { & subst.exe $normalizedDrive /D }
        if (Test-Path -LiteralPath $mappingPath) { [System.IO.File]::Delete($mappingPath) }
    }
    throw 'Unable to allocate a temporary ASCII drive letter for portable PostgreSQL. Disconnect an unused drive letter and retry.'
}

function Remove-StevenPortablePathMapping($Context) {
    if (-not $Context -or [string]::IsNullOrWhiteSpace($Context.Drive)) { return }
    if (Test-StevenPortablePathMapping $Context.Drive $Context.PhysicalRoot) {
        & subst.exe $Context.Drive /D
        if ($LASTEXITCODE -ne 0) { throw "Failed to remove temporary portable drive $($Context.Drive)." }
        $mappingPath = Join-Path $Context.PhysicalRoot 'data\runtime\portable-path-map.json'
        if (Test-Path -LiteralPath $mappingPath) { [System.IO.File]::Delete($mappingPath) }
    }
}
