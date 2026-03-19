@echo off
chcp 65001 >nul
:: QuantForge Windows 启动脚本

echo 🚀 QuantForge 启动脚本
echo ======================
echo.

:: 检查Docker
where docker-compose >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ 错误: docker-compose 未安装
    exit /b 1
)

:: 菜单
echo 请选择操作:
echo 1) 完整启动 (数据库 + 服务)
echo 2) 仅启动数据库
echo 3) 停止所有服务
echo 4) 重启服务
echo 5) 查看状态
echo 6) 运行测试
echo 7) 查看日志
echo q) 退出
echo.

set /p choice="输入选项 [1-7/q]: "

if "%choice%"=="1" (
    echo ▶️ 启动完整服务...
    docker-compose up -d
    echo ⏳ 等待数据库就绪 (10秒)...
    timeout /t 10 /nobreak >nul
    echo ✅ 所有服务已启动
    echo.
    echo 访问地址:
    echo   - Grafana: http://localhost:3000
    echo   - InfluxDB: http://localhost:8086
) else if "%choice%"=="2" (
    echo ▶️ 仅启动数据库...
    docker-compose up -d mysql influxdb redis
) else if "%choice%"=="3" (
    echo 🛑 停止所有服务...
    docker-compose down
) else if "%choice%"=="4" (
    echo 🔄 重启服务...
    docker-compose restart
) else if "%choice%"=="5" (
    echo 📊 服务状态:
    docker-compose ps
) else if "%choice%"=="6" (
    echo 🧪 运行测试...
    pytest modules\qf-database\tests modules\qf-data\tests -v
) else if "%choice%"=="7" (
    echo 查看日志 (按 Ctrl+C 退出)...
    docker-compose logs -f
) else if "%choice%"=="q" (
    echo 退出
    exit /b 0
) else (
    echo ❌ 无效选项
    exit /b 1
)

echo.
echo 完成！
