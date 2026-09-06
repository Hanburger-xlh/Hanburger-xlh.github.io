@echo off
rem Install launcher (ASCII-only to avoid codepage issues).
rem Registers run-bili.ps1 into the current user's Startup folder.
rem Usage: double-click, or run from a command line.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-startup.ps1"
echo.
pause
