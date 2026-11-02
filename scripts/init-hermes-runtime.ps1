# Init Hermes runtime dir var\hermes (HERMES_HOME)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$RuntimeHome = Join-Path $RepoRoot "var\hermes"

Write-Host "RepoRoot=$RepoRoot"
Write-Host "RuntimeHome=$RuntimeHome"

New-Item -ItemType Directory -Force -Path $RuntimeHome | Out-Null

function Ensure-Junction {
    param(
        [string]$LinkPath,
        [string]$TargetPath
    )
    if (-not (Test-Path $TargetPath)) {
        throw "Target not found: $TargetPath"
    }
    if (Test-Path $LinkPath) {
        $item = Get-Item $LinkPath -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Write-Host "Junction exists: $LinkPath"
            return
        }
        throw "Path exists and is not a junction: $LinkPath"
    }
    cmd /c mklink /J "$LinkPath" "$TargetPath" | Out-Null
    Write-Host "Created junction: $LinkPath -> $TargetPath"
}

Ensure-Junction -LinkPath (Join-Path $RuntimeHome "skills") -TargetPath (Join-Path $RepoRoot "skills")

Copy-Item -Force (Join-Path $RepoRoot "config.yaml") (Join-Path $RuntimeHome "config.yaml")
if (Test-Path (Join-Path $RepoRoot ".env")) {
    Copy-Item -Force (Join-Path $RepoRoot ".env") (Join-Path $RuntimeHome ".env")
}

Write-Host ""
Write-Host "Done. Start with chat.ps1 (HERMES_HOME=$RuntimeHome)"