$ErrorActionPreference="Stop"
$packageRoot=Split-Path -Parent $PSScriptRoot
$certificate=Join-Path $packageRoot "data\runtime\caddy-storage\pki\authorities\local\root.crt"
if(-not(Test-Path -LiteralPath $certificate)){throw "Start the portable Demo once before trusting its local HTTPS certificate."}
& certutil.exe -user -addstore -f Root $certificate|Out-Null
if($LASTEXITCODE-ne 0){throw "Failed to trust the local Steven HTTPS certificate."}
Write-Host "Steven local HTTPS certificate is trusted for the current Windows user."
