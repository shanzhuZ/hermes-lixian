# hermes-lixian 干净会话启动（HERMES_HOME 指向 var/hermes，运行时文件不污染仓库根）
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$RuntimeHome = Join-Path $RepoRoot "var\hermes"

if (-not (Test-Path $RuntimeHome)) {
    Write-Host "首次运行，初始化 var\hermes ..."
    & (Join-Path $RepoRoot "scripts\init-hermes-runtime.ps1")
}

$env:HERMES_HOME = $RuntimeHome
Write-Host "HERMES_HOME=$env:HERMES_HOME"
Write-Host "skills 目录:"
Get-ChildItem (Join-Path $env:HERMES_HOME "skills") -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }

# 优先用 PATH 里的 hermes；也可改成 hermes-agent 虚拟环境里的入口
$hermes = Get-Command hermes -ErrorAction SilentlyContinue
if (-not $hermes) {
    throw "未找到 hermes 命令。请先安装 hermes-agent，或把 hermes 加入 PATH。"
}
& hermes @args
