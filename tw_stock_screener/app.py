#!/usr/bin/env python3
"""
台股篩選系統 - TradingView 風格 Web Dashboard
==============================================
互動式網頁介面，提供 K 線圖 + 技術指標分析。

執行方式:
    cd tw_stock_screener
    streamlit run app.py

首次使用：
    python fetch_and_cache.py --all --days 365
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path

import streamlit as st
import pandas as pd

# ── 路徑設定 ─────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

# ── 股票觀察清單（分組 + 名稱）────────────────────────────────────────

WATCHLIST_GROUPS = {
    "AI與半導體核心權值股": [
        ('2330', '台積電'), ('2317', '鴻海'), ('2454', '聯發科'),
        ('2382', '廣達'), ('3231', '緯創'), ('2376', '技嘉'),
        ('2377', '微星'), ('3711', '日月光投控'), ('3661', '世芯-KY'), ('3443', '創意'),
    ],
    "網通訊號與高速傳輸": [
        ('2345', '智邦'), ('3596', '智易'), ('3034', '聯詠'),
        ('4966', '譜瑞-KY'), ('5269', '祥碩'), ('2379', '瑞昱'),
        ('3533', '嘉澤'), ('3105', '穩懋'), ('8086', '宏捷科'), ('2455', '全新'),
    ],
    "先進封裝材料與散熱": [
        ('2383', '台光電'), ('6274', '台燿'), ('6213', '聯茂'),
        ('2368', '金像電'), ('3653', '健策'), ('2308', '台達電'),
        ('5274', '信驊'), ('6187', '萬潤'), ('3680', '家登'), ('6223', '旺矽'),
    ],
    "重電綠能與航運": [
        ('1519', '華城'), ('1513', '中興電'), ('1504', '士電'),
        ('1514', '亞力'), ('6806', '森崴能源'), ('2603', '長榮'), ('2609', '陽明'),
    ],
    "矽光子 / CPO": [
        ('3081', '聯亞'), ('3363', '上詮'), ('3163', '波若威'),
    ],
    "液冷散熱技術": [
        ('3324', '雙鴻'), ('3017', '奇鋐'), ('8996', '高力'),
    ],
    "先進封裝設備": [
        ('3131', '弘塑'), ('3583', '辛耘'), ('8027', '鈦昇'),
    ],
    "其他": [
        ('2337', '旺宏'), ('00631L', '元大台灣50正2'),
    ],
}

# Build flat lookup
STOCK_NAMES = {}
ALL_STOCK_IDS = []
for grp_stocks in WATCHLIST_GROUPS.values():
    for sid, name in grp_stocks:
        if sid not in STOCK_NAMES:
            STOCK_NAMES[sid] = name
            ALL_STOCK_IDS.append(sid)


# ── 頁面設定 ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="台股 TradingView",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Reduce padding for TradingView-like look */
.block-container { padding-top: 1rem; padding-bottom: 0; }
section[data-testid="stSidebar"] > div { padding-top: 1rem; }
/* Stock button in sidebar */
.stock-btn { font-size: 0.85em; }
/* Metric cards */
div[data-testid="stMetric"] { background: #f8f9fa; border-radius: 8px; padding: 8px 12px; }
</style>
""", unsafe_allow_html=True)


# ── 工具函數 ──────────────────────────────────────────────────────────

def get_cached_stocks() -> set:
    data_dir = ROOT / 'data'
    if not data_dir.exists():
        return set()
    return {f.stem.replace('_cache', '') for f in data_dir.glob('*_cache.csv')}


def cache_age(stock_id: str) -> float:
    """Return cache age in hours, or -1 if no cache."""
    path = ROOT / 'data' / f'{stock_id}_cache.csv'
    if not path.exists():
        return -1
    return (time.time() - path.stat().st_mtime) / 3600


def cache_age_label(hours: float) -> str:
    if hours < 0:
        return "❌ 無資料"
    if hours < 1:
        return "🟢 剛更新"
    if hours < 24:
        return f"🟢 {hours:.0f}h 前"
    if hours < 72:
        return f"🟡 {hours/24:.0f}天前"
    return f"🔴 {hours/24:.0f}天前"


