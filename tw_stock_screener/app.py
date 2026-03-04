#!/usr/bin/env python3
"""
台股篩選系統 - Web Dashboard
==============================
互動式網頁介面，整合即時資料抓取、技術分析、與圖表展示。

執行方式:
    cd tw_stock_screener
    streamlit run app.py

功能:
    - 多股票切換（自動讀取 data/ 目錄中的快取）
    - K線圖 / Heikin Ashi 切換
    - UT Bot + SMC + EMA Ribbon 指標
    - 一鍵更新資料（呼叫 fetch_and_cache.py）
    - 顯示資料新鮮度與來源
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path

import streamlit as st
import pandas as pd

# ── 路徑設定 ─────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

# ── 股票名稱對照 ──────────────────────────────────────────────────────
STOCK_NAMES = {
    '2330': '台積電 TSMC',  '2317': '鴻海',       '2454': '聯發科',
    '2308': '台達電',       '2412': '中華電',      '3008': '大立光',
    '0050': '元大台灣50',   '0056': '元大高股息',  '2382': '廣達',
    '2357': '華碩',         '2395': '研華',        '2881': '富邦金',
    '2882': '國泰金',       '1301': '台塑',        '2002': '中鋼',
    '2336': '仁寶電腦',
}

# ── 頁面設定 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股監控儀表板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-box {
    background: #f8f9fa; border-radius: 10px; padding: 16px 20px;
    border-left: 4px solid #0066cc;
}
.signal-buy  { color: #00a651; font-weight: bold; font-size: 1.1em; }
.signal-sell { color: #e03131; font-weight: bold; font-size: 1.1em; }
.signal-hold { color: #f08c00; font-weight: bold; font-size: 1.1em; }
.data-fresh  { color: #00a651; }
.data-stale  { color: #f08c00; }
.data-old    { color: #e03131; }
</style>
""", unsafe_allow_html=True)


# ── 工具函數 ──────────────────────────────────────────────────────────

def get_cached_stocks() -> list[str]:
    """掃描 data/ 目錄，列出已有快取的股票。"""
    data_dir = ROOT / 'data'
    if not data_dir.exists():
        return []
    files = sorted(data_dir.glob('*_cache.csv'))
    return [f.stem.replace('_cache', '') for f in files]


def cache_age_str(stock_id: str) -> tuple[str, str]:
    """回傳 (age_string, css_class)"""
    path = ROOT / 'data' / f'{stock_id}_cache.csv'
    if not path.exists():
        return 'no cache', 'data-old'
    age_h = (time.time() - path.stat().st_mtime) / 3600
    if age_h < 24:
        return f'{age_h:.0f}h ago', 'data-fresh'
    elif age_h < 72:
        return f'{age_h/24:.0f}d ago', 'data-stale'
    else:
        return f'{age_h/24:.0f}d ago', 'data-old'


