"""
資料抓取模組 - 台股/美股資料來源
================================
支援：證交所 API、FinMind、yfinance、本地 CSV 快取
當 API 因網路限制無法連線時，自動使用本地快取資料。
"""

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time
import json
import os
from typing import Optional, List, Dict
import logging

# 證交所/櫃買 SSL 憑證缺少 Subject Key Identifier，部分環境（如 Python 3.13）會驗證失敗；
# 僅對 TWSE/TPEX 請求關閉驗證，其餘來源（FinMind、yfinance）仍驗證。
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

# 設定 logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 快取目錄
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class TWSEDataFetcher:
    """
    證交所 OpenAPI 資料抓取
    - 免費、官方資料
    - 日線資料
    """
    
    BASE_URL = "https://www.twse.com.tw"
    TPEX_URL = "https://www.tpex.org.tw"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_stock_data(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """
        取得單一股票歷史資料
        """
        all_data = []
        end_date = datetime.now()
        
        # 計算需要抓取幾個月
        months_needed = (days // 20) + 2
        
        for i in range(months_needed):
            target_date = end_date - timedelta(days=30*i)
            date_str = target_date.strftime('%Y%m%d')
            
            # 嘗試上市股票
            url = f"{self.BASE_URL}/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={stock_id}"
            
            try:
                response = self.session.get(url, timeout=10, verify=False)
                data = response.json()
                
                if data.get('stat') == 'OK' and 'data' in data:
                    for row in data['data']:
                        try:
                            # 轉換民國年為西元年
                            date_parts = row[0].split('/')
                            year = int(date_parts[0]) + 1911
                            date_str_parsed = f"{year}/{date_parts[1]}/{date_parts[2]}"
                            
                            all_data.append({
                                'date': date_str_parsed,
                                'volume': int(row[1].replace(',', '')) if row[1] != '--' else 0,
                                'turnover': int(row[2].replace(',', '')) if row[2] != '--' else 0,
                                'open': float(row[3].replace(',', '')) if row[3] != '--' else np.nan,
                                'high': float(row[4].replace(',', '')) if row[4] != '--' else np.nan,
                                'low': float(row[5].replace(',', '')) if row[5] != '--' else np.nan,
                                'close': float(row[6].replace(',', '')) if row[6] != '--' else np.nan,
                            })
                        except (ValueError, IndexError) as e:
                            continue
                            
            except Exception as e:
                logger.warning(f"TWSE fetch error for {stock_id}: {e}")
            
            time.sleep(0.3)  # 避免請求過快
        
        if not all_data:
            # 嘗試上櫃股票
            return self._get_tpex_data(stock_id, days)
        
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.drop_duplicates(subset=['date'])
        df = df.sort_values('date').reset_index(drop=True)
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        
        return df.tail(days) if len(df) > days else df
    
    def _get_tpex_data(self, stock_id: str, days: int) -> Optional[pd.DataFrame]:
        """
        取得上櫃股票資料
        """
        all_data = []
        end_date = datetime.now()
        months_needed = (days // 20) + 2
        
        for i in range(months_needed):
            target_date = end_date - timedelta(days=30*i)
            # 轉換為民國年
            roc_year = target_date.year - 1911
            date_str = f"{roc_year}/{target_date.month:02d}/01"
            
            url = f"{self.TPEX_URL}/web/stock/aftertrading/daily_trading_info/st43_result.php?l=zh-tw&d={date_str}&stkno={stock_id}"
            
            try:
                response = self.session.get(url, timeout=10, verify=False)
                data = response.json()
                
                if 'aaData' in data:
                    for row in data['aaData']:
                        try:
                            date_parts = row[0].split('/')
                            year = int(date_parts[0]) + 1911
                            date_str_parsed = f"{year}/{date_parts[1]}/{date_parts[2]}"
                            
                            all_data.append({
                                'date': date_str_parsed,
                                'volume': int(row[1].replace(',', '')) * 1000 if row[1] != '--' else 0,
                                'open': float(row[4].replace(',', '')) if row[4] != '--' else np.nan,
                                'high': float(row[5].replace(',', '')) if row[5] != '--' else np.nan,
                                'low': float(row[6].replace(',', '')) if row[6] != '--' else np.nan,
                                'close': float(row[2].replace(',', '')) if row[2] != '--' else np.nan,
                            })
                        except (ValueError, IndexError):
                            continue
                            
            except Exception as e:
                logger.warning(f"TPEX fetch error for {stock_id}: {e}")
            
            time.sleep(0.3)
        
        if not all_data:
            return None
            
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.drop_duplicates(subset=['date'])
        df = df.sort_values('date').reset_index(drop=True)
        df = df.dropna(subset=['open', 'high', 'low', 'close'])
        
        return df.tail(days) if len(df) > days else df
    
    def get_institutional_trading(self, stock_id: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        取得三大法人買賣超資料
        """
        all_data = []
        end_date = datetime.now()
        
        for i in range(days + 10):
            target_date = end_date - timedelta(days=i)
            if target_date.weekday() >= 5:  # 跳過週末
                continue
                
            date_str = target_date.strftime('%Y%m%d')
            url = f"{self.BASE_URL}/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
            
            try:
                response = self.session.get(url, timeout=10, verify=False)
                data = response.json()
                
                if data.get('stat') == 'OK' and 'data' in data:
                    for row in data['data']:
                        if row[0].strip() == stock_id:
                            all_data.append({
                                'date': target_date.strftime('%Y-%m-%d'),
                                'stock_id': stock_id,
                                'foreign_buy': int(row[2].replace(',', '')),
                                'foreign_sell': int(row[3].replace(',', '')),
                                'foreign_net': int(row[4].replace(',', '')),
                                'investment_trust_buy': int(row[5].replace(',', '')),
                                'investment_trust_sell': int(row[6].replace(',', '')),
                                'investment_trust_net': int(row[7].replace(',', '')),
                                'dealer_net': int(row[8].replace(',', '')),
                                'total_net': int(row[11].replace(',', '')) if len(row) > 11 else 0,
                            })
                            break
                            
            except Exception as e:
                pass
            
            time.sleep(0.2)
            
            if len(all_data) >= days:
                break
        
        if not all_data:
            return None
            
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        return df


class FinMindDataFetcher:
    """
    FinMind API 資料抓取
    - 免費版有每日請求限制
    - 包含更多技術面、籌碼面資料
    """
    
    BASE_URL = "https://api.finmindtrade.com/api/v4/data"
    
    def __init__(self, token: str = ""):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    def get_stock_data(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """
        取得股票歷史資料
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)
        
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
        }
        
        try:
            response = requests.get(self.BASE_URL, headers=self.headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('status') == 200 and data.get('data'):
                df = pd.DataFrame(data['data'])
                df['date'] = pd.to_datetime(df['date'])
                df = df.rename(columns={
                    'Trading_Volume': 'volume',
                    'open': 'open',
                    'max': 'high',
                    'min': 'low',
                    'close': 'close'
                })
                df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
                df = df.sort_values('date').reset_index(drop=True)
                return df.tail(days)
                
        except Exception as e:
            logger.error(f"FinMind fetch error for {stock_id}: {e}")
        
        return None
    
    def get_institutional_trading(self, stock_id: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        取得三大法人買賣超
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days * 2)
        
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": stock_id,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
        }
        
        try:
            response = requests.get(self.BASE_URL, headers=self.headers, params=params, timeout=10)
            data = response.json()
            
            if data.get('status') == 200 and data.get('data'):
                df = pd.DataFrame(data['data'])
                df['date'] = pd.to_datetime(df['date'])
                
                # 整理資料格式
                pivot_df = df.pivot_table(
                    index='date',
                    columns='name',
                    values='buy',
                    aggfunc='sum'
                ).reset_index()
                
                return pivot_df.tail(days)
                
        except Exception as e:
            logger.error(f"FinMind institutional fetch error: {e}")
        
        return None


class YFinanceDataFetcher:
    """
    yfinance 資料抓取（備用方案）
    - 台股代碼需加 .TW 或 .TWO
    - 美股直接使用代碼
    """
    
    def __init__(self):
        try:
            import yfinance as yf
            self.yf = yf
            self.available = True
        except ImportError:
            logger.warning("yfinance not installed. Run: pip install yfinance")
            self.available = False
    
    def get_stock_data(self, stock_id: str, days: int = 120, market: str = 'TW') -> Optional[pd.DataFrame]:
        """
        取得股票歷史資料
        market: 'TW' (台股), 'US' (美股)
        """
        if not self.available:
            return None
        
        # 處理代碼
        if market == 'TW':
            ticker = f"{stock_id}.TW"
        elif market == 'TWO':  # 上櫃
            ticker = f"{stock_id}.TWO"
        else:  # 美股
            ticker = stock_id
        
        try:
            stock = self.yf.Ticker(ticker)
            df = stock.history(period=f"{days}d")
            
            if df.empty and market == 'TW':
                # 嘗試上櫃
                ticker = f"{stock_id}.TWO"
                stock = self.yf.Ticker(ticker)
                df = stock.history(period=f"{days}d")
            
            if df.empty:
                return None
            
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={'date': 'date'})
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            
            return df[['date', 'open', 'high', 'low', 'close', 'volume']]
            
        except Exception as e:
            logger.error(f"yfinance fetch error for {stock_id}: {e}")
            return None


class GitHubRawDataFetcher:
    """
    從 GitHub Raw Content 下載 CSV 快取。

    為什麼有用？
    ─────────────────────────────────────────────────────────────────
    本系統的 GitHub Actions 工作流（.github/workflows/update_data.yml）
    每天自動在 GitHub 上執行 fetch_and_cache.py，並將最新的
    data/<stock_id>_cache.csv 提交回倉庫。

    由於 raw.githubusercontent.com 被此受限環境的出口代理白名單允許，
    即使 TWSE / Yahoo Finance / FinMind 被封鎖，也能透過 GitHub Raw URL
    取得每日更新的股價資料。

    設定方式（擇一）：
    1. 環境變數: export STOCK_DATA_GITHUB_REPO=owner/repo
    2. 環境變數: export STOCK_DATA_GITHUB_BRANCH=main
    3. 直接傳入 owner/repo 字串給建構子
    ─────────────────────────────────────────────────────────────────
    """

    RAW_BASE = "https://raw.githubusercontent.com"
    DEFAULT_REPO   = os.environ.get("STOCK_DATA_GITHUB_REPO",   "vup1120/stock_screener")
    DEFAULT_BRANCH = os.environ.get("STOCK_DATA_GITHUB_BRANCH", "main")

    def __init__(self, repo: str = None, branch: str = None):
        self.repo   = repo   or self.DEFAULT_REPO
        self.branch = branch or self.DEFAULT_BRANCH

    def _url(self, stock_id: str) -> str:
        return (
            f"{self.RAW_BASE}/{self.repo}/{self.branch}"
            f"/tw_stock_screener/data/{stock_id}_cache.csv"
        )

    def get_stock_data(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """
        從 GitHub Raw URL 下載最新 CSV 快取。
        該 CSV 由 GitHub Actions 工作流每日自動更新。
        """
        url = self._url(stock_id)
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"GitHub raw fetch HTTP {resp.status_code} for {stock_id}: {url}")
                return None
            from io import StringIO
            df = pd.read_csv(StringIO(resp.text))
            df['date'] = pd.to_datetime(df['date'])
            required = {'date', 'open', 'high', 'low', 'close', 'volume'}
            if not required.issubset(df.columns):
                logger.warning(f"GitHub raw CSV for {stock_id} missing columns")
                return None
            df = df.sort_values('date').reset_index(drop=True)
            logger.info(f"GitHub raw: fetched {len(df)} rows for {stock_id} from {url}")
            return df.tail(days).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"GitHub raw fetch error for {stock_id}: {e}")
            return None


