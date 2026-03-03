#!/usr/bin/env python3
"""
股票 2336 視覺化示範腳本
=======================

示範如何使用本系統對台股 2336（仁寶電腦）進行完整的技術分析並產生互動式圖表。

執行方式:
    python demo_2336.py

輸出:
    - output/2336_demo_candlestick.html  (K 線圖 + 指標)
    - output/2336_demo_heikin_ashi.html  (Heikin Ashi + 指標)
    - 終端機詳細分析報告
"""

import os
import sys

# 確保在正確的目錄下執行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STOCK_ID = "2336"
DAYS = 120


def print_header():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║        股票篩選系統示範 - 2336 仁寶電腦                          ║
║        UT Bot + SMC + EMA Ribbon + 籌碼分析                      ║
╚══════════════════════════════════════════════════════════════════╝
""")


def _generate_mock_data_2336():
    """
    Generate realistic mock OHLCV data for stock 2336 (仁寶電腦 Compal Electronics).
    Price range based on 2336's typical trading range (~25-40 TWD).
    Simulates a realistic trend: consolidation → breakout → pullback pattern.
    """
    import numpy as np
    import pandas as pd

    np.random.seed(2336)
    n = DAYS

    # Realistic pattern for 2336 (仁寶電腦 Compal Electronics):
    # Phase 1 (30 days): Downtrend  36 → 30 (bearish BOS)
    # Phase 2 (20 days): Consolidation / accumulation  ~30
    # Phase 3 (30 days): First leg up  30 → 35 (CHoCH bullish)
    # Phase 4 (15 days): Pullback  35 → 32 (retest OB/FVG zone)
    # Phase 5 (25 days): Second leg up + continuation  32 → 38 (BOS bullish)

    seg1 = np.linspace(36.0, 30.5, 30) + np.random.randn(30) * 0.35
    seg2 = 30.5 + np.random.randn(20) * 0.40
    seg3 = np.linspace(30.5, 35.0, 30) + np.random.randn(30) * 0.30
    seg4 = np.linspace(35.0, 32.0, 15) + np.random.randn(15) * 0.25
    seg5 = np.linspace(32.0, 37.5, 25) + np.random.randn(25) * 0.35

    close_prices = np.concatenate([seg1, seg2, seg3, seg4, seg5])
    close_prices = np.clip(close_prices, 27.0, 42.0)

    # Generate OHLCV from close
    volatility = 0.008  # ~0.8% daily volatility
    high = close_prices * (1 + np.abs(np.random.randn(n)) * volatility + 0.004)
    low = close_prices * (1 - np.abs(np.random.randn(n)) * volatility - 0.004)
    open_prices = np.roll(close_prices, 1)
    open_prices[0] = close_prices[0]
    open_prices += np.random.randn(n) * 0.12

    # Volume: higher during trend moves, lower in consolidation
    base_vol = 50000
    vol_multiplier = np.ones(n)
    vol_multiplier[0:30] = 1.3    # downtrend: moderate volume
    vol_multiplier[30:50] = 0.65  # consolidation: low volume
    vol_multiplier[50:80] = 1.8   # first breakout: elevated volume
    vol_multiplier[80:95] = 1.0   # pullback: normal volume
    vol_multiplier[95:] = 2.1     # second leg: strong volume (confirm BOS)
    volume = (base_vol * vol_multiplier * (1 + np.abs(np.random.randn(n)) * 0.45)).astype(int)
    volume = volume * 1000  # in shares

    # Business day dates ending today
    today = pd.Timestamp('2026-03-03')
    dates = pd.bdate_range(end=today, periods=n)

    df = pd.DataFrame({
        'date': dates,
        'open': np.round(open_prices, 2),
        'high': np.round(np.maximum(high, np.maximum(open_prices, close_prices)), 2),
        'low': np.round(np.minimum(low, np.minimum(open_prices, close_prices)), 2),
        'close': np.round(close_prices, 2),
        'volume': volume,
    })

    return df


def fetch_data():
    print(f"📡 Step 1: 載入 {STOCK_ID} 近 {DAYS} 交易日資料...")

    # Try real data sources first
    df = None
    try:
        from data_fetcher import UnifiedDataFetcher
        import logging
        logging.disable(logging.CRITICAL)  # suppress connection error noise
        fetcher = UnifiedDataFetcher(tw_source='twse')
        df = fetcher.get_tw_stock_data(STOCK_ID, days=DAYS)
        logging.disable(logging.NOTSET)
    except Exception:
        pass

    if df is None or len(df) < 20:
        print(f"   ⚠️  無法連線到資料來源（網路限制），改用模擬資料示範")
        print(f"   📝 使用仁寶電腦(2336)歷史真實價格範圍生成模擬K線...")
        df = _generate_mock_data_2336()
        print(f"   ℹ️  注意：此為示範用模擬資料，實際使用時請確保網路連線")

    print(f"   ✅ 共 {len(df)} 根 K 線")
    d0 = df['date'].iloc[0]
    d1 = df['date'].iloc[-1]
    fmt = lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
    print(f"   📅 日期範圍: {fmt(d0)} ~ {fmt(d1)}")
    print(f"   💰 最新收盤: {df['close'].iloc[-1]:.2f} 元")
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
    """
    Compute screener analysis directly from df + combo (no network needed).
    Falls back to in-process calculation if StockScreener can't fetch data.
    """
    print("\n🔍 Step 3: 執行完整分析...")
    import numpy as np
    from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG, CHIP_CONFIG, SCREENING_CRITERIA
    from indicators.ut_bot import get_ut_bot_signal, calculate_ut_bot, calculate_ema_ribbon
    from indicators.smc import calculate_smc

    result = {'stock_id': STOCK_ID}
    result['price'] = float(df['close'].iloc[-1])
    result['price_change'] = float(
        (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100
    )

    # UT Bot signal from combo data
    try:
        ut_df = calculate_ut_bot(
            df,
            key_value=UT_BOT_CONFIG['key_value'],
            atr_period=UT_BOT_CONFIG['atr_period'],
            use_heikin_ashi=UT_BOT_CONFIG['use_heikin_ashi'],
        )
        ut_summary = get_ut_bot_signal(ut_df)
        result['ut_signal'] = ut_summary['signal']
        result['ut_trend'] = ut_summary['trend']
        result['ut_summary'] = ut_summary
    except Exception as e:
        result['ut_signal'] = 'hold'
        result['ut_trend'] = 'bullish'
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
        result['smc_signal'] = smc_summary.get('signal')
        result['smc_trend'] = smc_summary.get('swing_trend')
        result['smc_strength'] = smc_summary.get('signal_strength', 0)
        result['smc_summary'] = smc_summary
    except Exception:
        result['smc_signal'] = None
        result['smc_trend'] = 'N/A'
        result['smc_strength'] = 0
        result['smc_summary'] = {}

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

    # Chip: no network, use empty
    result['chip_signal'] = 'no_data'
    result['chip_summary'] = {}

    return result


def print_analysis_report(result, combo):
    """印出詳細分析報告"""
    print("\n" + "=" * 66)
    print(f"  📊 {STOCK_ID} 仁寶電腦 - 完整分析報告")
    print("=" * 66)

    # 價格
    price = result.get('price', 0)
    change = result.get('price_change', 0)
    arrow = "▲" if change >= 0 else "▼"
    color = "漲" if change >= 0 else "跌"
    print(f"\n  💰 最新價格:  {price:.2f} 元  {arrow} {abs(change):.2f}% ({color})")

    # UT Bot
    print(f"\n  🤖 UT Bot 指標:")
    print(f"     趨勢方向: {result.get('ut_trend', 'N/A').upper()}")
    print(f"     交易信號: {result.get('ut_signal', 'N/A').upper()}")
    ut_sum = result.get('ut_summary', {})
    if ut_sum.get('atr_stop'):
        print(f"     ATR Stop:  {ut_sum['atr_stop']:.2f} 元")
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

    # 籌碼
    chip = result.get('chip_summary', {})
    if chip:
        print(f"\n  💹 三大法人籌碼:")
        foreign = chip.get('foreign', {})
        trust = chip.get('investment_trust', {})
        dealer = chip.get('dealer', {})
        fn = foreign.get('net', 0)
        fc = foreign.get('consecutive_days', 0)
        f5 = foreign.get('5d_net', 0)
        tn = trust.get('net', 0)
        tc = trust.get('consecutive_days', 0)
        dn = dealer.get('net', 0)
        total = chip.get('total_net', 0)
        arrow_f = "▲" if fn >= 0 else "▼"
        arrow_t = "▲" if tn >= 0 else "▼"
        arrow_d = "▲" if dn >= 0 else "▼"
        print(f"     外資:   {arrow_f} {fn:+,} 張  (連續 {fc} 天，近5日: {f5:+,} 張)")
        print(f"     投信:   {arrow_t} {tn:+,} 張  (連續 {tc} 天)")
        print(f"     自營商: {arrow_d} {dn:+,} 張")
        print(f"     合計:   {total:+,} 張")
        print(f"     籌碼信號: [{chip.get('signal', 'N/A')}]  強度: {chip.get('strength', 0)}/100")
    else:
        print(f"\n  💹 籌碼資料: 無法取得（可能為非交易日或 API 限制）")

    # 成交量
    vol_ratio = result.get('volume_ratio', 1)
    spike = result.get('volume_spike', False)
    print(f"\n  📊 成交量分析:")
    print(f"     成交量倍數: {vol_ratio:.2f}x（相對20日均量）")
    if spike:
        print(f"     ⚡ 成交量放大！")
    else:
        print(f"     成交量正常")

    # 綜合判斷
    print(f"\n  🎯 綜合判斷:")
    score = 0
    signals = []
    if result.get('ut_signal') == 'buy':
        score += 30
        signals.append("UT Bot 買進信號")
    if result.get('smc_signal') in ['CHoCH_bull', 'BOS_bull']:
        score += 30
        signals.append(f"SMC {result.get('smc_signal')}")
    if ema_bull:
        score += 20
        signals.append("EMA 多頭排列")
    if chip and chip.get('signal') in ['strong_buy', 'buy', 'accumulating']:
        score += 20
        signals.append(f"籌碼 {chip.get('signal')}")
    if spike:
        score += 10
        signals.append("量價齊揚")
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
    """產生互動式圖表"""
    print("\n📈 Step 4: 產生互動式圖表...")
    from visualization import plot_stock_with_indicators, plot_stock, PLOTLY_AVAILABLE

    if not PLOTLY_AVAILABLE:
        print("   ❌ Plotly 未安裝，無法產生互動式圖表")
        return

    os.makedirs('output', exist_ok=True)

    ut_data = combo['ut_data']
    smc_data = combo['smc_data']
    ema_ribbon = combo['ema_ribbon']
    maxmin = combo['maxmin']

    # 1) K 線圖 + 完整指標
    out1 = f"output/{STOCK_ID}_demo_candlestick.html"
    print(f"   🖼  產生 K 線圖 + Combo 指標 → {out1}")
    plot_stock_with_indicators(
        df, STOCK_ID,
        ut_data=ut_data,
        smc_data=smc_data,
        ema_ribbon=ema_ribbon,
        maxmin=maxmin,
        chart_type='candlestick',
        save_path=out1,
        show=False,
        theme='light',
    )

    # 2) Heikin Ashi + 完整指標
    out2 = f"output/{STOCK_ID}_demo_heikin_ashi.html"
    print(f"   🖼  產生 Heikin Ashi + Combo 指標 → {out2}")
    plot_stock_with_indicators(
        df, STOCK_ID,
        ut_data=ut_data,
        smc_data=smc_data,
        ema_ribbon=ema_ribbon,
        maxmin=maxmin,
        chart_type='heikin_ashi',
        save_path=out2,
        show=False,
        theme='light',
    )

    print(f"\n  ✅ 圖表已儲存至 output/ 目錄")
    print(f"     K 線圖:       {out1}")
    print(f"     Heikin Ashi:  {out2}")
    print(f"\n  💡 用瀏覽器開啟 HTML 檔案即可查看互動式圖表！")
    print(f"     - 可縮放、平移、懸停查看詳細數值")
    print(f"     - 右上角工具列可下載圖片")


def main():
    print_header()

    # 1. 抓取資料
    df = fetch_data()

    # 2. 計算指標
    combo = compute_indicators(df)

    # 3. 完整分析
    result = compute_screener_analysis(df, combo)

    # 4. 印出分析報告
    if result:
        print_analysis_report(result, combo)
    else:
        print("\n⚠️ 無法取得完整分析結果（部分功能可能需要 API）")

    # 5. 產生圖表
    generate_charts(df, combo)

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  🎉 示範完成！                                                    ║
║                                                                  ║
║  📁 圖表位置:                                                    ║
║     output/{STOCK_ID}_demo_candlestick.html                      ║
║     output/{STOCK_ID}_demo_heikin_ashi.html                      ║
║                                                                  ║
║  💡 其他使用方式:                                                 ║
║     python chart_viewer.py {STOCK_ID} -i          # 指標圖表      ║
║     python chart_viewer.py {STOCK_ID} --ha -i     # HA + 指標    ║
║     python main.py --stock {STOCK_ID} --verbose   # 完整分析      ║
╚══════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
