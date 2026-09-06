# install-startup.ps1
# 把 run-bili.ps1 加入当前用户的"启动"文件夹，开机登录自动运行。
# 无需管理员、不弹 UAC，适合无人值守。
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path   # ...\bili-daily
$repo = Split-Path -Parent $here
$runps1 = Join-Path $here 'run-bili.ps1'

if (-not (Test-Path $runps1)) {
    throw "找不到 $runps1 ，请把本脚本放在仓库的 bili-daily 目录下运行。"
}

$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$lnk = Join-Path $startup 'B站动态每日抓取.lnk'

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath = 'powershell.exe'
$sc.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $runps1 + '"'
$sc.WorkingDirectory = $repo
$sc.WindowStyle = 7   # 7=最小化
$sc.Description = '开机时抓B站动态并自动推送'
$sc.Save()

Write-Host ('已创建开机自启: ' + $lnk)
