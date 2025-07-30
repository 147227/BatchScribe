@echo off
chcp 65001 > nul
title AI小说生成器 v4.1.3

echo.
echo ========================================
echo   AI小说生成器 v4.1.3
echo   启动中...
echo ========================================
echo.

REM 检查是否在正确的目录
if not exist "AI小说生成器_v4.1.3.exe" (
    echo ❌ 错误: 未找到主程序文件
    echo 请确保此脚本与主程序在同一目录
    pause
    exit /b 1
)

REM 启动主程序
echo 🚀 正在启动 AI小说生成器...
start "" "AI小说生成器_v4.1.3.exe"

echo.
echo ✅ 程序已启动
echo 如果程序没有正常启动，请直接双击 AI小说生成器_v4.1.3.exe
echo.
timeout /t 3 /nobreak >nul