@st.cache_data(ttl=600, show_spinner=False)
def load_stock(stock_id: str, days: int):
    """從本地快取載入 OHLCV 資料。"""
    path = ROOT / 'data' / f'{stock_id}_cache.csv'
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df.tail(days).reset_index(drop=True)


@st.cache_data(ttl=600, show_spinner=False)
def compute_analysis(stock_id: str, days: int, chart_type: str, theme: str):
    """計算指標並建立圖表。"""
    from indicators.combo_indicator import calculate_combo
    from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG, SCREENING_CRITERIA
    from indicators.ut_bot import get_ut_bot_signal, calculate_ut_bot, calculate_ema_ribbon
    from indicators.smc import calculate_smc
    from visualization import plot_stock_with_indicators

    df = load_stock(stock_id, days)
    if df is None or len(df) < 20:
        return None

    # 指標
    combo = calculate_combo(
        df, ut_config=UT_BOT_CONFIG,
        ema_periods=EMA_CONFIG.get('periods', [5, 20, 60, 120, 240]),
        mm_length=1, smc_config=SMC_CONFIG,
    )

    # 分析
    r = {'stock_id': stock_id, 'price': float(df['close'].iloc[-1])}
    r['change'] = float(
        (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    ) if len(df) >= 2 else 0.0

    try:
        ut_df = calculate_ut_bot(df, **{k: UT_BOT_CONFIG[k] for k in ['key_value', 'atr_period', 'use_heikin_ashi']})
        ut_sum = get_ut_bot_signal(ut_df)
        r['ut_signal'] = ut_sum['signal']
        r['ut_trend']  = ut_sum['trend']
        r['ut_stop']   = ut_sum.get('atr_stop')
        r['ut_str']    = ut_sum.get('strength', 0)
    except Exception:
        r['ut_signal'] = 'hold'; r['ut_trend'] = 'N/A'; r['ut_stop'] = None; r['ut_str'] = 0

    try:
        _, smc_sum = calculate_smc(df, **{k: SMC_CONFIG[k] for k in
            ['swing_length', 'internal_length', 'equal_hl_threshold', 'order_block_filter', 'fvg_threshold']})
        r['smc_signal'] = smc_sum.get('signal')
        r['smc_trend']  = smc_sum.get('swing_trend', 'N/A')
        r['smc_str']    = smc_sum.get('signal_strength', 0)
        r['smc_ob']     = smc_sum.get('order_blocks_count', 0)
        r['smc_fvg']    = smc_sum.get('fvg_count', 0)
    except Exception:
        r['smc_signal'] = None; r['smc_trend'] = 'N/A'; r['smc_str'] = 0; r['smc_ob'] = 0; r['smc_fvg'] = 0

    try:
        ema_df = calculate_ema_ribbon(df, periods=EMA_CONFIG['periods'])
        r['ema_bull'] = bool(ema_df['ema_bullish'].iloc[-1]) if 'ema_bullish' in ema_df.columns else False
        r['ema_bear'] = bool(ema_df['ema_bearish'].iloc[-1]) if 'ema_bearish' in ema_df.columns else False
    except Exception:
        r['ema_bull'] = False; r['ema_bear'] = False

    if len(df) >= 20:
        avg_vol = df['volume'].tail(20).mean()
        r['vol_ratio'] = float(df['volume'].iloc[-1] / avg_vol) if avg_vol > 0 else 1.0
        r['vol_spike'] = r['vol_ratio'] > SCREENING_CRITERIA['volume_ratio']
    else:
        r['vol_ratio'] = 1.0; r['vol_spike'] = False

    # 綜合評分
    score = 0
    if r['ut_signal'] == 'buy':         score += 30
    if 'bull' in str(r['smc_signal']): score += 30
    if r['ema_bull']:                   score += 20
    if r['vol_spike']:                  score += 10
    r['score'] = score

    # 圖表
    fig = plot_stock_with_indicators(
        df, stock_id,
        ut_data=combo['ut_data'], smc_data=combo['smc_data'],
        ema_ribbon=combo['ema_ribbon'], maxmin=combo['maxmin'],
        chart_type=chart_type, save_path=None, show=False, theme=theme,
    )
    # Make chart taller
    fig.update_layout(height=700)

    return {'df': df, 'r': r, 'fig': fig}


def run_fetch(stock_ids: list[str]):
    """執行 fetch_and_cache.py"""
    script = str(ROOT / 'fetch_and_cache.py')
    cmd = [sys.executable, script, '--days', '365'] + stock_ids
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    return proc.stdout + proc.stderr


# ── Sidebar: 股票選擇器 ──────────────────────────────────────────────

cached_stocks = get_cached_stocks()

with st.sidebar:
    st.markdown("### 📈 台股監控")

    # 圖表設定（compact）
    col_a, col_b = st.columns(2)
    with col_a:
        chart_type = st.selectbox("圖表", ['candlestick', 'heikin_ashi'],
                                   format_func=lambda x: 'K線' if x == 'candlestick' else 'HA')
    with col_b:
        days = st.selectbox("天數", [60, 90, 120, 180, 245], index=2)

    theme = st.radio("主題", ['light', 'dark'], horizontal=True, label_visibility="collapsed")

    st.divider()

    # 股票分組列表
    if 'selected_stock' not in st.session_state:
        st.session_state.selected_stock = '2330'

    for group_name, stocks in WATCHLIST_GROUPS.items():
        with st.expander(group_name, expanded=(group_name == "AI與半導體核心權值股")):
            for sid, name in stocks:
                has_data = sid in cached_stocks
                icon = "🟢" if has_data else "⚫"
                label = f"{icon} {sid} {name}"
                if st.button(label, key=f"btn_{sid}", use_container_width=True):
                    st.session_state.selected_stock = sid
                    st.rerun()

    st.divider()

    # 自訂代碼
    custom = st.text_input("自訂股票代碼", placeholder="例: 2303")
    if custom.strip():
        st.session_state.selected_stock = custom.strip()

    st.divider()

    # 批次更新
    if st.button("🔄 更新全部資料", use_container_width=True, type="primary"):
        with st.spinner("正在抓取所有股票資料（首次可能需要幾分鐘）..."):
            output = run_fetch(ALL_STOCK_IDS)
        load_stock.clear()
        compute_analysis.clear()
        st.success("資料已更新！")
        with st.expander("抓取詳情"):
            st.code(output)
        st.rerun()

    # 單一股票更新
    if st.button(f"🔄 只更新 {st.session_state.selected_stock}", use_container_width=True):
        with st.spinner(f"正在抓取 {st.session_state.selected_stock}..."):
            output = run_fetch([st.session_state.selected_stock])
        load_stock.clear()
        compute_analysis.clear()
        st.success("完成")
        st.rerun()


# ── 主畫面 ────────────────────────────────────────────────────────────

stock_id = st.session_state.selected_stock
stock_name = STOCK_NAMES.get(stock_id, '')
age_h = cache_age(stock_id)

# Header
hdr1, hdr2 = st.columns([3, 1])
with hdr1:
    st.markdown(f"## {stock_id}　{stock_name}")
with hdr2:
    st.caption(f"資料更新: {cache_age_label(age_h)}")

if age_h < 0:
    st.warning(f"沒有 {stock_id} 的快取資料。請點擊左側「🔄 更新全部資料」或在本機執行：")
    st.code(f"python fetch_and_cache.py {stock_id} --days 365")
    st.stop()

# 計算
with st.spinner("計算指標..."):
    data = compute_analysis(stock_id, days, chart_type, theme)

if data is None:
    st.error(f"資料不足以計算指標（{stock_id} 快取可能損壞）。")
    st.stop()

df  = data['df']
r   = data['r']
fig = data['fig']

# ── 指標卡片 ──────────────────────────────────────────────────────────

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric("收盤價", f"{r['price']:,.1f}", f"{r['change']:+.2f}%")

vol_label = f"{r['vol_ratio']:.1f}x" + (" ⚡" if r['vol_spike'] else "")
c2.metric("量能", vol_label)

ut_icon = {'buy': '🟢', 'sell': '🔴'}.get(r['ut_signal'], '🟡')
c3.metric("UT Bot", f"{ut_icon} {r['ut_signal'].upper()}", r['ut_trend'])

smc_s = str(r['smc_signal'] or 'N/A')
smc_icon = '🟢' if 'bull' in smc_s.lower() else ('🔴' if 'bear' in smc_s.lower() else '⚪')
c4.metric("SMC", f"{smc_icon} {smc_s}", f"{r['smc_str']}/100")

ema_label = '🟢 多頭' if r['ema_bull'] else ('🔴 空頭' if r['ema_bear'] else '🟡 整理')
c5.metric("EMA", ema_label)

verdict = '🟢 強勢' if r['score'] >= 70 else ('🟡 觀望' if r['score'] >= 40 else '🔴 謹慎')
c6.metric("綜合", verdict, f"{r['score']}/100")

# ── K線圖（全寬）─────────────────────────────────────────────────────

st.plotly_chart(fig, use_container_width=True, key="main_chart")

# ── 下方分析面板 ──────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📊 詳細指標", "📋 K線資料", "ℹ️ 說明"])

with tab1:
    p1, p2, p3 = st.columns(3)
    with p1:
        st.markdown("#### 🤖 UT Bot")
        st.write(f"趨勢: **{r['ut_trend'].upper()}**")
        st.write(f"信號: **{r['ut_signal'].upper()}**")
        if r['ut_stop']:
            st.write(f"ATR Stop: **{r['ut_stop']:,.1f}**")
        st.progress(min(r['ut_str'], 100), text=f"強度 {r['ut_str']}/100")

    with p2:
        st.markdown("#### 📐 SMC 智慧資金")
        st.write(f"趨勢: **{r['smc_trend']}**")
        st.write(f"信號: **{r['smc_signal'] or 'N/A'}**")
        st.write(f"Order Blocks: **{r['smc_ob']}** / FVG: **{r['smc_fvg']}**")
        st.progress(min(r['smc_str'], 100), text=f"強度 {r['smc_str']}/100")

    with p3:
        st.markdown("#### 📊 量能 & 趨勢")
        st.write(f"成交量倍數: **{r['vol_ratio']:.2f}x**")
        st.write(f"{'⚡ 放量突破！' if r['vol_spike'] else '正常量能'}")
        st.write(f"EMA: **{'✅ 多頭排列' if r['ema_bull'] else ('🔴 空頭排列' if r['ema_bear'] else '⚠️ 混合整理')}**")
        st.divider()
        st.write(f"**綜合評分: {r['score']}/100**")

with tab2:
    show_df = df.tail(30).copy()
    show_df['date'] = pd.to_datetime(show_df['date']).dt.strftime('%Y-%m-%d')
    show_df['漲跌%'] = show_df['close'].pct_change().mul(100).round(2)
    show_df = show_df.rename(columns={
        'date': '日期', 'open': '開盤', 'high': '最高',
        'low': '最低', 'close': '收盤', 'volume': '成交量'
    })
    st.dataframe(
        show_df[['日期', '開盤', '最高', '最低', '收盤', '成交量', '漲跌%']].iloc[::-1],
        use_container_width=True, hide_index=True,
    )

with tab3:
    st.markdown(f"""
### 使用說明

**首次使用** — 在本機執行以下指令下載全部股票 1 年歷史資料：
```bash
cd tw_stock_screener
python fetch_and_cache.py --all --days 365
```

**日常更新** — 兩種方式：
1. 點擊左側「🔄 更新全部資料」按鈕
2. GitHub Actions 每日 14:30 TST 自動更新（需先合併至 main）

**資料來源**: TWSE → FinMind → yfinance（自動切換）

**指標說明**:
- **UT Bot**: 基於 ATR 的趨勢追蹤 + Heikin Ashi
- **SMC**: 智慧資金概念（BOS/CHoCH/Order Block/FVG）
- **EMA Ribbon**: 5/20/60/120/240 均線排列
- **綜合評分**: UT Bot(30) + SMC(30) + EMA(20) + 量能(10) = 最高90分
    """)
