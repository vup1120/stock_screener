"""
SMC (Smart Money Concepts) 指標模組
====================================
根據 LuxAlgo Smart Money Concepts 指標轉換為 Python
參考 joshyattridge/smart-money-concepts 開源實作改良

包含功能:
- Swing High/Low 偵測 (含交替驗證)
- BOS (Break of Structure) 結構突破 (4 點模式驗證)
- CHoCH (Change of Character) 性格轉變
- Order Blocks 訂單塊 (含成交量分析與突破追蹤)
- Fair Value Gaps (FVG) 公允價值缺口 (含修復追蹤)
- Equal Highs/Lows 等高/等低
- Premium/Discount Zones 溢價/折價區
- Liquidity 流動性偵測
- Retracements 回撤計算
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
    mitigated_index: int = 0
    volume: float = 0.0
    percentage: float = 0.0


@dataclass
class FairValueGap:
    """公允價值缺口資料結構"""
    top: float
    bottom: float
    bar_index: int
    bar_time: pd.Timestamp
    bias: TrendBias
    filled: bool = False
    mitigated_index: int = 0


@dataclass
class StructureSignal:
    """結構信號資料結構"""
    signal_type: str  # 'BOS' or 'CHoCH'
    bias: TrendBias   # BULLISH or BEARISH
    level: float
    bar_index: int
    bar_time: pd.Timestamp = None
    broken_index: int = 0


class SMCCalculator:
    """
    Smart Money Concepts 計算器

    改良版本，整合 joshyattridge/smart-money-concepts 的演算法:
    - 交替驗證的 swing 偵測 (消除連續同方向 pivot)
    - 4 點模式 BOS/CHoCH 偵測
    - 基於 swing 突破的 order block 偵測 (含成交量分析)
    - FVG 修復追蹤
    - 流動性偵測
    - 回撤計算
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

    @staticmethod
    def _swing_highs_lows(ohlc: pd.DataFrame, swing_length: int) -> pd.DataFrame:
        """
        使用 rolling window 偵測 swing high/low，並強制交替出現。

        演算法:
        1. 用 rolling(2*swing_length).max/min 偵測局部極值
        2. 消除連續同方向的 pivot (保留較極端的那個)
        3. 確保首尾 pivot 交替
        """
        n = len(ohlc)
        sl = swing_length * 2

        swing_highs_lows = np.where(
            ohlc["high"]
            == ohlc["high"].shift(-(sl // 2)).rolling(sl).max(),
            1,
            np.where(
                ohlc["low"]
                == ohlc["low"].shift(-(sl // 2)).rolling(sl).min(),
                -1,
                np.nan,
            ),
        )

        # 消除連續同方向 pivot (保留更極端的)
        while True:
            positions = np.where(~np.isnan(swing_highs_lows))[0]
            if len(positions) < 2:
                break

            current = swing_highs_lows[positions[:-1]]
            nxt = swing_highs_lows[positions[1:]]

            highs = ohlc["high"].iloc[positions[:-1]].values
            lows = ohlc["low"].iloc[positions[:-1]].values
            next_highs = ohlc["high"].iloc[positions[1:]].values
            next_lows = ohlc["low"].iloc[positions[1:]].values

            index_to_remove = np.zeros(len(positions), dtype=bool)

            consecutive_highs = (current == 1) & (nxt == 1)
            index_to_remove[:-1] |= consecutive_highs & (highs < next_highs)
            index_to_remove[1:] |= consecutive_highs & (highs >= next_highs)

            consecutive_lows = (current == -1) & (nxt == -1)
            index_to_remove[:-1] |= consecutive_lows & (lows > next_lows)
            index_to_remove[1:] |= consecutive_lows & (lows <= next_lows)

            if not index_to_remove.any():
                break

            swing_highs_lows[positions[index_to_remove]] = np.nan

        # 確保首尾有 pivot，且與第一個/最後一個 pivot 交替
        positions = np.where(~np.isnan(swing_highs_lows))[0]
        if len(positions) > 0:
            # Add opposite pivot at the start if first detected pivot isn't at index 0
            if positions[0] != 0:
                if swing_highs_lows[positions[0]] == 1:
                    swing_highs_lows[0] = -1
                else:
                    swing_highs_lows[0] = 1
            # Add opposite pivot at the end if last detected pivot isn't at last index
            if positions[-1] != n - 1:
                if swing_highs_lows[positions[-1]] == 1:
                    swing_highs_lows[-1] = -1
                else:
                    swing_highs_lows[-1] = 1

        level = np.where(
            ~np.isnan(swing_highs_lows),
            np.where(swing_highs_lows == 1, ohlc["high"], ohlc["low"]),
            np.nan,
        )

        return pd.DataFrame({
            'HighLow': swing_highs_lows,
            'Level': level,
        }, index=ohlc.index)

    @staticmethod
    def _detect_bos_choch(
        ohlc: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        close_break: bool = True,
    ) -> pd.DataFrame:
        """
        BOS/CHoCH 偵測 — 使用 4 點模式驗證。

        4 point pattern:
        - Bullish BOS: [-1, 1, -1, 1] with LL < HL and LH < HH (higher lows, higher highs)
        - Bearish BOS: [1, -1, 1, -1] with HH > LH and HL > LL (lower highs, lower lows)
        - Bullish CHoCH: [-1, 1, -1, 1] with HH > LH and LH > LL > HL (trend reversal)
        - Bearish CHoCH: [1, -1, 1, -1] with LL < HL and HL < HH < LH (trend reversal)
        """
        n = len(ohlc)
        level_order = []
        highs_lows_order = []

        bos = np.zeros(n, dtype=np.int32)
        choch = np.zeros(n, dtype=np.int32)
        level = np.zeros(n, dtype=np.float64)

        last_positions = []

        hl_values = swing_highs_lows['HighLow'].values
        lv_values = swing_highs_lows['Level'].values

        for i in range(n):
            if not np.isnan(hl_values[i]):
                level_order.append(lv_values[i])
                highs_lows_order.append(hl_values[i])
                if len(level_order) >= 4:
                    hl4 = highs_lows_order[-4:]
                    lv4 = level_order[-4:]

                    # Bullish BOS: [-1, 1, -1, 1] with LL < HL < LH < HH
                    if (hl4 == [-1, 1, -1, 1] and
                            lv4[0] < lv4[2] < lv4[1] < lv4[3]):
                        bos[last_positions[-2]] = 1
                        level[last_positions[-2]] = lv4[1]  # previous high level

                    # Bearish BOS: [1, -1, 1, -1] with HH > LH > HL > LL
                    if (hl4 == [1, -1, 1, -1] and
                            lv4[0] > lv4[2] > lv4[1] > lv4[3]):
                        bos[last_positions[-2]] = -1
                        level[last_positions[-2]] = lv4[1]  # previous low level

                    # Bullish CHoCH: [-1, 1, -1, 1] with HH > LH > LL > HL
                    if (hl4 == [-1, 1, -1, 1] and
                            lv4[3] > lv4[1] > lv4[0] > lv4[2]):
                        choch[last_positions[-2]] = 1
                        level[last_positions[-2]] = lv4[1]

                    # Bearish CHoCH: [1, -1, 1, -1] with LL < HL < HH < LH
                    if (hl4 == [1, -1, 1, -1] and
                            lv4[3] < lv4[1] < lv4[0] < lv4[2]):
                        choch[last_positions[-2]] = -1
                        level[last_positions[-2]] = lv4[1]

                last_positions.append(i)

        # Find break point for each BOS/CHoCH and move signal there
        # This places the signal at the bar where price actually crosses the level
        pivot_signals = np.where(np.logical_or(bos != 0, choch != 0))[0]

        # Collect (pivot_idx, break_idx) pairs
        confirmed = []
        for i in pivot_signals:
            search_start = i + 1
            if search_start >= n:
                continue
            if bos[i] == 1 or choch[i] == 1:
                vals = ohlc["close" if close_break else "high"].iloc[search_start:].values
                mask = vals > level[i]
            else:
                vals = ohlc["close" if close_break else "low"].iloc[search_start:].values
                mask = vals < level[i]
            if np.any(mask):
                j = search_start + int(np.argmax(mask))
                confirmed.append((i, j, bos[i], choch[i], level[i]))

        # Clear all signals, then re-place at break points
        bos[:] = 0
        choch[:] = 0
        level[:] = 0

        used_break_points = set()
        for pivot_idx, break_idx, bos_val, choch_val, lv in confirmed:
            # Skip if this break point already used by an earlier signal
            if break_idx in used_break_points:
                continue
            used_break_points.add(break_idx)
            bos[break_idx] = bos_val
            choch[break_idx] = choch_val
            level[break_idx] = lv

        bos = np.where(bos != 0, bos, np.nan)
        choch = np.where(choch != 0, choch, np.nan)
        level = np.where(level != 0, level, np.nan)

        return pd.DataFrame({
            'BOS': bos,
            'CHOCH': choch,
            'Level': level,
        }, index=ohlc.index)

    @staticmethod
    def _detect_order_blocks(
        ohlc: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        close_mitigation: bool = False,
        ob_filter: str = 'atr',
    ) -> pd.DataFrame:
        """
        Order Block 偵測 — 基於 swing point 突破。

        直接對應 Pine Script 的 storeOrdeBlock 函數:
        - Bullish OB: 當價格突破 swing high 時，找突破前 parsedLow 最低的蠟燭
        - Bearish OB: 當價格突破 swing low 時，找突破前 parsedHigh 最高的蠟燭
        - parsedHigh/parsedLow: 高波動 K 線 (range >= 2*ATR) 會反轉 high/low
        含成交量分析與突破追蹤。
        """
        n = len(ohlc)
        _open = ohlc["open"].values
        _high = ohlc["high"].values
        _low = ohlc["low"].values
        _close = ohlc["close"].values
        _volume = ohlc["volume"].values if "volume" in ohlc.columns else np.ones(n)
        swing_hl = swing_highs_lows["HighLow"].values

        # Pine Script: parsedHigh/parsedLow — invert for high volatility bars
        # atrMeasure = ta.atr(200); volatilityMeasure = atr or cumulative mean range
        # highVolatilityBar = (high - low) >= (2 * volatilityMeasure)
        # parsedHigh = highVolatilityBar ? low : high
        # parsedLow = highVolatilityBar ? high : low
        if 'atr' in ohlc.columns:
            atr_vals = ohlc['atr'].values
        else:
            tr = np.maximum(_high - _low,
                            np.maximum(np.abs(_high - np.roll(_close, 1)),
                                       np.abs(_low - np.roll(_close, 1))))
            atr_vals = pd.Series(tr).rolling(200, min_periods=1).mean().values

        if ob_filter == 'atr':
            vol_measure = atr_vals
        else:
            vol_measure = pd.Series(_high - _low).expanding().mean().values

        high_vol_bar = (_high - _low) >= (2 * vol_measure)
        parsed_high = np.where(high_vol_bar, _low, _high)
        parsed_low = np.where(high_vol_bar, _high, _low)

        crossed = np.full(n, False, dtype=bool)
        ob = np.zeros(n, dtype=np.int32)
        top_arr = np.zeros(n, dtype=np.float64)
        bottom_arr = np.zeros(n, dtype=np.float64)
        ob_volume = np.zeros(n, dtype=np.float64)
        mitigated_index = np.zeros(n, dtype=np.int32)
        percentage = np.zeros(n, dtype=np.float64)
        breaker = np.full(n, False, dtype=bool)

        swing_high_indices = np.flatnonzero(swing_hl == 1)
        swing_low_indices = np.flatnonzero(swing_hl == -1)

        # Bullish OBs
        active_bullish = []
        for i in range(n):
            # Update existing bullish OBs
            for idx in active_bullish.copy():
                if breaker[idx]:
                    if _high[i] > top_arr[idx]:
                        ob[idx] = 0
                        top_arr[idx] = 0.0
                        bottom_arr[idx] = 0.0
                        ob_volume[idx] = 0.0
                        mitigated_index[idx] = 0
                        percentage[idx] = 0.0
                        active_bullish.remove(idx)
                else:
                    if ((not close_mitigation and _low[i] < bottom_arr[idx])
                            or (close_mitigation and min(_open[i], _close[i]) < bottom_arr[idx])):
                        breaker[idx] = True
                        mitigated_index[idx] = i - 1

            # Find last swing high before current candle
            pos = np.searchsorted(swing_high_indices, i)
            last_top_index = swing_high_indices[pos - 1] if pos > 0 else None

            if last_top_index is not None:
                if _close[i] > _high[last_top_index] and not crossed[last_top_index]:
                    crossed[last_top_index] = True
                    # Pine Script: find candle with min parsedLow between pivot and break
                    default_index = i - 1
                    ob_btm = parsed_high[default_index]
                    ob_top = parsed_low[default_index]
                    ob_index = default_index

                    if i - last_top_index > 1:
                        start = last_top_index + 1
                        end = i
                        if end > start:
                            segment = parsed_low[start:end]
                            min_val = segment.min()
                            candidates = np.nonzero(segment == min_val)[0]
                            if candidates.size:
                                ci = start + candidates[-1]
                                ob_btm = parsed_low[ci]
                                ob_top = parsed_high[ci]
                                ob_index = ci

                    ob[ob_index] = 1
                    top_arr[ob_index] = ob_top
                    bottom_arr[ob_index] = ob_btm
                    v0 = _volume[i]
                    v1 = _volume[i - 1] if i >= 1 else 0.0
                    v2 = _volume[i - 2] if i >= 2 else 0.0
                    ob_volume[ob_index] = v0 + v1 + v2
                    low_vol = v2
                    high_vol = v0 + v1
                    max_vol = max(high_vol, low_vol)
                    percentage[ob_index] = (min(high_vol, low_vol) / max_vol * 100.0) if max_vol != 0 else 100.0
                    active_bullish.append(ob_index)

        # Bearish OBs
        active_bearish = []
        breaker = np.full(n, False, dtype=bool)
        for i in range(n):
            for idx in active_bearish.copy():
                if breaker[idx]:
                    if _low[i] < bottom_arr[idx]:
                        ob[idx] = 0
                        top_arr[idx] = 0.0
                        bottom_arr[idx] = 0.0
                        ob_volume[idx] = 0.0
                        mitigated_index[idx] = 0
                        percentage[idx] = 0.0
                        active_bearish.remove(idx)
                else:
                    if ((not close_mitigation and _high[i] > top_arr[idx])
                            or (close_mitigation and max(_open[i], _close[i]) > top_arr[idx])):
                        breaker[idx] = True
                        mitigated_index[idx] = i

            pos = np.searchsorted(swing_low_indices, i)
            last_btm_index = swing_low_indices[pos - 1] if pos > 0 else None

            if last_btm_index is not None:
                if _close[i] < _low[last_btm_index] and not crossed[last_btm_index]:
                    crossed[last_btm_index] = True
                    # Pine Script: find candle with max parsedHigh between pivot and break
                    default_index = i - 1
                    ob_top = parsed_high[default_index]
                    ob_btm = parsed_low[default_index]
                    ob_index = default_index

                    if i - last_btm_index > 1:
                        start = last_btm_index + 1
                        end = i
                        if end > start:
                            segment = parsed_high[start:end]
                            max_val = segment.max()
                            candidates = np.nonzero(segment == max_val)[0]
                            if candidates.size:
                                ci = start + candidates[-1]
                                ob_top = parsed_high[ci]
                                ob_btm = parsed_low[ci]
                                ob_index = ci

                    ob[ob_index] = -1
                    top_arr[ob_index] = ob_top
                    bottom_arr[ob_index] = ob_btm
                    v0 = _volume[i]
                    v1 = _volume[i - 1] if i >= 1 else 0.0
                    v2 = _volume[i - 2] if i >= 2 else 0.0
                    ob_volume[ob_index] = v0 + v1 + v2
                    low_vol = v0 + v1
                    high_vol = v2
                    max_vol = max(high_vol, low_vol)
                    percentage[ob_index] = (min(high_vol, low_vol) / max_vol * 100.0) if max_vol != 0 else 100.0
                    active_bearish.append(ob_index)

        ob = np.where(ob != 0, ob, np.nan)
        top_arr = np.where(~np.isnan(ob), top_arr, np.nan)
        bottom_arr = np.where(~np.isnan(ob), bottom_arr, np.nan)
        ob_volume = np.where(~np.isnan(ob), ob_volume, np.nan)
        mitigated_index = np.where(~np.isnan(ob), mitigated_index, np.nan)
        percentage = np.where(~np.isnan(ob), percentage, np.nan)

        return pd.DataFrame({
            'OB': ob,
            'Top': top_arr,
            'Bottom': bottom_arr,
            'OBVolume': ob_volume,
            'MitigatedIndex': mitigated_index,
            'Percentage': percentage,
        }, index=ohlc.index)

    @staticmethod
    def _detect_fvg(ohlc: pd.DataFrame, join_consecutive: bool = False) -> pd.DataFrame:
        """
        FVG 偵測 — 含修復追蹤。

        Bullish FVG: previous high < next low (gap up)
        Bearish FVG: previous low > next high (gap down)
        """
        fvg = np.where(
            (
                (ohlc["high"].shift(1) < ohlc["low"].shift(-1))
                & (ohlc["close"] > ohlc["open"])
            )
            | (
                (ohlc["low"].shift(1) > ohlc["high"].shift(-1))
                & (ohlc["close"] < ohlc["open"])
            ),
            np.where(ohlc["close"] > ohlc["open"], 1, -1),
            np.nan,
        )

        top = np.where(
            ~np.isnan(fvg),
            np.where(
                ohlc["close"] > ohlc["open"],
                ohlc["low"].shift(-1),
                ohlc["low"].shift(1),
            ),
            np.nan,
        )

        bottom = np.where(
            ~np.isnan(fvg),
            np.where(
                ohlc["close"] > ohlc["open"],
                ohlc["high"].shift(1),
                ohlc["high"].shift(-1),
            ),
            np.nan,
        )

        if join_consecutive:
            for i in range(len(fvg) - 1):
                if fvg[i] == fvg[i + 1]:
                    top[i + 1] = max(top[i], top[i + 1])
                    bottom[i + 1] = min(bottom[i], bottom[i + 1])
                    fvg[i] = top[i] = bottom[i] = np.nan

        # Track mitigation
        mitigated_index = np.zeros(len(ohlc), dtype=np.int32)
        for i in np.where(~np.isnan(fvg))[0]:
            if i + 2 >= len(ohlc):
                continue
            mask = np.zeros(len(ohlc) - i - 2, dtype=np.bool_)
            if fvg[i] == 1:
                mask = ohlc["low"].iloc[i + 2:].values <= top[i]
            elif fvg[i] == -1:
                mask = ohlc["high"].iloc[i + 2:].values >= bottom[i]
            if np.any(mask):
                j = np.argmax(mask) + i + 2
                mitigated_index[i] = j

        mitigated_index = np.where(np.isnan(fvg), np.nan, mitigated_index)

        return pd.DataFrame({
            'FVG': fvg,
            'Top': top,
            'Bottom': bottom,
            'MitigatedIndex': mitigated_index,
        }, index=ohlc.index)

    @staticmethod
    def _detect_liquidity(
        ohlc: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        range_percent: float = 0.01,
    ) -> pd.DataFrame:
        """
        流動性偵測 — 多個 swing point 集中在小範圍內。
        """
        n = len(ohlc)
        pip_range = (ohlc["high"].max() - ohlc["low"].min()) * range_percent

        ohlc_high = ohlc["high"].values
        ohlc_low = ohlc["low"].values

        shl_HL = swing_highs_lows["HighLow"].values.copy()
        shl_Level = swing_highs_lows["Level"].values.copy()

        liquidity = np.full(n, np.nan, dtype=np.float64)
        liquidity_level = np.full(n, np.nan, dtype=np.float64)
        liquidity_end = np.full(n, np.nan, dtype=np.float64)
        liquidity_swept = np.full(n, np.nan, dtype=np.float64)

        # Bullish liquidity (clustered highs)
        bull_indices = np.nonzero(shl_HL == 1)[0]
        for i in bull_indices:
            if shl_HL[i] != 1:
                continue
            high_level = shl_Level[i]
            range_low = high_level - pip_range
            range_high = high_level + pip_range
            group_levels = [high_level]
            group_end = i

            c_start = i + 1
            swept = 0
            if c_start < n:
                cond = ohlc_high[c_start:] >= range_high
                if np.any(cond):
                    swept = c_start + int(np.argmax(cond))

            for j in bull_indices:
                if j <= i:
                    continue
                if swept and j >= swept:
                    break
                if shl_HL[j] == 1 and (range_low <= shl_Level[j] <= range_high):
                    group_levels.append(shl_Level[j])
                    group_end = j
                    shl_HL[j] = 0

            if len(group_levels) > 1:
                avg_level = sum(group_levels) / len(group_levels)
                liquidity[i] = 1
                liquidity_level[i] = avg_level
                liquidity_end[i] = group_end
                liquidity_swept[i] = swept

        # Bearish liquidity (clustered lows)
        bear_indices = np.nonzero(shl_HL == -1)[0]
        for i in bear_indices:
            if shl_HL[i] != -1:
                continue
            low_level = shl_Level[i]
            range_low = low_level - pip_range
            range_high = low_level + pip_range
            group_levels = [low_level]
            group_end = i

            c_start = i + 1
            swept = 0
            if c_start < n:
                cond = ohlc_low[c_start:] <= range_low
                if np.any(cond):
                    swept = c_start + int(np.argmax(cond))

            for j in bear_indices:
                if j <= i:
                    continue
                if swept and j >= swept:
                    break
                if shl_HL[j] == -1 and (range_low <= shl_Level[j] <= range_high):
                    group_levels.append(shl_Level[j])
                    group_end = j
                    shl_HL[j] = 0

            if len(group_levels) > 1:
                avg_level = sum(group_levels) / len(group_levels)
                liquidity[i] = -1
                liquidity_level[i] = avg_level
                liquidity_end[i] = group_end
                liquidity_swept[i] = swept

        return pd.DataFrame({
            'Liquidity': liquidity,
            'Level': liquidity_level,
            'End': liquidity_end,
            'Swept': liquidity_swept,
        }, index=ohlc.index)

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

        # Normalize column names to lowercase
        df.columns = [c.lower() for c in df.columns]

        # Auto-scale swing_length to fit available data
        # Need at least 4 alternating pivots; each pivot needs a centered window of 2*swing_length
        # Heuristic: swing_length <= len(df) / 10 ensures enough pivots
        n = len(df)
        effective_swing = min(self.swing_length, max(5, n // 10))
        effective_internal = min(self.internal_length, max(3, n // 20))
        if effective_swing != self.swing_length:
            logger.info(f"Auto-scaled swing_length {self.swing_length} -> {effective_swing} for {n} bars")

        # 計算 ATR
        df['atr'] = self._calculate_atr(df)
        df['volatility'] = df['atr'] if self.order_block_filter == 'atr' else (df['high'] - df['low']).expanding().mean()

        # ---- Swing 結構 (使用改良演算法) ----
        swing_result = self._swing_highs_lows(df, effective_swing)
        df['swing_high_point'] = (swing_result['HighLow'] == 1).values
        df['swing_low_point'] = (swing_result['HighLow'] == -1).values
        df['swing_high_level'] = np.where(swing_result['HighLow'] == 1, swing_result['Level'], np.nan)
        df['swing_low_level'] = np.where(swing_result['HighLow'] == -1, swing_result['Level'], np.nan)

        # ---- Internal 結構 ----
        internal_result = self._swing_highs_lows(df, effective_internal)
        df['internal_high_point'] = (internal_result['HighLow'] == 1).values
        df['internal_low_point'] = (internal_result['HighLow'] == -1).values
        df['internal_high_level'] = np.where(internal_result['HighLow'] == 1, internal_result['Level'], np.nan)
        df['internal_low_level'] = np.where(internal_result['HighLow'] == -1, internal_result['Level'], np.nan)

        # ---- Leg 方向 ----
        df['leg'] = 0
        size = effective_swing
        for i in range(size, len(df)):
            if df['high'].iloc[i] > df['high'].iloc[i - size:i].max():
                df.iloc[i, df.columns.get_loc('leg')] = 0
            elif df['low'].iloc[i] < df['low'].iloc[i - size:i].min():
                df.iloc[i, df.columns.get_loc('leg')] = 1
            else:
                df.iloc[i, df.columns.get_loc('leg')] = df['leg'].iloc[i - 1]

        # ---- BOS/CHoCH (使用 4 點模式) ----
        bos_choch_swing = self._detect_bos_choch(df, swing_result, close_break=True)
        bos_choch_internal = self._detect_bos_choch(df, internal_result, close_break=True)

        df['bos_bull'] = (bos_choch_swing['BOS'] == 1).values
        df['bos_bear'] = (bos_choch_swing['BOS'] == -1).values
        df['choch_bull'] = (bos_choch_swing['CHOCH'] == 1).values
        df['choch_bear'] = (bos_choch_swing['CHOCH'] == -1).values
        df['internal_bos_bull'] = (bos_choch_internal['BOS'] == 1).values
        df['internal_bos_bear'] = (bos_choch_internal['BOS'] == -1).values
        df['internal_choch_bull'] = (bos_choch_internal['CHOCH'] == 1).values
        df['internal_choch_bear'] = (bos_choch_internal['CHOCH'] == -1).values

        # Derive swing/internal trend from BOS/CHoCH signals
        df['swing_trend'] = 0
        df['internal_trend'] = 0
        swing_trend = 0
        internal_trend = 0
        for i in range(len(df)):
            if df['bos_bull'].iloc[i] or df['choch_bull'].iloc[i]:
                swing_trend = 1
            elif df['bos_bear'].iloc[i] or df['choch_bear'].iloc[i]:
                swing_trend = -1
            if df['internal_bos_bull'].iloc[i] or df['internal_choch_bull'].iloc[i]:
                internal_trend = 1
            elif df['internal_bos_bear'].iloc[i] or df['internal_choch_bear'].iloc[i]:
                internal_trend = -1
            df.iloc[i, df.columns.get_loc('swing_trend')] = swing_trend
            df.iloc[i, df.columns.get_loc('internal_trend')] = internal_trend

        self.swing_trend = TrendBias(swing_trend) if swing_trend != 0 else TrendBias.NEUTRAL
        self.internal_trend = TrendBias(internal_trend) if internal_trend != 0 else TrendBias.NEUTRAL

        # Store structure signals
        for i in range(len(df)):
            bar_time = df['date'].iloc[i] if 'date' in df.columns else None
            if df['bos_bull'].iloc[i]:
                self.structure_signals.append(StructureSignal('BOS', TrendBias.BULLISH, bos_choch_swing['Level'].iloc[i], i, bar_time))
            if df['bos_bear'].iloc[i]:
                self.structure_signals.append(StructureSignal('BOS', TrendBias.BEARISH, bos_choch_swing['Level'].iloc[i], i, bar_time))
            if df['choch_bull'].iloc[i]:
                self.structure_signals.append(StructureSignal('CHoCH', TrendBias.BULLISH, bos_choch_swing['Level'].iloc[i], i, bar_time))
            if df['choch_bear'].iloc[i]:
                self.structure_signals.append(StructureSignal('CHoCH', TrendBias.BEARISH, bos_choch_swing['Level'].iloc[i], i, bar_time))

        # ---- Order Blocks (基於 swing 突破, 使用 parsedHigh/parsedLow) ----
        ob_result = self._detect_order_blocks(df, swing_result, close_mitigation=False, ob_filter=self.order_block_filter)
        df['bullish_ob'] = (ob_result['OB'] == 1).values
        df['bearish_ob'] = (ob_result['OB'] == -1).values
        df['ob_high'] = np.where(~np.isnan(ob_result['OB']), ob_result['Top'], np.nan)
        df['ob_low'] = np.where(~np.isnan(ob_result['OB']), ob_result['Bottom'], np.nan)

        # Store order blocks
        for i in range(len(df)):
            if not np.isnan(ob_result['OB'].iloc[i]):
                bias = TrendBias.BULLISH if ob_result['OB'].iloc[i] == 1 else TrendBias.BEARISH
                bar_time = df['date'].iloc[i] if 'date' in df.columns else None
                mit_idx = int(ob_result['MitigatedIndex'].iloc[i]) if not np.isnan(ob_result['MitigatedIndex'].iloc[i]) else 0
                self.order_blocks.append(OrderBlock(
                    high=ob_result['Top'].iloc[i],
                    low=ob_result['Bottom'].iloc[i],
                    bar_index=i,
                    bar_time=bar_time,
                    bias=bias,
                    mitigated=mit_idx > 0,
                    mitigated_index=mit_idx,
                    volume=ob_result['OBVolume'].iloc[i] if not np.isnan(ob_result['OBVolume'].iloc[i]) else 0,
                    percentage=ob_result['Percentage'].iloc[i] if not np.isnan(ob_result['Percentage'].iloc[i]) else 0,
                ))

        # ---- FVG (含修復追蹤) ----
        fvg_result = self._detect_fvg(df)
        df['bullish_fvg'] = (fvg_result['FVG'] == 1).values
        df['bearish_fvg'] = (fvg_result['FVG'] == -1).values
        df['fvg_top'] = np.where(~np.isnan(fvg_result['FVG']), fvg_result['Top'], np.nan)
        df['fvg_bottom'] = np.where(~np.isnan(fvg_result['FVG']), fvg_result['Bottom'], np.nan)

        for i in range(len(df)):
            if not np.isnan(fvg_result['FVG'].iloc[i]):
                bias = TrendBias.BULLISH if fvg_result['FVG'].iloc[i] == 1 else TrendBias.BEARISH
                bar_time = df['date'].iloc[i] if 'date' in df.columns else None
                mit_idx = int(fvg_result['MitigatedIndex'].iloc[i]) if not np.isnan(fvg_result['MitigatedIndex'].iloc[i]) else 0
                self.fair_value_gaps.append(FairValueGap(
                    top=fvg_result['Top'].iloc[i],
                    bottom=fvg_result['Bottom'].iloc[i],
                    bar_index=i,
                    bar_time=bar_time,
                    bias=bias,
                    filled=mit_idx > 0,
                    mitigated_index=mit_idx,
                ))

        # ---- Equal Highs/Lows ----
        df = self._detect_equal_hl(df)

        # ---- Premium/Discount 區域 ----
        df = self._calculate_zones(df)

        return df

    def _detect_equal_hl(self, df: pd.DataFrame) -> pd.DataFrame:
        """偵測 Equal Highs 和 Equal Lows"""
        df['equal_high'] = False
        df['equal_low'] = False

        lookback = 20
        threshold = self.equal_hl_threshold

        for i in range(lookback, len(df)):
            atr = df['atr'].iloc[i]
            current_high = df['high'].iloc[i]
            current_low = df['low'].iloc[i]

            for j in range(i - lookback, i):
                if abs(current_high - df['high'].iloc[j]) < threshold * atr:
                    df.iloc[i, df.columns.get_loc('equal_high')] = True
                    break

            for j in range(i - lookback, i):
                if abs(current_low - df['low'].iloc[j]) < threshold * atr:
                    df.iloc[i, df.columns.get_loc('equal_low')] = True
                    break

        return df

    def _calculate_zones(self, df: pd.DataFrame) -> pd.DataFrame:
        """計算 Premium/Discount 區域"""
        swing_highs = df[df['swing_high_point']]['high']
        swing_lows = df[df['swing_low_point']]['low']

        if len(swing_highs) > 0 and len(swing_lows) > 0:
            recent_high = swing_highs.iloc[-1]
            recent_low = swing_lows.iloc[-1]

            equilibrium = (recent_high + recent_low) / 2

            df['zone_high'] = recent_high
            df['zone_low'] = recent_low
            df['equilibrium'] = equilibrium
            df['premium_zone'] = df['close'] > equilibrium
            df['discount_zone'] = df['close'] < equilibrium

            df['zone_position'] = (df['close'] - recent_low) / (recent_high - recent_low) if recent_high != recent_low else 0.5

        return df

    def get_summary(self, df: pd.DataFrame) -> Dict:
        """取得 SMC 分析摘要"""
        if len(df) < 2:
            return {'error': 'Insufficient data'}

        last_row = df.iloc[-1]

        # Use stored structure signals (already collected during calculate())
        recent_signals = [
            {
                'type': sig.signal_type,
                'bias': 'bullish' if sig.bias == TrendBias.BULLISH else 'bearish',
                'index': sig.bar_index,
            }
            for sig in self.structure_signals
        ]
        # Sort by bar_index to get the most recent
        recent_signals.sort(key=lambda s: s['index'])

        last_signal = recent_signals[-1] if recent_signals else None

        signal = None
        signal_strength = 0

        if last_signal:
            signal = f"{last_signal['type']}_{last_signal['bias'][:4]}"
            signal_strength = 90 if last_signal['type'] == 'CHoCH' else 70

        bullish_ob_count = len([ob for ob in self.order_blocks if ob.bias == TrendBias.BULLISH and not ob.mitigated])
        bearish_ob_count = len([ob for ob in self.order_blocks if ob.bias == TrendBias.BEARISH and not ob.mitigated])

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
            'order_blocks_count': bullish_ob_count + bearish_ob_count,
            'bullish_fvg': bullish_fvg_count,
            'bearish_fvg': bearish_fvg_count,
            'fvg_count': bullish_fvg_count + bearish_fvg_count,
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
