#!/usr/bin/env python3
"""
台股篩選系統 - TradingView 風格 Web Dashboard
==============================================
執行方式:
    cd tw_stock_screener
    streamlit run app.py

首次使用：
    python fetch_and_cache.py --days 365
"""

import os, sys, time, subprocess, logging
from pathlib import Path

import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

# ── 觀察清單（分組）────────────────────────────────────────────────────

WATCHLIST_GROUPS = {
    "AI與半導體核心權值股": [
        ('2330','台積電'),('2317','鴻海'),('2454','聯發科'),('2382','廣達'),
        ('3231','緯創'),('2376','技嘉'),('2377','微星'),('3711','日月光投控'),
        ('3661','世芯-KY'),('3443','創意'),
    ],
    "網通訊號與高速傳輸": [
        ('2345','智邦'),('3596','智易'),('3034','聯詠'),('4966','譜瑞-KY'),
        ('5269','祥碩'),('2379','瑞昱'),('3533','嘉澤'),('3105','穩懋'),
        ('8086','宏捷科'),('2455','全新'),
    ],
    "先進封裝材料與散熱": [
        ('2383','台光電'),('6274','台燿'),('6213','聯茂'),('2368','金像電'),
        ('3653','健策'),('2308','台達電'),('5274','信驊'),('6187','萬潤'),
        ('3680','家登'),('6223','旺矽'),
    ],
    "重電綠能與航運": [
        ('1519','華城'),('1513','中興電'),('1504','士電'),('1514','亞力'),
        ('6806','森崴能源'),('2603','長榮'),('2609','陽明'),
    ],
    "矽光子 / CPO": [('3081','聯亞'),('3363','上詮'),('3163','波若威')],
    "液冷散熱": [('3324','雙鴻'),('3017','奇鋐'),('8996','高力')],
    "先進封裝設備": [('3131','弘塑'),('3583','辛耘'),('8027','鈦昇')],
    "其他": [('2337','旺宏'),('00631L','元大台灣50正2')],
}

STOCK_NAMES = {sid: name for g in WATCHLIST_GROUPS.values() for sid, name in g}
ALL_STOCK_IDS = list(STOCK_NAMES.keys())

