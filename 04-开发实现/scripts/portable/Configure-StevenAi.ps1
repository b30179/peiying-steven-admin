param(
    [switch]$Status,
    [switch]$DisableOnline
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Security
. (Join-Path $PSScriptRoot "Portable-Path.ps1")
$scriptRoot = $PSScriptRoot
$parentRoot = Split-Path -Parent $scriptRoot
$packageRoot = if ((Split-Path -Leaf $scriptRoot) -eq "portable") { Split-Path -Parent $parentRoot } else { $parentRoot }
$secretRoot = Join-Path $packageRoot "data\secrets"
$configPath = Join-Path $secretRoot "ai-provider.json"
$secretPath = Join-Path $secretRoot "deepseek-api-key.dpapi"
$physicalRoot = Get-StevenPortablePhysicalRoot $PSScriptRoot

function Write-Utf8([string]$Path, [string]$Content) {
    Write-StevenPortableTextAtomic $Path $Content
}

function Protect-Secret([string]$Value) {
    $plainBytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    return [System.Security.Cryptography.ProtectedData]::Protect(
        $plainBytes,
        $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
}

function Unprotect-Secret([string]$Path) {
    $protectedBytes = [System.IO.File]::ReadAllBytes($Path)
    $plainBytes = [System.Security.Cryptography.ProtectedData]::Unprotect(
        $protectedBytes,
        $null,
        [System.Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    return [System.Text.Encoding]::UTF8.GetString($plainBytes)
}

function Read-Configuration {
    if (-not (Test-Path -LiteralPath $configPath)) {
        return [pscustomobject]@{
            enabled = $false
            provider = "deepseek"
            endpoint = "https://api.deepseek.com/v1"
            model = "deepseek-chat"
        }
    }
    return Get-Content -LiteralPath $configPath -Encoding UTF8 -Raw | ConvertFrom-Json
}

function Save-Configuration([bool]$Enabled, [string]$Endpoint, [string]$Model, [string]$ApiKey) {
    $operationLock = Enter-StevenPortableOperationLock $physicalRoot
    try {
    $endpointValue = $Endpoint.Trim().TrimEnd("/")
    $modelValue = $Model.Trim()
    if ($Enabled) {
        if (-not $endpointValue.StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Endpoint 必须使用 HTTPS。"
        }
        if ([string]::IsNullOrWhiteSpace($modelValue)) {
            throw "模型名称不能为空。"
        }
        if ([string]::IsNullOrWhiteSpace($ApiKey) -and -not (Test-Path -LiteralPath $secretPath)) {
            throw "首次启用 DeepSeek 时必须填写 API Key。"
        }
    }
    New-Item -ItemType Directory -Path $secretRoot -Force | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($ApiKey)) {
        Write-StevenPortableBytesAtomic $secretPath (Protect-Secret $ApiKey.Trim())
    }
    $configuration = [ordered]@{
        enabled = $Enabled
        provider = "deepseek"
        endpoint = $endpointValue
        model = $modelValue
        updated_at = [datetimeoffset]::Now.ToString("o")
        secret_storage = "windows-dpapi-current-user"
    }
    Write-Utf8 $configPath (($configuration | ConvertTo-Json) + [Environment]::NewLine)
    } finally {
        Exit-StevenPortableOperationLock $operationLock
    }
}

$configuration = Read-Configuration

if ($Status) {
    $mode = if ($configuration.enabled -eq $true) { "DeepSeek online" } else { "local Mock" }
    $keyStatus = if (Test-Path -LiteralPath $secretPath) { "configured" } else { "not configured" }
    Write-Host "AI mode: $mode"
    Write-Host "Endpoint: $($configuration.endpoint)"
    Write-Host "Model: $($configuration.model)"
    Write-Host "Protected API key: $keyStatus"
    exit 0
}

if ($DisableOnline) {
    Save-Configuration $false $configuration.endpoint $configuration.model ""
    Write-Host "Online DeepSeek is disabled. Steven will use the explicit local Mock after restart."
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = "Steven 大模型 API 设置"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size(620, 410)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 10)

$title = New-Object System.Windows.Forms.Label
$title.Text = "DeepSeek（OpenAI 兼容接口）"
$title.Location = New-Object System.Drawing.Point(24, 20)
$title.Size = New-Object System.Drawing.Size(560, 30)
$title.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 14, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($title)

$description = New-Object System.Windows.Forms.Label
$description.Text = "Endpoint 和模型已预填。API Key 仅在本机以 Windows DPAPI 加密保存，不会写入日志、数据库或使用手册。"
$description.Location = New-Object System.Drawing.Point(24, 56)
$description.Size = New-Object System.Drawing.Size(570, 44)
$form.Controls.Add($description)

$enabled = New-Object System.Windows.Forms.CheckBox
$enabled.Text = "启用在线 DeepSeek（关闭时使用明确标记的本地 Mock）"
$enabled.Location = New-Object System.Drawing.Point(28, 105)
$enabled.Size = New-Object System.Drawing.Size(550, 28)
$enabled.Checked = $configuration.enabled -eq $true
$form.Controls.Add($enabled)

function Add-Field([string]$Label, [int]$Top, [string]$Value, [bool]$Password = $false) {
    $fieldLabel = New-Object System.Windows.Forms.Label
    $fieldLabel.Text = $Label
    $fieldLabel.Location = New-Object System.Drawing.Point(28, $Top)
    $fieldLabel.Size = New-Object System.Drawing.Size(120, 26)
    $form.Controls.Add($fieldLabel)
    $textBox = New-Object System.Windows.Forms.TextBox
    $textBox.Location = New-Object System.Drawing.Point(155, ($Top - 2))
    $textBox.Size = New-Object System.Drawing.Size(420, 28)
    $textBox.Text = $Value
    $textBox.UseSystemPasswordChar = $Password
    $form.Controls.Add($textBox)
    return $textBox
}

$endpoint = Add-Field "Endpoint" 150 $configuration.endpoint
$model = Add-Field "模型" 195 $configuration.model
$apiKey = Add-Field "API Key" 240 "" $true

$keyHint = New-Object System.Windows.Forms.Label
$keyHint.Text = if (Test-Path -LiteralPath $secretPath) { "已存在本机加密 Key；留空可保留原 Key。" } else { "尚未配置 Key。首次启用时必须填写。" }
$keyHint.Location = New-Object System.Drawing.Point(155, 272)
$keyHint.Size = New-Object System.Drawing.Size(420, 24)
$keyHint.ForeColor = [System.Drawing.Color]::DimGray
$form.Controls.Add($keyHint)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Location = New-Object System.Drawing.Point(28, 305)
$statusLabel.Size = New-Object System.Drawing.Size(550, 40)
$statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen
$form.Controls.Add($statusLabel)

$testButton = New-Object System.Windows.Forms.Button
$testButton.Text = "测试连接"
$testButton.Location = New-Object System.Drawing.Point(28, 352)
$testButton.Size = New-Object System.Drawing.Size(120, 36)
$form.Controls.Add($testButton)

$saveButton = New-Object System.Windows.Forms.Button
$saveButton.Text = "保存设置"
$saveButton.Location = New-Object System.Drawing.Point(326, 352)
$saveButton.Size = New-Object System.Drawing.Size(120, 36)
$form.Controls.Add($saveButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "取消"
$cancelButton.Location = New-Object System.Drawing.Point(455, 352)
$cancelButton.Size = New-Object System.Drawing.Size(120, 36)
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($cancelButton)

$testButton.Add_Click({
    $testKey = $null
    try {
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkOrange
        $statusLabel.Text = "正在测试，请稍候……"
        $form.Refresh()
        $testKey = $apiKey.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($testKey) -and (Test-Path -LiteralPath $secretPath)) {
            $testKey = Unprotect-Secret $secretPath
        }
        if ([string]::IsNullOrWhiteSpace($testKey)) { throw "请先填写 API Key。" }
        $testEndpoint = $endpoint.Text.Trim().TrimEnd("/")
        if (-not $testEndpoint.StartsWith("https://", [System.StringComparison]::OrdinalIgnoreCase)) { throw "Endpoint 必须使用 HTTPS。" }
        $payload = @{
            model = $model.Text.Trim()
            messages = @(@{role="user";content="Reply with OK only."})
            temperature = 0
            max_tokens = 8
        } | ConvertTo-Json -Depth 5
        $headers = @{ Authorization = "Bearer $testKey" }
        $null = Invoke-RestMethod -Method Post -Uri "$testEndpoint/chat/completions" -Headers $headers -ContentType "application/json" -Body $payload -TimeoutSec 30
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen
        $statusLabel.Text = "连接成功。保存后重启 Steven Demo 生效。"
    } catch {
        $statusLabel.ForeColor = [System.Drawing.Color]::Firebrick
        $statusLabel.Text = "连接失败。请检查 Endpoint、模型、网络和 API Key。"
    } finally {
        $testKey = $null
    }
})

$saveButton.Add_Click({
    try {
        Save-Configuration $enabled.Checked $endpoint.Text $model.Text $apiKey.Text
        $statusLabel.ForeColor = [System.Drawing.Color]::DarkGreen
        $statusLabel.Text = "设置已保存。请停止并重新启动 Steven Demo。"
        [System.Windows.Forms.MessageBox]::Show("设置已保存。请重新启动 Steven Demo 后生效。", "Steven", "OK", "Information") | Out-Null
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    } catch {
        $statusLabel.ForeColor = [System.Drawing.Color]::Firebrick
        $statusLabel.Text = $_.Exception.Message
    }
})

$form.AcceptButton = $saveButton
$form.CancelButton = $cancelButton
$null = $form.ShowDialog()
$apiKey.Text = ""
