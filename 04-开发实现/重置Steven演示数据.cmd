@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || (
  echo [错误] 无法进入 Steven Demo 项目目录。
  pause
  exit /b 1
)
set "SCRIPT=%~dp0scripts\run_steven_demo_reset.ps1"
if not exist "%SCRIPT%" (
  echo [错误] 找不到受控重置脚本：%SCRIPT%
  pause
  exit /b 1
)
echo [安全提示] 不带参数时仅执行 dry-run，不会修改数据库或文件。
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS_EXE=pwsh.exe"
"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
  echo [完成] 重置命令已结束；若未提供 --apply，本次仅为 dry-run。
) else (
  echo [停止] 重置命令未执行或被安全检查阻断，请查看上方信息。
)
if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