class LocalCSVDataFetcher:
    """
    本地 CSV 快取資料來源
    - 當外部 API 無法連線時作為最終備援
    - 同時在 API 成功後自動儲存快取供離線使用
    - 快取路徑: tw_stock_screener/data/<stock_id>_cache.csv
    """

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def cache_path(self, stock_id: str) -> str:
        return os.path.join(self.cache_dir, f"{stock_id}_cache.csv")

    def save(self, stock_id: str, df: pd.DataFrame) -> None:
        """儲存資料到本地 CSV 快取"""
        try:
            path = self.cache_path(stock_id)
            df_save = df.copy()
            df_save['date'] = pd.to_datetime(df_save['date']).dt.strftime('%Y-%m-%d')
            df_save.to_csv(path, index=False)
            logger.info(f"Cached {len(df)} rows for {stock_id} → {path}")
        except Exception as e:
            logger.warning(f"Failed to save cache for {stock_id}: {e}")

    def load(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """從本地 CSV 快取載入資料"""
        path = self.cache_path(stock_id)
        if not os.path.exists(path):
            return None
        try:
            df = pd.read_csv(path)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            # 只回傳指定天數
            return df.tail(days).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Failed to load cache for {stock_id}: {e}")
            return None

    def is_fresh(self, stock_id: str, max_age_days: int = 1) -> bool:
        """快取是否在 max_age_days 天內"""
        path = self.cache_path(stock_id)
        if not os.path.exists(path):
            return False
        mtime = os.path.getmtime(path)
        age = (time.time() - mtime) / 86400
        return age < max_age_days


class UnifiedDataFetcher:
    """
    統一資料抓取介面
    自動選擇最佳資料來源，並快取到本地 CSV。

    資料來源優先順序（完全自動）：
      1. 本地 CSV 快取  — 若當天已更新，立即使用（零延遲）
      2. TWSE / FinMind / yfinance — 直接呼叫外部 API（需網路）
      3. GitHub Raw CSV — 從 GitHub repo 的 data/ 目錄下載 CSV
         raw.githubusercontent.com 在此受限環境的代理白名單中可存取。
         CSV 由 .github/workflows/update_data.yml 每日自動更新。
      4. 本地 CSV 快取（舊版備援）— 即使快取過期，仍有資料可用
    """

    def __init__(self, tw_source: str = 'twse', finmind_token: str = "",
                 github_repo: str = None, github_branch: str = None):
        self.tw_source = tw_source
        self.twse      = TWSEDataFetcher()
        self.finmind   = FinMindDataFetcher(finmind_token)
        self.yfinance  = YFinanceDataFetcher()
        self.github    = GitHubRawDataFetcher(github_repo, github_branch)
        self.cache     = LocalCSVDataFetcher()

    def get_tw_stock_data(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """
        取得台股資料（自動選擇來源 + GitHub Raw + 本地快取備援）
        """
        # 1. 若當天快取已存在，直接使用（跳過所有網路請求）
        if self.cache.is_fresh(stock_id, max_age_days=1):
            cached = self.cache.load(stock_id, days)
            if cached is not None and len(cached) >= 20:
                logger.info(f"Using fresh local cache for {stock_id}")
                return cached

        df = None

        # 2. 嘗試各外部 API 來源
        api_sources = {
            'twse':    [('TWSE',    lambda: self.twse.get_stock_data(stock_id, days)),
                        ('FinMind', lambda: self.finmind.get_stock_data(stock_id, days)),
                        ('yfinance',lambda: self.yfinance.get_stock_data(stock_id, days, market='TW'))],
            'finmind': [('FinMind', lambda: self.finmind.get_stock_data(stock_id, days)),
                        ('TWSE',    lambda: self.twse.get_stock_data(stock_id, days)),
                        ('yfinance',lambda: self.yfinance.get_stock_data(stock_id, days, market='TW'))],
            'yfinance':[('yfinance',lambda: self.yfinance.get_stock_data(stock_id, days, market='TW')),
                        ('TWSE',    lambda: self.twse.get_stock_data(stock_id, days)),
                        ('FinMind', lambda: self.finmind.get_stock_data(stock_id, days))],
        }
        sources = api_sources.get(self.tw_source, api_sources['twse'])

        for name, fetcher_fn in sources:
            try:
                result = fetcher_fn()
                if result is not None and len(result) >= 20:
                    logger.info(f"Fetched {len(result)} rows for {stock_id} via {name}")
                    df = result
                    self.cache.save(stock_id, df)  # 成功後存快取
                    break
            except Exception as e:
                logger.warning(f"{name} failed for {stock_id}: {e}")

        # 3. 所有直接 API 失敗 → GitHub Raw（raw.githubusercontent.com 在代理白名單中）
        if df is None or len(df) < 20:
            logger.info(f"Direct APIs failed; trying GitHub raw for {stock_id}")
            try:
                result = self.github.get_stock_data(stock_id, days)
                if result is not None and len(result) >= 20:
                    logger.info(f"GitHub raw: {len(result)} rows for {stock_id}")
                    df = result
                    self.cache.save(stock_id, df)  # 存到本地快取
            except Exception as e:
                logger.warning(f"GitHub raw failed for {stock_id}: {e}")

        # 4. 都失敗 → 使用任何現有的本地快取（即使已過期）
        if df is None or len(df) < 20:
            cached = self.cache.load(stock_id, days)
            if cached is not None and len(cached) >= 20:
                logger.info(f"All sources failed; using stale local cache for {stock_id}")
                df = cached

        return df

    def get_us_stock_data(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """
        取得美股資料
        """
        return self.yfinance.get_stock_data(stock_id, days, market='US')

    def get_institutional_trading(self, stock_id: str, days: int = 30) -> Optional[pd.DataFrame]:
        """
        取得三大法人買賣超
        """
        df = self.twse.get_institutional_trading(stock_id, days)

        if df is None or len(df) < 5:
            df = self.finmind.get_institutional_trading(stock_id, days)

        return df


# ============================================================
# 測試函數
# ============================================================

def test_data_fetcher():
    """測試資料抓取"""
    fetcher = UnifiedDataFetcher()
    
    # 測試台股
    print("測試台股資料抓取 (2330 台積電)...")
    df = fetcher.get_tw_stock_data('2330', days=60)
    if df is not None:
        print(f"✅ 成功取得 {len(df)} 筆資料")
        print(df.tail())
    else:
        print("❌ 取得資料失敗")
    
    # 測試籌碼
    print("\n測試籌碼資料抓取...")
    chip_df = fetcher.get_institutional_trading('2330', days=10)
    if chip_df is not None:
        print(f"✅ 成功取得籌碼資料")
        print(chip_df.tail())
    else:
        print("❌ 取得籌碼資料失敗")


if __name__ == "__main__":
    test_data_fetcher()
