$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

function Get-EnvOrDefault {
 param(
 [string]$Name,
 [string]$DefaultValue
 )
 $value = [Environment]::GetEnvironmentVariable($Name)
 if ([string]::IsNullOrWhiteSpace($value)) {
 return $DefaultValue
 }
 return $value
}

$Workers = Get-EnvOrDefault -Name "WORKERS" -DefaultValue "200"
$Timeout = Get-EnvOrDefault -Name "TIMEOUT" -DefaultValue "8"
$FastMs = Get-EnvOrDefault -Name "FAST_MS" -DefaultValue "5000"
$Limit = Get-EnvOrDefault -Name "LIMIT" -DefaultValue "0"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
 $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
 Write-Host "Python was not found. Install Python3.10+ first." -ForegroundColor Red
 Write-Host "Download: https://www.python.org/downloads/windows/"
 exit 1
}

$argsList = @(
 "./check_socks5.py",
 "--collect",
 "--check",
 "--workers", $Workers,
 "--timeout", $Timeout,
 "--fast-ms", $FastMs
)

if ($Limit -ne "0") {
 $argsList += @("--limit", $Limit)
}

Write-Host "[run] workers=$Workers timeout=$Timeout fast_ms=$FastMs limit=$Limit"
& $python.Source @argsList
exit $LASTEXITCODE
