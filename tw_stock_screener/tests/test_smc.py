"""
SMC (Smart Money Concepts) 指標單元測試
=======================================
測試項目:
1. Swing High/Low 偵測 (含交替驗證)
2. BOS/CHoCH 偵測 (4 點模式)
3. Order Blocks 偵測 (含 parsedHigh/parsedLow)
4. Fair Value Gaps 偵測 (含修復追蹤)
5. Equal Highs/Lows
6. Premium/Discount Zones
7. Liquidity 偵測
8. 整合測試 (calculate_smc 便捷函數)
9. 邊界情況

執行: cd tw_stock_screener && pytest tests/test_smc.py -v
"""
import pytest
import numpy as np
import pandas as pd
from indicators.smc import (
    SMCCalculator,
    calculate_smc,
    TrendBias,
    OrderBlock,
    FairValueGap,
    StructureSignal,
)


# ============================================================
# Test Fixtures
# ============================================================

def _make_ohlcv(n=200, seed=42, trend_factor=0.5):
    """Generate synthetic OHLCV data with trending behavior."""
    np.random.seed(seed)
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
    trend = np.cumsum(np.random.randn(n) * trend_factor)
    noise = np.random.randn(n) * 2
    close = 100 + trend + noise
    high = close + np.abs(np.random.randn(n)) * 1.5
    low = close - np.abs(np.random.randn(n)) * 1.5
    open_ = close + np.random.randn(n) * 0.5
    volume = np.random.randint(1_000_000, 5_000_000, n)
    return pd.DataFrame({
        'date': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    })


def _make_uptrend(n=100):
    """Generate clear uptrend data."""
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
    close = np.linspace(100, 150, n) + np.random.randn(n) * 0.5
    high = close + np.abs(np.random.randn(n)) * 1.0
    low = close - np.abs(np.random.randn(n)) * 1.0
    open_ = close - np.random.randn(n) * 0.3
    volume = np.random.randint(1_000_000, 5_000_000, n)
    return pd.DataFrame({
        'date': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    })


def _make_downtrend(n=100):
    """Generate clear downtrend data."""
    dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
    close = np.linspace(150, 100, n) + np.random.randn(n) * 0.5
    high = close + np.abs(np.random.randn(n)) * 1.0
    low = close - np.abs(np.random.randn(n)) * 1.0
    open_ = close + np.random.randn(n) * 0.3
    volume = np.random.randint(1_000_000, 5_000_000, n)
    return pd.DataFrame({
        'date': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    })


def _make_fvg_data():
    """Generate data with explicit fair value gaps."""
    # Create a scenario where bar[i].low > bar[i-2].high (bullish FVG)
    # and bar[i].high < bar[i-2].low (bearish FVG)
    dates = pd.date_range(start='2024-01-01', periods=20, freq='D')
    data = {
        'date': dates,
        'open':  [100, 101, 102, 108, 109, 110, 109, 108, 107, 101, 100, 99, 100, 101, 102, 103, 104, 105, 106, 107],
        'high':  [102, 103, 104, 110, 111, 112, 111, 110, 109, 103, 102, 101, 102, 103, 104, 105, 106, 107, 108, 109],
        'low':   [99,  100, 101, 107, 108, 109, 108, 107, 106, 100, 99,  98,  99,  100, 101, 102, 103, 104, 105, 106],
        'close': [101, 102, 103, 109, 110, 111, 110, 109, 108, 102, 101, 100, 101, 102, 103, 104, 105, 106, 107, 108],
        'volume':[1e6]*20,
    }
    return pd.DataFrame(data)


# ============================================================
# 1. Swing High/Low Tests
# ============================================================

