param(
    [string]$ExePath = "dist\JobMatcherApp\JobMatcherApp.exe",
    [string]$Thumbprint = "",
    [string]$PfxPath = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$SignToolPath = ""
)

$ErrorActionPreference = "Stop"

function Find-SignTool {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (Test-Path $ExplicitPath) {
            return (Resolve-Path $ExplicitPath).Path
        }
        throw "signtool.exe nao encontrado em: $ExplicitPath"
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $sdkRoots = @(
        "C:\Program Files (x86)\Windows Kits\10\bin",
        "C:\Program Files\Windows Kits\10\bin"
    )
    foreach ($root in $sdkRoots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $candidate = Get-ChildItem $root -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    throw "signtool.exe nao encontrado. Instale o Windows SDK ou informe -SignToolPath."
}

if (-not (Test-Path $ExePath)) {
    throw "Executavel nao encontrado: $ExePath"
}

if (-not $Thumbprint -and -not $PfxPath) {
    throw "Informe -Thumbprint para certificado instalado ou -PfxPath para arquivo .pfx."
}

$signTool = Find-SignTool -ExplicitPath $SignToolPath
$resolvedExe = (Resolve-Path $ExePath).Path

Write-Host "Signing: $resolvedExe"
Write-Host "Using signtool: $signTool"

if ($Thumbprint) {
    & $signTool sign /fd SHA256 /td SHA256 /tr $TimestampUrl /sha1 $Thumbprint $resolvedExe
} else {
    if (-not (Test-Path $PfxPath)) {
        throw "Arquivo .pfx nao encontrado: $PfxPath"
    }
    $resolvedPfx = (Resolve-Path $PfxPath).Path
    $password = $env:SIGNTOOL_PFX_PASSWORD
    if (-not $password) {
        $secure = Read-Host "Senha do PFX" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
    & $signTool sign /fd SHA256 /td SHA256 /tr $TimestampUrl /f $resolvedPfx /p $password $resolvedExe
}

Write-Host "Verifying signature..."
& $signTool verify /pa /v $resolvedExe

Write-Host "Signed successfully."
