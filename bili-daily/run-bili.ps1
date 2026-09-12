# run-bili.ps1
# 每天(开机登录时)由计划任务 BiliCrawlDaily 调用：
#   1. 与远端 main 快进同步（仅在仓库干净时，避免覆盖本地未提交改动）
#   2. 运行 .github/scripts/crawl-bili.js 抓取 B 站动态
#   3. 把运行过程写入日志  <仓库>/logs/bili-crawl.log
#   4. 若 bili.json 有更新则自动 git 提交并 push 到 GitHub
# 任何一步失败都不抛错中断，而是记入日志，保证计划任务总是“成功结束”。
$ErrorActionPreference = 'Continue'

# ---- 路径 ----
$here = Split-Path -Parent $MyInvocation.MyCommand.Path      # ...\bili-daily
$repo = Split-Path -Parent $here                              # 仓库根目录
$logDir = Join-Path $repo 'logs'
$logFile = Join-Path $logDir 'bili-crawl.log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
    param([string]$msg)
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

function Resolve-Node {
    $c = Get-Command node -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $fallback = 'H:\Program Files\nodejs\node.exe'
    if (Test-Path $fallback) { return $fallback }
    return $null
}

# 本机 git 全局配置了 http/https.proxy = 127.0.0.1:7897，所有 git 操作都会强制走该代理。
# 开机时梯子常常还没启动，git 就会直接失败。这里先探测代理端口：不可达就改用直连。
function Get-GitNetArgs {
    $proxy = (git config --get https.proxy 2>$null)
    if (-not $proxy) { $proxy = (git config --get http.proxy 2>$null) }
    if (-not $proxy) { return @() }
    $m = [regex]::Match([string]$proxy, '://([^:/]+):(\d+)')
    if (-not $m.Success) { return @() }
    $hp = $m.Groups[1].Value
    $pp = [int]$m.Groups[2].Value
    $ok = $false
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect($hp, $pp)
        $ok = $client.Connected
        $client.Close()
    } catch { $ok = $false }
    if (-not $ok) {
        Write-Log "提示: 本地代理 $proxy 未在监听(可能开机未启动梯子)，本次改用直连。"
        return @('-c', 'http.proxy=', '-c', 'https.proxy=')
    }
    return @()
}

# 带回退与重试的 git push：先按上面的方式选传输路径，失败则重试数次。
function Invoke-GitPush {
    param([string]$Branch = 'main', [int]$Retry = 3, [int]$IntervalSec = 15)
    $netArgs = Get-GitNetArgs
    for ($i = 1; $i -le $Retry; $i++) {
        $out = git @netArgs push origin $Branch 2>&1 | Out-String
        Write-Log ($out.Trim())
        if ($LASTEXITCODE -eq 0) { return $true }
        Write-Log "push 第 $i/$Retry 次失败，${IntervalSec} 秒后重试..."
        if ($i -lt $Retry) { Start-Sleep -Seconds $IntervalSec }
    }
    return $false
}

Write-Log "==== 开始每日 B 站动态抓取 ===="
Write-Log "仓库: $repo"

Set-Location $repo

# 确认在 git 仓库且分支为 main
$branch = git rev-parse --abbrev-ref HEAD 2>$null
if ($LASTEXITCODE -ne 0) { Write-Log "错误: 不是 git 仓库，退出"; exit 0 }
Write-Log "分支: $branch"

# ---- 1) 尝试快进同步到远端（保持本地为最新）----
Write-Log "--- 尝试同步远端 (git pull --ff-only) ---"
$netArgs = Get-GitNetArgs
$pullOut = git @netArgs pull --ff-only origin main 2>&1 | Out-String
Write-Log ($pullOut.Trim())
if ($LASTEXITCODE -ne 0) {
    Write-Log "提示: 无法快进同步(可能本地有未提交改动或非 main/网络不可达)。继续用当前本地副本抓取。"
}

# ---- 2) 定位 node 并跑爬虫 ----
$nodeExe = Resolve-Node
if (-not $nodeExe) {
    Write-Log "错误: 找不到 node.exe，跳过抓取。请在任务环境安装 Node.js。"
    exit 0
}
Write-Log "node: $nodeExe"
Write-Log "--- 运行 crawl-bili.js ---"
$crawlOut = & $nodeExe (Join-Path $repo '.github\scripts\crawl-bili.js') 2>&1 | Out-String
Write-Log ($crawlOut.Trim())
Write-Log "crawl 退出码: $LASTEXITCODE"

# ---- 3) 发布"昨天"的日常日志摘要（三月七小助手），生成 daily-log.json ----
Write-Log "--- 运行 assistant-logs\parse-and-publish.js ---"
$pubOut = & $nodeExe (Join-Path $repo 'assistant-logs\parse-and-publish.js') 2>&1 | Out-String
Write-Log ($pubOut.Trim())
Write-Log "publish 退出码: $LASTEXITCODE"

# ---- 4) 若有 bili.json 或 daily-log.json 变化则提交并推送 ----
git add -- bili.json daily-log.json 2>&1 | Out-Null
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Log "无内容更新，无需提交。"
    Write-Log "==== 结束(无更新) ===="
    exit 0
}
Write-Log "检测到更新(bili.json / daily-log.json)，开始提交并推送..."

$commitOut = git commit -m "chore(update): 每日B站动态/日常日志" 2>&1 | Out-String
Write-Log ($commitOut.Trim())

# push 前先尝试与远端同步(rebase 本机刚提交的这条，冲突很罕见)
git @netArgs pull --rebase origin main 2>&1 | Out-String | ForEach-Object { Write-Log $_.Trim() }

if (Invoke-GitPush -Branch 'main') {
    Write-Log "推送成功，网站数据已更新。"
} else {
    Write-Log "注意: push 多次重试仍失败。本地提交已保留，可稍后手动 push。"
    Write-Log "      常见原因：网络不可达 GitHub、代理未启动且直连被阻断、或推送凭据过期。"
}

Write-Log "==== 结束 ===="
exit 0
