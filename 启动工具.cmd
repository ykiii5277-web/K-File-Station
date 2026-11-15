@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\K文件处理台\K文件处理台.exe" (
    start "" "dist\K文件处理台\K文件处理台.exe"
) else (
    echo Please extract the portable release ZIP and run the EXE inside.
    pause
)
