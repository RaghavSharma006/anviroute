@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "ANVIROUTE_INSTALL_EXIT=%ERRORLEVEL%"
if not "%~1"=="" exit /b %ANVIROUTE_INSTALL_EXIT%
pause
exit /b %ANVIROUTE_INSTALL_EXIT%
