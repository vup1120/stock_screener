"""
SMC (Smart Money Concepts) 指標模組
====================================
根據 LuxAlgo Smart Money Concepts 指標轉換為 Python

包含功能:
- Swing High/Low 偵測
- BOS (Break of Structure) 結構突破
- CHoCH (Change of Character) 性格轉變
- Order Blocks 訂單塊
- Fair Value Gaps (FVG) 公允價值缺口
- Equal Highs/Lows 等高/等低
- Premium/Discount Zones 溢價/折價區
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TrendBias(Enum):
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0


@dataclass
class Pivot:
    """樞紐點資料結構"""
    level: float
    bar_index: int
    bar_time: pd.Timestamp = None
    crossed: bool = False
    last_level: float = 0.0


@dataclass
class OrderBlock:
    """訂單塊資料結構"""
    high: float
    low: float
    bar_index: int
    bar_time: pd.Timestamp
    bias: TrendBias
    mitigated: bool = False


@dataclass
class FairValueGap:
    """公允價值缺口資料結構"""
    top: float
    bottom: float
    bar_index: int
    bar_time: pd.Timestamp
    bias: TrendBias
    filled: bool = False


@dataclass
class StructureSignal:
    """結構信號資料結構"""
    signal_type: str  # 'BOS' or 'CHoCH'
    bias: TrendBias   # BULLISH or BEARISH
    level: float
    bar_index: int
    bar_time: pd.Timestamp = None


class SMCCalculator:
    """
    Smart Money Concepts 計算器
    """
    
    def __init__(
        self,
        swing_length: int = 50,
        internal_length: int = 5,
        equal_hl_threshold: float = 0.1,
        order_block_filter: str = 'atr',
        fvg_threshold: bool = True,
        show_internal_structure: bool = True,
        show_swing_structure: bool = True,
        show_order_blocks: bool = True,
        show_fvg: bool = True,
    ):
        self.swing_length = swing_length
        self.internal_length = internal_length
        self.equal_hl_threshold = equal_hl_threshold
        self.order_block_filter = order_block_filter
        self.fvg_threshold = fvg_threshold
        self.show_internal_structure = show_internal_structure
        self.show_swing_structure = show_swing_structure
        self.show_order_blocks = show_order_blocks
        self.show_fvg = show_fvg
        
        # 初始化狀態
        self.swing_high = Pivot(level=0, bar_index=0)
        self.swing_low = Pivot(level=0, bar_index=0)
        self.internal_high = Pivot(level=0, bar_index=0)
        self.internal_low = Pivot(level=0, bar_index=0)
        
        self.swing_trend = TrendBias.NEUTRAL
        self.internal_trend = TrendBias.NEUTRAL
        
        self.order_blocks: List[OrderBlock] = []
        self.fair_value_gaps: List[FairValueGap] = []
        self.structure_signals: List[StructureSignal] = []
    
    def _find_swing_points(self, df: pd.DataFrame, lookback: int) -> pd.DataFrame:
        """
        找出 Swing High 和 Swing Low
        使用 Pivot 概念：當前點是前後 lookback 根 K 線中的最高/最低點
        """
        df = df.copy()
        df['swing_high'] = False
        df['swing_low'] = False
        df['swing_high_level'] = np.nan
        df['swing_low_level'] = np.nan
        
        for i in range(lookback, len(df) - lookback):
            # Swing High
            window_high = df['high'].iloc[i-lookback:i+lookback+1].max()
            if df['high'].iloc[i] == window_high:
                df.loc[df.index[i], 'swing_high'] = True
                df.loc[df.index[i], 'swing_high_level'] = df['high'].iloc[i]
            
            # Swing Low
            window_low = df['low'].iloc[i-lookback:i+lookback+1].min()
            if df['low'].iloc[i] == window_low:
                df.loc[df.index[i], 'swing_low'] = True
                df.loc[df.index[i], 'swing_low_level'] = df['low'].iloc[i]
        
        return df
    
    def _detect_leg(self, df: pd.DataFrame, size: int) -> pd.DataFrame:
        """
        偵測腿部方向 (Bullish leg / Bearish leg)
        """
        df = df.copy()
        df['leg'] = 0
        
        for i in range(size, len(df)):
            # 新的 Bearish leg: 當前高點比前 size 根 K 線的最高點還高
            if df['high'].iloc[i] > df['high'].iloc[i-size:i].max():
                df.loc[df.index[i], 'leg'] = 0  # Bearish leg
            # 新的 Bullish leg: 當前低點比前 size 根 K 線的最低點還低
            elif df['low'].iloc[i] < df['low'].iloc[i-size:i].min():
                df.loc[df.index[i], 'leg'] = 1  # Bullish leg
            else:
                df.loc[df.index[i], 'leg'] = df['leg'].iloc[i-1]
        
        return df
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 200) -> pd.Series:
        """計算 ATR"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        
        return atr
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        執行完整的 SMC 計算
        """
        df = df.copy()
        
        # 計算 ATR
        df['atr'] = self._calculate_atr(df)
        df['volatility'] = df['atr'] if self.order_block_filter == 'atr' else (df['high'] - df['low']).expanding().mean()
        
        # 找出 Swing 結構
        df = self._find_swing_points(df, self.swing_length)
        df = df.rename(columns={
            'swing_high': 'swing_high_point',
            'swing_low': 'swing_low_point'
        })
        
        # 找出 Internal 結構
        df_internal = self._find_swing_points(df, self.internal_length)
        df['internal_high_point'] = df_internal['swing_high']
        df['internal_low_point'] = df_internal['swing_low']
        df['internal_high_level'] = df_internal['swing_high_level']
        df['internal_low_level'] = df_internal['swing_low_level']
        
        # 偵測腿部方向
        df = self._detect_leg(df, self.swing_length)
        
        # 初始化信號欄位
        df['bos_bull'] = False
        df['bos_bear'] = False
        df['choch_bull'] = False
        df['choch_bear'] = False
        df['internal_bos_bull'] = False
        df['internal_bos_bear'] = False
        df['internal_choch_bull'] = False
        df['internal_choch_bear'] = False
        df['swing_trend'] = 0
        df['internal_trend'] = 0
        
        # 偵測結構突破
        df = self._detect_structure(df)
        
        # 偵測 Order Blocks
        df = self._detect_order_blocks(df)
        
        # 偵測 FVG
        df = self._detect_fvg(df)
        
        # 偵測 Equal Highs/Lows
        df = self._detect_equal_hl(df)
        
        # 計算 Premium/Discount 區域
        df = self._calculate_zones(df)
        
        return df
    
    def _detect_structure(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        偵測市場結構 (BOS 和 CHoCH)
        """
        swing_high_level = 0.0
        swing_low_level = float('inf')
        internal_high_level = 0.0
        internal_low_level = float('inf')
        
        swing_high_crossed = False
        swing_low_crossed = False
        internal_high_crossed = False
        internal_low_crossed = False
        
        swing_trend = TrendBias.NEUTRAL
        internal_trend = TrendBias.NEUTRAL
        
        for i in range(1, len(df)):
            close = df['close'].iloc[i]
            
            # 更新 Swing High/Low
            if df['swing_high_point'].iloc[i]:
                swing_high_level = df['high'].iloc[i]
                swing_high_crossed = False
            
            if df['swing_low_point'].iloc[i]:
                swing_low_level = df['low'].iloc[i]
                swing_low_crossed = False
            
            # 更新 Internal High/Low
            if df['internal_high_point'].iloc[i]:
                internal_high_level = df['high'].iloc[i]
                internal_high_crossed = False
            
            if df['internal_low_point'].iloc[i]:
                internal_low_level = df['low'].iloc[i]
                internal_low_crossed = False
            
            # Swing 結構突破檢測
            # Bullish: 收盤價突破前高
            if close > swing_high_level and not swing_high_crossed and swing_high_level > 0:
                swing_high_crossed = True
                if swing_trend == TrendBias.BEARISH:
                    df.loc[df.index[i], 'choch_bull'] = True
                    self.structure_signals.append(StructureSignal(
                        signal_type='CHoCH',
                        bias=TrendBias.BULLISH,
                        level=swing_high_level,
                        bar_index=i,
                        bar_time=df['date'].iloc[i] if 'date' in df.columns else None
                    ))
                else:
                    df.loc[df.index[i], 'bos_bull'] = True
                    self.structure_signals.append(StructureSignal(
                        signal_type='BOS',
                        bias=TrendBias.BULLISH,
                        level=swing_high_level,
                        bar_index=i,
                        bar_time=df['date'].iloc[i] if 'date' in df.columns else None
                    ))
                swing_trend = TrendBias.BULLISH
            
            # Bearish: 收盤價跌破前低
            if close < swing_low_level and not swing_low_crossed and swing_low_level < float('inf'):
                swing_low_crossed = True
                if swing_trend == TrendBias.BULLISH:
                    df.loc[df.index[i], 'choch_bear'] = True
                    self.structure_signals.append(StructureSignal(
                        signal_type='CHoCH',
                        bias=TrendBias.BEARISH,
                        level=swing_low_level,
                        bar_index=i,
                        bar_time=df['date'].iloc[i] if 'date' in df.columns else None
                    ))
                else:
                    df.loc[df.index[i], 'bos_bear'] = True
                    self.structure_signals.append(StructureSignal(
                        signal_type='BOS',
                        bias=TrendBias.BEARISH,
                        level=swing_low_level,
                        bar_index=i,
                        bar_time=df['date'].iloc[i] if 'date' in df.columns else None
                    ))
                swing_trend = TrendBias.BEARISH
            
            # Internal 結構突破檢測
            if close > internal_high_level and not internal_high_crossed and internal_high_level > 0:
                internal_high_crossed = True
                if internal_trend == TrendBias.BEARISH:
                    df.loc[df.index[i], 'internal_choch_bull'] = True
                else:
                    df.loc[df.index[i], 'internal_bos_bull'] = True
                internal_trend = TrendBias.BULLISH
            
            if close < internal_low_level and not internal_low_crossed and internal_low_level < float('inf'):
                internal_low_crossed = True
                if internal_trend == TrendBias.BULLISH:
                    df.loc[df.index[i], 'internal_choch_bear'] = True
                else:
                    df.loc[df.index[i], 'internal_bos_bear'] = True
                internal_trend = TrendBias.BEARISH
            
            df.loc[df.index[i], 'swing_trend'] = swing_trend.value
            df.loc[df.index[i], 'internal_trend'] = internal_trend.value
        
        self.swing_trend = swing_trend
        self.internal_trend = internal_trend
        
        return df
    
    def _detect_order_blocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        偵測 Order Blocks
        Order Block = 大幅移動前的最後一根反向 K 線
        """
        df['bullish_ob'] = False
        df['bearish_ob'] = False
        df['ob_high'] = np.nan
        df['ob_low'] = np.nan
        
        lookback = 10
        
        for i in range(lookback + 1, len(df)):
            volatility = df['volatility'].iloc[i]
            move = abs(df['close'].iloc[i] - df['close'].iloc[i-1])
            
            # 檢查是否有大幅移動 (超過 2 倍波動)
            if move > 2 * volatility:
                # Bullish Order Block: 上漲前的最後一根陰線
                if df['close'].iloc[i] > df['close'].iloc[i-1]:
                    # 向後找最近的陰線
                    for j in range(i-1, max(i-lookback, 0), -1):
                        if df['close'].iloc[j] < df['open'].iloc[j]:
                            self.order_blocks.append(OrderBlock(
                                high=df['high'].iloc[j],
                                low=df['low'].iloc[j],
                                bar_index=j,
                                bar_time=df['date'].iloc[j] if 'date' in df.columns else None,
                                bias=TrendBias.BULLISH
                            ))
                            df.loc[df.index[i], 'bullish_ob'] = True
                            df.loc[df.index[i], 'ob_high'] = df['high'].iloc[j]
                            df.loc[df.index[i], 'ob_low'] = df['low'].iloc[j]
                            break
                
                # Bearish Order Block: 下跌前的最後一根陽線
                elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                    for j in range(i-1, max(i-lookback, 0), -1):
                        if df['close'].iloc[j] > df['open'].iloc[j]:
                            self.order_blocks.append(OrderBlock(
                                high=df['high'].iloc[j],
                                low=df['low'].iloc[j],
                                bar_index=j,
                                bar_time=df['date'].iloc[j] if 'date' in df.columns else None,
                                bias=TrendBias.BEARISH
                            ))
                            df.loc[df.index[i], 'bearish_ob'] = True
                            df.loc[df.index[i], 'ob_high'] = df['high'].iloc[j]
                            df.loc[df.index[i], 'ob_low'] = df['low'].iloc[j]
                            break
        
        return df
    
    def _detect_fvg(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        偵測 Fair Value Gaps (FVG)
        Bullish FVG: 第三根 K 線的低點 > 第一根 K 線的高點
        Bearish FVG: 第三根 K 線的高點 < 第一根 K 線的低點
        """
        df['bullish_fvg'] = False
        df['bearish_fvg'] = False
        df['fvg_top'] = np.nan
        df['fvg_bottom'] = np.nan
        
        for i in range(2, len(df)):
            # Bullish FVG
            if df['low'].iloc[i] > df['high'].iloc[i-2]:
                gap_size = df['low'].iloc[i] - df['high'].iloc[i-2]
                
                # 閾值過濾
                if not self.fvg_threshold or gap_size > df['atr'].iloc[i] * 0.5:
                    df.loc[df.index[i], 'bullish_fvg'] = True
                    df.loc[df.index[i], 'fvg_top'] = df['low'].iloc[i]
                    df.loc[df.index[i], 'fvg_bottom'] = df['high'].iloc[i-2]
                    
                    self.fair_value_gaps.append(FairValueGap(
                        top=df['low'].iloc[i],
                        bottom=df['high'].iloc[i-2],
                        bar_index=i,
                        bar_time=df['date'].iloc[i] if 'date' in df.columns else None,
                        bias=TrendBias.BULLISH
                    ))
            
            # Bearish FVG
            if df['high'].iloc[i] < df['low'].iloc[i-2]:
                gap_size = df['low'].iloc[i-2] - df['high'].iloc[i]
                
                if not self.fvg_threshold or gap_size > df['atr'].iloc[i] * 0.5:
                    df.loc[df.index[i], 'bearish_fvg'] = True
                    df.loc[df.index[i], 'fvg_top'] = df['low'].iloc[i-2]
                    df.loc[df.index[i], 'fvg_bottom'] = df['high'].iloc[i]
                    
                    self.fair_value_gaps.append(FairValueGap(
                        top=df['low'].iloc[i-2],
                        bottom=df['high'].iloc[i],
                        bar_index=i,
                        bar_time=df['date'].iloc[i] if 'date' in df.columns else None,
                        bias=TrendBias.BEARISH
                    ))
        
        return df
    
    def _detect_equal_hl(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        偵測 Equal Highs 和 Equal Lows
        """
        df['equal_high'] = False
        df['equal_low'] = False
        
        lookback = 20
        threshold = self.equal_hl_threshold
        
        for i in range(lookback, len(df)):
            atr = df['atr'].iloc[i]
            current_high = df['high'].iloc[i]
            current_low = df['low'].iloc[i]
            
            # 檢查 Equal Highs
            for j in range(i-lookback, i):
                if abs(current_high - df['high'].iloc[j]) < threshold * atr:
                    df.loc[df.index[i], 'equal_high'] = True
                    break
            
            # 檢查 Equal Lows
            for j in range(i-lookback, i):
                if abs(current_low - df['low'].iloc[j]) < threshold * atr:
                    df.loc[df.index[i], 'equal_low'] = True
                    break
        
        return df
    
    def _calculate_zones(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        計算 Premium/Discount 區域
        """
        # 找最近的 Swing High 和 Swing Low
        swing_highs = df[df['swing_high_point']]['high']
        swing_lows = df[df['swing_low_point']]['low']
        
        if len(swing_highs) > 0 and len(swing_lows) > 0:
            recent_high = swing_highs.iloc[-1] if len(swing_highs) > 0 else df['high'].max()
            recent_low = swing_lows.iloc[-1] if len(swing_lows) > 0 else df['low'].min()
            
            equilibrium = (recent_high + recent_low) / 2
            
            df['zone_high'] = recent_high
            df['zone_low'] = recent_low
            df['equilibrium'] = equilibrium
            df['premium_zone'] = df['close'] > equilibrium
            df['discount_zone'] = df['close'] < equilibrium
            
            # 目前價格在 Premium (0.5-1) 還是 Discount (0-0.5) 區
            df['zone_position'] = (df['close'] - recent_low) / (recent_high - recent_low) if recent_high != recent_low else 0.5
        
        return df
    
    def get_summary(self, df: pd.DataFrame) -> Dict:
        """
        取得 SMC 分析摘要
        """
        if len(df) < 2:
            return {'error': 'Insufficient data'}
        
        last_row = df.iloc[-1]
        
        # 找最近的信號
        recent_signals = []
        lookback = 10
        
        for i in range(max(0, len(df)-lookback), len(df)):
            row = df.iloc[i]
            if row.get('bos_bull', False):
                recent_signals.append({'type': 'BOS', 'bias': 'bullish', 'index': i})
            if row.get('bos_bear', False):
                recent_signals.append({'type': 'BOS', 'bias': 'bearish', 'index': i})
            if row.get('choch_bull', False):
                recent_signals.append({'type': 'CHoCH', 'bias': 'bullish', 'index': i})
            if row.get('choch_bear', False):
                recent_signals.append({'type': 'CHoCH', 'bias': 'bearish', 'index': i})
        
        # 判斷主信號
        last_signal = recent_signals[-1] if recent_signals else None
        
        signal = None
        signal_strength = 0
        
        if last_signal:
            signal = f"{last_signal['type']}_{last_signal['bias'][:4]}"
            signal_strength = 90 if last_signal['type'] == 'CHoCH' else 70
        
        # Order Blocks 統計
        bullish_ob_count = len([ob for ob in self.order_blocks if ob.bias == TrendBias.BULLISH and not ob.mitigated])
        bearish_ob_count = len([ob for ob in self.order_blocks if ob.bias == TrendBias.BEARISH and not ob.mitigated])
        
        # FVG 統計
        bullish_fvg_count = len([fvg for fvg in self.fair_value_gaps if fvg.bias == TrendBias.BULLISH and not fvg.filled])
        bearish_fvg_count = len([fvg for fvg in self.fair_value_gaps if fvg.bias == TrendBias.BEARISH and not fvg.filled])
        
        return {
            'swing_trend': 'bullish' if last_row.get('swing_trend', 0) > 0 else ('bearish' if last_row.get('swing_trend', 0) < 0 else 'neutral'),
            'internal_trend': 'bullish' if last_row.get('internal_trend', 0) > 0 else ('bearish' if last_row.get('internal_trend', 0) < 0 else 'neutral'),
            'signal': signal,
            'signal_strength': signal_strength,
            'recent_signals': recent_signals[-5:],
            'bullish_order_blocks': bullish_ob_count,
            'bearish_order_blocks': bearish_ob_count,
            'bullish_fvg': bullish_fvg_count,
            'bearish_fvg': bearish_fvg_count,
            'zone_position': last_row.get('zone_position', 0.5),
            'in_premium': last_row.get('premium_zone', False),
            'in_discount': last_row.get('discount_zone', False),
            'equilibrium': last_row.get('equilibrium', 0),
            'equal_high': last_row.get('equal_high', False),
            'equal_low': last_row.get('equal_low', False),
            'current_price': last_row['close']
        }


# ============================================================
# 便捷函數
# ============================================================

def calculate_smc(
    df: pd.DataFrame,
    swing_length: int = 50,
    internal_length: int = 5,
    **kwargs
) -> Tuple[pd.DataFrame, Dict]:
    """
    計算 SMC 指標的便捷函數
    
    返回:
    - df: 包含 SMC 指標的 DataFrame
    - summary: SMC 分析摘要
    """
    calculator = SMCCalculator(
        swing_length=swing_length,
        internal_length=internal_length,
        **kwargs
    )
    
    result_df = calculator.calculate(df)
    summary = calculator.get_summary(result_df)
    
    return result_df, summary


# ============================================================
# 測試函數
# ============================================================

def test_smc():
    """測試 SMC 計算"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=200, freq='D')
    
    # 模擬有趨勢的價格走勢
    trend = np.cumsum(np.random.randn(200) * 0.5)
    noise = np.random.randn(200) * 2
    close = 100 + trend + noise
    
    high = close + np.abs(np.random.randn(200)) * 1.5
    low = close - np.abs(np.random.randn(200)) * 1.5
    open_price = close + np.random.randn(200) * 0.5
    volume = np.random.randint(1000000, 5000000, 200)
    
    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    # 計算 SMC
    result_df, summary = calculate_smc(df, swing_length=20, internal_length=5)
    
    print("SMC 計算結果：")
    print("\n結構信號：")
    signal_cols = ['date', 'close', 'bos_bull', 'bos_bear', 'choch_bull', 'choch_bear', 'swing_trend']
    print(result_df[result_df['bos_bull'] | result_df['bos_bear'] | result_df['choch_bull'] | result_df['choch_bear']][signal_cols].tail(10))
    
    print("\n\nSMC 摘要：")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    test_smc()
