@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0" || (
  echo [错误] 无法进入 Steven Demo 项目目录。
  pause
  exit /b 1
)
set "SCRIPT=%~dp0scripts\stop_steven_demo.ps1"
if not exist "%SCRIPT%" (
  echo [错误] 找不到停止脚本：%SCRIPT%
  pause
  exit /b 1
)
set "PS_EXE=powershell.exe"
where pwsh.exe >nul 2>&1 && set "PS_EXE=pwsh.exe"
"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo [失败] Steven 本地 Demo 未能安全停止，请查看上方错误信息。
  if not "%STEVEN_DEMO_NO_PAUSE%"=="1" pause
) else (
  echo [完成] Steven 本地 Demo 已停止；PostgreSQL 服务未被修改。
)
exit /b %EXIT_CODE%