@st.cache_data(ttl=300, show_spinner=False)
def load_and_analyse(stock_id: str, days: int, chart_type: str, theme: str):
    """載入資料並計算所有指標（Streamlit 快取 5 分鐘）。"""
    from data_fetcher import UnifiedDataFetcher
    from indicators.combo_indicator import calculate_combo
    from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG, SCREENING_CRITERIA
    from indicators.ut_bot import get_ut_bot_signal, calculate_ut_bot, calculate_ema_ribbon
    from indicators.smc import calculate_smc
    from visualization import plot_stock_with_indicators

    # 1. 取得資料
    fetcher = UnifiedDataFetcher(tw_source='twse')
    df = fetcher.get_tw_stock_data(stock_id, days=days)
    if df is None or len(df) < 20:
        return None

    # 2. 計算指標
    combo = calculate_combo(
        df,
        ut_config=UT_BOT_CONFIG,
        ema_periods=EMA_CONFIG.get('periods', [5, 20, 60, 120, 240]),
        mm_length=1,
        smc_config=SMC_CONFIG,
    )

    # 3. 分析結果
    result = {'stock_id': stock_id, 'price': float(df['close'].iloc[-1])}
    result['price_change'] = float(
        (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    ) if len(df) >= 2 else 0.0

    try:
        ut_df = calculate_ut_bot(df, key_value=UT_BOT_CONFIG['key_value'],
                                  atr_period=UT_BOT_CONFIG['atr_period'],
                                  use_heikin_ashi=UT_BOT_CONFIG['use_heikin_ashi'])
        ut_sum = get_ut_bot_signal(ut_df)
        result['ut_signal'] = ut_sum['signal']
        result['ut_trend']  = ut_sum['trend']
        result['ut_atr_stop'] = ut_sum.get('atr_stop')
        result['ut_strength']  = ut_sum.get('strength', 0)
    except Exception:
        result['ut_signal'] = 'hold'; result['ut_trend'] = 'N/A'
        result['ut_atr_stop'] = None; result['ut_strength'] = 0

    try:
        _, smc_sum = calculate_smc(df,
            swing_length=SMC_CONFIG['swing_length'],
            internal_length=SMC_CONFIG['internal_length'],
            equal_hl_threshold=SMC_CONFIG['equal_hl_threshold'],
            order_block_filter=SMC_CONFIG['order_block_filter'],
            fvg_threshold=SMC_CONFIG['fvg_threshold'])
        result['smc_signal']   = smc_sum.get('signal')
        result['smc_trend']    = smc_sum.get('swing_trend', 'N/A')
        result['smc_strength'] = smc_sum.get('signal_strength', 0)
        result['smc_ob_count'] = smc_sum.get('order_blocks_count', 0)
        result['smc_fvg_count']= smc_sum.get('fvg_count', 0)
    except Exception:
        result['smc_signal'] = None; result['smc_trend'] = 'N/A'
        result['smc_strength'] = 0; result['smc_ob_count'] = 0; result['smc_fvg_count'] = 0

    try:
        ema_df = calculate_ema_ribbon(df, periods=EMA_CONFIG['periods'])
        result['ema_bullish'] = bool(ema_df['ema_bullish'].iloc[-1]) if 'ema_bullish' in ema_df.columns else False
        result['ema_bearish'] = bool(ema_df['ema_bearish'].iloc[-1]) if 'ema_bearish' in ema_df.columns else False
    except Exception:
        result['ema_bullish'] = False; result['ema_bearish'] = False

    if len(df) >= 20:
        avg_vol = df['volume'].tail(20).mean()
        cur_vol = df['volume'].iloc[-1]
        result['vol_ratio'] = float(cur_vol / avg_vol) if avg_vol > 0 else 1.0
        result['vol_spike']  = result['vol_ratio'] > SCREENING_CRITERIA['volume_ratio']
    else:
        result['vol_ratio'] = 1.0; result['vol_spike'] = False

    # 4. 建立圖表（回傳 plotly figure）
    fig = plot_stock_with_indicators(
        df, stock_id,
        ut_data=combo['ut_data'], smc_data=combo['smc_data'],
        ema_ribbon=combo['ema_ribbon'], maxmin=combo['maxmin'],
        chart_type=chart_type,
        save_path=None, show=False, theme=theme,
    )

    return {'df': df, 'result': result, 'fig': fig}


def run_fetch(stock_id: str):
    """在後台執行 fetch_and_cache.py 並回傳輸出。"""
    script = str(ROOT / 'fetch_and_cache.py')
    proc = subprocess.run(
        [sys.executable, script, stock_id, '--days', '180'],
        capture_output=True, text=True, timeout=120,
        cwd=str(ROOT),
    )
    return proc.stdout + proc.stderr


# ── Sidebar ───────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📈 台股監控儀表板")
    st.divider()

    # 股票選擇
    cached = get_cached_stocks()
    all_stocks = sorted(set(cached + list(STOCK_NAMES.keys())))
    default_idx = all_stocks.index('2330') if '2330' in all_stocks else 0

    stock_id = st.selectbox(
        "選擇股票",
        options=all_stocks,
        index=default_idx,
        format_func=lambda s: f"{s}  {STOCK_NAMES.get(s, '')}",
    )

    # 自訂股票輸入
    custom = st.text_input("或輸入股票代碼", placeholder="例: 2303", max_chars=6)
    if custom.strip():
        stock_id = custom.strip()

    st.divider()

    # 顯示天數
    days = st.select_slider(
        "顯示天數",
        options=[30, 60, 90, 120, 180],
        value=120,
    )

    # 圖表類型
    chart_type = st.radio(
        "圖表類型",
        options=['candlestick', 'heikin_ashi'],
        format_func=lambda x: '🕯 K線圖' if x == 'candlestick' else '🔵 Heikin Ashi',
        horizontal=True,
    )

    # 主題
    theme = st.radio("主題", ['light', 'dark'], horizontal=True)

    st.divider()

    # 資料狀態
    age_str, age_cls = cache_age_str(stock_id)
    st.markdown(f"**資料狀態:** <span class='{age_cls}'>{age_str}</span>", unsafe_allow_html=True)

    # 更新按鈕
    if st.button("🔄 更新資料", use_container_width=True, type="primary"):
        with st.spinner(f"正在抓取 {stock_id} 最新資料..."):
            output = run_fetch(stock_id)
        load_and_analyse.clear()
        st.success("資料已更新！")
        with st.expander("抓取詳情"):
            st.code(output)
        st.rerun()

    st.divider()
    st.caption("資料來源: TWSE / FinMind / yfinance")
    st.caption("每日 14:30 TST 由 GitHub Actions 自動更新")


# ── 主畫面 ────────────────────────────────────────────────────────────

stock_name = STOCK_NAMES.get(stock_id, stock_id)
st.title(f"{stock_id}  {stock_name}")

with st.spinner("載入資料與計算指標中..."):
    data = load_and_analyse(stock_id, days, chart_type, theme)

if data is None:
    st.error(f"無法載入 {stock_id} 的資料。")
    st.info("請點擊左側「🔄 更新資料」按鈕，或確認股票代碼是否正確。")
    st.stop()

df     = data['df']
result = data['result']
fig    = data['fig']

# ── 價格指標列 ────────────────────────────────────────────────────────

price  = result['price']
change = result['price_change']
col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("最新收盤", f"{price:,.1f}", f"{change:+.2f}%",
            delta_color="normal")
col2.metric("成交量倍數", f"{result['vol_ratio']:.2f}x",
            "⚡ 放大" if result['vol_spike'] else "正常",
            delta_color="off")

# UT Bot
ut_sig = result['ut_signal'].upper()
ut_color = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '🟡'}.get(ut_sig, '⚪')
col3.metric("UT Bot 信號", f"{ut_color} {ut_sig}", result['ut_trend'].upper())

