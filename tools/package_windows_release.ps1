param(
    [string]$Version = "",
    [string]$DistPath = "dist\JobMatcherApp",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $Version) {
    $Version = (Get-Content VERSION -Raw).Trim()
}

if (-not $OutputPath) {
    $OutputPath = "JobMatcherApp-v$Version-windows.zip"
}

if (-not (Test-Path $DistPath)) {
    throw "Pasta de distribuicao nao encontrada: $DistPath"
}

$stage = Join-Path $env:TEMP ("jobmatcher-package-" + [guid]::NewGuid().ToString("N"))
$root = Join-Path $stage "JobMatcherApp"
New-Item -ItemType Directory -Force -Path $root | Out-Null
Copy-Item -Path (Join-Path $DistPath "*") -Destination $root -Recurse -Force

Compress-Archive -Path $root -DestinationPath $OutputPath -Force

Write-Host "Package created:"
Get-Item $OutputPath | Select-Object FullName,Length,LastWriteTime
