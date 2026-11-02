# 为本仓库 hermes-agent 创建独立 venv（不依赖 hermes-xa）
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path $PSScriptRoot -Parent
$AgentDir = Join-Path $RepoRoot "hermes-agent"
$VenvDir = Join-Path $AgentDir "venv"
$Py = "D:\environment\python\python.exe"
if (-not (Test-Path $Py)) {
    $Py = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "RepoRoot=$RepoRoot"
Write-Host "Python=$Py"
& $Py --version

Push-Location $AgentDir
try {
    if (-not (Test-Path $VenvDir)) {
        Write-Host "Creating venv ..."
        & $Py -m venv $VenvDir
    }
    $pip = Join-Path $VenvDir "Scripts\pip.exe"
    $venvPy = Join-Path $VenvDir "Scripts\python.exe"
    & $venvPy -m pip install -U pip setuptools wheel
    # 优先 uv sync（有锁更快更可复现）；失败再退回 pip editable
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) {
        Write-Host "uv sync ..."
        & $uv.Source sync --python $venvPy
        # API Server / gateway 需要 aiohttp（在 messaging extra 里）
        & $uv.Source pip install -e ".[messaging]" --python $venvPy
    } else {
        Write-Host "pip install -e .[messaging] ..."
        & $pip install -e ".[messaging]"
    }
    $hermes = Join-Path $VenvDir "Scripts\hermes.exe"
    if (-not (Test-Path $hermes)) {
        throw "install finished but hermes.exe missing: $hermes"
    }
    Write-Host ""
    Write-Host "OK: $hermes"
    & $hermes --version
    Write-Host ""
    Write-Host "Next:"
    Write-Host "  1) Stop any other gateway on :8642 (especially hermes-xa)"
    Write-Host "  2) .\chat.ps1 gateway"
} finally {
    Pop-Location
}
