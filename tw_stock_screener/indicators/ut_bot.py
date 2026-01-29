"""
UT Bot 指標模組
==============
根據 TradingView Pine Script 轉換為 Python

UT Bot Alerts 是一個基於 ATR 的趨勢追蹤指標
- 使用 ATR Trailing Stop 判斷趨勢
- 支援 Heikin Ashi 蠟燭計算
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    計算 ATR (Average True Range)
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ATR = TR 的移動平均
    atr = tr.rolling(window=period).mean()
    
    return atr


def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    計算 Heikin Ashi 蠟燭
    """
    ha_df = df.copy()
    
    # HA Close = (Open + High + Low + Close) / 4
    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # HA Open = (Previous HA Open + Previous HA Close) / 2
    ha_df['ha_open'] = 0.0
    ha_df.iloc[0, ha_df.columns.get_loc('ha_open')] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    
    for i in range(1, len(ha_df)):
        ha_df.iloc[i, ha_df.columns.get_loc('ha_open')] = (
            ha_df['ha_open'].iloc[i-1] + ha_df['ha_close'].iloc[i-1]
        ) / 2
    
    # HA High = max(High, HA Open, HA Close)
    ha_df['ha_high'] = pd.concat([df['high'], ha_df['ha_open'], ha_df['ha_close']], axis=1).max(axis=1)
    
    # HA Low = min(Low, HA Open, HA Close)
    ha_df['ha_low'] = pd.concat([df['low'], ha_df['ha_open'], ha_df['ha_close']], axis=1).min(axis=1)
    
    return ha_df


def calculate_ut_bot(
    df: pd.DataFrame,
    key_value: float = 1.0,
    atr_period: int = 10,
    use_heikin_ashi: bool = True
) -> pd.DataFrame:
    """
    計算 UT Bot 指標
    
    參數:
    - df: 包含 OHLCV 的 DataFrame
    - key_value: 靈敏度參數 (越小越敏感)
    - atr_period: ATR 週期
    - use_heikin_ashi: 是否使用 Heikin Ashi 計算
    
    返回:
    - 包含 UT Bot 信號的 DataFrame
    """
    df = df.copy()
    
    # 計算 ATR
    df['atr'] = calculate_atr(df, atr_period)
    df['n_loss'] = key_value * df['atr']
    
    # 決定使用的價格來源
    if use_heikin_ashi:
        ha_df = calculate_heikin_ashi(df)
        src = ha_df['ha_close']
    else:
        src = df['close']
    
    df['src'] = src
    
    # 計算 ATR Trailing Stop
    df['atr_trailing_stop'] = 0.0
    
    for i in range(1, len(df)):
        n_loss = df['n_loss'].iloc[i]
        prev_stop = df['atr_trailing_stop'].iloc[i-1]
        curr_src = df['src'].iloc[i]
        prev_src = df['src'].iloc[i-1]
        
        if curr_src > prev_stop and prev_src > prev_stop:
            # 多頭趨勢中，Stop 只能上升
            df.iloc[i, df.columns.get_loc('atr_trailing_stop')] = max(prev_stop, curr_src - n_loss)
        elif curr_src < prev_stop and prev_src < prev_stop:
            # 空頭趨勢中，Stop 只能下降
            df.iloc[i, df.columns.get_loc('atr_trailing_stop')] = min(prev_stop, curr_src + n_loss)
        elif curr_src > prev_stop:
            df.iloc[i, df.columns.get_loc('atr_trailing_stop')] = curr_src - n_loss
        else:
            df.iloc[i, df.columns.get_loc('atr_trailing_stop')] = curr_src + n_loss
    
    # 計算位置 (多頭/空頭)
    df['ut_pos'] = 0
    for i in range(1, len(df)):
        prev_stop = df['atr_trailing_stop'].iloc[i-1]
        curr_src = df['src'].iloc[i]
        prev_src = df['src'].iloc[i-1]
        prev_pos = df['ut_pos'].iloc[i-1]
        
        if prev_src < prev_stop and curr_src > prev_stop:
            df.iloc[i, df.columns.get_loc('ut_pos')] = 1  # 轉多
        elif prev_src > prev_stop and curr_src < prev_stop:
            df.iloc[i, df.columns.get_loc('ut_pos')] = -1  # 轉空
        else:
            df.iloc[i, df.columns.get_loc('ut_pos')] = prev_pos
    
    # 計算 EMA (用於交叉判斷)
    df['ut_ema'] = df['src'].ewm(span=1, adjust=False).mean()
    
    # 判斷買賣信號
    df['ut_above'] = (df['ut_ema'] > df['atr_trailing_stop']) & (df['ut_ema'].shift(1) <= df['atr_trailing_stop'].shift(1))
    df['ut_below'] = (df['ut_ema'] < df['atr_trailing_stop']) & (df['ut_ema'].shift(1) >= df['atr_trailing_stop'].shift(1))
    
    # Buy: 價格在 Stop 之上 且 向上穿越
    df['ut_buy'] = (df['src'] > df['atr_trailing_stop']) & df['ut_above']
    
    # Sell: 價格在 Stop 之下 且 向下穿越
    df['ut_sell'] = (df['src'] < df['atr_trailing_stop']) & df['ut_below']
    
    # 目前是否在多頭/空頭區間
    df['ut_bullish'] = df['src'] > df['atr_trailing_stop']
    df['ut_bearish'] = df['src'] < df['atr_trailing_stop']
    
    return df


