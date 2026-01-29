"""
pytest 設定：確保 tests 可從專案根或 tw_stock_screener 執行，並註冊 integration mark
"""
import sys
from pathlib import Path

# 讓 from data_fetcher import ... 能正確解析（從 repo 根執行 pytest 時）
_tw_stock_screener = Path(__file__).resolve().parent.parent
if str(_tw_stock_screener) not in sys.path:
    sys.path.insert(0, str(_tw_stock_screener))


def pytest_configure(config):
    """註冊自訂 mark，避免 pytest 對未知 mark 發出警告"""
    config.addinivalue_line("markers", "integration: 整合測試，會實際呼叫外部 API（可略過：pytest -m 'not integration'）")