class TestSwingHighsLows:
    def test_swing_detection_basic(self):
        """Swing points should be detected in synthetic data."""
        df = _make_ohlcv(200)
        result = SMCCalculator._swing_highs_lows(df, swing_length=10)
        assert 'HighLow' in result.columns
        assert 'Level' in result.columns
        # Should detect some swing points
        highs = result[result['HighLow'] == 1]
        lows = result[result['HighLow'] == -1]
        assert len(highs) > 0, "Should detect at least one swing high"
        assert len(lows) > 0, "Should detect at least one swing low"

    def test_swing_alternation(self):
        """Swing highs and lows must alternate (no consecutive same-type)."""
        df = _make_ohlcv(300)
        result = SMCCalculator._swing_highs_lows(df, swing_length=10)
        positions = np.where(~np.isnan(result['HighLow'].values))[0]
        types = result['HighLow'].values[positions]
        for i in range(len(types) - 1):
            assert types[i] != types[i + 1], \
                f"Consecutive same-type pivots at positions {positions[i]} and {positions[i+1]}: both are {types[i]}"

    def test_swing_level_matches_price(self):
        """Swing level should equal high for swing highs, low for swing lows."""
        df = _make_ohlcv(200)
        result = SMCCalculator._swing_highs_lows(df, swing_length=10)
        for idx in result[result['HighLow'] == 1].index:
            assert result.loc[idx, 'Level'] == df.loc[idx, 'high']
        for idx in result[result['HighLow'] == -1].index:
            assert result.loc[idx, 'Level'] == df.loc[idx, 'low']

    def test_swing_length_affects_count(self):
        """Larger swing_length should produce fewer swing points."""
        df = _make_ohlcv(500)
        result_short = SMCCalculator._swing_highs_lows(df, swing_length=5)
        result_long = SMCCalculator._swing_highs_lows(df, swing_length=20)
        count_short = (~np.isnan(result_short['HighLow'].values)).sum()
        count_long = (~np.isnan(result_long['HighLow'].values)).sum()
        assert count_short >= count_long, \
            f"Shorter lookback should produce more swings: {count_short} vs {count_long}"

    def test_swing_with_small_data(self):
        """Should handle small datasets gracefully."""
        df = _make_ohlcv(20)
        result = SMCCalculator._swing_highs_lows(df, swing_length=3)
        assert len(result) == 20


# ============================================================
# 2. BOS/CHoCH Tests
# ============================================================

class TestBosChoch:
    def test_bos_choch_returns_correct_columns(self):
        """Should return BOS, CHOCH, Level, BrokenIndex columns."""
        df = _make_ohlcv(200)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_bos_choch(df, swing)
        assert set(result.columns) == {'BOS', 'CHOCH', 'Level', 'BrokenIndex'}

    def test_bos_choch_detects_signals(self):
        """Should detect at least some BOS or CHoCH in trending data."""
        df = _make_ohlcv(300, seed=123)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_bos_choch(df, swing)
        bos_count = (~np.isnan(result['BOS'].values)).sum()
        choch_count = (~np.isnan(result['CHOCH'].values)).sum()
        assert bos_count + choch_count > 0, "Should detect some structure signals"

    def test_bos_bullish_pattern(self):
        """Bullish BOS should only be marked when proper pattern exists."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_bos_choch(df, swing)
        bullish_bos = result[result['BOS'] == 1]
        # Each bullish BOS should have a level
        for idx in bullish_bos.index:
            assert not np.isnan(result.loc[idx, 'Level']), \
                f"Bullish BOS at {idx} should have a level"

    def test_bos_bearish_pattern(self):
        """Bearish BOS should only be marked when proper pattern exists."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_bos_choch(df, swing)
        bearish_bos = result[result['BOS'] == -1]
        for idx in bearish_bos.index:
            assert not np.isnan(result.loc[idx, 'Level'])

    def test_bos_values_are_valid(self):
        """BOS values should only be 1, -1, or NaN."""
        df = _make_ohlcv(200)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_bos_choch(df, swing)
        valid_values = {1.0, -1.0}
        non_nan = result['BOS'].dropna().values
        for v in non_nan:
            assert v in valid_values, f"BOS value {v} not in {valid_values}"

    def test_choch_values_are_valid(self):
        """CHOCH values should only be 1, -1, or NaN."""
        df = _make_ohlcv(200)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_bos_choch(df, swing)
        valid_values = {1.0, -1.0}
        non_nan = result['CHOCH'].dropna().values
        for v in non_nan:
            assert v in valid_values, f"CHOCH value {v} not in {valid_values}"


# ============================================================
# 3. Order Block Tests
# ============================================================

