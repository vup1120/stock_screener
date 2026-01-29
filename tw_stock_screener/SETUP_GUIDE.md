# 🐍 Python 虛擬環境設定指南

## 為什麼需要獨立環境？

```
你的電腦
├── pfdha_env/          ← PFDHA 專案（OpenQuake, 地震分析）
│   ├── openquake
│   ├── numpy==1.24.x
│   └── ...
│
└── venv_screener/      ← 股票篩選專案（獨立！）
    ├── pandas
    ├── yfinance
    ├── google-generativeai
    └── ...
```

**好處**：
- ✅ 套件版本不衝突
- ✅ 專案互不干擾
- ✅ 方便管理依賴
- ✅ 部署更簡單

---

## 🚀 快速設定

### 方法一：使用設定腳本（推薦）

**Linux / macOS:**
```bash
cd tw_stock_screener
chmod +x setup_env.sh
./setup_env.sh
```

**Windows:**
```cmd
cd tw_stock_screener
setup_env.bat
```

---

### 方法二：手動設定

#### Linux / macOS

```bash
# 1. 進入專案目錄
cd tw_stock_screener

# 2. 建立虛擬環境
python3 -m venv venv_screener

# 3. 啟動環境
source venv_screener/bin/activate

# 4. 確認環境已啟動（會看到 (venv_screener) 前綴）
which python
# 應該顯示: /path/to/tw_stock_screener/venv_screener/bin/python

# 5. 升級 pip
pip install --upgrade pip

# 6. 安裝套件
pip install -r requirements.txt

# 7. 驗證安裝
python -c "import pandas; import numpy; print('✅ 安裝成功!')"
```

#### Windows (CMD)

```cmd
# 1. 進入專案目錄
cd tw_stock_screener

# 2. 建立虛擬環境
python -m venv venv_screener

# 3. 啟動環境
venv_screener\Scripts\activate

# 4. 確認環境已啟動（會看到 (venv_screener) 前綴）
where python

# 5. 升級 pip
python -m pip install --upgrade pip

# 6. 安裝套件
pip install -r requirements.txt

# 7. 驗證安裝
python -c "import pandas; import numpy; print('安裝成功!')"
```

#### Windows (PowerShell)

```powershell
# 1. 進入專案目錄
cd tw_stock_screener

# 2. 建立虛擬環境
python -m venv venv_screener

# 3. 啟動環境（PowerShell 語法不同）
.\venv_screener\Scripts\Activate.ps1

# 如果出現執行原則錯誤，先執行：
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 4-7. 同上
```

---

## 📋 日常使用

### 每次使用前，啟動環境：

```bash
# Linux / macOS
cd tw_stock_screener
source venv_screener/bin/activate

# Windows CMD
cd tw_stock_screener
venv_screener\Scripts\activate

# Windows PowerShell
cd tw_stock_screener
.\venv_screener\Scripts\Activate.ps1
```

### 執行篩選：

```bash
# 確認環境已啟動（看到 (venv_screener) 前綴）
python main.py --market tw
```

### 使用完畢，離開環境：

```bash
deactivate
```

---

## 🔄 切換專案

```bash
# 早上：分析股票
cd ~/projects/tw_stock_screener
source venv_screener/bin/activate
python main.py --market tw
deactivate

# 下午：PFDHA 研究
cd ~/projects/pfdha
conda activate pfdha_env  # 或你的 PFDHA 環境
python your_pfdha_script.py
```

---

## 🛠️ 常見問題

### Q1: `python3: command not found`

```bash
# 嘗試使用 python 而非 python3
python -m venv venv_screener
```

### Q2: PowerShell 執行原則錯誤

```powershell
# 執行這行允許執行腳本
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q3: 套件安裝失敗

```bash
# 確認 pip 是最新版
pip install --upgrade pip

# 單獨安裝問題套件
pip install pandas
pip install yfinance
pip install google-generativeai
```

### Q4: 如何確認使用的是正確環境？

```bash
# 檢查 Python 路徑
which python  # Linux/macOS
where python  # Windows

# 應該指向 venv_screener 目錄內的 python
```

### Q5: 如何刪除虛擬環境？

```bash
# 先離開環境
deactivate

# 直接刪除資料夾
rm -rf venv_screener  # Linux/macOS
rmdir /s venv_screener  # Windows
```

---

## 📁 最終目錄結構

```
tw_stock_screener/
├── venv_screener/          ← 虛擬環境（不要上傳到 Git）
│   ├── bin/ (或 Scripts/)
│   ├── lib/
│   └── ...
├── indicators/
│   ├── __init__.py
│   ├── ut_bot.py
│   ├── smc.py
│   └── chip_analysis.py
├── output/
├── logs/
├── config.py
├── main.py
├── data_fetcher.py
├── notifications.py
├── ai_analyzer.py
├── requirements.txt
├── setup_env.sh
├── setup_env.bat
└── README.md
```

---

## 🎯 快速參考卡

| 動作 | Linux/macOS | Windows |
|------|-------------|---------|
| 建立環境 | `python3 -m venv venv_screener` | `python -m venv venv_screener` |
| 啟動環境 | `source venv_screener/bin/activate` | `venv_screener\Scripts\activate` |
| 離開環境 | `deactivate` | `deactivate` |
| 安裝套件 | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| 執行程式 | `python main.py` | `python main.py` |

---

## ✅ 設定檢查清單

- [ ] Python 3.9+ 已安裝
- [ ] 虛擬環境已建立
- [ ] 環境已啟動（看到前綴）
- [ ] 套件已安裝
- [ ] 測試執行成功
- [ ] config.py 已設定 API Key

完成以上步驟，你就可以開始使用篩選系統了！ 🚀
