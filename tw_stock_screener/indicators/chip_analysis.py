"""
籌碼分析模組 - 三大法人買賣超分析
================================
分析外資、投信、自營商的買賣行為
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ChipAnalysisResult:
    """籌碼分析結果"""
    foreign_net: int = 0           # 外資買賣超
    investment_trust_net: int = 0  # 投信買賣超
    dealer_net: int = 0            # 自營商買賣超
    total_net: int = 0             # 三大法人合計
    foreign_consecutive: int = 0   # 外資連續買超天數（負數為連續賣超）
    trust_consecutive: int = 0     # 投信連續買超天數
    foreign_5d_net: int = 0        # 外資近 5 日買賣超
    trust_5d_net: int = 0          # 投信近 5 日買賣超
    signal: str = 'neutral'        # 籌碼信號
    strength: int = 0              # 信號強度


def analyze_chip_data(df: pd.DataFrame, config: Dict = None) -> ChipAnalysisResult:
    """
    分析籌碼資料
    
    參數:
    - df: 籌碼資料 DataFrame，需包含：
        - date
        - foreign_net: 外資買賣超
        - investment_trust_net: 投信買賣超
        - dealer_net: 自營商買賣超
    - config: 配置參數
    
    返回:
    - ChipAnalysisResult
    """
    if df is None or len(df) == 0:
        return ChipAnalysisResult()
    
    config = config or {
        'foreign_threshold': 1000,
        'investment_trust_threshold': 500,
        'dealer_threshold': 500,
        'consecutive_days': 3,
    }
    
    result = ChipAnalysisResult()
    
    # 取最新一日資料
    df = df.sort_values('date').reset_index(drop=True)
    latest = df.iloc[-1]
    
    result.foreign_net = int(latest.get('foreign_net', 0))
    result.investment_trust_net = int(latest.get('investment_trust_net', 0))
    result.dealer_net = int(latest.get('dealer_net', 0))
    result.total_net = result.foreign_net + result.investment_trust_net + result.dealer_net
    
    # 計算連續買賣超天數
    result.foreign_consecutive = _calculate_consecutive_days(df, 'foreign_net')
    result.trust_consecutive = _calculate_consecutive_days(df, 'investment_trust_net')
    
    # 計算近 5 日買賣超
    if len(df) >= 5:
        result.foreign_5d_net = int(df['foreign_net'].tail(5).sum())
        result.trust_5d_net = int(df['investment_trust_net'].tail(5).sum())
    
    # 判斷籌碼信號
    signal, strength = _determine_chip_signal(result, config)
    result.signal = signal
    result.strength = strength
    
    return result


def _calculate_consecutive_days(df: pd.DataFrame, column: str) -> int:
    """
    計算連續買超/賣超天數
    正數 = 連續買超天數
    負數 = 連續賣超天數
    """
    if column not in df.columns or len(df) == 0:
        return 0
    
    values = df[column].values
    
    # 從最新一天往回數
    consecutive = 0
    last_sign = np.sign(values[-1])
    
    for i in range(len(values) - 1, -1, -1):
        current_sign = np.sign(values[i])
        if current_sign == last_sign and current_sign != 0:
            consecutive += 1
        else:
            break
    
    return consecutive * int(last_sign) if last_sign != 0 else 0


def _determine_chip_signal(result: ChipAnalysisResult, config: Dict) -> tuple:
    """
    判斷籌碼信號
    """
    signal = 'neutral'
    strength = 0
    
    foreign_threshold = config.get('foreign_threshold', 1000)
    trust_threshold = config.get('investment_trust_threshold', 500)
    consecutive_threshold = config.get('consecutive_days', 3)
    
    # 強烈買進信號：外資 + 投信同步買超
    if (result.foreign_net > foreign_threshold and 
        result.investment_trust_net > trust_threshold):
        signal = 'strong_buy'
        strength = 90
    
    # 買進信號：外資大買
    elif result.foreign_net > foreign_threshold * 2:
        signal = 'buy'
        strength = 80
    
    # 買進信號：投信連續買超
    elif (result.investment_trust_net > trust_threshold and 
          result.trust_consecutive >= consecutive_threshold):
        signal = 'buy'
        strength = 75
    
    # 外資連續買超
    elif result.foreign_consecutive >= consecutive_threshold:
        signal = 'accumulating'
        strength = 60
    
    # 強烈賣出信號：外資 + 投信同步賣超
    elif (result.foreign_net < -foreign_threshold and 
          result.investment_trust_net < -trust_threshold):
        signal = 'strong_sell'
        strength = 90
    
    # 賣出信號：外資大賣
    elif result.foreign_net < -foreign_threshold * 2:
        signal = 'sell'
        strength = 80
    
    # 外資連續賣超
    elif result.foreign_consecutive <= -consecutive_threshold:
        signal = 'distributing'
        strength = 60
    
    # 中性偏多
    elif result.total_net > 0:
        signal = 'slight_buy'
        strength = 40
    
    # 中性偏空
    elif result.total_net < 0:
        signal = 'slight_sell'
        strength = 40
    
    return signal, strength


def get_chip_analysis_summary(result: ChipAnalysisResult) -> Dict:
    """
    取得籌碼分析摘要
    """
    return {
        'foreign': {
            'net': result.foreign_net,
            'consecutive_days': result.foreign_consecutive,
            '5d_net': result.foreign_5d_net,
        },
        'investment_trust': {
            'net': result.investment_trust_net,
            'consecutive_days': result.trust_consecutive,
            '5d_net': result.trust_5d_net,
        },
        'dealer': {
            'net': result.dealer_net,
        },
        'total_net': result.total_net,
        'signal': result.signal,
        'strength': result.strength,
        'description': _get_signal_description(result),
    }


def _get_signal_description(result: ChipAnalysisResult) -> str:
    """
    取得信號描述
    """
    descriptions = {
        'strong_buy': '外資+投信同步買超，籌碼面強勢',
        'buy': '主力積極布局',
        'accumulating': f'外資連續買超 {result.foreign_consecutive} 天',
        'slight_buy': '三大法人小幅買超',
        'neutral': '籌碼面中性',
        'slight_sell': '三大法人小幅賣超',
        'distributing': f'外資連續賣超 {abs(result.foreign_consecutive)} 天',
        'sell': '主力積極出貨',
        'strong_sell': '外資+投信同步賣超，籌碼面弱勢',
    }
    
    base_desc = descriptions.get(result.signal, '籌碼面中性')
    
    # 加入額外資訊
    extra = []
    if result.trust_consecutive >= 3:
        extra.append(f'投信連買 {result.trust_consecutive} 天')
    elif result.trust_consecutive <= -3:
        extra.append(f'投信連賣 {abs(result.trust_consecutive)} 天')
    
    if extra:
        base_desc += f'（{", ".join(extra)}）'
    
    return base_desc


def format_chip_data(result: ChipAnalysisResult) -> str:
    """
    格式化籌碼資料為可讀字串
    """
    def format_num(n):
        if abs(n) >= 10000:
            return f"{n/10000:.1f}萬張"
        elif abs(n) >= 1000:
            return f"{n/1000:.1f}千張"
        else:
            return f"{n}張"
    
    lines = [
        f"📊 籌碼分析",
        f"外資: {format_num(result.foreign_net)} {'📈' if result.foreign_net > 0 else '📉' if result.foreign_net < 0 else '➖'}",
        f"投信: {format_num(result.investment_trust_net)} {'📈' if result.investment_trust_net > 0 else '📉' if result.investment_trust_net < 0 else '➖'}",
        f"自營: {format_num(result.dealer_net)}",
        f"合計: {format_num(result.total_net)}",
    ]
    
    if result.foreign_consecutive != 0:
        lines.append(f"外資連續{'買' if result.foreign_consecutive > 0 else '賣'}超: {abs(result.foreign_consecutive)} 天")
    
    if result.trust_consecutive != 0:
        lines.append(f"投信連續{'買' if result.trust_consecutive > 0 else '賣'}超: {abs(result.trust_consecutive)} 天")
    
    lines.append(f"信號: {result.signal} (強度: {result.strength})")
    
    return "\n".join(lines)


# ============================================================
# 測試函數
# ============================================================

def test_chip_analysis():
    """測試籌碼分析"""
    # 模擬籌碼資料
    dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
    
    df = pd.DataFrame({
        'date': dates,
        'foreign_net': [1000, 1500, 2000, 1800, 2500, 3000, 2800, 3500, 4000, 5000],
        'investment_trust_net': [200, 300, -100, 500, 600, 800, 700, 900, 1000, 1200],
        'dealer_net': [-100, 200, -200, 100, -50, 300, -100, 200, 100, -200],
    })
    
    result = analyze_chip_data(df)
    
    print("籌碼分析結果：")
    print(format_chip_data(result))
    
    print("\n詳細摘要：")
    summary = get_chip_analysis_summary(result)
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    test_chip_analysis()
