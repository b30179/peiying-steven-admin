@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "SCRIPT=%~dp0scripts\portable\Configure-StevenAi.ps1"
if not exist "%SCRIPT%" (
  echo [错误] 找不到大模型 API 配置脚本。
  pause
  exit /b 1
)
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo [失败] 大模型 API 设置未保存，请查看上方错误信息。
) else (
  echo.
  echo [完成] 配置窗口已关闭。
)
pause