# ── 頁面設定 ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="台股 TradingView",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container { padding-top: 1.5rem; padding-bottom: 0; }
section[data-testid="stSidebar"] > div { padding-top: 0.8rem; }
div[data-testid="stMetric"] {
    background: #f0f2f6; border-radius: 8px; padding: 6px 10px;
}
div[data-testid="stMetric"] label {
    font-size: 0.8rem !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.1rem !important;
    white-space: nowrap;
    overflow: visible;
}
</style>
""", unsafe_allow_html=True)


# ── 工具函數 ──────────────────────────────────────────────────────────

def cached_stocks() -> set:
    d = ROOT / 'data'
    return {f.stem.replace('_cache','') for f in d.glob('*_cache.csv')} if d.exists() else set()

def cache_age_h(sid: str) -> float:
    p = ROOT / 'data' / f'{sid}_cache.csv'
    return (time.time() - p.stat().st_mtime) / 3600 if p.exists() else -1

def age_label(h: float) -> str:
    if h < 0:   return "❌ 無資料"
    if h < 1:   return "🟢 剛更新"
    if h < 24:  return f"🟢 {h:.0f}h 前"
    if h < 72:  return f"🟡 {h/24:.1f}天前"
    return f"🔴 {h/24:.0f}天前"

# Step 1 — cached: load CSV + compute all indicators (slow once, then instant)
@st.cache_data(ttl=600, show_spinner=False)
def compute_indicators(stock_id: str, days: int):
    from indicators.combo_indicator import calculate_combo
    from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG, SCREENING_CRITERIA
    from indicators.ut_bot import get_ut_bot_signal, calculate_ut_bot, calculate_ema_ribbon
    from indicators.smc import calculate_smc

    p = ROOT / 'data' / f'{stock_id}_cache.csv'
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').tail(days).reset_index(drop=True)
    if len(df) < 20:
        return None

    combo = calculate_combo(df, ut_config=UT_BOT_CONFIG,
        ema_periods=EMA_CONFIG.get('periods',[5,20,60,120,240]),
        mm_length=1, smc_config=SMC_CONFIG)

    # Analysis summary
    r = {'price': float(df['close'].iloc[-1])}
    r['change'] = float((df['close'].iloc[-1]-df['close'].iloc[-2])/df['close'].iloc[-2]*100) if len(df)>=2 else 0.0

    try:
        ut_df = calculate_ut_bot(df, key_value=UT_BOT_CONFIG['key_value'],
            atr_period=UT_BOT_CONFIG['atr_period'], use_heikin_ashi=UT_BOT_CONFIG['use_heikin_ashi'])
        ut = get_ut_bot_signal(ut_df)
        r['ut_signal']=ut['signal']; r['ut_trend']=ut['trend']
        r['ut_stop']=ut.get('atr_stop'); r['ut_str']=ut.get('strength',0)
    except Exception:
        r['ut_signal']='hold'; r['ut_trend']='N/A'; r['ut_stop']=None; r['ut_str']=0

    try:
        smc_df, sm = calculate_smc(df, swing_length=SMC_CONFIG['swing_length'],
            internal_length=SMC_CONFIG['internal_length'],
            equal_hl_threshold=SMC_CONFIG['equal_hl_threshold'],
            order_block_filter=SMC_CONFIG['order_block_filter'],
            fvg_threshold=SMC_CONFIG['fvg_threshold'])
        # Check both swing and internal signals (internal are more frequent)
        smc_signal = sm.get('signal')
        smc_str = sm.get('signal_strength', 0)
        if not smc_signal:
            # Fall back to internal signals if no swing signal in last 10 bars
            lookback = min(20, len(smc_df))
            for i in range(len(smc_df) - 1, max(0, len(smc_df) - lookback) - 1, -1):
                row = smc_df.iloc[i]
                if row.get('internal_choch_bull', False):
                    smc_signal = 'CHoCH_bull'; smc_str = 85; break
                if row.get('internal_choch_bear', False):
                    smc_signal = 'CHoCH_bear'; smc_str = 85; break
                if row.get('internal_bos_bull', False):
                    smc_signal = 'BOS_bull'; smc_str = 65; break
                if row.get('internal_bos_bear', False):
                    smc_signal = 'BOS_bear'; smc_str = 65; break
        r['smc_signal'] = smc_signal
        r['smc_trend'] = sm.get('swing_trend', sm.get('internal_trend', 'N/A'))
        r['smc_str'] = smc_str
        r['smc_ob'] = sm.get('order_blocks_count', 0); r['smc_fvg'] = sm.get('fvg_count', 0)
    except Exception:
        r['smc_signal']=None; r['smc_trend']='N/A'; r['smc_str']=0; r['smc_ob']=0; r['smc_fvg']=0

    try:
        ema_df = calculate_ema_ribbon(df, periods=EMA_CONFIG['periods'])
        r['ema_bull'] = bool(ema_df['ema_bullish'].iloc[-1]) if 'ema_bullish' in ema_df.columns else False
        r['ema_bear'] = bool(ema_df['ema_bearish'].iloc[-1]) if 'ema_bearish' in ema_df.columns else False
    except Exception:
        r['ema_bull']=False; r['ema_bear']=False

    if len(df)>=20:
        avg = df['volume'].tail(20).mean()
        r['vol_ratio'] = float(df['volume'].iloc[-1]/avg) if avg>0 else 1.0
        r['vol_spike'] = r['vol_ratio'] > SCREENING_CRITERIA['volume_ratio']
    else:
        r['vol_ratio']=1.0; r['vol_spike']=False

    s = 0
    if r['ut_signal']=='buy':         s+=30
    if 'bull' in str(r['smc_signal']): s+=30
    if r['ema_bull']:                  s+=20
    if r['vol_spike']:                 s+=10
    r['score'] = s

    return {'df': df, 'combo': combo, 'r': r}


# Step 2 — NOT cached: build Plotly figure from computed data + current toggle selections
def build_chart(df, stock_id, combo, chart_type, theme, show_flags):
    from visualization import plot_stock_with_indicators

    c = combo

    # Filter ut_data based on toggles
    ut = None
    if show_flags['ut_stop'] or show_flags['ut_signals']:
        ut = {
            'atr_trailing_stop': c['ut_data'].get('atr_trailing_stop') if show_flags['ut_stop'] else None,
            'ut_buy':  c['ut_data'].get('ut_buy')  if show_flags['ut_signals'] else None,
            'ut_sell': c['ut_data'].get('ut_sell') if show_flags['ut_signals'] else None,
        }

    # Filter smc_data based on toggles
    smc = None
    if show_flags['smc_struct'] or show_flags['ob'] or show_flags['fvg']:
        smc = {
            'bos_bull':    c['smc_data'].get('bos_bull')    if show_flags['smc_struct'] else None,
            'bos_bear':    c['smc_data'].get('bos_bear')    if show_flags['smc_struct'] else None,
            'choch_bull':  c['smc_data'].get('choch_bull')  if show_flags['smc_struct'] else None,
            'choch_bear':  c['smc_data'].get('choch_bear')  if show_flags['smc_struct'] else None,
            'order_blocks':c['smc_data'].get('order_blocks')if show_flags['ob']         else None,
            'fvg':         c['smc_data'].get('fvg')         if show_flags['fvg']        else None,
        }

    ema = c['ema_ribbon'] if show_flags['ema'] else None
    mm  = c['maxmin']     if show_flags['maxmin'] else None

    fig = plot_stock_with_indicators(
        df, stock_id,
        ut_data=ut, smc_data=smc, ema_ribbon=ema, maxmin=mm,
        chart_type=chart_type, save_path=None, show=False, theme=theme,
    )
    fig.update_layout(height=680, margin=dict(l=0, r=0, t=30, b=0))
    return fig

def run_fetch(ids):
    proc = subprocess.run(
        [sys.executable, str(ROOT/'fetch_and_cache.py'), '--days','365'] + ids,
        capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    return proc.stdout + proc.stderr


# ── Sidebar ───────────────────────────────────────────────────────────

have_cache = cached_stocks()

with st.sidebar:
    st.markdown("### 📈 台股監控")

    # ── 圖表基本設定 ──────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        chart_type = st.selectbox("圖表",['candlestick','heikin_ashi'],
            format_func=lambda x: 'K線' if x=='candlestick' else 'HA')
    with c2:
        days = st.selectbox("天數",[60,90,120,180,245],index=2)
    theme = st.radio("主題",['light','dark'],horizontal=True,label_visibility="collapsed")

    st.divider()

    # ── 指標顯示控制 ──────────────────────────────────────
    st.markdown("**指標選擇**")
    fl = {}  # show_flags dict

    col_l, col_r = st.columns(2)
    with col_l:
        fl['ut_stop']    = st.checkbox("UT Bot 止損線",  value=True)
        fl['smc_struct'] = st.checkbox("SMC BOS/CHoCH", value=True)
        fl['fvg']        = st.checkbox("FVG 缺口",       value=False)
    with col_r:
        fl['ut_signals'] = st.checkbox("UT Bot 信號",   value=True)
        fl['ob']         = st.checkbox("Order Blocks",  value=True)
        fl['ema']        = st.checkbox("EMA Ribbon",    value=True)

    fl['maxmin'] = st.checkbox("MaxMin 區間", value=False)

    st.divider()

    # ── 股票清單（分組）──────────────────────────────────
    if 'selected' not in st.session_state:
        st.session_state.selected = '2330'

    for grp, stocks in WATCHLIST_GROUPS.items():
        with st.expander(grp, expanded=(grp=="AI與半導體核心權值股")):
            for sid, name in stocks:
                icon = "🟢" if sid in have_cache else "⚫"
                if st.button(f"{icon} {sid} {name}", key=f"b_{sid}", use_container_width=True):
                    st.session_state.selected = sid
                    st.rerun()

    custom = st.text_input("自訂代碼", placeholder="例: 2303")
    if custom.strip():
        st.session_state.selected = custom.strip()

    st.divider()

    if st.button("🔄 更新全部", use_container_width=True, type="primary"):
        with st.spinner("抓取全部 48 支股票資料中…"):
            out = run_fetch(ALL_STOCK_IDS)
        compute_indicators.clear()
        st.success("完成！")
        with st.expander("詳情"):
            st.code(out)
        st.rerun()

    sid_now = st.session_state.selected
    if st.button(f"🔄 只更新 {sid_now}", use_container_width=True):
        with st.spinner(f"抓取 {sid_now}…"):
            out = run_fetch([sid_now])
        compute_indicators.clear()
        st.rerun()


# ── 主畫面 ────────────────────────────────────────────────────────────

sid = st.session_state.selected
name = STOCK_NAMES.get(sid, '')
age  = cache_age_h(sid)

h1, h2 = st.columns([5, 1])
with h1:
    st.markdown(f"### {sid}　{name}")
with h2:
    st.caption(age_label(age))

if age < 0:
    st.warning(f"沒有 {sid} 的快取資料。請執行：")
    st.code(f"python fetch_and_cache.py {sid} --days 365")
    st.stop()

with st.spinner("計算指標中…"):
    data = compute_indicators(sid, days)

if data is None:
    st.error("資料不足，請重新抓取。")
    st.stop()

df    = data['df']
combo = data['combo']
r     = data['r']

# ── 指標卡片 ──────────────────────────────────────────────────────────

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("收盤", f"{r['price']:,.1f}", f"{r['change']:+.2f}%")
m2.metric("量能", f"{r['vol_ratio']:.1f}x", "放量" if r['vol_spike'] else "正常")

ut_ic = {'buy': '🟢', 'sell': '🔴'}.get(r['ut_signal'], '🟡')
m3.metric("UT Bot", f"{ut_ic} {r['ut_signal'].upper()}", r['ut_trend'])

# SMC: show short readable signal
smc_raw = str(r['smc_signal'] or '')
if 'CHoCH' in smc_raw and 'bull' in smc_raw:
    smc_label = '🟢 CHoCH多'
elif 'CHoCH' in smc_raw and 'bear' in smc_raw:
    smc_label = '🔴 CHoCH空'
elif 'BOS' in smc_raw and 'bull' in smc_raw:
    smc_label = '🟢 BOS多'
elif 'BOS' in smc_raw and 'bear' in smc_raw:
    smc_label = '🔴 BOS空'
else:
    smc_label = '⚪ --'
m4.metric("SMC", smc_label, f"{r['smc_str']}/100")

ema_l = '🟢 多頭' if r['ema_bull'] else ('🔴 空頭' if r['ema_bear'] else '🟡 整理')
m5.metric("EMA", ema_l)

vrd = '🟢 強勢' if r['score'] >= 70 else ('🟡 觀望' if r['score'] >= 40 else '🔴 謹慎')
m6.metric("綜合", vrd, f"{r['score']}/100")

# ── 圖表（指標選擇即時生效）──────────────────────────────────────────

fig = build_chart(df, sid, combo, chart_type, theme, fl)
st.plotly_chart(fig, use_container_width=True, key="chart")

# ── 下方 Tabs ─────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["📊 詳細指標", "📋 K線資料", "ℹ️ 說明"])

with tab1:
    p1, p2, p3 = st.columns(3)
    with p1:
        st.markdown("#### 🤖 UT Bot")
        st.write(f"趨勢: **{r['ut_trend'].upper()}**")
        st.write(f"信號: **{r['ut_signal'].upper()}**")
        if r['ut_stop']:
            st.write(f"ATR Stop: **{r['ut_stop']:,.1f}**")
        st.progress(min(r['ut_str'],100), text=f"強度 {r['ut_str']}/100")
    with p2:
        st.markdown("#### 📐 SMC")
        st.write(f"趨勢: **{r['smc_trend']}**")
        st.write(f"信號: **{r['smc_signal'] or 'N/A'}**")
        st.write(f"OB: **{r['smc_ob']}**　FVG: **{r['smc_fvg']}**")
        st.progress(min(r['smc_str'],100), text=f"強度 {r['smc_str']}/100")
    with p3:
        st.markdown("#### 📊 量能 & EMA")
        st.write(f"成交量倍數: **{r['vol_ratio']:.2f}x**")
        if r['vol_spike']:
            st.write("⚡ **放量突破！**")
        ema_desc = '✅ 多頭排列' if r['ema_bull'] else ('🔴 空頭排列' if r['ema_bear'] else '⚠️ 整理中')
        st.write(f"EMA: **{ema_desc}**")
        st.divider()
        st.write(f"**綜合評分: {r['score']}/100**　{vrd}")

with tab2:
    disp = df.tail(30).copy()
    disp['date'] = pd.to_datetime(disp['date']).dt.strftime('%Y-%m-%d')
    disp['漲跌%'] = disp['close'].pct_change().mul(100).round(2)
    disp = disp.rename(columns={'date':'日期','open':'開盤','high':'最高',
                                 'low':'最低','close':'收盤','volume':'成交量'})
    st.dataframe(disp[['日期','開盤','最高','最低','收盤','成交量','漲跌%']].iloc[::-1],
                 use_container_width=True, hide_index=True)

with tab3:
    st.markdown(f"""
### 指標說明

| 指標 | 說明 |
|------|------|
| **UT Bot 止損線** | ATR 動態止損線（紅/綠），穿越時反轉 |
| **UT Bot 信號** | 買進(▲綠) / 賣出(▼紅) 箭頭 |
| **SMC BOS/CHoCH** | Break of Structure / Change of Character 結構突破標記 |
| **Order Blocks** | 機構買賣區塊（多方=綠框/空方=紅框） |
| **FVG 缺口** | Fair Value Gap 未填補缺口（公允價值缺口） |
| **EMA Ribbon** | 5/20/60/120/240 均線排列 |
| **MaxMin 區間** | 近期高低點通道 |

### 資料更新
```bash
# 更新全部 48 支股票（約 2-3 分鐘）
python fetch_and_cache.py

# 只更新單一股票
python fetch_and_cache.py 2330
```
GitHub Actions 每日 14:30 TST 自動更新後推送至倉庫。
    """)
