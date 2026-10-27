@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "PY="

if exist "%HERE%.venv\Scripts\pythonw.exe" (
    set "PY=%HERE%.venv\Scripts\pythonw.exe"
    goto :run
)
if exist "%USERPROFILE%\.workbuddy-ai\binaries\python\envs\jietu\Scripts\pythonw.exe" (
    set "PY=%USERPROFILE%\.workbuddy-ai\binaries\python\envs\jietu\Scripts\pythonw.exe"
    goto :run
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    set "PY=pythonw"
    goto :run
)

echo [错误] 没有找到可用的 Python 运行环境。
echo 请先双击运行 setup.bat 完成安装。
pause
exit /b 1

:run
start "" "%PY%" "%HERE%main.py" %*
exit /b 0
