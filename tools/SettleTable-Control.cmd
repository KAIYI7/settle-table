@echo off
rem ===========================================================================
rem SettleTable Windows Host Lifecycle Controller - Native Command Launcher
rem
rem Provides zero-configuration execution for Companion App Quick Actions,
rem Stream Deck buttons, desktop shortcuts, CMD, and PowerShell under default
rem Windows PowerShell execution policies (such as Restricted).
rem ===========================================================================
setlocal
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>nul
if %ERRORLEVEL% equ 0 set "PS_EXE=pwsh.exe"
"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0SettleTable-Control.ps1" %*
exit /b %ERRORLEVEL%
