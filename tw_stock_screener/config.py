"""
配置檔案 - 台股/美股 SMC + UT Bot 篩選系統
==========================================
"""

# ============================================================
# API 金鑰設定（請填入你的金鑰）
# ============================================================

# Gemini API
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# Line Notify Token（從 https://notify-bot.line.me/ 取得）
LINE_NOTIFY_TOKEN = "YOUR_LINE_NOTIFY_TOKEN"

# ============================================================
# 資料來源設定
# ============================================================

# 台股資料來源選擇: 'twse', 'finmind', 'yfinance'
TW_DATA_SOURCE = 'twse'

# FinMind API Token（可選，免費版有限制）
FINMIND_TOKEN = ""

# ============================================================
# 篩選參數設定
# ============================================================

# UT Bot 參數
UT_BOT_CONFIG = {
    'key_value': 1.0,      # Key Value (Sensitivity) - 靈敏度
    'atr_period': 10,      # ATR Period
    'use_heikin_ashi': True  # 是否使用 Heikin Ashi
}

# SMC 參數
SMC_CONFIG = {
    'swing_length': 50,           # Swing 結構長度
    'internal_length': 5,         # Internal 結構長度
    'show_internal_structure': True,
    'show_swing_structure': True,
    'show_order_blocks': True,
    'show_fvg': True,
    'order_block_filter': 'atr',  # 'atr' or 'range'
    'fvg_threshold': True,        # 自動閾值
    'equal_hl_threshold': 0.1,    # Equal High/Low 閾值
    # 進階 SMC 參數 (from profittown-sniper-smc)
    'enable_liquidity_sweeps': True,   # 啟用流動性掃蕩偵測
    'enable_fibonacci_ote': True,      # 啟用 Fibonacci OTE 區域驗證
    'enable_ob_scoring': True,         # 啟用 Order Block 進階評分
    'liquidity_sweep_lookback': 10,    # 流動性掃蕩回顧期（K 線數）
    'fibonacci_ote_low': 0.618,        # Fibonacci OTE 下限
    'fibonacci_ote_high': 0.786,       # Fibonacci OTE 上限
    'ob_score_threshold': 3,           # Perfect OB 最低分數 (0-5)
}

# EMA Ribbon 參數
EMA_CONFIG = {
    'periods': [5, 20, 60, 120, 240]
}

# ============================================================
# 籌碼分析設定
# ============================================================

CHIP_CONFIG = {
    'foreign_threshold': 1000,     # 外資買超張數閾值
    'investment_trust_threshold': 500,  # 投信買超張數閾值
    'dealer_threshold': 500,       # 自營商買超張數閾值
    'consecutive_days': 3,         # 連續買超天數
}

# ============================================================
# 篩選條件設定
# ============================================================

SCREENING_CRITERIA = {
    # SMC 信號
    'smc_signals': ['CHoCH_bull', 'BOS_bull'],  # 要篩選的 SMC 信號
    'min_signal_strength': 70,
    
    # UT Bot 信號
    'ut_bot_signal': 'buy',  # 'buy', 'sell', 'any'
    
    # 籌碼條件
    'chip_condition': 'foreign_buy',  # 'foreign_buy', 'all_buy', 'any'
    
    # 成交量條件
    'volume_spike': True,
    'volume_ratio': 1.5,
}

# ============================================================
# 股票列表設定
# ============================================================

# 台股觀察清單（可自訂）
TW_STOCK_LIST = [
    # 電子股
    '2330', '2317', '2454', '2308', '2412', '3008', '2357', '2382', '2395', '3711',
    # 金融股
    '2882', '2881', '2891', '2886', '2884', '2885', '2892', '2880', '5880', '2883',
    # 傳產股
    '1301', '1303', '1326', '2002', '2912', '1216', '2105', '9910', '1101', '1102',
    # ETF
    '0050', '0056', '00878', '00919', '00929',
    # 其他熱門
    '2603', '2609', '2615', '6505', '2618', '2801', '2823', '3037', '2049', '1590'
]

# 美股觀察清單
US_STOCK_LIST = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AMD', 'INTC', 'TSM',
    'JPM', 'V', 'MA', 'BAC', 'WFC',
    'SPY', 'QQQ', 'IWM', 'DIA'
]

# ============================================================
# 排程設定
# ============================================================

SCHEDULE_CONFIG = {
    'tw_scan_time': '09:30',      # 台股掃描時間（開盤後）
    'tw_close_scan_time': '13:45', # 台股收盤前掃描
    'us_scan_time': '22:30',      # 美股掃描時間（台灣時間）
    'daily_report_time': '18:00', # 每日報告時間
}

# ============================================================
# 輸出設定
# ============================================================

OUTPUT_CONFIG = {
    'save_csv': True,
    'save_json': True,
    'output_dir': './output',
    'log_dir': './logs',
}
