#!/bin/bash
# ============================================================
# 台股/美股篩選系統 - 環境設定腳本
# ============================================================
# 
# 使用方式：
#   chmod +x setup_env.sh
#   ./setup_env.sh
#
# 或者手動執行以下步驟
# ============================================================

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║     台股/美股 SMC + UT Bot 篩選系統 - 環境設定            ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# 設定虛擬環境名稱
VENV_NAME="venv_screener"

# 檢查 Python 版本
echo "🔍 檢查 Python 版本..."
python3 --version

# 建立虛擬環境
echo ""
echo "📦 建立虛擬環境: $VENV_NAME"
python3 -m venv $VENV_NAME

# 啟動虛擬環境
echo ""
echo "🚀 啟動虛擬環境..."
source $VENV_NAME/bin/activate

# 升級 pip
echo ""
echo "⬆️  升級 pip..."
pip install --upgrade pip

# 安裝套件
echo ""
echo "📥 安裝必要套件..."
pip install -r requirements.txt

# 顯示已安裝套件
echo ""
echo "✅ 已安裝套件："
pip list

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    設定完成！                              ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "📌 使用方式："
echo ""
echo "   啟動環境："
echo "   source $VENV_NAME/bin/activate"
echo ""
echo "   執行篩選："
echo "   python main.py --market tw"
echo ""
echo "   離開環境："
echo "   deactivate"
echo ""
