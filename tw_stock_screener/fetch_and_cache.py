#!/usr/bin/env python3
"""
即時資料抓取並快取腳本
========================
在有網路存取的環境（本機、CI/CD）中執行此腳本，
將最新股價資料存入 data/<stock_id>_cache.csv。

下次在任何環境（包含受限制的雲端環境）中執行 demo_2330.py 時，
系統會自動從本地快取讀取資料，不再需要連線到外部 API。

使用方式：
    python fetch_and_cache.py              # 更新預設股票列表
    python fetch_and_cache.py 2330 2317    # 更新指定股票
    python fetch_and_cache.py --all        # 更新所有 TW_STOCK_LIST

資料來源優先順序：
    TWSE（證交所）→ FinMind → yfinance
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_STOCKS = ['2330', '2317', '2454', '2308', '2412']
DAYS = 180  # 快取 180 個交易日


def fetch_and_save(stock_ids, days=DAYS):
    from data_fetcher import UnifiedDataFetcher, LocalCSVDataFetcher

    fetcher = UnifiedDataFetcher(tw_source='twse')
    cache   = LocalCSVDataFetcher()
    results = {'ok': [], 'fail': []}

    for sid in stock_ids:
        print(f"\n[{sid}] 抓取資料中...", flush=True)
        try:
            # Force bypass cache to get fresh data
            df = None
            # Try TWSE
            try:
                df = fetcher.twse.get_stock_data(sid, days)
                if df is not None and len(df) >= 20:
                    print(f"  ✅ TWSE: {len(df)} rows")
            except Exception as e:
                print(f"  ⚠️  TWSE 失敗: {e}")

            # Fallback: FinMind
            if df is None or len(df) < 20:
                try:
                    df = fetcher.finmind.get_stock_data(sid, days)
                    if df is not None and len(df) >= 20:
                        print(f"  ✅ FinMind: {len(df)} rows")
                except Exception as e:
                    print(f"  ⚠️  FinMind 失敗: {e}")

            # Fallback: yfinance
            if df is None or len(df) < 20:
                try:
                    df = fetcher.yfinance.get_stock_data(sid, days, market='TW')
                    if df is not None and len(df) >= 20:
                        print(f"  ✅ yfinance: {len(df)} rows")
                except Exception as e:
                    print(f"  ⚠️  yfinance 失敗: {e}")

            if df is not None and len(df) >= 20:
                cache.save(sid, df)
                price = df['close'].iloc[-1]
                date  = df['date'].iloc[-1]
                fmt   = lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
                print(f"  💾 已儲存 {len(df)} 筆  最新: {fmt(date)} 收盤 {price:.1f} 元")
                results['ok'].append(sid)
            else:
                print(f"  ❌ 取得資料失敗（所有來源均無法連線）")
                results['fail'].append(sid)

        except Exception as e:
            print(f"  ❌ 例外錯誤: {e}")
            results['fail'].append(sid)

        time.sleep(1)  # 避免 API 過快

    print("\n" + "=" * 50)
    print(f"完成：成功 {len(results['ok'])} 支，失敗 {len(results['fail'])} 支")
    if results['ok']:
        print(f"  ✅ {', '.join(results['ok'])}")
    if results['fail']:
        print(f"  ❌ {', '.join(results['fail'])}")
    if results['ok']:
        print("\n💡 快取已更新，現在可在任何環境執行 demo_2330.py")
    return results


def main():
    parser = argparse.ArgumentParser(description='台股資料抓取並快取')
    parser.add_argument('stocks', nargs='*', help='股票代碼（預設: 2330 2317 2454 2308 2412）')
    parser.add_argument('--all', action='store_true', help='更新 TW_STOCK_LIST 所有股票')
    parser.add_argument('--days', type=int, default=DAYS, help=f'抓取天數（預設: {DAYS}）')
    args = parser.parse_args()

    if args.all:
        from config import TW_STOCK_LIST
        stock_ids = TW_STOCK_LIST
    elif args.stocks:
        stock_ids = args.stocks
    else:
        stock_ids = DEFAULT_STOCKS

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  台股資料抓取並快取 - fetch_and_cache.py                          ║
║  在本機執行此腳本以更新資料快取                                   ║
╚══════════════════════════════════════════════════════════════════╝

股票: {', '.join(stock_ids)}
天數: {args.days}
""")

    fetch_and_save(stock_ids, days=args.days)


if __name__ == "__main__":
    main()
