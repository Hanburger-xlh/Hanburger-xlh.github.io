@echo off
chcp 65001 >nul
title 网站 B 站动态 - 每日自动抓取任务注册
setlocal

rem ============================================
rem 注册一个"开机登录即运行"的计划任务 BiliCrawlDaily：
rem   电脑开机自动登录(约每天7点，配合游戏日常一起开机)后，
rem   运行 run-bili.ps1 -> 抓B站动态 -> 写日志 -> 有更新自动 git push。
rem 用法:
rem   右键本脚本 -> 以管理员身份运行          (注册)
rem   本脚本加参数 uninstall (或以管理员执行 schtasks /Delete /TN BiliCrawlDaily /F)  (卸载)
rem ============================================

set "RUNPS1=%~dp0run-bili.ps1"
set "TASKNAME=BiliCrawlDaily"

if /i "%~1"=="uninstall" goto uninstall
if /i "%~1"=="delete" goto uninstall

:install
echo.
echo [1/2] 注册计划任务: %TASKNAME%
echo       触发: 开机登录后自动运行
echo       脚本: %RUNPS1%
echo.
schtasks /Create /TN "%TASKNAME%" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%RUNPS1%\"" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
  echo.
  echo [错误] 注册失败！请右键本脚本，选择"以管理员身份运行"。
  goto end
)
echo [2/2] 注册成功。
echo.
echo 验证: schtasks /Query /TN "%TASKNAME%" /V /FO LIST
echo 手动测试(立即跑一次): powershell -ExecutionPolicy Bypass -File "%RUNPS1%"
goto end

:uninstall
echo 删除计划任务: %TASKNAME%
schtasks /Delete /TN "%TASKNAME%" /F
if errorlevel 1 (
  echo [提示] 任务不存在或删除失败(可能需要管理员权限)。
) else (
  echo 已删除。
)
goto end

:end
echo.
endlocal
if /i "%~1"=="autoclose" exit /b
pause
