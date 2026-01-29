# 台股/美股 SMC + UT Bot 篩選系統

## 🎯 功能特色

- **UT Bot 指標**：基於 ATR 的趨勢追蹤系統
- **SMC 指標**：Smart Money Concepts 完整分析
  - BOS (Break of Structure) 結構突破
  - CHoCH (Change of Character) 性格轉變
  - Order Blocks 訂單塊
  - Fair Value Gaps (FVG) 公允價值缺口
  - Premium/Discount Zones 溢價/折價區
- **籌碼分析**：三大法人買賣超追蹤
- **Gemini AI**：智能分析與建議
- **Line 通知**：即時推播篩選結果

---

## 🚀 快速開始

### 1. 安裝套件

```bash
cd tw_stock_screener
pip install -r requirements.txt
```

### 2. 設定 API 金鑰

編輯 `config.py`：

```python
# Gemini API（從 https://makersuite.google.com/app/apikey 取得）
GEMINI_API_KEY = "你的 Gemini API Key"

# Line Notify Token（從 https://notify-bot.line.me/ 取得）
LINE_NOTIFY_TOKEN = "你的 Line Notify Token"
```

### 3. 執行篩選

```bash
# 台股篩選
python main.py --market tw

# 美股篩選
python main.py --market us

# 分析單一股票
python main.py --stock 2330 --verbose

# 啟用 Line 通知
python main.py --market tw --notify
```

---

## 📁 專案結構

```
tw_stock_screener/
├── config.py              # 配置檔案
├── main.py                # 主程式
├── data_fetcher.py        # 資料抓取模組
├── notifications.py       # Line 通知模組
├── ai_analyzer.py         # Gemini AI 模組
├── requirements.txt       # 套件清單
├── indicators/            # 指標模組
│   ├── __init__.py
│   ├── ut_bot.py          # UT Bot 指標
│   ├── smc.py             # SMC 指標
│   └── chip_analysis.py   # 籌碼分析
├── output/                # 輸出結果
└── logs/                  # 日誌檔案
```

---

## 📊 指標說明

### UT Bot 指標

根據 TradingView Pine Script 轉換，使用 ATR Trailing Stop 判斷趨勢。

**參數設定** (`config.py`)：
```python
UT_BOT_CONFIG = {
    'key_value': 1.0,      # 靈敏度（越小越敏感）
    'atr_period': 10,      # ATR 週期
    'use_heikin_ashi': True  # 使用 Heikin Ashi
}
```

**信號說明**：
- `buy`：買進信號（價格向上突破 ATR Stop）
- `sell`：賣出信號（價格向下跌破 ATR Stop）
- `hold`：持有觀望

---

### SMC 指標

完整的 Smart Money Concepts 分析。

**信號說明**：
- `BOS_bull`：多方 Break of Structure（趨勢延續）
- `BOS_bear`：空方 Break of Structure
- `CHoCH_bull`：多方 Change of Character（趨勢反轉）
- `CHoCH_bear`：空方 Change of Character

**參數設定**：
```python
SMC_CONFIG = {
    'swing_length': 50,      # Swing 結構長度
    'internal_length': 5,    # Internal 結構長度
    'show_order_blocks': True,
    'show_fvg': True,
}
```

---

### 籌碼分析

三大法人買賣超追蹤（僅限台股）。

**信號說明**：
- `strong_buy`：外資+投信同步買超
- `buy`：主力積極布局
- `accumulating`：連續買超中
- `strong_sell`：外資+投信同步賣超
- `sell`：主力積極出貨
- `distributing`：連續賣超中

---

## 🔧 自訂篩選條件

編輯 `config.py` 中的 `SCREENING_CRITERIA`：

```python
SCREENING_CRITERIA = {
    # SMC 信號
    'smc_signals': ['CHoCH_bull', 'BOS_bull'],
    'min_signal_strength': 70,
    
    # UT Bot 信號
    'ut_bot_signal': 'buy',  # 'buy', 'sell', 'any'
    
    # 籌碼條件
    'chip_condition': 'foreign_buy',  # 'foreign_buy', 'all_buy', 'any'
    
    # 成交量條件
    'volume_spike': True,
    'volume_ratio': 1.5,
}
```

---

## 📱 Line 通知設定

1. 前往 https://notify-bot.line.me/
2. 登入 Line 帳號
3. 點擊「發行權杖」
4. 選擇要接收通知的聊天室（或 1 對 1）
5. 複製 Token 到 `config.py`

---

## 🤖 Gemini AI 設定

1. 前往 https://makersuite.google.com/app/apikey
2. 建立 API Key
3. 複製到 `config.py`

**AI 功能**：
- 單股分析建議
- 交易信號評分
- 市場概況分析

---

## 📈 使用範例

### 範例 1：每日台股篩選

```python
from main import StockScreener

screener = StockScreener(market='tw', enable_ai=True, enable_notify=True)
results = screener.run_screening()

# 儲存結果
screener.save_results(results)

# 發送通知
screener.send_daily_report(results)
```

### 範例 2：分析特定股票

```python
from main import StockScreener

screener = StockScreener(market='tw')
result = screener.analyze_single_stock('2330', verbose=True)

# 取得 AI 建議
suggestion = result.get('ai_suggestion', {})
print(f"建議: {suggestion.get('action')}")
print(f"評分: {suggestion.get('score')}")
```

### 範例 3：自訂篩選條件

```python
from main import StockScreener

screener = StockScreener(market='tw')

# 自訂篩選條件
custom_filters = {
    'smc_signals': ['CHoCH_bull'],  # 只看 CHoCH 多方
    'ut_bot_signal': 'buy',          # UT Bot 買進
    'chip_condition': 'all_buy',     # 三大法人買超
    'volume_spike': True,            # 量能放大
}

results = screener.run_screening(filters=custom_filters)
```

### 範例 4：排程自動執行

```python
import schedule
import time
from main import StockScreener

def daily_scan():
    screener = StockScreener(market='tw', enable_notify=True)
    results = screener.run_screening()
    screener.send_daily_report(results)
    screener.save_results(results)

# 每天 09:30 執行
schedule.every().day.at("09:30").do(daily_scan)

# 每天 13:45 執行（收盤前）
schedule.every().day.at("13:45").do(daily_scan)

while True:
    schedule.run_pending()
    time.sleep(60)
```

---

## ⚠️ 注意事項

1. **請求頻率**：證交所 API 有請求限制，建議間隔 0.3-0.5 秒
2. **資料延遲**：免費資料可能有延遲
3. **僅供參考**：此工具僅供學習研究，投資決策請自行判斷
4. **台股交易時間**：09:00-13:30
5. **美股交易時間**：21:30-04:00（台灣時間，夏令時）

---

## 🔗 資料來源

- **證交所 OpenAPI**：https://openapi.twse.com.tw/
- **櫃買中心**：https://www.tpex.org.tw/
- **Yahoo Finance**：yfinance 套件
- **FinMind**：https://finmind.github.io/

---

## 📝 更新日誌

### v1.0.0 (2024-01)
- 初始版本
- 整合 UT Bot、SMC、籌碼分析
- 支援 Gemini AI 分析
- 支援 Line 通知

---

## 📧 問題回報

如有問題或建議，請提出 Issue 或 PR。

---

## ⚖️ 免責聲明

本工具僅供學習與研究目的，不構成任何投資建議。使用者應自行承擔投資風險，作者不對任何因使用本工具而產生的損失負責。
