"""
Gemini AI 整合模組
==================
使用 Google Gemini Pro 進行股票分析
"""

import json
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    """
    Gemini AI 分析器
    
    需要安裝: pip install google-generativeai
    取得 API Key: https://makersuite.google.com/app/apikey
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = None
        self._initialize()
    
    def _initialize(self):
        """初始化 Gemini API"""
        if not self.api_key or self.api_key == "YOUR_GEMINI_API_KEY":
            logger.warning("Gemini API Key 未設定")
            return
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
            logger.info("Gemini API 初始化成功")
        except ImportError:
            logger.error("請安裝 google-generativeai: pip install google-generativeai")
        except Exception as e:
            logger.error(f"Gemini API 初始化失敗: {e}")
    
    def analyze_stock(self, stock_data: Dict) -> str:
        """
        分析單一股票
        """
        if not self.model:
            return self._mock_analysis(stock_data)
        
        prompt = self._build_analysis_prompt(stock_data)
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini 分析錯誤: {e}")
            return self._mock_analysis(stock_data)
    
    def _build_analysis_prompt(self, stock_data: Dict) -> str:
        """
        建立分析提示詞
        """
        stock_id = stock_data.get('stock_id', 'N/A')
        price = stock_data.get('price', 0)
        change = stock_data.get('price_change', 0)
        
        # SMC 資料
        smc = stock_data.get('smc_summary', {})
        smc_trend = smc.get('swing_trend', 'N/A')
        smc_signal = smc.get('signal', 'N/A')
        smc_strength = smc.get('signal_strength', 0)
        zone_position = smc.get('zone_position', 0.5)
        
        # UT Bot 資料
        ut = stock_data.get('ut_summary', {})
        ut_trend = ut.get('trend', 'N/A')
        ut_signal = ut.get('signal', 'N/A')
        
        # 籌碼資料
        chip = stock_data.get('chip_summary', {})
        foreign_net = chip.get('foreign', {}).get('net', 0)
        trust_net = chip.get('investment_trust', {}).get('net', 0)
        chip_signal = chip.get('signal', 'N/A')
        
        prompt = f"""
你是一位專業的股票技術分析師，請根據以下資料分析這檔股票：

股票代碼：{stock_id}
目前價格：{price:.2f}
漲跌幅：{change:+.2f}%

【SMC (Smart Money Concepts) 分析】
- Swing 趨勢：{smc_trend}
- 結構信號：{smc_signal}
- 信號強度：{smc_strength}/100
- 價格位置：{'折價區' if zone_position < 0.5 else '溢價區'} ({zone_position:.1%})
- Order Blocks：多方 {smc.get('bullish_order_blocks', 0)} 個 / 空方 {smc.get('bearish_order_blocks', 0)} 個
- Fair Value Gaps：多方 {smc.get('bullish_fvg', 0)} 個 / 空方 {smc.get('bearish_fvg', 0)} 個

【UT Bot 分析】
- 趨勢：{ut_trend}
- 信號：{ut_signal}
- ATR Trailing Stop：{ut.get('atr_stop', 0):.2f}

【籌碼分析】
- 外資買賣超：{foreign_net:+,} 張
- 投信買賣超：{trust_net:+,} 張
- 籌碼信號：{chip_signal}

請提供：
1. 綜合分析（50字以內）
2. 操作建議（買進/觀望/賣出）
3. 關鍵支撐壓力位
4. 風險提示