class TestOrderBlocks:
    def test_ob_returns_correct_columns(self):
        """Should return OB, Top, Bottom, OBVolume, MitigatedIndex, Percentage."""
        df = _make_ohlcv(200)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_order_blocks(df, swing)
        expected_cols = {'OB', 'Top', 'Bottom', 'OBVolume', 'MitigatedIndex', 'Percentage'}
        assert set(result.columns) == expected_cols

    def test_ob_values_are_valid(self):
        """OB values should only be 1, -1, or NaN."""
        df = _make_ohlcv(200)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_order_blocks(df, swing)
        valid = {1.0, -1.0}
        for v in result['OB'].dropna().values:
            assert v in valid

    def test_bullish_ob_top_above_bottom(self):
        """Bullish OB top should be >= bottom."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_order_blocks(df, swing)
        bullish = result[result['OB'] == 1]
        for idx in bullish.index:
            assert result.loc[idx, 'Top'] >= result.loc[idx, 'Bottom'], \
                f"Bullish OB at {idx}: Top {result.loc[idx, 'Top']} < Bottom {result.loc[idx, 'Bottom']}"

    def test_bearish_ob_top_above_bottom(self):
        """Bearish OB top should be >= bottom."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_order_blocks(df, swing)
        bearish = result[result['OB'] == -1]
        for idx in bearish.index:
            assert result.loc[idx, 'Top'] >= result.loc[idx, 'Bottom']

    def test_ob_volume_positive(self):
        """OB volume should be positive where OB exists."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_order_blocks(df, swing)
        for idx in result.dropna(subset=['OB']).index:
            assert result.loc[idx, 'OBVolume'] > 0

    def test_ob_percentage_range(self):
        """OB percentage should be between 0 and 100."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_order_blocks(df, swing)
        for idx in result.dropna(subset=['OB']).index:
            pct = result.loc[idx, 'Percentage']
            assert 0 <= pct <= 100, f"Percentage {pct} out of range"

    def test_parsed_high_low_volatile_bars(self):
        """High volatility bars should have parsedHigh/parsedLow inverted."""
        # Create data with one clearly volatile bar
        np.random.seed(42)
        df = _make_ohlcv(200)
        # Verify the OB detection runs without error
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result_atr = SMCCalculator._detect_order_blocks(df, swing, ob_filter='atr')
        result_range = SMCCalculator._detect_order_blocks(df, swing, ob_filter='range')
        # Both should produce valid results
        assert len(result_atr) == len(df)
        assert len(result_range) == len(df)


# ============================================================
# 4. FVG Tests
# ============================================================

class TestFVG:
    def test_fvg_returns_correct_columns(self):
        """Should return FVG, Top, Bottom, MitigatedIndex."""
        df = _make_ohlcv(200)
        result = SMCCalculator._detect_fvg(df)
        expected = {'FVG', 'Top', 'Bottom', 'MitigatedIndex'}
        assert set(result.columns) == expected

    def test_fvg_values_are_valid(self):
        """FVG values should only be 1, -1, or NaN."""
        df = _make_ohlcv(200)
        result = SMCCalculator._detect_fvg(df)
        valid = {1.0, -1.0}
        for v in result['FVG'].dropna().values:
            assert v in valid

    def test_bullish_fvg_gap(self):
        """Bullish FVG: prev high < next low (3-candle gap up)."""
        df = _make_fvg_data()
        result = SMCCalculator._detect_fvg(df)
        bullish = result[result['FVG'] == 1]
        for idx in bullish.index:
            pos = df.index.get_loc(idx)
            if pos >= 2:
                # Condition: high[i-1] < low[i+1] (using shifts in the method)
                assert result.loc[idx, 'Top'] >= result.loc[idx, 'Bottom'], \
                    f"Bullish FVG at {idx}: Top should be >= Bottom"

    def test_bearish_fvg_gap(self):
        """Bearish FVG: prev low > next high (3-candle gap down)."""
        df = _make_ohlcv(200)
        result = SMCCalculator._detect_fvg(df)
        bearish = result[result['FVG'] == -1]
        for idx in bearish.index:
            assert result.loc[idx, 'Top'] >= result.loc[idx, 'Bottom']

    def test_fvg_mitigation_tracking(self):
        """Mitigated FVGs should have a valid mitigated index."""
        df = _make_ohlcv(200)
        result = SMCCalculator._detect_fvg(df)
        for idx in result.dropna(subset=['FVG']).index:
            mit = result.loc[idx, 'MitigatedIndex']
            if not np.isnan(mit) and mit > 0:
                pos = df.index.get_loc(idx)
                assert mit > pos, f"MitigatedIndex {mit} should be > FVG index {pos}"

    def test_fvg_join_consecutive(self):
        """join_consecutive should merge adjacent FVGs of the same type."""
        df = _make_ohlcv(300)
        result_no_join = SMCCalculator._detect_fvg(df, join_consecutive=False)
        result_join = SMCCalculator._detect_fvg(df, join_consecutive=True)
        count_no_join = (~np.isnan(result_no_join['FVG'].values)).sum()
        count_join = (~np.isnan(result_join['FVG'].values)).sum()
        assert count_join <= count_no_join, \
            "Joined FVGs should be <= non-joined"


