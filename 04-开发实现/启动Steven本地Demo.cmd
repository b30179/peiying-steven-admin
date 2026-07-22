@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0" || (
  echo [ERROR] Cannot enter the Steven Demo project directory.
  if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
  exit /b 1
)

set "SOURCE_PYTHON=%~dp0.venv\Scripts\python.exe"
set "SOURCE_WEB=%~dp0apps\web\package.json"
if exist "%SOURCE_PYTHON%" if exist "%SOURCE_WEB%" goto :run_source

set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS_EXE=pwsh.exe"
set "PORTABLE_ROOT=%STEVEN_PORTABLE_ROOT%"
if not defined PORTABLE_ROOT (
  for /d %%I in ("%~dp0..\..\*") do (
    if exist "%%~fI\Steven_Portable_Demo_20260718\scripts\Start-StevenPortable.ps1" set "PORTABLE_ROOT=%%~fI\Steven_Portable_Demo_20260718"
  )
)
set "PORTABLE_START=!PORTABLE_ROOT!\scripts\Start-StevenPortable.ps1"
if exist "!PORTABLE_START!" (
  echo [INFO] Source runtime is incomplete. Starting the verified portable Demo.
  "%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "!PORTABLE_START!"
  set "EXIT_CODE=!ERRORLEVEL!"
  if not "!EXIT_CODE!"=="0" (
    echo [FAILED] Portable Steven Demo did not start. Review the error above.
    if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
  ) else (
    echo [DONE] Portable Steven Demo is running or already healthy.
  )
  exit /b !EXIT_CODE!
)

echo [ERROR] Source runtime is incomplete and no portable Demo was found.
echo Set STEVEN_PORTABLE_ROOT or restore .venv and apps\web source files.
if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
exit /b 1

:run_source
set "SCRIPT=%~dp0scripts\start_steven_demo.ps1"
if not exist "%SCRIPT%" (
  echo [ERROR] Start script was not found: %SCRIPT%
  if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
  exit /b 1
)
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS_EXE=pwsh.exe"
"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -EnableDeepSeekProofreading %*
set "EXIT_CODE=!ERRORLEVEL!"
if not "!EXIT_CODE!"=="0" (
  echo [FAILED] Steven local Demo did not start. Review the error above.
  if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
) else (
  echo [DONE] Steven local Demo is running or already healthy.
)
exit /b !EXIT_CODE!