請用繁體中文回答，簡潔扼要。
"""
        return prompt
    
    def _mock_analysis(self, stock_data: Dict) -> str:
        """
        模擬分析（當 API 不可用時）
        """
        stock_id = stock_data.get('stock_id', 'N/A')
        smc = stock_data.get('smc_summary', {})
        ut = stock_data.get('ut_summary', {})
        chip = stock_data.get('chip_summary', {})
        
        # 簡單的規則式分析
        signals = []
        
        # SMC 信號
        smc_signal = smc.get('signal', '')
        if 'bull' in str(smc_signal).lower():
            signals.append(('bullish', 'SMC 出現多方結構信號'))
        elif 'bear' in str(smc_signal).lower():
            signals.append(('bearish', 'SMC 出現空方結構信號'))
        
        # UT Bot 信號
        ut_signal = ut.get('signal', '')
        if ut_signal == 'buy':
            signals.append(('bullish', 'UT Bot 發出買進信號'))
        elif ut_signal == 'sell':
            signals.append(('bearish', 'UT Bot 發出賣出信號'))
        
        # 籌碼信號
        chip_signal = chip.get('signal', '')
        if 'buy' in str(chip_signal).lower():
            signals.append(('bullish', '籌碼面偏多'))
        elif 'sell' in str(chip_signal).lower():
            signals.append(('bearish', '籌碼面偏空'))
        
        # 綜合判斷
        bullish_count = sum(1 for s in signals if s[0] == 'bullish')
        bearish_count = sum(1 for s in signals if s[0] == 'bearish')
        
        if bullish_count > bearish_count:
            recommendation = "偏多操作"
            analysis = "多項指標顯示多方訊號"
        elif bearish_count > bullish_count:
            recommendation = "偏空操作"
            analysis = "多項指標顯示空方訊號"
        else:
            recommendation = "觀望為主"
            analysis = "指標訊號分歧，建議觀望"
        
        # 建立回應
        response = f"""
【{stock_id} AI 分析】

📊 綜合分析：
{analysis}

🎯 操作建議：{recommendation}

📝 信號摘要：
"""
        for signal_type, desc in signals:
            emoji = '📈' if signal_type == 'bullish' else '📉'
            response += f"• {emoji} {desc}\n"
        
        response += f"""
⚠️ 風險提示：
此為 AI 輔助分析，僅供參考，投資決策請自行判斷。

⏰ 分析時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        return response
    
    def analyze_market_overview(self, results: List[Dict]) -> str:
        """
        分析整體市場概況
        """
        if not results:
            return "無足夠資料進行市場分析"
        
        # 統計
        bullish_count = sum(1 for r in results if 'bull' in str(r.get('smc_signal', '')).lower())
        bearish_count = sum(1 for r in results if 'bear' in str(r.get('smc_signal', '')).lower())
        ut_buy = sum(1 for r in results if r.get('ut_signal') == 'buy')
        ut_sell = sum(1 for r in results if r.get('ut_signal') == 'sell')
        
        # 計算平均漲跌
        avg_change = sum(r.get('price_change', 0) for r in results) / len(results) if results else 0
        
        if not self.model:
            # 簡易分析
            if bullish_count > bearish_count * 1.5:
                sentiment = "偏多"
            elif bearish_count > bullish_count * 1.5:
                sentiment = "偏空"
            else:
                sentiment = "中性"
            
            return f"""
【市場概況分析】

📊 掃描統計：
• 總共掃描：{len(results)} 檔
• 平均漲跌：{avg_change:+.2f}%

🔍 SMC 信號分布：
• 多方信號：{bullish_count} 檔 ({bullish_count/len(results)*100:.1f}%)
• 空方信號：{bearish_count} 檔 ({bearish_count/len(results)*100:.1f}%)

🤖 UT Bot 信號：
• 買進信號：{ut_buy} 檔
• 賣出信號：{ut_sell} 檔

📈 市場情緒：{sentiment}

⏰ 分析時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
        
        prompt = f"""
請分析以下台股市場掃描結果：

掃描股票數：{len(results)}
平均漲跌：{avg_change:+.2f}%

SMC 多方信號：{bullish_count} 檔
SMC 空方信號：{bearish_count} 檔
UT Bot 買進信號：{ut_buy} 檔
UT Bot 賣出信號：{ut_sell} 檔

請提供：
1. 目前市場情緒判斷
2. 短期操作建議
3. 需要注意的風險