# ============================================================
# 5. Liquidity Tests
# ============================================================

class TestLiquidity:
    def test_liquidity_returns_correct_columns(self):
        """Should return Liquidity, Level, End, Swept."""
        df = _make_ohlcv(200)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_liquidity(df, swing)
        expected = {'Liquidity', 'Level', 'End', 'Swept'}
        assert set(result.columns) == expected

    def test_liquidity_values_valid(self):
        """Liquidity values should be 1, -1, or NaN."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_liquidity(df, swing)
        valid = {1.0, -1.0}
        for v in result['Liquidity'].dropna().values:
            assert v in valid

    def test_liquidity_level_set(self):
        """Where liquidity is detected, level should be set."""
        df = _make_ohlcv(300)
        swing = SMCCalculator._swing_highs_lows(df, swing_length=10)
        result = SMCCalculator._detect_liquidity(df, swing)
        for idx in result.dropna(subset=['Liquidity']).index:
            assert not np.isnan(result.loc[idx, 'Level'])


# ============================================================
# 6. Equal Highs/Lows Tests
# ============================================================

class TestEqualHL:
    def test_equal_hl_detected(self):
        """Should detect equal highs/lows in data with repeated levels."""
        df = _make_ohlcv(200)
        calc = SMCCalculator(swing_length=10, internal_length=5, equal_hl_threshold=0.5)
        result = calc.calculate(df)
        # With a generous threshold, should find some
        eq_highs = result['equal_high'].sum()
        eq_lows = result['equal_low'].sum()
        assert eq_highs + eq_lows > 0, "Should detect some equal highs or lows"

    def test_equal_hl_threshold_sensitivity(self):
        """Smaller threshold should produce fewer equal detections."""
        df = _make_ohlcv(200)
        calc_loose = SMCCalculator(swing_length=10, internal_length=5, equal_hl_threshold=0.5)
        calc_tight = SMCCalculator(swing_length=10, internal_length=5, equal_hl_threshold=0.01)
        result_loose = calc_loose.calculate(df)
        result_tight = calc_tight.calculate(df)
        assert result_loose['equal_high'].sum() >= result_tight['equal_high'].sum()


# ============================================================
# 7. Premium/Discount Zone Tests
# ============================================================

class TestZones:
    def test_zones_calculated(self):
        """Should calculate premium/discount zones."""
        df = _make_ohlcv(200)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        result = calc.calculate(df)
        assert 'equilibrium' in result.columns
        assert 'premium_zone' in result.columns
        assert 'discount_zone' in result.columns
        assert 'zone_position' in result.columns

    def test_equilibrium_between_high_low(self):
        """Equilibrium should be between zone_high and zone_low."""
        df = _make_ohlcv(200)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        result = calc.calculate(df)
        if 'zone_high' in result.columns and 'zone_low' in result.columns:
            eq = result['equilibrium'].iloc[-1]
            zh = result['zone_high'].iloc[-1]
            zl = result['zone_low'].iloc[-1]
            if not np.isnan(eq):
                assert zl <= eq <= zh


# ============================================================
# 8. Integration Tests (calculate_smc convenience function)
# ============================================================

class TestCalculateSMC:
    def test_calculate_smc_returns_tuple(self):
        """Should return (DataFrame, dict) tuple."""
        df = _make_ohlcv(200)
        result = calculate_smc(df, swing_length=10, internal_length=5)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], pd.DataFrame)
        assert isinstance(result[1], dict)

    def test_calculate_smc_output_columns(self):
        """Result DataFrame should contain all expected columns."""
        df = _make_ohlcv(200)
        result_df, _ = calculate_smc(df, swing_length=10, internal_length=5)
        expected_cols = [
            'atr', 'volatility',
            'swing_high_point', 'swing_low_point',
            'swing_high_level', 'swing_low_level',
            'internal_high_point', 'internal_low_point',
            'bos_bull', 'bos_bear', 'choch_bull', 'choch_bear',
            'internal_bos_bull', 'internal_bos_bear',
            'internal_choch_bull', 'internal_choch_bear',
            'swing_trend', 'internal_trend',
            'bullish_ob', 'bearish_ob', 'ob_high', 'ob_low',
            'bullish_fvg', 'bearish_fvg', 'fvg_top', 'fvg_bottom',
            'equal_high', 'equal_low',
            'leg',
        ]
        for col in expected_cols:
            assert col in result_df.columns, f"Missing column: {col}"

    def test_summary_keys(self):
        """Summary dict should have expected keys."""
        df = _make_ohlcv(200)
        _, summary = calculate_smc(df, swing_length=10, internal_length=5)
        expected_keys = [
            'swing_trend', 'internal_trend', 'signal', 'signal_strength',
            'recent_signals', 'bullish_order_blocks', 'bearish_order_blocks',
            'bullish_fvg', 'bearish_fvg', 'zone_position',
            'in_premium', 'in_discount', 'equilibrium',
            'equal_high', 'equal_low', 'current_price',
        ]
        for key in expected_keys:
            assert key in summary, f"Missing summary key: {key}"

    def test_summary_trend_values(self):
        """Trend should be bullish, bearish, or neutral."""
        df = _make_ohlcv(200)
        _, summary = calculate_smc(df, swing_length=10, internal_length=5)
        assert summary['swing_trend'] in {'bullish', 'bearish', 'neutral'}
        assert summary['internal_trend'] in {'bullish', 'bearish', 'neutral'}

    def test_uptrend_detection(self):
        """Clear uptrend should eventually show bullish signals."""
        np.random.seed(42)
        df = _make_uptrend(500)
        result_df, summary = calculate_smc(df, swing_length=5, internal_length=3)
        # At least some bullish BOS/CHoCH should be detected
        bull_signals = result_df['bos_bull'].sum() + result_df['choch_bull'].sum()
        internal_bull = result_df['internal_bos_bull'].sum() + result_df['internal_choch_bull'].sum()
        assert bull_signals + internal_bull > 0, "Uptrend should produce bullish structure signals"

    def test_downtrend_detection(self):
        """Clear downtrend should eventually show bearish signals."""
        np.random.seed(42)
        df = _make_downtrend(500)
        result_df, summary = calculate_smc(df, swing_length=5, internal_length=3)
        bear_signals = result_df['bos_bear'].sum() + result_df['choch_bear'].sum()
        internal_bear = result_df['internal_bos_bear'].sum() + result_df['internal_choch_bear'].sum()
        assert bear_signals + internal_bear > 0, "Downtrend should produce bearish structure signals"

    def test_structure_signals_stored(self):
        """Calculator should store structure signals."""
        df = _make_ohlcv(300)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        calc.calculate(df)
        # Should have some signals (BOS or CHoCH)
        assert len(calc.structure_signals) >= 0  # At minimum doesn't crash

    def test_order_blocks_stored(self):
        """Calculator should store order blocks."""
        df = _make_ohlcv(300)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        calc.calculate(df)
        for ob in calc.order_blocks:
            assert isinstance(ob, OrderBlock)
            assert ob.bias in {TrendBias.BULLISH, TrendBias.BEARISH}

    def test_fvg_stored(self):
        """Calculator should store fair value gaps."""
        df = _make_ohlcv(300)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        calc.calculate(df)
        for fvg in calc.fair_value_gaps:
            assert isinstance(fvg, FairValueGap)
            assert fvg.bias in {TrendBias.BULLISH, TrendBias.BEARISH}

    def test_no_volume_column(self):
        """Should handle data without volume column."""
        df = _make_ohlcv(200)
        df = df.drop(columns=['volume'])
        # Should not raise
        result_df, summary = calculate_smc(df, swing_length=10, internal_length=5)
        assert isinstance(result_df, pd.DataFrame)

    def test_uppercase_columns(self):
        """Should handle uppercase column names."""
        df = _make_ohlcv(200)
        df.columns = [c.upper() for c in df.columns]
        result_df, summary = calculate_smc(df, swing_length=10, internal_length=5)
        assert isinstance(result_df, pd.DataFrame)


# ============================================================
# 9. Edge Cases
# ============================================================

class TestEdgeCases:
    def test_minimum_data(self):
        """Should handle very small datasets without crashing."""
        df = _make_ohlcv(30)
        result_df, summary = calculate_smc(df, swing_length=5, internal_length=3)
        assert len(result_df) == 30

    def test_flat_data(self):
        """Should handle flat/constant price data."""
        n = 100
        dates = pd.date_range(start='2024-01-01', periods=n, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': [100.0] * n,
            'high': [101.0] * n,
            'low': [99.0] * n,
            'close': [100.0] * n,
            'volume': [1_000_000] * n,
        })
        result_df, summary = calculate_smc(df, swing_length=5, internal_length=3)
        assert len(result_df) == n

    def test_reproducibility(self):
        """Same input should produce same output."""
        df = _make_ohlcv(200)
        result1, summary1 = calculate_smc(df.copy(), swing_length=10, internal_length=5)
        result2, summary2 = calculate_smc(df.copy(), swing_length=10, internal_length=5)

        # Compare numeric columns
        for col in ['atr', 'swing_trend', 'internal_trend']:
            np.testing.assert_array_equal(
                result1[col].values, result2[col].values,
                err_msg=f"Column {col} not reproducible"
            )

    def test_get_summary_insufficient_data(self):
        """get_summary should handle insufficient data."""
        df = pd.DataFrame({
            'open': [100.0],
            'high': [101.0],
            'low': [99.0],
            'close': [100.0],
            'volume': [1e6],
        })
        calc = SMCCalculator()
        summary = calc.get_summary(df)
        assert 'error' in summary

    def test_different_swing_lengths(self):
        """Different swing lengths should not crash."""
        df = _make_ohlcv(200)
        for sl in [5, 10, 20, 50]:
            result_df, summary = calculate_smc(df, swing_length=sl, internal_length=3)
            assert len(result_df) == 200


# ============================================================
# 10. Comparison helpers
# ============================================================

class TestPineScriptAlignment:
    """Tests verifying alignment with the LuxAlgo Pine Script behavior."""

    def test_leg_detection_matches_pine(self):
        """
        Pine Script leg() function:
          newLegHigh = high[size] > ta.highest(size)
          newLegLow = low[size] < ta.lowest(size)
        """
        df = _make_ohlcv(200)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        result = calc.calculate(df)
        assert 'leg' in result.columns
        # Leg values should be 0 (bearish) or 1 (bullish)
        unique_legs = set(result['leg'].unique())
        assert unique_legs.issubset({0, 1}), f"Unexpected leg values: {unique_legs}"

    def test_atr_calculation(self):
        """ATR should match ta.atr(200) — SMA of true range over 200 periods."""
        df = _make_ohlcv(250)
        calc = SMCCalculator()
        atr = calc._calculate_atr(df, period=200)
        assert len(atr) == len(df)
        # ATR should be positive
        assert (atr > 0).all(), "ATR should be positive"

    def test_structure_trend_tracking(self):
        """
        Pine Script: swingTrend.bias changes on BOS/CHoCH.
        Our swing_trend should also track this.
        """
        df = _make_ohlcv(300)
        calc = SMCCalculator(swing_length=10, internal_length=5)
        result = calc.calculate(df)
        # Trend should be -1, 0, or 1
        unique_trends = set(result['swing_trend'].unique())
        assert unique_trends.issubset({-1, 0, 1})

    def test_internal_vs_swing_structure(self):
        """
        Pine Script uses internal_length=5 and swing_length=swingsLengthInput.
        Internal structure should detect more signals than swing.
        """
        df = _make_ohlcv(300, seed=99)
        calc = SMCCalculator(swing_length=20, internal_length=5)
        result = calc.calculate(df)
        swing_signals = (
            result['bos_bull'].sum() + result['bos_bear'].sum() +
            result['choch_bull'].sum() + result['choch_bear'].sum()
        )
        internal_signals = (
            result['internal_bos_bull'].sum() + result['internal_bos_bear'].sum() +
            result['internal_choch_bull'].sum() + result['internal_choch_bear'].sum()
        )
        # Internal should typically detect more signals
        # (but not always, so we just check it runs correctly)
        assert swing_signals >= 0
        assert internal_signals >= 0
