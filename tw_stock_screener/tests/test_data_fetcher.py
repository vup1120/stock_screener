"""
資料抓取整合測試 - 驗證能否成功從外部 API 取得台股資料
執行：cd tw_stock_screener && pytest tests/test_data_fetcher.py -v
"""
import pytest
import pandas as pd

from data_fetcher import UnifiedDataFetcher

REQUIRED_OHLCV_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume']


@pytest.mark.integration
def test_fetch_tw_stock_data_success():
    """台股日線：UnifiedDataFetcher 能成功取得 2330 台積電資料且格式正確"""
    fetcher = UnifiedDataFetcher()
    df = fetcher.get_tw_stock_data('2330', days=30)

    assert df is not None, "應回傳 DataFrame，不應為 None"
    assert isinstance(df, pd.DataFrame), "回傳型別應為 pd.DataFrame"

    for col in REQUIRED_OHLCV_COLUMNS:
        assert col in df.columns, f"應包含欄位: {col}"

    assert len(df) >= 1, "至少應有一筆資料"

    assert pd.api.types.is_datetime64_any_dtype(df['date']), "date 應為 datetime"
    for col in ['open', 'high', 'low', 'close', 'volume']:
        assert pd.api.types.is_numeric_dtype(df[col]), f"{col} 應為數值型別"


@pytest.mark.integration
def test_fetch_institutional_trading_success():
    """三大法人：能成功取得 2330 三大法人買賣超資料"""
    fetcher = UnifiedDataFetcher()
    df = fetcher.get_institutional_trading('2330', days=5)

    assert df is not None, "應回傳 DataFrame，不應為 None"
    assert isinstance(df, pd.DataFrame), "回傳型別應為 pd.DataFrame"
    assert len(df) >= 1, "至少應有一筆資料"