請用繁體中文，簡潔回答（100字以內）。
"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini 市場分析錯誤: {e}")
            return "AI 市場分析暫時無法使用"
    
    def get_trading_suggestion(self, stock_data: Dict) -> Dict:
        """
        取得交易建議（結構化輸出）
        """
        smc = stock_data.get('smc_summary', {})
        ut = stock_data.get('ut_summary', {})
        chip = stock_data.get('chip_summary', {})
        
        # 計算綜合分數
        score = 50  # 基礎分數
        reasons = []
        
        # SMC 信號
        smc_signal = str(smc.get('signal', '')).lower()
        if 'choch_bull' in smc_signal:
            score += 20
            reasons.append("SMC CHoCH 多方反轉")
        elif 'bos_bull' in smc_signal:
            score += 15
            reasons.append("SMC BOS 多方延續")
        elif 'choch_bear' in smc_signal:
            score -= 20
            reasons.append("SMC CHoCH 空方反轉")
        elif 'bos_bear' in smc_signal:
            score -= 15
            reasons.append("SMC BOS 空方延續")
        
        # 價格位置
        if smc.get('in_discount'):
            score += 10
            reasons.append("處於折價區")
        elif smc.get('in_premium'):
            score -= 10
            reasons.append("處於溢價區")
        
        # UT Bot 信號
        if ut.get('signal') == 'buy':
            score += 15
            reasons.append("UT Bot 買進信號")
        elif ut.get('signal') == 'sell':
            score -= 15
            reasons.append("UT Bot 賣出信號")
        
        # 籌碼信號
        chip_signal = str(chip.get('signal', '')).lower()
        if 'strong_buy' in chip_signal:
            score += 15
            reasons.append("籌碼強力買超")
        elif 'buy' in chip_signal:
            score += 10
            reasons.append("籌碼買超")
        elif 'strong_sell' in chip_signal:
            score -= 15
            reasons.append("籌碼強力賣超")
        elif 'sell' in chip_signal:
            score -= 10
            reasons.append("籌碼賣超")
        
        # 限制分數範圍
        score = max(0, min(100, score))
        
        # 決定建議
        if score >= 70:
            action = 'buy'
            confidence = 'high'
        elif score >= 55:
            action = 'buy'
            confidence = 'medium'
        elif score <= 30:
            action = 'sell'
            confidence = 'high'
        elif score <= 45:
            action = 'sell'
            confidence = 'medium'
        else:
            action = 'hold'
            confidence = 'low'
        
        return {
            'score': score,
            'action': action,
            'confidence': confidence,
            'reasons': reasons,
            'stop_loss': ut.get('atr_stop', 0),
        }


# ============================================================
# 測試函數
# ============================================================

def test_gemini_analyzer():
    """測試 Gemini 分析器"""
    analyzer = GeminiAnalyzer("YOUR_GEMINI_API_KEY")
    
    # 模擬股票資料
    stock_data = {
        'stock_id': '2330',
        'price': 580.0,
        'price_change': 2.5,
        'smc_summary': {
            'swing_trend': 'bullish',
            'signal': 'CHoCH_bull',
            'signal_strength': 90,
            'zone_position': 0.35,
            'in_discount': True,
            'bullish_order_blocks': 2,
            'bearish_order_blocks': 1,
            'bullish_fvg': 3,
            'bearish_fvg': 1,
        },
        'ut_summary': {
            'trend': 'bullish',
            'signal': 'buy',
            'atr_stop': 565.5,
        },
        'chip_summary': {
            'foreign': {'net': 15000},
            'investment_trust': {'net': 3000},
            'signal': 'strong_buy',
        },
    }
    
    print("=" * 50)
    print("單一股票分析：")
    print(analyzer.analyze_stock(stock_data))
    
    print("\n" + "=" * 50)
    print("交易建議：")
    suggestion = analyzer.get_trading_suggestion(stock_data)
    for key, value in suggestion.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 50)
    print("市場概況分析：")
    mock_results = [
        {'smc_signal': 'CHoCH_bull', 'ut_signal': 'buy', 'price_change': 2.5},
        {'smc_signal': 'BOS_bull', 'ut_signal': 'hold', 'price_change': 1.2},
        {'smc_signal': 'BOS_bear', 'ut_signal': 'sell', 'price_change': -1.5},
    ]
    print(analyzer.analyze_market_overview(mock_results))


if __name__ == "__main__":
    test_gemini_analyzer()