# SMC
smc_sig = str(result['smc_signal'] or 'N/A')
smc_color = '🟢' if 'bull' in smc_sig.lower() else ('🔴' if 'bear' in smc_sig.lower() else '⚪')
col4.metric("SMC 信號", f"{smc_color} {smc_sig}", f"強度 {result['smc_strength']}/100")

# EMA
ema_status = '🟢 多頭' if result['ema_bullish'] else ('🔴 空頭' if result['ema_bearish'] else '🟡 混合')
col5.metric("EMA Ribbon", ema_status, "5>20>60>120>240" if result['ema_bullish'] else "")

# ── 圖表 ──────────────────────────────────────────────────────────────

st.plotly_chart(fig, use_container_width=True)

# ── 詳細分析 ──────────────────────────────────────────────────────────

st.subheader("詳細分析")
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("##### 🤖 UT Bot")
    st.write(f"**趨勢:** {result['ut_trend'].upper()}")
    st.write(f"**信號:** {result['ut_signal'].upper()}")
    if result['ut_atr_stop']:
        st.write(f"**ATR Stop:** {result['ut_atr_stop']:,.1f} 元")
    st.progress(min(result['ut_strength'], 100), text=f"強度 {result['ut_strength']}/100")

with c2:
    st.markdown("##### 📐 SMC 智慧資金")
    st.write(f"**主趨勢:** {result['smc_trend']}")
    st.write(f"**信號:** {result['smc_signal'] or 'N/A'}")
    st.write(f"**Order Blocks:** {result['smc_ob_count']} 個")
    st.write(f"**FVG:** {result['smc_fvg_count']} 個")
    st.progress(min(result['smc_strength'], 100), text=f"強度 {result['smc_strength']}/100")

with c3:
    st.markdown("##### 📊 量能 & EMA")
    st.write(f"**成交量:** {result['vol_ratio']:.2f}x 均量")
    if result['vol_spike']:
        st.write("⚡ **成交量放大！**")
    st.write(f"**EMA 排列:** {'✅ 多頭' if result['ema_bullish'] else ('🔴 空頭' if result['ema_bearish'] else '⚠️ 混合')}")

    # 綜合評分
    score = 0
    if result['ut_signal'] == 'buy':         score += 30
    if 'bull' in str(result['smc_signal']): score += 30
    if result['ema_bullish']:                score += 20
    if result['vol_spike']:                  score += 10
    verdict = ('🟢 多方強勢' if score >= 70 else
               '🟡 偏多觀望' if score >= 40 else '🔴 偏空謹慎')
    st.write(f"**綜合評分:** {score}/100")
    st.write(f"**研判:** {verdict}")

# ── 原始資料表 ────────────────────────────────────────────────────────

with st.expander("📋 原始資料（最近 20 筆）"):
    display_df = df.tail(20).copy()
    display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%Y-%m-%d')
    display_df['change%'] = display_df['close'].pct_change().mul(100).round(2)
    st.dataframe(display_df[['date','open','high','low','close','volume','change%']],
                 use_container_width=True, hide_index=True)

# ── 資料狀態 ──────────────────────────────────────────────────────────

with st.expander("ℹ️ 資料來源與狀態"):
    age_str, _ = cache_age_str(stock_id)
    st.write(f"**快取檔案:** `data/{stock_id}_cache.csv`")
    st.write(f"**資料新鮮度:** {age_str}")
    st.write(f"**資料筆數:** {len(df)} 根 K線")
    d0 = df['date'].iloc[0]; d1 = df['date'].iloc[-1]
    fmt = lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
    st.write(f"**日期範圍:** {fmt(d0)} ~ {fmt(d1)}")
    st.divider()
    st.markdown("""
**資料更新方式:**
1. 點擊側邊欄「🔄 更新資料」（需外部 API 可連線）
2. GitHub Actions 每日 14:30 TST 自動執行並提交最新 CSV
3. 系統自動從 `raw.githubusercontent.com` 下載最新快取
    """)
