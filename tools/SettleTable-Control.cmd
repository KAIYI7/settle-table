@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0SettleTable-Control.ps1" %*
exit /b %ERRORLEVEL%
