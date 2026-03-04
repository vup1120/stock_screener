#!/usr/bin/env python3
"""
股票 2330 (台積電 TSMC) 視覺化示範腳本
======================================

示範如何使用本系統對台股 2330（台積電）進行完整的技術分析並產生互動式圖表。

資料來源優先順序（完全自動，無需手動設定）：
  1. 本地 CSV 快取 (data/2330_cache.csv) — 隨時可用，即使在受限環境中
  2. 證交所 TWSE API     — 需連線 www.twse.com.tw
  3. FinMind API         — 需連線 api.finmindtrade.com
  4. Yahoo Finance       — 需連線 finance.yahoo.com

在本機有網路時，執行 fetch_and_cache.py 可更新快取到最新資料。

執行方式:
    python demo_2330.py

輸出:
    - output/2330_demo_candlestick.html  (K 線圖 + 指標)
    - output/2330_demo_heikin_ashi.html  (Heikin Ashi + 指標)
    - 終端機詳細分析報告
"""

import os
import sys

# 確保在正確的目錄下執行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STOCK_ID = "2330"
STOCK_NAME = "台積電 TSMC"
DAYS = 120


def print_header():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║        股票篩選系統示範 - 2330 台積電 (TSMC)                     ║
║        UT Bot + SMC + EMA Ribbon + 籌碼分析                      ║
╚══════════════════════════════════════════════════════════════════╝
""")


def fetch_data():
    print(f"📡 Step 1: 載入 {STOCK_ID} 近 {DAYS} 交易日資料...")

    import logging
    logging.disable(logging.CRITICAL)

    df = None
    source_used = None

    # ── 1. 嘗試本地快取 ──────────────────────────────────────────────
    try:
        from data_fetcher import LocalCSVDataFetcher
        cache = LocalCSVDataFetcher()
        cached = cache.load(STOCK_ID, DAYS)
        if cached is not None and len(cached) >= 20:
            df = cached
            import os as _os
            cache_path = cache.cache_path(STOCK_ID)
            import time as _time
            age_h = (_time.time() - _os.path.getmtime(cache_path)) / 3600
            age_str = f"{age_h:.0f}h 前" if age_h < 48 else f"{age_h/24:.0f} 天前"
            source_used = f"本地快取（更新於 {age_str}）"
    except Exception:
        pass

    # ── 2. 嘗試外部 API（可能在受限環境被封鎖）──────────────────────
    if df is None or len(df) < 20:
        try:
            from data_fetcher import UnifiedDataFetcher
            fetcher = UnifiedDataFetcher(tw_source='twse')
            result = fetcher.get_tw_stock_data(STOCK_ID, days=DAYS)
            if result is not None and len(result) >= 20:
                df = result
                source_used = "即時 API（已更新本地快取）"
        except Exception:
            pass

    logging.disable(logging.NOTSET)

    if df is None or len(df) < 20:
        print("   ❌ 無法載入資料（本地快取不存在且 API 無法連線）")
        print("   💡 請先在本機執行: python fetch_and_cache.py")
        sys.exit(1)

    print(f"   ✅ 共 {len(df)} 根 K 線  （來源: {source_used}）")
    d0 = df['date'].iloc[0]
    d1 = df['date'].iloc[-1]
    fmt = lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
    print(f"   📅 日期範圍: {fmt(d0)} ~ {fmt(d1)}")
    print(f"   💰 最新收盤: {df['close'].iloc[-1]:.1f} 元")
    if len(df) >= 2:
        pct = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
        arrow = "▲" if pct >= 0 else "▼"
        print(f"   {arrow} 漲跌幅: {pct:+.2f}%")
    return df


def compute_indicators(df):
    print("\n🔧 Step 2: 計算 Combo 指標 (UT Bot + EMA Ribbon + MaxMin + SMC)...")
    from indicators.combo_indicator import calculate_combo
    from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG

    combo = calculate_combo(
        df,
        ut_config=UT_BOT_CONFIG,
        ema_periods=EMA_CONFIG.get('periods', [5, 20, 60, 120, 240]),
        mm_length=1,
        smc_config=SMC_CONFIG,
    )
    print("   ✅ 指標計算完成")
    return combo


def compute_screener_analysis(df, combo):
    print("\n🔍 Step 3: 執行完整分析...")
    from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG, SCREENING_CRITERIA
    from indicators.ut_bot import get_ut_bot_signal, calculate_ut_bot, calculate_ema_ribbon
    from indicators.smc import calculate_smc

    result = {'stock_id': STOCK_ID}
    result['price'] = float(df['close'].iloc[-1])
    result['price_change'] = float(
        (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    ) if len(df) >= 2 else 0.0

    # UT Bot
    try:
        ut_df = calculate_ut_bot(
            df,
            key_value=UT_BOT_CONFIG['key_value'],
            atr_period=UT_BOT_CONFIG['atr_period'],
            use_heikin_ashi=UT_BOT_CONFIG['use_heikin_ashi'],
        )
        ut_summary = get_ut_bot_signal(ut_df)
        result['ut_signal'] = ut_summary['signal']
        result['ut_trend']  = ut_summary['trend']
        result['ut_summary'] = ut_summary
    except Exception:
        result['ut_signal'] = 'hold'
        result['ut_trend']  = 'bullish'
        result['ut_summary'] = {}

    # SMC
    try:
        smc_df, smc_summary = calculate_smc(
            df,
            swing_length=SMC_CONFIG['swing_length'],
            internal_length=SMC_CONFIG['internal_length'],
            equal_hl_threshold=SMC_CONFIG['equal_hl_threshold'],
            order_block_filter=SMC_CONFIG['order_block_filter'],
            fvg_threshold=SMC_CONFIG['fvg_threshold'],
        )
        result['smc_signal']   = smc_summary.get('signal')
        result['smc_trend']    = smc_summary.get('swing_trend')
        result['smc_strength'] = smc_summary.get('signal_strength', 0)
        result['smc_summary']  = smc_summary
    except Exception:
        result['smc_signal']   = None
        result['smc_trend']    = 'N/A'
        result['smc_strength'] = 0
        result['smc_summary']  = {}

    # EMA Ribbon
    try:
        ema_df = calculate_ema_ribbon(df, periods=EMA_CONFIG['periods'])
        result['ema_bullish'] = bool(ema_df['ema_bullish'].iloc[-1]) if 'ema_bullish' in ema_df.columns else False
        result['ema_bearish'] = bool(ema_df['ema_bearish'].iloc[-1]) if 'ema_bearish' in ema_df.columns else False
    except Exception:
        result['ema_bullish'] = False
        result['ema_bearish'] = False

    # Volume analysis
    if len(df) >= 20:
        avg_vol = df['volume'].tail(20).mean()
        cur_vol = df['volume'].iloc[-1]
        result['volume_ratio'] = float(cur_vol / avg_vol) if avg_vol > 0 else 1.0
        result['volume_spike'] = result['volume_ratio'] > SCREENING_CRITERIA['volume_ratio']

    result['chip_signal']  = 'no_data'
    result['chip_summary'] = {}

    return result


def print_analysis_report(result, combo):
    print("\n" + "=" * 66)
    print(f"  📊 {STOCK_ID} {STOCK_NAME} - 完整分析報告")
    print("=" * 66)

    price  = result.get('price', 0)
    change = result.get('price_change', 0)
    arrow  = "▲" if change >= 0 else "▼"
    color  = "漲" if change >= 0 else "跌"
    print(f"\n  💰 最新價格:  {price:.1f} 元  {arrow} {abs(change):.2f}% ({color})")

    # UT Bot
    print(f"\n  🤖 UT Bot 指標:")
    print(f"     趨勢方向: {result.get('ut_trend', 'N/A').upper()}")
    print(f"     交易信號: {result.get('ut_signal', 'N/A').upper()}")
    ut_sum = result.get('ut_summary', {})
    if ut_sum.get('atr_stop'):
        print(f"     ATR Stop:  {ut_sum['atr_stop']:.1f} 元")
    if ut_sum.get('strength'):
        print(f"     強度分數:  {ut_sum['strength']}/100")

    # SMC
    print(f"\n  📐 SMC 智慧資金概念:")
    print(f"     主趨勢:   {result.get('smc_trend', 'N/A')}")
    print(f"     結構信號: {result.get('smc_signal', 'N/A')}")
    print(f"     信號強度: {result.get('smc_strength', 0)}/100")
    smc_sum = combo.get('smc_summary', {})
    if smc_sum.get('order_blocks_count'):
        print(f"     Order Blocks: {smc_sum['order_blocks_count']} 個")
    if smc_sum.get('fvg_count'):
        print(f"     Fair Value Gaps: {smc_sum['fvg_count']} 個")

    # EMA Ribbon
    print(f"\n  📈 EMA Ribbon 趨勢:")
    ema_bull = result.get('ema_bullish', False)
    ema_bear = result.get('ema_bearish', False)
    if ema_bull:
        print(f"     狀態: ✅ 多頭排列（EMA 由上往下: 5>20>60>120>240）")
    elif ema_bear:
        print(f"     狀態: 🔴 空頭排列（EMA 由下往上: 5<20<60<120<240）")
    else:
        print(f"     狀態: ⚠️  混合排列（整理中）")

    # Volume
    vol_ratio = result.get('volume_ratio', 1)
    spike     = result.get('volume_spike', False)
    print(f"\n  📊 成交量分析:")
    print(f"     成交量倍數: {vol_ratio:.2f}x（相對20日均量）")
    print(f"     ⚡ 成交量放大！" if spike else "     成交量正常")

    # 綜合判斷
    print(f"\n  🎯 綜合判斷:")
    score   = 0
    signals = []
    if result.get('ut_signal') == 'buy':
        score += 30; signals.append("UT Bot 買進信號")
    if result.get('smc_signal') in ['CHoCH_bull', 'BOS_bull']:
        score += 30; signals.append(f"SMC {result.get('smc_signal')}")
    if ema_bull:
        score += 20; signals.append("EMA 多頭排列")
    if spike:
        score += 10; signals.append("量價齊揚")

    if score >= 70:
        verdict = "🟢 多方強勢 - 可積極布局"
    elif score >= 40:
        verdict = "🟡 偏多觀望 - 等待更明確信號"
    else:
        verdict = "🔴 偏空謹慎 - 暫時觀望"

    print(f"     綜合評分: {score}/100")
    print(f"     研判: {verdict}")
    if signals:
        print(f"     正面信號: {' | '.join(signals)}")
    print("=" * 66)


def generate_charts(df, combo):
    print("\n📈 Step 4: 產生互動式圖表...")
    from visualization import plot_stock_with_indicators, PLOTLY_AVAILABLE

    if not PLOTLY_AVAILABLE:
        print("   ❌ Plotly 未安裝，無法產生互動式圖表")
        return

    os.makedirs('output', exist_ok=True)

    ut_data    = combo['ut_data']
    smc_data   = combo['smc_data']
    ema_ribbon = combo['ema_ribbon']
    maxmin     = combo['maxmin']

    out1 = f"output/{STOCK_ID}_demo_candlestick.html"
    print(f"   🖼  K 線圖 + Combo 指標 → {out1}")
    plot_stock_with_indicators(
        df, STOCK_ID,
        ut_data=ut_data, smc_data=smc_data,
        ema_ribbon=ema_ribbon, maxmin=maxmin,
        chart_type='candlestick',
        save_path=out1, show=False, theme='light',
    )

    out2 = f"output/{STOCK_ID}_demo_heikin_ashi.html"
    print(f"   🖼  Heikin Ashi + Combo 指標 → {out2}")
    plot_stock_with_indicators(
        df, STOCK_ID,
        ut_data=ut_data, smc_data=smc_data,
        ema_ribbon=ema_ribbon, maxmin=maxmin,
        chart_type='heikin_ashi',
        save_path=out2, show=False, theme='light',
    )

    print(f"\n  ✅ 圖表已儲存至 output/ 目錄")
    print(f"     K 線圖:       {out1}")
    print(f"     Heikin Ashi:  {out2}")
    print(f"\n  💡 用瀏覽器開啟 HTML 檔案即可查看互動式圖表！")


def main():
    print_header()

    df    = fetch_data()
    combo = compute_indicators(df)
    result = compute_screener_analysis(df, combo)

    if result:
        print_analysis_report(result, combo)

    generate_charts(df, combo)

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  🎉 示範完成！                                                    ║
║                                                                  ║
║  📁 圖表位置:                                                    ║
║     output/{STOCK_ID}_demo_candlestick.html                      ║
║     output/{STOCK_ID}_demo_heikin_ashi.html                      ║
║                                                                  ║
║  💡 更新資料（需網路）:                                           ║
║     python fetch_and_cache.py                                    ║
║                                                                  ║
║  💡 其他使用方式:                                                 ║
║     python chart_viewer.py {STOCK_ID} -i          # 指標圖表      ║
║     python chart_viewer.py {STOCK_ID} --ha -i     # HA + 指標    ║
║     python main.py --stock {STOCK_ID} --verbose   # 完整分析      ║
╚══════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
