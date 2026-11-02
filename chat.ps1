# hermes-lixian launcher
# - HERMES_HOME 必须指向本项目 var\hermes（配置/skills/.env）
# - hermes.exe 优先用本仓库 hermes-agent\venv（可独立部署，不依赖 hermes-xa）
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$RuntimeHome = Join-Path $RepoRoot "var\hermes"
$LocalHermes = Join-Path $RepoRoot "hermes-agent\venv\Scripts\hermes.exe"

if (-not (Test-Path $RuntimeHome)) {
    Write-Host "First run: init var\hermes ..."
    & (Join-Path $RepoRoot "scripts\init-hermes-runtime.ps1")
}

# 每次启动强制覆盖，避免当前窗口残留其它项目的 HERMES_HOME
$env:HERMES_HOME = $RuntimeHome
# MCP config.yaml 用 ${LIXIAN_ROOT} / ${LIXIAN_PYTHON}，勿写死盘符
$env:LIXIAN_ROOT = $RepoRoot
if (-not $env:LIXIAN_PYTHON) {
    $venvPy = Join-Path $RepoRoot "hermes-agent\venv\Scripts\python.exe"
    $fallbackPy = "D:\environment\python\python.exe"
    if (Test-Path $venvPy) {
        $env:LIXIAN_PYTHON = $venvPy
    } elseif (Test-Path $fallbackPy) {
        $env:LIXIAN_PYTHON = $fallbackPy
    } else {
        $env:LIXIAN_PYTHON = (Get-Command python -ErrorAction Stop).Source
    }
}
Write-Host "HERMES_HOME=$env:HERMES_HOME"
Write-Host "LIXIAN_ROOT=$env:LIXIAN_ROOT"
Write-Host "LIXIAN_PYTHON=$env:LIXIAN_PYTHON"

# 解析 hermes.exe：HERMES_BIN > 本仓库 venv > PATH（不再默认落到 hermes-xa）
$hermesExe = $null
if ($env:HERMES_BIN -and (Test-Path $env:HERMES_BIN)) {
    $hermesExe = $env:HERMES_BIN
    Write-Host "HERMES_BIN(env)=$hermesExe"
} elseif (Test-Path $LocalHermes) {
    $hermesExe = $LocalHermes
} else {
    $cmd = Get-Command hermes -ErrorAction SilentlyContinue
    if ($cmd) { $hermesExe = $cmd.Source }
}

if (-not $hermesExe) {
    throw @"
本仓库尚未安装 hermes CLI。请先执行：
  cd $RepoRoot\hermes-agent
  python -m venv venv
  .\venv\Scripts\python.exe -m pip install -U pip
  .\venv\Scripts\pip.exe install -e .[messaging]
然后再运行: .\chat.ps1 gateway
或设置 HERMES_BIN 指向本仓库的 hermes.exe。
"@
}

Write-Host "HERMES_BIN=$hermesExe"
Write-Host "skills:"
Get-ChildItem (Join-Path $env:HERMES_HOME "skills") -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }

# 同步根目录最新 config / .env / SOUL 到运行时（避免只改了仓库根却仍用旧配置）
Copy-Item -Force (Join-Path $RepoRoot "config.yaml") (Join-Path $RuntimeHome "config.yaml")
if (Test-Path (Join-Path $RepoRoot ".env")) {
    Copy-Item -Force (Join-Path $RepoRoot ".env") (Join-Path $RuntimeHome ".env")
}
if (Test-Path (Join-Path $RepoRoot "SOUL.md")) {
    Copy-Item -Force (Join-Path $RepoRoot "SOUL.md") (Join-Path $RuntimeHome "SOUL.md")
}

& $hermesExe @args