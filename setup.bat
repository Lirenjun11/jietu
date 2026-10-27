@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"

echo ============================================
echo   Jietu Pro 安装依赖
echo ============================================
echo.

if exist "%HERE%.venv\Scripts\python.exe" goto :install

echo [1/3] 创建虚拟环境 .venv ...
py -3 -m venv "%HERE%.venv" 2>nul
if not exist "%HERE%.venv\Scripts\python.exe" python -m venv "%HERE%.venv"
if not exist "%HERE%.venv\Scripts\python.exe" (
    echo [错误] 创建虚拟环境失败，请确认已安装 Python 3.9 及以上版本，
    echo        且安装时勾选了 "Add Python to PATH"。
    pause
    exit /b 1
)

:install
echo [2/3] 升级 pip ...
"%HERE%.venv\Scripts\python.exe" -m pip install --upgrade pip -q

echo [3/3] 安装 PySide6 与 Pillow（约 100MB，请耐心等待）...
"%HERE%.venv\Scripts\python.exe" -m pip install -r "%HERE%requirements.txt"

if errorlevel 1 (
    echo.
    echo [错误] 依赖安装失败，请检查网络后重试。
    echo        国内网络可先执行：
    echo        .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo.
echo 安装完成！双击 run.bat 即可启动。
pause
