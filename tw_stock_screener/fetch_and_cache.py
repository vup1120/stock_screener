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

DEFAULT_STOCKS = [
    # AI與半導體核心權值股
    '2330', '2317', '2454', '2382', '3231', '2376', '2377', '3711', '3661', '3443',
    # 網通訊號與高速傳輸
    '2345', '3596', '3034', '4966', '5269', '2379', '3533', '3105', '8086', '2455',
    # 先進封裝材料與散熱
    '2383', '6274', '6213', '2368', '3653', '2308', '5274', '6187', '3680', '6223',
    # 重電綠能與航運
    '1519', '1513', '1504', '1514', '6806', '2603', '2609',
    # 矽光子 / CPO
    '3081', '3363', '3163',
    # 液冷散熱
    '3324', '3017', '8996',
    # 先進封裝設備
    '3131', '3583', '8027',
    # 其他
    '2337', '00631L',
]
DAYS = 365  # 快取一年交易日

# GitHub Actions 環境下優先使用 yfinance（TWSE 可能封鎖 GH Actions IP）
IN_GITHUB_ACTIONS = os.environ.get('GITHUB_ACTIONS') == 'true'


def fetch_and_save(stock_ids, days=DAYS):
    from data_fetcher import UnifiedDataFetcher, LocalCSVDataFetcher

    fetcher = UnifiedDataFetcher(tw_source='twse')
    cache   = LocalCSVDataFetcher()
    results = {'ok': [], 'fail': []}

    # 在 GitHub Actions 中，yfinance 最穩定；本機優先用 TWSE（官方資料）
    if IN_GITHUB_ACTIONS:
        source_order = [
            ('yfinance', lambda sid: fetcher.yfinance.get_stock_data(sid, days, market='TW')),
            ('TWSE',     lambda sid: fetcher.twse.get_stock_data(sid, days)),
            ('FinMind',  lambda sid: fetcher.finmind.get_stock_data(sid, days)),
        ]
        print("  ℹ️  GitHub Actions 環境：優先使用 yfinance")
    else:
        source_order = [
            ('TWSE',     lambda sid: fetcher.twse.get_stock_data(sid, days)),
            ('FinMind',  lambda sid: fetcher.finmind.get_stock_data(sid, days)),
            ('yfinance', lambda sid: fetcher.yfinance.get_stock_data(sid, days, market='TW')),
        ]

    for sid in stock_ids:
        print(f"\n[{sid}] 抓取資料中...", flush=True)
        try:
            df = None
            for src_name, src_fn in source_order:
                try:
                    result = src_fn(sid)
                    if result is not None and len(result) >= 20:
                        df = result
                        print(f"  ✅ {src_name}: {len(df)} rows")
                        break
                    else:
                        print(f"  ⚠️  {src_name}: 無資料")
                except Exception as e:
                    print(f"  ⚠️  {src_name} 失敗: {type(e).__name__}: {e}")

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

        time.sleep(0.5 if IN_GITHUB_ACTIONS else 1)

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
