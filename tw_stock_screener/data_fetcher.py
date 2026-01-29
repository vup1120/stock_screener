"""
資料抓取模組 - 台股/美股資料來源
================================
支援：證交所 API、FinMind、yfinance
"""

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import time
import json
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


class UnifiedDataFetcher:
    """
    統一資料抓取介面
    自動選擇最佳資料來源
    """
    
    def __init__(self, tw_source: str = 'twse', finmind_token: str = ""):
        self.tw_source = tw_source
        self.twse = TWSEDataFetcher()
        self.finmind = FinMindDataFetcher(finmind_token)
        self.yfinance = YFinanceDataFetcher()
    
    def get_tw_stock_data(self, stock_id: str, days: int = 120) -> Optional[pd.DataFrame]:
        """
        取得台股資料（自動選擇來源）
        """
        df = None
        
        if self.tw_source == 'twse':
            df = self.twse.get_stock_data(stock_id, days)
        elif self.tw_source == 'finmind':
            df = self.finmind.get_stock_data(stock_id, days)
        
        # 備用方案
        if df is None or len(df) < 30:
            df = self.yfinance.get_stock_data(stock_id, days, market='TW')
        
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
