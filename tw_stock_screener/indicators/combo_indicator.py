"""
Combo Indicator - UT Bot Migo + EMA Ribbon + MaxMin + SMC
===========================================================
Translated from Pine Script: Combo_Indicator (UT Bot Alerts Migo, EMA Ribbon 1D, Max-Min Price Range, Smart Money Concepts)

Components:
1. UT Bot Alerts Migo - ATR trailing stop, buy/sell signals (use indicators.ut_bot)
2. EMA Ribbon (Fixed 1D) - EMAs 5, 20, 60, 120, 240 on close
3. Max-Min Price Range - rolling highest(high) and lowest(low), optional cloud fill
4. SMC - BOS, CHoCH, Order Blocks, FVG (use indicators.smc)
"""

import pandas as pd
from typing import Dict, Tuple, List, Optional

from .ut_bot import calculate_ut_bot
from .smc import calculate_smc, SMCCalculator
from .smc import TrendBias


# EMA Ribbon colors (Pine: #74b7e7, #1b98f1, #056ab3, #054f84, #032e4c)
EMA_RIBBON_COLORS = {
    5: '#74b7e7',
    20: '#1b98f1',
    60: '#056ab3',
    120: '#054f84',
    240: '#032e4c',
}


def calculate_ema_ribbon(
    df: pd.DataFrame,
    periods: List[int] = [5, 20, 60, 120, 240],
) -> Dict[str, pd.Series]:
    """
    EMA Ribbon (Fixed 1D style).
    In Pine: request.security(..., "1D", ta.ema(close, length)).
    For daily data we compute EMA(close, period) directly.

    Returns:
        dict with keys ema_5, ema_20, ema_60, ema_120, ema_240 (or as per periods)
    """
    result = {}
    close = df['close']
    for p in periods:
        result[f'ema_{p}'] = close.ewm(span=p, adjust=False).mean()
    return result


def calculate_maxmin(
    df: pd.DataFrame,
    length: int = 1,
) -> Tuple[pd.Series, pd.Series]:
    """
    Max-Min Price Range (Pine: ta.highest(high, length), ta.lowest(low, length)).

    Returns:
        (mm_high, mm_low) - rolling highest high and lowest low
    """
    mm_high = df['high'].rolling(window=length, min_periods=1).max()
    mm_low = df['low'].rolling(window=length, min_periods=1).min()
    return mm_high, mm_low


def calculate_combo(
    df: pd.DataFrame,
    ut_config: Optional[Dict] = None,
    ema_periods: Optional[List[int]] = None,
    mm_length: int = 1,
    smc_config: Optional[Dict] = None,
) -> Dict:
    """
    Run full Combo: UT Bot + EMA Ribbon + MaxMin + SMC.

    Returns:
        dict with:
        - ut_data: {atr_trailing_stop, ut_buy, ut_sell} from UT Bot
        - ema_ribbon: {ema_5, ema_20, ...} Series
        - maxmin: {mm_high, mm_low} Series
        - smc_data: {bos_bull, bos_bear, choch_bull, choch_bear, order_blocks, fvg} from SMC
        - smc_summary: SMC summary dict
    """
    ut_config = ut_config or {}
    ema_periods = ema_periods or [5, 20, 60, 120, 240]
    smc_config = smc_config or {}

    out = {}

    # 1. UT Bot
    ut_df = calculate_ut_bot(df, **ut_config)
    out['ut_data'] = {
        'atr_trailing_stop': ut_df['atr_trailing_stop'],
        'ut_buy': ut_df['ut_buy'],
        'ut_sell': ut_df['ut_sell'],
    }

    # 2. EMA Ribbon
    out['ema_ribbon'] = calculate_ema_ribbon(df, periods=ema_periods)

    # 3. Max-Min
    mm_high, mm_low = calculate_maxmin(df, length=mm_length)
    out['maxmin'] = {'mm_high': mm_high, 'mm_low': mm_low}

    # 4. SMC (run calculator so we can pass order_blocks, fvg, sweeps to chart)
    calculator = SMCCalculator(**smc_config)
    smc_df = calculator.calculate(df)
    smc_summary = calculator.get_summary(smc_df)
    ob_list = [
        {
            'high': ob.high, 'low': ob.low, 'bar_index': ob.bar_index,
            'bias': 'bullish' if ob.bias == TrendBias.BULLISH else 'bearish',
            'mitigated': ob.mitigated,
            'confluence_score': ob.confluence_score,
            'has_liquidity_sweep': ob.has_liquidity_sweep,
            'in_fibonacci_ote': ob.in_fibonacci_ote,
            'has_clean_structure': ob.has_clean_structure,
            'has_impulse_to_bos': ob.has_impulse_to_bos,
        }
        for ob in calculator.order_blocks[-10:]
    ]
    fvg_list = [
        {'top': fvg.top, 'bottom': fvg.bottom, 'bar_index': fvg.bar_index, 'bias': 'bullish' if fvg.bias == TrendBias.BULLISH else 'bearish'}
        for fvg in calculator.fair_value_gaps[-10:]
    ]
    sweep_list = [
        {
            'level': s.level, 'swept_level': s.swept_level,
            'bar_index': s.bar_index,
            'bias': 'bullish' if s.bias == TrendBias.BULLISH else 'bearish',
        }
        for s in calculator.liquidity_sweeps[-10:]
    ]
    out['smc_data'] = {
        'bos_bull': smc_df.get('bos_bull'),
        'bos_bear': smc_df.get('bos_bear'),
        'choch_bull': smc_df.get('choch_bull'),
        'choch_bear': smc_df.get('choch_bear'),
        'order_blocks': ob_list,
        'fvg': fvg_list,
        'liquidity_sweeps': sweep_list,
        'liquidity_sweep_bull': smc_df.get('liquidity_sweep_bull'),
        'liquidity_sweep_bear': smc_df.get('liquidity_sweep_bear'),
    }
    out['smc_summary'] = smc_summary

    return out
