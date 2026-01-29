"""
台股/美股 SMC + UT Bot 篩選系統 - 主程式
=========================================

整合功能：
1. UT Bot 指標
2. SMC (Smart Money Concepts) 指標
3. 籌碼分析（三大法人）
4. Gemini AI 分析
5. Line 通知

使用方式：
python main.py --market tw --notify
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
import json
import time

# 加入模組路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 載入模組
from config import (
    GEMINI_API_KEY, LINE_NOTIFY_TOKEN,
    TW_DATA_SOURCE, FINMIND_TOKEN,
    UT_BOT_CONFIG, SMC_CONFIG, EMA_CONFIG, CHIP_CONFIG,
    SCREENING_CRITERIA, TW_STOCK_LIST, US_STOCK_LIST,
    OUTPUT_CONFIG
)
from data_fetcher import UnifiedDataFetcher
from indicators.ut_bot import calculate_ut_bot, get_ut_bot_signal, calculate_ema_ribbon
from indicators.smc import calculate_smc
from indicators.chip_analysis import analyze_chip_data, format_chip_data
from notifications import (
    LineNotifier, 
    format_screening_result, 
    format_single_stock_alert,
    format_daily_report
)
from ai_analyzer import GeminiAnalyzer

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'logs/screener_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class StockScreener:
    """
    股票篩選系統
    """
    
    def __init__(
        self,
        market: str = 'tw',
        enable_ai: bool = True,
        enable_notify: bool = False
    ):
        self.market = market.lower()
        self.enable_ai = enable_ai
        self.enable_notify = enable_notify
        
        # 初始化資料抓取器
        self.data_fetcher = UnifiedDataFetcher(
            tw_source=TW_DATA_SOURCE,
            finmind_token=FINMIND_TOKEN
        )
        
        # 初始化 AI 分析器
        if enable_ai:
            self.ai_analyzer = GeminiAnalyzer(GEMINI_API_KEY)
        else:
            self.ai_analyzer = None
        
        # 初始化通知器
        if enable_notify:
            self.notifier = LineNotifier(LINE_NOTIFY_TOKEN)
        else:
            self.notifier = None
        
        # 建立輸出目錄
        os.makedirs(OUTPUT_CONFIG['output_dir'], exist_ok=True)
        os.makedirs(OUTPUT_CONFIG['log_dir'], exist_ok=True)
    
    def analyze_single_stock(self, stock_id: str, verbose: bool = False) -> Optional[Dict]:
        """
        分析單一股票
        """
        logger.info(f"分析股票: {stock_id}")
        
        # 抓取價格資料
        if self.market == 'tw':
            df = self.data_fetcher.get_tw_stock_data(stock_id, days=120)
        else:
            df = self.data_fetcher.get_us_stock_data(stock_id, days=120)
        
        if df is None or len(df) < 50:
            logger.warning(f"無法取得 {stock_id} 的足夠資料")
            return None
        
        result = {'stock_id': stock_id}
        
        # 基本價格資訊
        result['price'] = df['close'].iloc[-1]
        result['price_change'] = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100 if len(df) >= 2 else 0
        
        # 計算 UT Bot
        try:
            ut_df = calculate_ut_bot(
                df,
                key_value=UT_BOT_CONFIG['key_value'],
                atr_period=UT_BOT_CONFIG['atr_period'],
                use_heikin_ashi=UT_BOT_CONFIG['use_heikin_ashi']
            )
            ut_summary = get_ut_bot_signal(ut_df)
            result['ut_signal'] = ut_summary['signal']
            result['ut_trend'] = ut_summary['trend']
            result['ut_summary'] = ut_summary
        except Exception as e:
            logger.error(f"UT Bot 計算錯誤 ({stock_id}): {e}")
            result['ut_signal'] = 'error'
            result['ut_summary'] = {}
        
        # 計算 SMC
        try:
            smc_df, smc_summary = calculate_smc(
                df,
                swing_length=SMC_CONFIG['swing_length'],
                internal_length=SMC_CONFIG['internal_length'],
                equal_hl_threshold=SMC_CONFIG['equal_hl_threshold'],
                order_block_filter=SMC_CONFIG['order_block_filter'],
                fvg_threshold=SMC_CONFIG['fvg_threshold']
            )
            result['smc_signal'] = smc_summary.get('signal')
            result['smc_trend'] = smc_summary.get('swing_trend')
            result['smc_strength'] = smc_summary.get('signal_strength', 0)
            result['smc_summary'] = smc_summary
        except Exception as e:
            logger.error(f"SMC 計算錯誤 ({stock_id}): {e}")
            result['smc_signal'] = None
            result['smc_summary'] = {}
        
        # 計算 EMA Ribbon
        try:
            ema_df = calculate_ema_ribbon(df, periods=EMA_CONFIG['periods'])
            result['ema_bullish'] = ema_df['ema_bullish'].iloc[-1] if 'ema_bullish' in ema_df.columns else False
            result['ema_bearish'] = ema_df['ema_bearish'].iloc[-1] if 'ema_bearish' in ema_df.columns else False
        except Exception as e:
            logger.error(f"EMA Ribbon 計算錯誤 ({stock_id}): {e}")
        
        # 籌碼分析（僅台股）
        if self.market == 'tw':
            try:
                chip_df = self.data_fetcher.get_institutional_trading(stock_id, days=30)
                if chip_df is not None and len(chip_df) > 0:
                    chip_result = analyze_chip_data(chip_df, CHIP_CONFIG)
                    result['chip_signal'] = chip_result.signal
                    result['chip_strength'] = chip_result.strength
                    result['chip_summary'] = {
                        'foreign': {
                            'net': chip_result.foreign_net,
                            'consecutive_days': chip_result.foreign_consecutive,
                            '5d_net': chip_result.foreign_5d_net,
                        },
                        'investment_trust': {
                            'net': chip_result.investment_trust_net,
                            'consecutive_days': chip_result.trust_consecutive,
                            '5d_net': chip_result.trust_5d_net,
                        },
                        'dealer': {'net': chip_result.dealer_net},
                        'total_net': chip_result.total_net,
                        'signal': chip_result.signal,
                        'strength': chip_result.strength,
                    }
                else:
                    result['chip_signal'] = 'no_data'
                    result['chip_summary'] = {}
            except Exception as e:
                logger.error(f"籌碼分析錯誤 ({stock_id}): {e}")
                result['chip_signal'] = 'error'
                result['chip_summary'] = {}
        
        # 成交量分析
        if len(df) >= 20:
            avg_volume = df['volume'].tail(20).mean()
            current_volume = df['volume'].iloc[-1]
            result['volume_ratio'] = current_volume / avg_volume if avg_volume > 0 else 1
            result['volume_spike'] = result['volume_ratio'] > SCREENING_CRITERIA['volume_ratio']
        
        # AI 分析
        if self.enable_ai and self.ai_analyzer:
            try:
                result['ai_suggestion'] = self.ai_analyzer.get_trading_suggestion(result)
            except Exception as e:
                logger.error(f"AI 分析錯誤 ({stock_id}): {e}")
        
        if verbose:
            self._print_stock_analysis(result)
        
        return result
    
    def _print_stock_analysis(self, result: Dict):
        """
        印出股票分析結果
        """
        print("\n" + "=" * 60)
        print(f"📊 {result['stock_id']} 分析結果")
        print("=" * 60)
        
        price = result.get('price', 0)
        change = result.get('price_change', 0)
        change_symbol = '📈' if change > 0 else ('📉' if change < 0 else '➖')
        print(f"💰 價格: {price:.2f} {change_symbol} {change:+.2f}%")
        
        print(f"\n🤖 UT Bot:")
        print(f"   趨勢: {result.get('ut_trend', 'N/A')}")
        print(f"   信號: {result.get('ut_signal', 'N/A')}")
        if result.get('ut_summary', {}).get('atr_stop'):
            print(f"   ATR Stop: {result['ut_summary']['atr_stop']:.2f}")
        
        print(f"\n📊 SMC:")
        print(f"   趨勢: {result.get('smc_trend', 'N/A')}")
        print(f"   信號: {result.get('smc_signal', 'N/A')}")
        print(f"   強度: {result.get('smc_strength', 0)}")
        
        if result.get('chip_summary'):
            chip = result['chip_summary']
            print(f"\n💹 籌碼:")
            print(f"   外資: {chip.get('foreign', {}).get('net', 0):+,} 張")
            print(f"   投信: {chip.get('investment_trust', {}).get('net', 0):+,} 張")
            print(f"   信號: {chip.get('signal', 'N/A')}")
        
        if result.get('volume_spike'):
            print(f"\n📊 成交量放大: {result.get('volume_ratio', 1):.2f}x")
        
        if result.get('ai_suggestion'):
            ai = result['ai_suggestion']
            print(f"\n🤖 AI 建議:")
            print(f"   評分: {ai.get('score', 0)}/100")
            print(f"   建議: {ai.get('action', 'N/A').upper()}")
            print(f"   信心: {ai.get('confidence', 'N/A')}")
            if ai.get('reasons'):
                print(f"   原因: {', '.join(ai['reasons'][:3])}")
    
    def run_screening(
        self,
        stock_list: List[str] = None,
        filters: Dict = None
    ) -> List[Dict]:
        """
        執行篩選
        """
        if stock_list is None:
            stock_list = TW_STOCK_LIST if self.market == 'tw' else US_STOCK_LIST
        
        filters = filters or SCREENING_CRITERIA
        
        logger.info(f"開始篩選 {len(stock_list)} 檔股票...")
        print(f"\n🔍 開始篩選 {len(stock_list)} 檔{'台股' if self.market == 'tw' else '美股'}...")
        print("=" * 60)
        
        results = []
        
        for i, stock_id in enumerate(stock_list):
            print(f"\r處理中: {i+1}/{len(stock_list)} - {stock_id}    ", end='', flush=True)
            
            try:
                result = self.analyze_single_stock(stock_id)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"分析 {stock_id} 時發生錯誤: {e}")
            
            time.sleep(0.3)  # 避免請求過快
        
        print(f"\n\n✅ 完成掃描 {len(results)} 檔股票")
        
        # 套用篩選條件
        filtered_results = self._apply_filters(results, filters)
        
        logger.info(f"篩選完成，符合條件: {len(filtered_results)} 檔")
        
        return filtered_results
    
    def _apply_filters(self, results: List[Dict], filters: Dict) -> List[Dict]:
        """
        套用篩選條件
        """
        filtered = results.copy()
        
        # SMC 信號篩選
        smc_signals = filters.get('smc_signals', [])
        if smc_signals:
            filtered = [r for r in filtered if r.get('smc_signal') in smc_signals]
        
        # 最低信號強度
        min_strength = filters.get('min_signal_strength', 0)
        if min_strength > 0:
            filtered = [r for r in filtered if r.get('smc_strength', 0) >= min_strength]
        
        # UT Bot 信號篩選
        ut_signal = filters.get('ut_bot_signal', 'any')
        if ut_signal != 'any':
            filtered = [r for r in filtered if r.get('ut_signal') == ut_signal]
        
        # 籌碼條件篩選
        chip_condition = filters.get('chip_condition', 'any')
        if chip_condition == 'foreign_buy':
            filtered = [r for r in filtered if 
                       r.get('chip_summary', {}).get('foreign', {}).get('net', 0) > 0]
        elif chip_condition == 'all_buy':
            filtered = [r for r in filtered if 
                       r.get('chip_summary', {}).get('total_net', 0) > 0]
        
        # 成交量篩選
        if filters.get('volume_spike'):
            filtered = [r for r in filtered if r.get('volume_spike')]
        
        # 按信號強度排序
        filtered.sort(key=lambda x: x.get('smc_strength', 0) + x.get('chip_strength', 0), reverse=True)
        
        return filtered
    
    def save_results(self, results: List[Dict], filename: str = None) -> str:
        """
        儲存結果
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"screening_{self.market}_{timestamp}"
        
        # 儲存 CSV
        if OUTPUT_CONFIG['save_csv']:
            csv_path = os.path.join(OUTPUT_CONFIG['output_dir'], f"{filename}.csv")
            df = pd.DataFrame(results)
            
            # 選擇要輸出的欄位
            output_cols = [
                'stock_id', 'price', 'price_change', 
                'smc_signal', 'smc_trend', 'smc_strength',
                'ut_signal', 'ut_trend',
                'chip_signal', 'volume_ratio'
            ]
            output_cols = [c for c in output_cols if c in df.columns]
            
            df[output_cols].to_csv(csv_path, index=False, encoding='utf-8-sig')
            logger.info(f"CSV 已儲存: {csv_path}")
        
        # 儲存 JSON
        if OUTPUT_CONFIG['save_json']:
            json_path = os.path.join(OUTPUT_CONFIG['output_dir'], f"{filename}.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"JSON 已儲存: {json_path}")
        
        return filename
    
    def send_notification(self, results: List[Dict], title: str = None):
        """
        發送通知
        """
        if not self.notifier:
            logger.warning("通知功能未啟用")
            return
        
        title = title or f"{'台股' if self.market == 'tw' else '美股'}篩選結果"
        message = format_screening_result(results, title)
        
        self.notifier.send_message(message)
    
    def send_alert(self, stock: Dict):
        """
        發送單一股票警報
        """
        if not self.notifier:
            return
        
        message = format_single_stock_alert(stock)
        self.notifier.send_message(message)
    
    def send_daily_report(self, results: List[Dict]):
        """
        發送每日報告
        """
        if not self.notifier:
            return
        
        message = format_daily_report(results, '台股' if self.market == 'tw' else '美股')
        self.notifier.send_message(message)


def main():
    """主程式入口"""
    parser = argparse.ArgumentParser(description='台股/美股 SMC + UT Bot 篩選系統')
    parser.add_argument('--market', '-m', type=str, default='tw', choices=['tw', 'us'],
                        help='市場: tw (台股) 或 us (美股)')
    parser.add_argument('--stock', '-s', type=str, default=None,
                        help='分析單一股票代碼')
    parser.add_argument('--notify', '-n', action='store_true',
                        help='啟用 Line 通知')
    parser.add_argument('--ai', '-a', action='store_true', default=True,
                        help='啟用 AI 分析')
    parser.add_argument('--no-ai', action='store_true',
                        help='停用 AI 分析')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='詳細輸出')
    
    args = parser.parse_args()
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     台股/美股 SMC + UT Bot + 籌碼 篩選系統                ║
    ║     整合 UT Bot、SMC、籌碼分析、AI 建議                   ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # 建立篩選器
    screener = StockScreener(
        market=args.market,
        enable_ai=args.ai and not args.no_ai,
        enable_notify=args.notify
    )
    
    # 單一股票分析
    if args.stock:
        result = screener.analyze_single_stock(args.stock, verbose=True)
        
        if result and args.notify:
            screener.send_alert(result)
        
        return
    
    # 執行完整篩選
    results = screener.run_screening()
    
    # 顯示結果
    if results:
        print("\n" + "=" * 60)
        print("📊 篩選結果")
        print("=" * 60)
        
        for i, stock in enumerate(results[:20], 1):
            stock_id = stock.get('stock_id', 'N/A')
            price = stock.get('price', 0)
            change = stock.get('price_change', 0)
            smc = stock.get('smc_signal', 'N/A')
            ut = stock.get('ut_signal', 'N/A')
            chip = stock.get('chip_signal', 'N/A')
            
            change_emoji = '🔴' if change > 0 else ('🟢' if change < 0 else '⚪')
            print(f"{i:2d}. {stock_id:6s} | {price:8.2f} {change_emoji}{change:+6.2f}% | SMC: {str(smc):12s} | UT: {str(ut):6s} | 籌碼: {str(chip):12s}")
        
        if len(results) > 20:
            print(f"\n... 還有 {len(results) - 20} 檔")
    else:
        print("\n⚠️ 沒有找到符合條件的股票")
    
    # 儲存結果
    if results:
        filename = screener.save_results(results)
        print(f"\n✅ 結果已儲存: {filename}")
    
    # 發送通知
    if args.notify and results:
        screener.send_notification(results)
        print("📱 已發送 Line 通知")
    
    # AI 市場分析
    if screener.ai_analyzer and results:
        print("\n" + "=" * 60)
        print("🤖 AI 市場分析")
        print("=" * 60)
        analysis = screener.ai_analyzer.analyze_market_overview(results)
        print(analysis)


if __name__ == "__main__":
    main()
