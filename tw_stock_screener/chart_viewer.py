#!/usr/bin/env python3
"""
股票圖表檢視器
==============

整合 UT Bot + SMC 指標的 TradingView 風格圖表

使用方式:
    python chart_viewer.py 2330                    # 台股 K 線
    python chart_viewer.py 2330 --ha               # 台股 Heikin Ashi
    python chart_viewer.py AAPL --market us        # 美股
    python chart_viewer.py 2330 --save             # 儲存圖表
    python chart_viewer.py 2330 --indicators       # 顯示 UT Bot + SMC
"""

import sys
import os
import argparse

# 加入模組路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(
        description='股票圖表檢視器 - TradingView 風格',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python chart_viewer.py 2330              # 台積電 K 線圖
  python chart_viewer.py 2330 --ha         # Heikin Ashi 圖表
  python chart_viewer.py 2330 -i           # 顯示 UT Bot + SMC 指標
  python chart_viewer.py AAPL -m us        # 美股 Apple
  python chart_viewer.py 2330 --save       # 儲存為 HTML
  python chart_viewer.py 2330 --png        # 儲存為 PNG
        """
    )
    
    parser.add_argument('stock', type=str, help='股票代碼 (例: 2330, AAPL)')
    parser.add_argument('-m', '--market', type=str, default='tw', 
                        choices=['tw', 'us'], help='市場: tw=台股, us=美股')
    parser.add_argument('--ha', '--heikin-ashi', action='store_true', 
                        dest='heikin_ashi', help='使用 Heikin Ashi')
    parser.add_argument('-i', '--indicators', action='store_true',
                        help='顯示 UT Bot + SMC 指標')
    parser.add_argument('-d', '--days', type=int, default=120,
                        help='顯示天數 (預設: 120)')
    parser.add_argument('--ema', type=str, default='5,20,60',
                        help='EMA 週期，逗號分隔 (預設: 5,20,60)')
    parser.add_argument('--save', action='store_true', help='儲存為 HTML')
    parser.add_argument('--png', action='store_true', help='儲存為 PNG')
    parser.add_argument('--engine', type=str, default='plotly',
                        choices=['plotly', 'mplfinance'], help='圖表引擎')
    parser.add_argument('--no-volume', action='store_true', help='不顯示成交量')
    parser.add_argument('--dark', action='store_true', help='使用深色主題（預設為淺色）')
    
    args = parser.parse_args()
    theme = 'dark' if args.dark else 'light'
    
    # 標題
    print("""
╔══════════════════════════════════════════════════════════════╗
║          股票圖表檢視器 - TradingView 風格                    ║
║          Candlestick / Heikin Ashi / UT Bot / SMC            ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # 導入模組
    try:
        from data_fetcher import UnifiedDataFetcher
        from visualization import plot_stock, plot_stock_with_indicators, PLOTLY_AVAILABLE, MPLFINANCE_AVAILABLE
    except ImportError as e:
        print(f"❌ 模組載入失敗: {e}")
        print("請確保在 tw_stock_screener 目錄下執行")
        sys.exit(1)
    
    # 檢查視覺化套件
    if args.engine == 'plotly' and not PLOTLY_AVAILABLE:
        print("❌ plotly 未安裝，請執行: pip install plotly")
        sys.exit(1)
    
    if args.engine == 'mplfinance' and not MPLFINANCE_AVAILABLE:
        print("❌ mplfinance 未安裝，請執行: pip install mplfinance matplotlib")
        sys.exit(1)
    
    # 抓取資料
    print(f"📊 載入 {args.stock} 資料...")
    fetcher = UnifiedDataFetcher()
    
    if args.market == 'tw':
        df = fetcher.get_tw_stock_data(args.stock, days=args.days)
    else:
        df = fetcher.get_us_stock_data(args.stock, days=args.days)
    
    if df is None or len(df) < 10:
        print(f"❌ 無法取得 {args.stock} 的資料")
        sys.exit(1)
    
    print(f"✅ 載入 {len(df)} 根 K 線")
    
    # 解析 EMA 週期
    ema_periods = [int(x.strip()) for x in args.ema.split(',')]
    
    # 圖表類型
    chart_type = 'heikin_ashi' if args.heikin_ashi else 'candlestick'
    chart_label = 'Heikin Ashi' if args.heikin_ashi else 'K 線圖'
    
    # 儲存路徑
    save_path = None
    if args.save:
        os.makedirs('output', exist_ok=True)
        ext = 'html' if args.engine == 'plotly' else 'png'
        save_path = f"output/{args.stock}_{chart_type}.{ext}"
    elif args.png:
        os.makedirs('output', exist_ok=True)
        save_path = f"output/{args.stock}_{chart_type}.png"
    
    # 是否加入指標（Combo: UT Bot + EMA Ribbon + MaxMin + SMC）
    if args.indicators:
        print("🔧 計算 Combo 指標 (UT Bot + EMA Ribbon + MaxMin + SMC)...")
        
        try:
            from indicators.combo_indicator import calculate_combo
            from config import UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG
            
            ema_periods_combo = EMA_CONFIG.get('periods', [5, 20, 60, 120, 240])
            combo = calculate_combo(
                df,
                ut_config=UT_BOT_CONFIG,
                ema_periods=ema_periods_combo,
                mm_length=1,
                smc_config=SMC_CONFIG,
            )
            
            print(f"   SMC 趨勢: {combo['smc_summary'].get('swing_trend', 'N/A')}")
            
            # 繪製 Combo 圖表
            print(f"\n📈 繪製 {chart_label} + Combo 指標...")
            plot_stock_with_indicators(
                df, args.stock,
                ut_data=combo['ut_data'],
                smc_data=combo['smc_data'],
                ema_ribbon=combo['ema_ribbon'],
                maxmin=combo['maxmin'],
                chart_type=chart_type,
                save_path=save_path,
                show=not (args.save or args.png),
                theme=theme
            )
            
        except Exception as e:
            print(f"⚠️ 指標計算失敗: {e}")
            print("改用基本圖表...")
            plot_stock(
                df, args.stock,
                chart_type=chart_type,
                engine=args.engine,
                show_volume=not args.no_volume,
                show_ema=ema_periods,
                save_path=save_path,
                show=not (args.save or args.png),
                theme=theme
            )
    else:
        # 繪製基本圖表
        print(f"\n📈 繪製 {chart_label}...")
        plot_stock(
            df, args.stock,
            chart_type=chart_type,
            engine=args.engine,
            show_volume=not args.no_volume,
            show_ema=ema_periods,
            save_path=save_path,
            show=not (args.save or args.png),
            theme=theme
        )
    
    if save_path:
        print(f"\n💾 圖表已儲存: {save_path}")
    
    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
