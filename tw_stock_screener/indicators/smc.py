"""
SMC (Smart Money Concepts) 指標模組
====================================
Faithful Python port of LuxAlgo Smart Money Concepts Pine Script indicator.

Bar-by-bar processing matching Pine Script logic:
- leg() function for swing detection
- getCurrentStructure() for pivot tracking with currentLevel/lastLevel/crossed
- displayStructure() for BOS/CHoCH via real-time crossover + trend state
- storeOrdeBlock() triggered on BOS/CHoCH events
- Equal Highs/Lows via swing point comparison
- Fair Value Gaps with mitigation tracking
- Premium/Discount Zones with trailing extremes
- Liquidity detection
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
    """Pine Script pivot UDT equivalent."""
    level: float
    bar_index: int
    bar_time: pd.Timestamp = None
    crossed: bool = False
    last_level: float = 0.0


@dataclass
class OrderBlock:
    """Order block data structure."""
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
    """Fair value gap data structure."""
    top: float
    bottom: float
    bar_index: int
    bar_time: pd.Timestamp
    bias: TrendBias
    filled: bool = False
    mitigated_index: int = 0


@dataclass
class StructureSignal:
    """Structure signal (BOS/CHoCH)."""
    signal_type: str  # 'BOS' or 'CHoCH'
    bias: TrendBias   # BULLISH or BEARISH
    level: float
    bar_index: int
    bar_time: pd.Timestamp = None
    broken_index: int = 0


class SMCCalculator:
    """
    Smart Money Concepts calculator — faithful port of LuxAlgo Pine Script.

    Key design: bar-by-bar processing matching Pine Script execution model.
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

        self.order_blocks: List[OrderBlock] = []
        self.fair_value_gaps: List[FairValueGap] = []
        self.structure_signals: List[StructureSignal] = []

    # ------------------------------------------------------------------
    # Pine Script: leg(size) — detect current leg direction
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_legs(highs: np.ndarray, lows: np.ndarray, size: int) -> np.ndarray:
        """
        Pine Script leg() function:
            var leg = 0
            newLegHigh = high[size] > ta.highest(size)
            newLegLow  = low[size]  < ta.lowest(size)
            if newLegHigh: leg := 0  (BEARISH_LEG)
            if newLegLow:  leg := 1  (BULLISH_LEG)

        high[size] is the bar `size` bars ago.
        ta.highest(size) is the highest of bars [0..size-1] (the `size` most recent bars).
        """
        n = len(highs)
        legs = np.zeros(n, dtype=np.int32)
        leg = 0

        for i in range(size, n):
            bar_high = highs[i - size]  # high[size] in Pine (size bars ago from i)

            # ta.highest(size): highest of the `size` bars before current
            # In Pine at bar i: bars [i-size+1 .. i-1] when checking high[size]
            # Actually Pine's ta.highest(size) at bar i looks at [i-(size-1) .. i]
            # But high[size] is bar i-size
            # So: newLegHigh = high[size] > ta.highest(size)
            # means: the bar `size` ago is higher than max of last `size` bars
            # ta.highest(size) at bar i = max(high[i], high[i-1], ..., high[i-size+1])
            window_high = highs[i - size + 1: i + 1].max()

            bar_low = lows[i - size]
            window_low = lows[i - size + 1: i + 1].min()

            if bar_high > window_high:
                leg = 0  # BEARISH_LEG — detected a swing high
            elif bar_low < window_low:
                leg = 1  # BULLISH_LEG — detected a swing low

            legs[i] = leg

        return legs

    # ------------------------------------------------------------------
    # Pine Script: getCurrentStructure() — detect pivots bar by bar
    # ------------------------------------------------------------------
    @staticmethod
    def _get_current_structure(
        highs: np.ndarray,
        lows: np.ndarray,
        size: int,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Pine Script getCurrentStructure(size, equalHighLow=false, internal=false).

        Returns:
            pivot_type: 1 for swing high, -1 for swing low, 0 otherwise
            pivot_level: price level at pivot
            pivot_last_level: previous level of same type
            pivot_bar_index: bar index of pivot (i - size)
            crossed: whether pivot has been crossed
        """
        n = len(highs)
        legs = SMCCalculator._compute_legs(highs, lows, size)

        pivot_type = np.zeros(n, dtype=np.int32)
        pivot_level = np.full(n, np.nan)

        # Track current pivot state (Pine: var pivot swingHigh/swingLow)
        current_high_level = np.nan
        current_high_last_level = np.nan
        current_high_index = 0
        current_low_level = np.nan
        current_low_last_level = np.nan
        current_low_index = 0

        # Store pivot info for each bar
        high_levels = np.full(n, np.nan)
        high_last_levels = np.full(n, np.nan)
        high_crossed = np.zeros(n, dtype=bool)
        high_indices = np.zeros(n, dtype=np.int32)
        low_levels = np.full(n, np.nan)
        low_last_levels = np.full(n, np.nan)
        low_crossed = np.zeros(n, dtype=bool)
        low_indices = np.zeros(n, dtype=np.int32)

        for i in range(size, n):
            # Pine: startOfNewLeg = ta.change(leg) != 0
            prev_leg = legs[i - 1] if i > 0 else 0
            curr_leg = legs[i]
            new_leg = curr_leg != prev_leg

            if new_leg:
                pivot_low = curr_leg > prev_leg   # startOfBullishLeg: leg changed from 0 to 1
                pivot_high = curr_leg < prev_leg  # startOfBearishLeg: leg changed from 1 to 0

                if pivot_low:
                    # New swing low detected at bar (i - size)
                    current_low_last_level = current_low_level
                    current_low_level = lows[i - size]
                    current_low_index = i - size
                    # Mark in output
                    pivot_type[i] = -1
                    pivot_level[i] = current_low_level

                elif pivot_high:
                    # New swing high detected at bar (i - size)
                    current_high_last_level = current_high_level
                    current_high_level = highs[i - size]
                    current_high_index = i - size
                    pivot_type[i] = 1
                    pivot_level[i] = current_high_level

            # Store current state for displayStructure
            high_levels[i] = current_high_level
            high_last_levels[i] = current_high_last_level
            high_crossed[i] = False  # will be set by displayStructure
            high_indices[i] = current_high_index
            low_levels[i] = current_low_level
            low_last_levels[i] = current_low_last_level
            low_crossed[i] = False
            low_indices[i] = current_low_index

        return (pivot_type, pivot_level,
                high_levels, high_indices, high_crossed,
                low_levels, low_indices, low_crossed)

    # ------------------------------------------------------------------
    # Pine Script: displayStructure() — detect BOS/CHoCH via crossover
    # ------------------------------------------------------------------
    @staticmethod
    def _display_structure(
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        size: int,
        internal: bool = False,
        swing_high_levels: np.ndarray = None,
        swing_low_levels: np.ndarray = None,
    ) -> Dict[str, np.ndarray]:
        """
        Pine Script displayStructure(internal).

        BOS/CHoCH logic:
        - Bullish: close crosses above pivotHigh.currentLevel and not crossed
          - If trend was BEARISH → CHoCH, else → BOS
        - Bearish: close crosses below pivotLow.currentLevel and not crossed
          - If trend was BULLISH → CHoCH, else → BOS

        For internal structure, extra condition:
          internalHigh.currentLevel != swingHigh.currentLevel (confluence filter)
        """
        n = len(closes)
        legs = SMCCalculator._compute_legs(highs, lows, size)

        bos = np.zeros(n, dtype=np.int32)
        choch = np.zeros(n, dtype=np.int32)
        level = np.full(n, np.nan)

        # Pine: var trend t_rend = trend.new(0)
        trend_bias = 0  # 0 = neutral, 1 = BULLISH, -1 = BEARISH

        # Pine: var pivot swingHigh/swingLow with currentLevel, crossed
        ph_level = np.nan      # pivotHigh.currentLevel
        ph_crossed = True      # pivotHigh.crossed (start True so no spurious signals)
        ph_index = 0           # pivotHigh.barIndex

        pl_level = np.nan      # pivotLow.currentLevel
        pl_crossed = True
        pl_index = 0

        trend_arr = np.zeros(n, dtype=np.int32)

        # Tracking for order blocks: record when BOS/CHoCH fires
        ob_events = []  # list of (bar_index, bias, pivot_index)

        for i in range(1, n):
            prev_leg = legs[i - 1] if i > 0 else 0
            curr_leg = legs[i]

            # getCurrentStructure: detect new pivots
            if curr_leg != prev_leg and i >= size:
                if curr_leg > prev_leg:  # pivot low (bullish leg start)
                    pl_level = lows[i - size]
                    pl_crossed = False
                    pl_index = i - size
                elif curr_leg < prev_leg:  # pivot high (bearish leg start)
                    ph_level = highs[i - size]
                    ph_crossed = False
                    ph_index = i - size

            # displayStructure: check for crossover/crossunder
            # Bullish: close crosses above pivotHigh level
            if (not np.isnan(ph_level) and not ph_crossed):
                extra_condition = True
                if internal and swing_high_levels is not None:
                    # Pine: internalHigh.currentLevel != swingHigh.currentLevel
                    if not np.isnan(swing_high_levels[i]) and ph_level == swing_high_levels[i]:
                        extra_condition = False

                if closes[i] > ph_level and extra_condition:
                    if trend_bias == -1:  # was BEARISH → CHoCH
                        choch[i] = 1
                        level[i] = ph_level
                    else:  # was BULLISH or NEUTRAL → BOS
                        bos[i] = 1
                        level[i] = ph_level
                    ph_crossed = True
                    trend_bias = 1  # BULLISH
                    ob_events.append((i, 1, ph_index))  # bullish break

            # Bearish: close crosses below pivotLow level
            if (not np.isnan(pl_level) and not pl_crossed):
                extra_condition = True
                if internal and swing_low_levels is not None:
                    if not np.isnan(swing_low_levels[i]) and pl_level == swing_low_levels[i]:
                        extra_condition = False

                if closes[i] < pl_level and extra_condition:
                    if trend_bias == 1:  # was BULLISH → CHoCH
                        choch[i] = -1
                        level[i] = pl_level
                    else:  # was BEARISH or NEUTRAL → BOS
                        bos[i] = -1
                        level[i] = pl_level
                    pl_crossed = True
                    trend_bias = -1  # BEARISH
                    ob_events.append((i, -1, pl_index))  # bearish break

            trend_arr[i] = trend_bias

        return {
            'bos': bos,
            'choch': choch,
            'level': level,
            'trend': trend_arr,
            'ob_events': ob_events,
        }

    # ------------------------------------------------------------------
    # Swing highs/lows for DataFrame output (rolling window + alternation)
    # ------------------------------------------------------------------
    @staticmethod
    def _swing_highs_lows(ohlc: pd.DataFrame, swing_length: int) -> pd.DataFrame:
        """
        Detect swing high/low using rolling window with alternation enforcement.
        Used for DataFrame column output and order block detection.
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

        # Enforce alternation (remove consecutive same-direction pivots)
        while True:
            positions = np.where(~np.isnan(swing_highs_lows))[0]
            if len(positions) < 2:
                break

            current = swing_highs_lows[positions[:-1]]
            nxt = swing_highs_lows[positions[1:]]

            h = ohlc["high"].iloc[positions[:-1]].values
            l = ohlc["low"].iloc[positions[:-1]].values
            nh = ohlc["high"].iloc[positions[1:]].values
            nl = ohlc["low"].iloc[positions[1:]].values

            index_to_remove = np.zeros(len(positions), dtype=bool)

            consecutive_highs = (current == 1) & (nxt == 1)
            index_to_remove[:-1] |= consecutive_highs & (h < nh)
            index_to_remove[1:] |= consecutive_highs & (h >= nh)

            consecutive_lows = (current == -1) & (nxt == -1)
            index_to_remove[:-1] |= consecutive_lows & (l > nl)
            index_to_remove[1:] |= consecutive_lows & (l <= nl)

            if not index_to_remove.any():
                break

            swing_highs_lows[positions[index_to_remove]] = np.nan

        # Ensure first/last pivot alternation
        positions = np.where(~np.isnan(swing_highs_lows))[0]
        if len(positions) > 0:
            if swing_highs_lows[positions[0]] == 1:
                swing_highs_lows[0] = -1
            if swing_highs_lows[positions[0]] == -1:
                swing_highs_lows[0] = 1
            if swing_highs_lows[positions[-1]] == -1:
                swing_highs_lows[-1] = 1
            if swing_highs_lows[positions[-1]] == 1:
                swing_highs_lows[-1] = -1

        level = np.where(
            ~np.isnan(swing_highs_lows),
            np.where(swing_highs_lows == 1, ohlc["high"], ohlc["low"]),
            np.nan,
        )

        return pd.DataFrame({
            'HighLow': swing_highs_lows,
            'Level': level,
        }, index=ohlc.index)

    # ------------------------------------------------------------------
    # Pine Script: storeOrdeBlock — find OB candle between pivot and break
    # ------------------------------------------------------------------
    @staticmethod
    def _find_order_block(
        parsed_highs: np.ndarray,
        parsed_lows: np.ndarray,
        pivot_index: int,
        break_index: int,
        bias: int,
    ) -> Tuple[int, float, float]:
        """
        Pine Script storeOrdeBlock logic:
        - Bullish: find min parsedLow between pivot and break
        - Bearish: find max parsedHigh between pivot and break
        """
        start = max(pivot_index, 0)
        end = break_index

        if end <= start:
            # Fallback to break bar - 1
            idx = max(break_index - 1, 0)
            return idx, parsed_highs[idx], parsed_lows[idx]

        if bias == 1:  # BULLISH — find min parsedLow
            segment = parsed_lows[start:end]
            min_idx = start + int(np.argmin(segment))
            return min_idx, parsed_highs[min_idx], parsed_lows[min_idx]
        else:  # BEARISH — find max parsedHigh
            segment = parsed_highs[start:end]
            max_idx = start + int(np.argmax(segment))
            return max_idx, parsed_highs[max_idx], parsed_lows[max_idx]

    # ------------------------------------------------------------------
    # Order block detection and mitigation
    # ------------------------------------------------------------------
    @staticmethod
    def _process_order_blocks(
        ohlc: pd.DataFrame,
        ob_events: list,
        ob_filter: str = 'atr',
        close_mitigation: bool = False,
    ) -> pd.DataFrame:
        """
        Process order blocks from BOS/CHoCH events.

        Pine Script flow:
        1. storeOrdeBlock called when BOS/CHoCH fires
        2. deleteOrderBlocks checks mitigation each bar
        3. drawOrderBlocks renders on chart
        """
        n = len(ohlc)
        _high = ohlc["high"].values
        _low = ohlc["low"].values
        _close = ohlc["close"].values
        _open = ohlc["open"].values
        _volume = ohlc["volume"].values if "volume" in ohlc.columns else np.ones(n)

        # Compute parsed highs/lows (Pine Script high volatility inversion)
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

        ob = np.zeros(n, dtype=np.int32)
        top_arr = np.zeros(n, dtype=np.float64)
        bottom_arr = np.zeros(n, dtype=np.float64)
        ob_volume = np.zeros(n, dtype=np.float64)
        mitigated_index = np.zeros(n, dtype=np.int32)
        percentage = np.zeros(n, dtype=np.float64)

        # Build OBs from events
        for break_bar, bias, pivot_idx in ob_events:
            ob_idx, ob_top, ob_btm = SMCCalculator._find_order_block(
                parsed_high, parsed_low, pivot_idx, break_bar, bias
            )

            ob[ob_idx] = bias
            top_arr[ob_idx] = ob_top
            bottom_arr[ob_idx] = ob_btm

            # Volume analysis
            v0 = _volume[break_bar] if break_bar < n else 0
            v1 = _volume[break_bar - 1] if break_bar >= 1 else 0
            v2 = _volume[break_bar - 2] if break_bar >= 2 else 0
            ob_volume[ob_idx] = v0 + v1 + v2
            if bias == 1:
                low_vol = v2
                high_vol = v0 + v1
            else:
                low_vol = v0 + v1
                high_vol = v2
            max_vol = max(high_vol, low_vol)
            percentage[ob_idx] = (min(high_vol, low_vol) / max_vol * 100.0) if max_vol != 0 else 100.0

        # Mitigation tracking (Pine: deleteOrderBlocks)
        for idx in np.where(ob != 0)[0]:
            bias = ob[idx]
            for j in range(idx + 1, n):
                if bias == -1:
                    # Bearish OB mitigated when price goes above
                    src = _high[j] if not close_mitigation else max(_open[j], _close[j])
                    if src > top_arr[idx]:
                        mitigated_index[idx] = j
                        break
                else:
                    # Bullish OB mitigated when price goes below
                    src = _low[j] if not close_mitigation else min(_open[j], _close[j])
                    if src < bottom_arr[idx]:
                        mitigated_index[idx] = j
                        break

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

    # ------------------------------------------------------------------
    # Also keep _detect_order_blocks for backward compatibility with tests
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_order_blocks(
        ohlc: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        close_mitigation: bool = False,
        ob_filter: str = 'atr',
    ) -> pd.DataFrame:
        """
        Order Block detection based on swing point breakouts.
        Kept for backward compatibility with existing tests.
        """
        n = len(ohlc)
        _open = ohlc["open"].values
        _high = ohlc["high"].values
        _low = ohlc["low"].values
        _close = ohlc["close"].values
        _volume = ohlc["volume"].values if "volume" in ohlc.columns else np.ones(n)
        swing_hl = swing_highs_lows["HighLow"].values

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

            pos = np.searchsorted(swing_high_indices, i)
            last_top_index = swing_high_indices[pos - 1] if pos > 0 else None

            if last_top_index is not None:
                if _close[i] > _high[last_top_index] and not crossed[last_top_index]:
                    crossed[last_top_index] = True
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

    # ------------------------------------------------------------------
    # BOS/CHoCH detection (backward compatible static method for tests)
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_bos_choch(
        ohlc: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        close_break: bool = True,
    ) -> pd.DataFrame:
        """
        BOS/CHoCH detection matching Pine Script displayStructure() logic.

        Uses real-time crossover of close vs pivot level + trend state:
        - BOS: trend continues (close crosses pivot in same direction as trend)
        - CHoCH: trend reverses (close crosses pivot against current trend)
        """
        n = len(ohlc)
        closes = ohlc["close"].values
        highs_arr = ohlc["high"].values
        lows_arr = ohlc["low"].values

        hl_values = swing_highs_lows['HighLow'].values
        lv_values = swing_highs_lows['Level'].values

        bos = np.zeros(n, dtype=np.int32)
        choch = np.zeros(n, dtype=np.int32)
        level = np.full(n, np.nan)
        broken = np.zeros(n, dtype=np.int32)

        # Pine Script state
        trend_bias = 0
        ph_level = np.nan
        ph_crossed = True
        ph_index = 0
        pl_level = np.nan
        pl_crossed = True
        pl_index = 0

        for i in range(n):
            # Update pivots from swing_highs_lows
            if not np.isnan(hl_values[i]):
                if hl_values[i] == 1:
                    ph_level = lv_values[i]
                    ph_crossed = False
                    ph_index = i
                elif hl_values[i] == -1:
                    pl_level = lv_values[i]
                    pl_crossed = False
                    pl_index = i

            # Bullish crossover
            if not np.isnan(ph_level) and not ph_crossed:
                cross_src = closes[i] if close_break else highs_arr[i]
                if cross_src > ph_level:
                    if trend_bias == -1:
                        choch[i] = 1
                    else:
                        bos[i] = 1
                    level[i] = ph_level
                    broken[i] = i
                    ph_crossed = True
                    trend_bias = 1

            # Bearish crossunder
            if not np.isnan(pl_level) and not pl_crossed:
                cross_src = closes[i] if close_break else lows_arr[i]
                if cross_src < pl_level:
                    if trend_bias == 1:
                        choch[i] = -1
                    else:
                        bos[i] = -1
                    level[i] = pl_level
                    broken[i] = i
                    pl_crossed = True
                    trend_bias = -1

        bos = np.where(bos != 0, bos, np.nan)
        choch = np.where(choch != 0, choch, np.nan)
        broken = np.where(broken != 0, broken, np.nan)

        return pd.DataFrame({
            'BOS': bos,
            'CHOCH': choch,
            'Level': level,
            'BrokenIndex': broken,
        }, index=ohlc.index)

    # ------------------------------------------------------------------
    # FVG detection
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_fvg(ohlc: pd.DataFrame, join_consecutive: bool = False) -> pd.DataFrame:
        """
        FVG detection with mitigation tracking.

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

        mitigated_index = np.zeros(len(ohlc), dtype=np.int32)
        for i in np.where(~np.isnan(fvg))[0]:
            if i + 2 >= len(ohlc):
                continue
            if fvg[i] == 1:
                mask = ohlc["low"].iloc[i + 2:].values <= top[i]
            elif fvg[i] == -1:
                mask = ohlc["high"].iloc[i + 2:].values >= bottom[i]
            else:
                continue
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

    # ------------------------------------------------------------------
    # Liquidity detection
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_liquidity(
        ohlc: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        range_percent: float = 0.01,
    ) -> pd.DataFrame:
        """Liquidity detection — clustered swing points."""
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

    # ------------------------------------------------------------------
    # ATR calculation
    # ------------------------------------------------------------------
    def _calculate_atr(self, df: pd.DataFrame, period: int = 200) -> pd.Series:
        """Pine Script: ta.atr(200) — SMA of true range."""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()

        return atr

    # ------------------------------------------------------------------
    # Equal Highs/Lows — Pine Script style (swing point comparison)
    # ------------------------------------------------------------------
    def _detect_equal_hl(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Pine Script getCurrentStructure(equalHighsLowsLengthInput, true):
        Compares consecutive swing point levels.
        Also checks within lookback window for nearby levels.
        """
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

    # ------------------------------------------------------------------
    # Premium/Discount Zones with trailing extremes
    # ------------------------------------------------------------------
    def _calculate_zones(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Pine Script: trailing extremes + premium/discount/equilibrium zones.

        trailing.top = max(high, trailing.top)  — updated each bar
        trailing.bottom = min(low, trailing.bottom)  — updated each bar
        Zones based on trailing range.
        """
        swing_highs = df[df['swing_high_point']]['high']
        swing_lows = df[df['swing_low_point']]['low']

        if len(swing_highs) > 0 and len(swing_lows) > 0:
            recent_high = swing_highs.iloc[-1]
            recent_low = swing_lows.iloc[-1]

            # Pine: trailing extremes update each bar after last swing
            last_swing_idx = max(swing_highs.index[-1], swing_lows.index[-1])
            trailing_top = recent_high
            trailing_bottom = recent_low

            for i in range(df.index.get_loc(last_swing_idx), len(df)):
                trailing_top = max(trailing_top, df['high'].iloc[i])
                trailing_bottom = min(trailing_bottom, df['low'].iloc[i])

            equilibrium = (trailing_top + trailing_bottom) / 2

            df['zone_high'] = trailing_top
            df['zone_low'] = trailing_bottom
            df['equilibrium'] = equilibrium
            df['premium_zone'] = df['close'] > equilibrium
            df['discount_zone'] = df['close'] < equilibrium

            rng = trailing_top - trailing_bottom
            df['zone_position'] = (df['close'] - trailing_bottom) / rng if rng != 0 else 0.5

        return df

    # ------------------------------------------------------------------
    # Main calculation pipeline
    # ------------------------------------------------------------------
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Execute full SMC calculation matching Pine Script logic."""
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]

        n = len(df)

        # Auto-scale swing_length to fit available data
        effective_swing = min(self.swing_length, max(5, n // 10))
        effective_internal = min(self.internal_length, max(3, n // 20))
        if effective_swing != self.swing_length:
            logger.info(f"Auto-scaled swing_length {self.swing_length} -> {effective_swing} for {n} bars")

        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        # ATR
        df['atr'] = self._calculate_atr(df)
        df['volatility'] = df['atr'] if self.order_block_filter == 'atr' else (df['high'] - df['low']).expanding().mean()

        # ---- Swing structure (rolling window for DataFrame output) ----
        swing_result = self._swing_highs_lows(df, effective_swing)
        df['swing_high_point'] = (swing_result['HighLow'] == 1).values
        df['swing_low_point'] = (swing_result['HighLow'] == -1).values
        df['swing_high_level'] = np.where(swing_result['HighLow'] == 1, swing_result['Level'], np.nan)
        df['swing_low_level'] = np.where(swing_result['HighLow'] == -1, swing_result['Level'], np.nan)

        # ---- Internal structure ----
        internal_result = self._swing_highs_lows(df, effective_internal)
        df['internal_high_point'] = (internal_result['HighLow'] == 1).values
        df['internal_low_point'] = (internal_result['HighLow'] == -1).values
        df['internal_high_level'] = np.where(internal_result['HighLow'] == 1, internal_result['Level'], np.nan)
        df['internal_low_level'] = np.where(internal_result['HighLow'] == -1, internal_result['Level'], np.nan)

        # ---- Leg direction (Pine Script leg() function) ----
        df['leg'] = 0
        size = effective_swing
        leg_vals = self._compute_legs(highs, lows, size)
        df['leg'] = leg_vals

        # ---- BOS/CHoCH via Pine Script displayStructure logic ----
        # Swing structure: use swing_result pivots
        swing_struct = self._detect_bos_choch(df, swing_result, close_break=True)

        # For internal structure, pass swing high/low levels for confluence filter
        swing_high_levels_arr = np.full(n, np.nan)
        swing_low_levels_arr = np.full(n, np.nan)
        # Forward-fill swing levels so internal structure can check confluence
        last_sh = np.nan
        last_sl = np.nan
        for i in range(n):
            if swing_result['HighLow'].values[i] == 1:
                last_sh = swing_result['Level'].values[i]
            if swing_result['HighLow'].values[i] == -1:
                last_sl = swing_result['Level'].values[i]
            swing_high_levels_arr[i] = last_sh
            swing_low_levels_arr[i] = last_sl

        internal_struct = self._display_structure(
            closes, highs, lows,
            effective_internal,
            internal=True,
            swing_high_levels=swing_high_levels_arr,
            swing_low_levels=swing_low_levels_arr,
        )

        # Swing BOS/CHoCH
        df['bos_bull'] = (swing_struct['BOS'] == 1).values
        df['bos_bear'] = (swing_struct['BOS'] == -1).values
        df['choch_bull'] = (swing_struct['CHOCH'] == 1).values
        df['choch_bear'] = (swing_struct['CHOCH'] == -1).values

        # Internal BOS/CHoCH
        df['internal_bos_bull'] = (internal_struct['bos'] == 1)
        df['internal_bos_bear'] = (internal_struct['bos'] == -1)
        df['internal_choch_bull'] = (internal_struct['choch'] == 1)
        df['internal_choch_bear'] = (internal_struct['choch'] == -1)

        # ---- Trend tracking ----
        # Swing trend from swing BOS/CHoCH
        df['swing_trend'] = 0
        swing_trend = 0
        for i in range(n):
            if df['bos_bull'].iloc[i] or df['choch_bull'].iloc[i]:
                swing_trend = 1
            elif df['bos_bear'].iloc[i] or df['choch_bear'].iloc[i]:
                swing_trend = -1
            df.iloc[i, df.columns.get_loc('swing_trend')] = swing_trend

        # Internal trend from internal BOS/CHoCH
        df['internal_trend'] = internal_struct['trend']

        self.swing_trend = TrendBias(swing_trend) if swing_trend != 0 else TrendBias.NEUTRAL
        internal_trend_val = internal_struct['trend'][-1] if n > 0 else 0
        self.internal_trend = TrendBias(internal_trend_val) if internal_trend_val != 0 else TrendBias.NEUTRAL

        # Store structure signals
        for i in range(n):
            bar_time = df['date'].iloc[i] if 'date' in df.columns else None
            if df['bos_bull'].iloc[i]:
                self.structure_signals.append(StructureSignal('BOS', TrendBias.BULLISH, swing_struct['Level'].iloc[i], i, bar_time))
            if df['bos_bear'].iloc[i]:
                self.structure_signals.append(StructureSignal('BOS', TrendBias.BEARISH, swing_struct['Level'].iloc[i], i, bar_time))
            if df['choch_bull'].iloc[i]:
                self.structure_signals.append(StructureSignal('CHoCH', TrendBias.BULLISH, swing_struct['Level'].iloc[i], i, bar_time))
            if df['choch_bear'].iloc[i]:
                self.structure_signals.append(StructureSignal('CHoCH', TrendBias.BEARISH, swing_struct['Level'].iloc[i], i, bar_time))

        # ---- Order Blocks (from swing structure BOS/CHoCH events) ----
        # Use the swing-breakout based method for order blocks
        ob_result = self._detect_order_blocks(df, swing_result, close_mitigation=False, ob_filter=self.order_block_filter)
        df['bullish_ob'] = (ob_result['OB'] == 1).values
        df['bearish_ob'] = (ob_result['OB'] == -1).values
        df['ob_high'] = np.where(~np.isnan(ob_result['OB']), ob_result['Top'], np.nan)
        df['ob_low'] = np.where(~np.isnan(ob_result['OB']), ob_result['Bottom'], np.nan)

        for i in range(n):
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

        # ---- FVG ----
        fvg_result = self._detect_fvg(df)
        df['bullish_fvg'] = (fvg_result['FVG'] == 1).values
        df['bearish_fvg'] = (fvg_result['FVG'] == -1).values
        df['fvg_top'] = np.where(~np.isnan(fvg_result['FVG']), fvg_result['Top'], np.nan)
        df['fvg_bottom'] = np.where(~np.isnan(fvg_result['FVG']), fvg_result['Bottom'], np.nan)

        for i in range(n):
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

        # ---- Premium/Discount Zones ----
        df = self._calculate_zones(df)

        return df

    def get_summary(self, df: pd.DataFrame) -> Dict:
        """Get SMC analysis summary."""
        if len(df) < 2:
            return {'error': 'Insufficient data'}

        last_row = df.iloc[-1]

        recent_signals = []
        lookback = 10

        for i in range(max(0, len(df) - lookback), len(df)):
            row = df.iloc[i]
            if row.get('bos_bull', False):
                recent_signals.append({'type': 'BOS', 'bias': 'bullish', 'index': i})
            if row.get('bos_bear', False):
                recent_signals.append({'type': 'BOS', 'bias': 'bearish', 'index': i})
            if row.get('choch_bull', False):
                recent_signals.append({'type': 'CHoCH', 'bias': 'bullish', 'index': i})
            if row.get('choch_bear', False):
                recent_signals.append({'type': 'CHoCH', 'bias': 'bearish', 'index': i})

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
# Convenience function
# ============================================================

def calculate_smc(
    df: pd.DataFrame,
    swing_length: int = 50,
    internal_length: int = 5,
    **kwargs
) -> Tuple[pd.DataFrame, Dict]:
    """
    Calculate SMC indicators.

    Returns:
    - df: DataFrame with SMC indicators
    - summary: SMC analysis summary dict
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
# Test function
# ============================================================

def test_smc():
    """Test SMC calculation."""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=200, freq='D')

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

    result_df, summary = calculate_smc(df, swing_length=20, internal_length=5)

    print("SMC Results:")
    print("\nStructure signals:")
    signal_cols = ['date', 'close', 'bos_bull', 'bos_bear', 'choch_bull', 'choch_bear', 'swing_trend']
    print(result_df[result_df['bos_bull'] | result_df['bos_bear'] | result_df['choch_bull'] | result_df['choch_bear']][signal_cols].tail(10))

    print("\n\nSMC Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    test_smc()
