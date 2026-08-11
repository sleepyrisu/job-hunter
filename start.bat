@echo off
chcp 65001 >nul
title AI Job Hunter - 新手一键启动
cd /d "%~dp0"

echo.
echo  ============================================
echo   AI Job Hunter  -  新手一键启动
echo  ============================================
echo.
echo  Starting the server... (first launch may take a few seconds)
echo  Your browser will open to http://localhost:8888
echo  Keep this window open while using the tool.
echo.

start "" "http://localhost:8888"

where python >nul 2>nul
if %errorlevel%==0 (
    python app.py
) else (
    "%LOCALAPPDATA%\Microsoft\WindowsApps\python3.12.exe" app.py
)
