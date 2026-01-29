@echo off
REM ============================================================
REM 台股/美股篩選系統 - Windows 環境設定腳本
REM ============================================================
REM 
REM 使用方式：雙擊執行或在 CMD 中執行
REM   setup_env.bat
REM
REM ============================================================

echo ╔═══════════════════════════════════════════════════════════╗
echo ║     台股/美股 SMC + UT Bot 篩選系統 - 環境設定            ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

set VENV_NAME=venv_screener

REM 檢查 Python 版本
echo 🔍 檢查 Python 版本...
python --version

REM 建立虛擬環境
echo.
echo 📦 建立虛擬環境: %VENV_NAME%
python -m venv %VENV_NAME%

REM 啟動虛擬環境
echo.
echo 🚀 啟動虛擬環境...
call %VENV_NAME%\Scripts\activate.bat

REM 升級 pip
echo.
echo ⬆️  升級 pip...
python -m pip install --upgrade pip

REM 安裝套件
echo.
echo 📥 安裝必要套件...
pip install -r requirements.txt

REM 顯示已安裝套件
echo.
echo ✅ 已安裝套件：
pip list

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                    設定完成！                              ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo 📌 使用方式：
echo.
echo    啟動環境：
echo    %VENV_NAME%\Scripts\activate
echo.
echo    執行篩選：
echo    python main.py --market tw
echo.
echo    離開環境：
echo    deactivate
echo.
pause
