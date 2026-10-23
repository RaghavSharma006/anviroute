@echo off
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
python -m anviroute %*
set "ANVIROUTE_EXIT=%ERRORLEVEL%"
if not "%~1"=="" exit /b %ANVIROUTE_EXIT%
pause
exit /b %ANVIROUTE_EXIT%