def get_ut_bot_signal(df: pd.DataFrame) -> Dict:
    """
    取得最新的 UT Bot 信號
    
    返回:
    - signal: 'buy', 'sell', 'hold'
    - trend: 'bullish', 'bearish'
    - atr_stop: ATR Trailing Stop 值
    - strength: 信號強度 (0-100)
    """
    if len(df) < 2:
        return {'signal': 'hold', 'trend': 'neutral', 'atr_stop': None, 'strength': 0}
    
    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    signal = 'hold'
    trend = 'neutral'
    strength = 0
    
    if last_row['ut_buy']:
        signal = 'buy'
        strength = 90
    elif last_row['ut_sell']:
        signal = 'sell'
        strength = 90
    elif last_row['ut_bullish']:
        trend = 'bullish'
        strength = 50
    elif last_row['ut_bearish']:
        trend = 'bearish'
        strength = 50
    
    # 計算價格與 Stop 的距離來調整強度
    if last_row['atr_trailing_stop'] > 0:
        distance_pct = abs(last_row['close'] - last_row['atr_trailing_stop']) / last_row['close'] * 100
        if distance_pct > 3:
            strength = min(strength + 20, 100)
    
    return {
        'signal': signal,
        'trend': 'bullish' if last_row['ut_bullish'] else ('bearish' if last_row['ut_bearish'] else 'neutral'),
        'atr_stop': last_row['atr_trailing_stop'],
        'strength': strength,
        'current_price': last_row['close'],
        'distance_from_stop': abs(last_row['close'] - last_row['atr_trailing_stop']) if last_row['atr_trailing_stop'] > 0 else 0
    }


def calculate_ema_ribbon(
    df: pd.DataFrame,
    periods: list = [5, 20, 60, 120, 240]
) -> pd.DataFrame:
    """
    計算 EMA Ribbon
    """
    df = df.copy()
    
    for period in periods:
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    
    # 判斷 EMA 排列
    if all(f'ema_{p}' in df.columns for p in periods):
        last_row = df.iloc[-1]
        ema_values = [last_row[f'ema_{p}'] for p in sorted(periods)]
        
        # 多頭排列：短期 EMA > 長期 EMA
        df['ema_bullish'] = all(ema_values[i] >= ema_values[i+1] for i in range(len(ema_values)-1))
        
        # 空頭排列：短期 EMA < 長期 EMA
        df['ema_bearish'] = all(ema_values[i] <= ema_values[i+1] for i in range(len(ema_values)-1))
    
    return df


# ============================================================
# 測試函數
# ============================================================

def test_ut_bot():
    """測試 UT Bot 計算"""
    # 生成測試資料
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    # 模擬股價走勢
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    high = close + np.abs(np.random.randn(100))
    low = close - np.abs(np.random.randn(100))
    open_price = close + np.random.randn(100) * 0.5
    volume = np.random.randint(1000000, 5000000, 100)
    
    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    # 計算 UT Bot
    result = calculate_ut_bot(df, key_value=1.0, atr_period=10, use_heikin_ashi=True)
    
    print("UT Bot 計算結果：")
    print(result[['date', 'close', 'atr_trailing_stop', 'ut_buy', 'ut_sell', 'ut_bullish']].tail(10))
    
    # 取得最新信號
    signal = get_ut_bot_signal(result)
    print(f"\n最新信號: {signal}")
    
    # 計算 EMA Ribbon
    result = calculate_ema_ribbon(result)
    print(f"\nEMA Ribbon:")
    for p in [5, 20, 60, 120, 240]:
        if f'ema_{p}' in result.columns:
            print(f"  EMA {p}: {result[f'ema_{p}'].iloc[-1]:.2f}")


if __name__ == "__main__":
    test_ut_bot()
