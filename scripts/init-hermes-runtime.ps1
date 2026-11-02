# 初始化 Hermes 运行时目录 var/hermes（HERMES_HOME）
# 配置/技能仍以仓库根为准，通过目录联接指向 var/hermes
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
        throw "目标不存在: $TargetPath"
    }
    if (Test-Path $LinkPath) {
        $item = Get-Item $LinkPath -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Write-Host "已存在联接: $LinkPath"
            return
        }
        throw "已存在非联接路径，请手动处理: $LinkPath"
    }
    cmd /c mklink /J "$LinkPath" "$TargetPath" | Out-Null
    Write-Host "创建联接: $LinkPath -> $TargetPath"
}

# 目录联接：skills（编辑仍在仓库根 skills/）
Ensure-Junction -LinkPath (Join-Path $RuntimeHome "skills") -TargetPath (Join-Path $RepoRoot "skills")

# 过程入库插件：xw-ingest（Hermes hook 直连 MySQL）
$PluginsHome = Join-Path $RuntimeHome "plugins"
New-Item -ItemType Directory -Force -Path $PluginsHome | Out-Null
Ensure-Junction -LinkPath (Join-Path $PluginsHome "xw-ingest") -TargetPath (Join-Path $RepoRoot "plugins\xw-ingest")

# 单文件：每次 init 从仓库根同步（以根目录 config 为准）
Copy-Item -Force (Join-Path $RepoRoot "config.yaml") (Join-Path $RuntimeHome "config.yaml")
if (Test-Path (Join-Path $RepoRoot ".env")) {
    Copy-Item -Force (Join-Path $RepoRoot ".env") (Join-Path $RuntimeHome ".env")
}

Write-Host ""
Write-Host "Done. Start with chat.ps1 (HERMES_HOME=$RuntimeHome)"
