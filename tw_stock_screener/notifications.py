"""
通知模組 - Line Notify 整合
============================
發送篩選結果到 Line
"""

import requests
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class LineNotifier:
    """
    Line Notify 通知發送器
    
    取得 Token:
    1. 前往 https://notify-bot.line.me/
    2. 登入 Line 帳號
    3. 點擊「發行權杖」
    4. 選擇要接收通知的聊天室
    5. 複製 Token
    """
    
    API_URL = "https://notify-api.line.me/api/notify"
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}"
        }
    
    def send_message(self, message: str) -> bool:
        """
        發送文字訊息
        """
        if not self.token or self.token == "YOUR_LINE_NOTIFY_TOKEN":
            logger.warning("Line Notify Token 未設定")
            print(f"[Line 通知預覽]\n{message}")
            return False
        
        try:
            data = {"message": message}
            response = requests.post(
                self.API_URL,
                headers=self.headers,
                data=data,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Line 通知發送成功")
                return True
            else:
                logger.error(f"Line 通知發送失敗: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Line 通知發送錯誤: {e}")
            return False
    
    def send_image(self, message: str, image_url: str) -> bool:
        """
        發送圖片訊息
        """
        if not self.token or self.token == "YOUR_LINE_NOTIFY_TOKEN":
            logger.warning("Line Notify Token 未設定")
            return False
        
        try:
            data = {
                "message": message,
                "imageThumbnail": image_url,
                "imageFullsize": image_url
            }
            response = requests.post(
                self.API_URL,
                headers=self.headers,
                data=data,
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Line 圖片通知發送錯誤: {e}")
            return False


def format_screening_result(results: List[Dict], title: str = "篩選結果") -> str:
    """
    格式化篩選結果為 Line 訊息
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = [
        f"\n📊 {title}",
        f"⏰ {now}",
        "─" * 20
    ]
    
    if not results:
        lines.append("無符合條件的股票")
        return "\n".join(lines)
    
    for i, stock in enumerate(results[:10], 1):  # 最多顯示 10 檔
        stock_id = stock.get('stock_id', 'N/A')
        price = stock.get('price', 0)
        change = stock.get('price_change', 0)
        
        # 價格變化 emoji
        if change > 0:
            change_emoji = '🔴'
            change_str = f"+{change:.2f}%"
        elif change < 0:
            change_emoji = '🟢'
            change_str = f"{change:.2f}%"
        else:
            change_emoji = '⚪'
            change_str = "0%"
        
        lines.append(f"\n{i}. {stock_id}")
        lines.append(f"   💰 {price:.2f} {change_emoji}{change_str}")
        
        # SMC 信號
        smc_signal = stock.get('smc_signal')
        if smc_signal:
            signal_emoji = '📈' if 'bull' in smc_signal.lower() else '📉'
            lines.append(f"   SMC: {signal_emoji} {smc_signal}")
        
        # UT Bot 信號
        ut_signal = stock.get('ut_signal')
        if ut_signal and ut_signal != 'hold':
            ut_emoji = '🟢' if ut_signal == 'buy' else '🔴'
            lines.append(f"   UT Bot: {ut_emoji} {ut_signal.upper()}")
        
        # 籌碼信號
        chip_signal = stock.get('chip_signal')
        if chip_signal and chip_signal != 'neutral':
            chip_emoji = '💹' if 'buy' in chip_signal else '💸'
            lines.append(f"   籌碼: {chip_emoji} {chip_signal}")
        
        # 成交量
        if stock.get('volume_spike'):
            vol_ratio = stock.get('volume_ratio', 1)
            lines.append(f"   📊 量能放大 {vol_ratio:.1f}x")
    
    if len(results) > 10:
        lines.append(f"\n... 還有 {len(results) - 10} 檔")
    
    lines.append("\n" + "─" * 20)
    lines.append("🤖 AI 台股篩選系統")
    
    return "\n".join(lines)


def format_single_stock_alert(stock: Dict) -> str:
    """
    格式化單一股票警報
    """
    stock_id = stock.get('stock_id', 'N/A')
    stock_name = stock.get('stock_name', '')
    price = stock.get('price', 0)
    change = stock.get('price_change', 0)
    
    change_emoji = '🔴' if change > 0 else ('🟢' if change < 0 else '⚪')
    change_str = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
    
    lines = [
        f"\n🚨 交易信號警報",
        f"─" * 20,
        f"📌 {stock_id} {stock_name}",
        f"💰 價格: {price:.2f} {change_emoji}{change_str}",
    ]
    
    # SMC 信號
    smc = stock.get('smc_summary', {})
    if smc:
        lines.append(f"\n📊 SMC 分析:")
        lines.append(f"   趨勢: {smc.get('swing_trend', 'N/A')}")
        if smc.get('signal'):
            lines.append(f"   信號: {smc.get('signal')} (強度: {smc.get('signal_strength', 0)})")
        if smc.get('in_discount'):
            lines.append(f"   ⚡ 處於折價區")
        elif smc.get('in_premium'):
            lines.append(f"   ⚠️ 處於溢價區")
    
    # UT Bot 信號
    ut = stock.get('ut_summary', {})
    if ut:
        lines.append(f"\n🤖 UT Bot:")
        lines.append(f"   趨勢: {ut.get('trend', 'N/A')}")
        if ut.get('signal') != 'hold':
            signal_emoji = '🟢' if ut.get('signal') == 'buy' else '🔴'
            lines.append(f"   信號: {signal_emoji} {ut.get('signal', '').upper()}")
        lines.append(f"   ATR Stop: {ut.get('atr_stop', 0):.2f}")
    
    # 籌碼分析
    chip = stock.get('chip_summary', {})
    if chip:
        lines.append(f"\n💹 籌碼分析:")
        foreign = chip.get('foreign', {})
        trust = chip.get('investment_trust', {})
        
        if foreign.get('net', 0) != 0:
            f_net = foreign.get('net', 0)
            f_emoji = '📈' if f_net > 0 else '📉'
            lines.append(f"   外資: {f_emoji} {f_net:+,} 張")
        
        if trust.get('net', 0) != 0:
            t_net = trust.get('net', 0)
            t_emoji = '📈' if t_net > 0 else '📉'
            lines.append(f"   投信: {t_emoji} {t_net:+,} 張")
        
        if chip.get('description'):
            lines.append(f"   {chip.get('description')}")
    
    lines.append("\n" + "─" * 20)
    lines.append(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    return "\n".join(lines)


def format_daily_report(results: List[Dict], market: str = "台股") -> str:
    """
    格式化每日報告
    """
    now = datetime.now()
    
    # 統計
    bullish_count = sum(1 for r in results if 'bull' in str(r.get('smc_signal', '')).lower())
    bearish_count = sum(1 for r in results if 'bear' in str(r.get('smc_signal', '')).lower())
    ut_buy_count = sum(1 for r in results if r.get('ut_signal') == 'buy')
    ut_sell_count = sum(1 for r in results if r.get('ut_signal') == 'sell')
    chip_buy_count = sum(1 for r in results if 'buy' in str(r.get('chip_signal', '')).lower())
    
    lines = [
        f"\n📈 {market}每日篩選報告",
        f"📅 {now.strftime('%Y-%m-%d')}",
        "═" * 25,
        "",
        f"📊 掃描統計:",
        f"   總共掃描: {len(results)} 檔",
        f"   SMC 多方信號: {bullish_count} 檔",
        f"   SMC 空方信號: {bearish_count} 檔",
        f"   UT Bot 買進: {ut_buy_count} 檔",
        f"   UT Bot 賣出: {ut_sell_count} 檔",
        f"   籌碼買超: {chip_buy_count} 檔",
        "",
    ]
    
    # 精選股票（符合多重條件）
    top_picks = [r for r in results if 
                 ('bull' in str(r.get('smc_signal', '')).lower() and 
                  (r.get('ut_signal') == 'buy' or 'buy' in str(r.get('chip_signal', '')).lower()))]
    
    if top_picks:
        lines.append("🌟 精選股票（多重條件符合）:")
        for stock in top_picks[:5]:
            stock_id = stock.get('stock_id', 'N/A')
            price = stock.get('price', 0)
            change = stock.get('price_change', 0)
            change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
            lines.append(f"   • {stock_id}: {price:.2f} ({change_str})")
        lines.append("")
    
    lines.append("═" * 25)
    lines.append("🤖 AI 台股篩選系統")
    
    return "\n".join(lines)


# ============================================================
# 測試函數
# ============================================================

def test_notification():
    """測試通知格式"""
    # 模擬篩選結果
    results = [
        {
            'stock_id': '2330',
            'price': 580.0,
            'price_change': 2.5,
            'smc_signal': 'CHoCH_bull',
            'ut_signal': 'buy',
            'chip_signal': 'strong_buy',
            'volume_spike': True,
            'volume_ratio': 1.8,
        },
        {
            'stock_id': '2317',
            'price': 105.5,
            'price_change': -1.2,
            'smc_signal': 'BOS_bear',
            'ut_signal': 'sell',
            'chip_signal': 'distributing',
            'volume_spike': False,
            'volume_ratio': 0.9,
        },
    ]
    
    print("=" * 50)
    print("篩選結果通知：")
    print(format_screening_result(results, "台股 SMC 篩選"))
    
    print("\n" + "=" * 50)
    print("單一股票警報：")
    
    stock_detail = {
        'stock_id': '2330',
        'stock_name': '台積電',
        'price': 580.0,
        'price_change': 2.5,
        'smc_summary': {
            'swing_trend': 'bullish',
            'signal': 'CHoCH_bull',
            'signal_strength': 90,
            'in_discount': True,
        },
        'ut_summary': {
            'trend': 'bullish',
            'signal': 'buy',
            'atr_stop': 565.5,
        },
        'chip_summary': {
            'foreign': {'net': 15000},
            'investment_trust': {'net': 3000},
            'description': '外資+投信同步買超，籌碼面強勢',
        },
    }
    print(format_single_stock_alert(stock_detail))
    
    print("\n" + "=" * 50)
    print("每日報告：")
    print(format_daily_report(results))


if __name__ == "__main__":
    test_notification()
