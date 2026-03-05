"""
股票視覺化模組 - TradingView 風格圖表
=====================================

支援圖表類型:
- Candlestick (K線圖)
- Heikin Ashi
- UT Bot 指標疊加
- SMC 指標疊加 (BOS, CHoCH, Order Blocks, FVG)
- EMA Ribbon
- 成交量

使用的函式庫:
- plotly: 互動式圖表（推薦，最像 TradingView）
- mplfinance: 靜態圖表（快速輸出）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import os

# 嘗試導入視覺化函式庫
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️ plotly 未安裝，請執行: pip install plotly")

try:
    import mplfinance as mpf
    import matplotlib.pyplot as plt
    MPLFINANCE_AVAILABLE = True
except ImportError:
    MPLFINANCE_AVAILABLE = False
    print("⚠️ mplfinance 未安裝，請執行: pip install mplfinance matplotlib")


# ============================================================
# Heikin Ashi 計算
# ============================================================

def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    計算 Heikin Ashi 蠟燭
    
    Heikin Ashi 公式:
    - HA Close = (Open + High + Low + Close) / 4
    - HA Open = (Previous HA Open + Previous HA Close) / 2
    - HA High = max(High, HA Open, HA Close)
    - HA Low = min(Low, HA Open, HA Close)
    """
    ha_df = df.copy()
    
    # HA Close = (Open + High + Low + Close) / 4
    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    
    # HA Open = (Previous HA Open + Previous HA Close) / 2
    ha_df['ha_open'] = 0.0
    ha_df.loc[ha_df.index[0], 'ha_open'] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2
    
    for i in range(1, len(ha_df)):
        ha_df.loc[ha_df.index[i], 'ha_open'] = (
            ha_df['ha_open'].iloc[i-1] + ha_df['ha_close'].iloc[i-1]
        ) / 2
    
    # HA High = max(High, HA Open, HA Close)
    ha_df['ha_high'] = ha_df[['high', 'ha_open', 'ha_close']].max(axis=1)
    
    # HA Low = min(Low, HA Open, HA Close)
    ha_df['ha_low'] = ha_df[['low', 'ha_open', 'ha_close']].min(axis=1)
    
    return ha_df


# ============================================================
# Plotly 互動式圖表（TradingView 風格）
# ============================================================

def _to_plotly_bar_color(hex_color: str) -> str:
    """Plotly bar.marker 不接受 8 位 hex（含 alpha），轉成 6 位 hex。"""
    if len(hex_color) == 9 and hex_color[0] == '#':
        return hex_color[:7]
    return hex_color


class PlotlyChart:
    """
    使用 Plotly 建立 TradingView 風格的互動式圖表
    
    功能:
    - 可縮放、平移
    - 滑鼠懸停顯示詳細資訊
    - 可儲存為 HTML 或圖片
    """
    
    # TradingView 風格配色
    COLORS = {
        'bg': '#131722',           # 深色背景
        'grid': '#1e222d',         # 網格線
        'text': '#d1d4dc',         # 文字
        'bullish': '#26a69a',      # 上漲（綠）
        'bearish': '#ef5350',      # 下跌（紅）
        'volume_up': '#26a69a80',  # 上漲成交量
        'volume_down': '#ef535080', # 下跌成交量
        'ema_5': '#f7525f',        # EMA 5
        'ema_20': '#2196f3',       # EMA 20
        'ema_60': '#ff9800',       # EMA 60
        'ema_120': '#9c27b0',      # EMA 120
        'ema_240': '#4caf50',      # EMA 240
        'ut_stop': '#e040fb',      # UT Bot Stop
        'bos_bull': '#00e676',     # BOS 多方
        'bos_bear': '#ff1744',     # BOS 空方
        'choch_bull': '#00e676',   # CHoCH 多方
        'choch_bear': '#ff1744',   # CHoCH 空方
        'ob_bull': 'rgba(33, 150, 243, 0.3)',   # Order Block 多方
        'ob_bear': 'rgba(244, 67, 54, 0.3)',    # Order Block 空方
        'fvg_bull': 'rgba(0, 230, 118, 0.2)',   # FVG 多方
        'fvg_bear': 'rgba(255, 23, 68, 0.2)',   # FVG 空方
    }

    # TradingView 淺色主題
    LIGHT_COLORS = {
        'bg': '#ffffff',
        'grid': '#e0e0e0',
        'text': '#333333',
        'bullish': '#26a69a',
        'bearish': '#ef5350',
        'volume_up': '#26a69a80',
        'volume_down': '#ef535080',
        'ema_5': '#f7525f',
        'ema_20': '#2196f3',
        'ema_60': '#ff9800',
        'ema_120': '#9c27b0',
        'ema_240': '#4caf50',
        'ut_stop': '#e040fb',
        'bos_bull': '#00e676',
        'bos_bear': '#ff1744',
        'choch_bull': '#00e676',
        'choch_bear': '#ff1744',
        'ob_bull': 'rgba(33, 150, 243, 0.3)',
        'ob_bear': 'rgba(244, 67, 54, 0.3)',
        'fvg_bull': 'rgba(0, 230, 118, 0.2)',
        'fvg_bear': 'rgba(255, 23, 68, 0.2)',
    }
    
    def __init__(self, df: pd.DataFrame, title: str = "Stock Chart", theme: str = "light"):
        """
        初始化圖表
        
        參數:
        - df: 包含 OHLCV 的 DataFrame
        - title: 圖表標題
        - theme: 'light' 或 'dark'
        """
        self.df = df.copy()
        self.title = title
        self.theme = theme
        self.fig = None
        self.COLORS = self.LIGHT_COLORS if theme == 'light' else self.__class__.COLORS
        
        # 確保有日期欄位
        if 'date' not in self.df.columns:
            self.df['date'] = self.df.index
        
        # 確保日期格式正確
        self.df['date'] = pd.to_datetime(self.df['date'])
    
    def create_candlestick_chart(
        self,
        show_volume: bool = True,
        show_ema: bool = True,
        ema_periods: List[int] = [5, 20, 60],
        height: int = 800
    ) -> go.Figure:
        """
        建立標準 K 線圖
        """
        # 計算子圖高度比例
        row_heights = [0.7, 0.3] if show_volume else [1.0]
        rows = 2 if show_volume else 1
        
        self.fig = make_subplots(
            rows=rows, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
            subplot_titles=(self.title, 'Volume') if show_volume else (self.title,)
        )
        
        # K 線
        self.fig.add_trace(
            go.Candlestick(
                x=self.df['date'],
                open=self.df['open'],
                high=self.df['high'],
                low=self.df['low'],
                close=self.df['close'],
                name='OHLC',
                increasing_line_color=self.COLORS['bullish'],
                decreasing_line_color=self.COLORS['bearish'],
                increasing_fillcolor=self.COLORS['bullish'],
                decreasing_fillcolor=self.COLORS['bearish'],
            ),
            row=1, col=1
        )
        
        # EMA
        if show_ema:
            ema_colors = [self.COLORS['ema_5'], self.COLORS['ema_20'], 
                         self.COLORS['ema_60'], self.COLORS['ema_120'], self.COLORS['ema_240']]
            
            for i, period in enumerate(ema_periods):
                ema = self.df['close'].ewm(span=period, adjust=False).mean()
                color = ema_colors[i % len(ema_colors)]
                
                self.fig.add_trace(
                    go.Scatter(
                        x=self.df['date'],
                        y=ema,
                        mode='lines',
                        name=f'EMA {period}',
                        line=dict(color=color, width=1),
                    ),
                    row=1, col=1
                )
        
        # 成交量
        if show_volume:
            colors = [self.COLORS['volume_up'] if c >= o else self.COLORS['volume_down'] 
                     for c, o in zip(self.df['close'], self.df['open'])]
            # Plotly bar.marker 不接受 8 位 hex（含 alpha），改為 6 位
            plotly_colors = [_to_plotly_bar_color(c) for c in colors]
            self.fig.add_trace(
                go.Bar(
                    x=self.df['date'],
                    y=self.df['volume'],
                    name='Volume',
                    marker_color=plotly_colors,
                ),
                row=2, col=1
            )
        
        self._apply_layout(height)
        return self.fig
    
    def create_heikin_ashi_chart(
        self,
        show_volume: bool = True,
        show_ema: bool = True,
        ema_periods: List[int] = [5, 20, 60],
        height: int = 800
    ) -> go.Figure:
        """
        建立 Heikin Ashi 圖表
        
        Heikin Ashi 特點:
        - 平滑趨勢，減少噪音
        - 連續同色 K 線表示強趨勢
        - 小實體/長影線表示可能轉折
        """
        # 計算 Heikin Ashi
        ha_df = calculate_heikin_ashi(self.df)
        
        row_heights = [0.7, 0.3] if show_volume else [1.0]
        rows = 2 if show_volume else 1
        
        self.fig = make_subplots(
            rows=rows, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
            subplot_titles=(f"{self.title} (Heikin Ashi)", 'Volume') if show_volume else (f"{self.title} (Heikin Ashi)",)
        )
        
        # Heikin Ashi K 線
        self.fig.add_trace(
            go.Candlestick(
                x=self.df['date'],
                open=ha_df['ha_open'],
                high=ha_df['ha_high'],
                low=ha_df['ha_low'],
                close=ha_df['ha_close'],
                name='Heikin Ashi',
                increasing_line_color=self.COLORS['bullish'],
                decreasing_line_color=self.COLORS['bearish'],
                increasing_fillcolor=self.COLORS['bullish'],
                decreasing_fillcolor=self.COLORS['bearish'],
            ),
            row=1, col=1
        )
        
        # EMA（基於原始價格）
        if show_ema:
            ema_colors = [self.COLORS['ema_5'], self.COLORS['ema_20'], 
                         self.COLORS['ema_60'], self.COLORS['ema_120'], self.COLORS['ema_240']]
            
            for i, period in enumerate(ema_periods):
                ema = self.df['close'].ewm(span=period, adjust=False).mean()
                color = ema_colors[i % len(ema_colors)]
                
                self.fig.add_trace(
                    go.Scatter(
                        x=self.df['date'],
                        y=ema,
                        mode='lines',
                        name=f'EMA {period}',
                        line=dict(color=color, width=1),
                    ),
                    row=1, col=1
                )
        
        # 成交量
        if show_volume:
            colors = [self.COLORS['volume_up'] if c >= o else self.COLORS['volume_down'] 
                     for c, o in zip(ha_df['ha_close'], ha_df['ha_open'])]
            plotly_colors = [_to_plotly_bar_color(c) for c in colors]
            self.fig.add_trace(
                go.Bar(
                    x=self.df['date'],
                    y=self.df['volume'],
                    name='Volume',
                    marker_color=plotly_colors,
                ),
                row=2, col=1
            )
        
        self._apply_layout(height)
        return self.fig
    
    def add_ut_bot(
        self,
        atr_trailing_stop: pd.Series,
        buy_signals: pd.Series = None,
        sell_signals: pd.Series = None
    ):
        """
        加入 UT Bot 指標
        
        參數:
        - atr_trailing_stop: ATR Trailing Stop 數值
        - buy_signals: 買進信號 (Boolean Series)
        - sell_signals: 賣出信號 (Boolean Series)
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        
        # ATR Trailing Stop 線：只繪製最近 75% 資料，略過開頭不穩定區段
        n = len(self.df)
        start_idx = int(n * 0.25)
        x_stop = self.df['date'].iloc[start_idx:]
        y_stop = atr_trailing_stop.iloc[start_idx:]
        self.fig.add_trace(
            go.Scatter(
                x=x_stop,
                y=y_stop,
                mode='lines',
                name='UT Bot Stop',
                line=dict(color=self.COLORS['ut_stop'], width=2, dash='dot'),
            ),
            row=1, col=1
        )
        
        # Buy/Sell 標籤（TradingView 風格：實心綠/紅矩形、白字）
        if buy_signals is not None:
            buy_points = self.df[buy_signals]
            for _, row in buy_points.iterrows():
                self.fig.add_annotation(
                    x=row['date'],
                    y=row['low'] * 0.99,
                    text="Buy",
                    showarrow=False,
                    xref="x",
                    yref="y",
                    bgcolor=self.COLORS['bullish'],
                    font=dict(color="white", size=11),
                    borderpad=4,
                    borderwidth=0,
                )
        if sell_signals is not None:
            sell_points = self.df[sell_signals]
            for _, row in sell_points.iterrows():
                self.fig.add_annotation(
                    x=row['date'],
                    y=row['high'] * 1.01,
                    text="Sell",
                    showarrow=False,
                    xref="x",
                    yref="y",
                    bgcolor=self.COLORS['bearish'],
                    font=dict(color="white", size=11),
                    borderpad=4,
                    borderwidth=0,
                )
        return self.fig

    # EMA Ribbon colors (Pine Combo: 1D Ribbon)
    EMA_RIBBON_COLORS = {5: '#74b7e7', 20: '#1b98f1', 60: '#056ab3', 120: '#054f84', 240: '#032e4c'}

    def add_ema_ribbon(self, ema_dict: Dict[str, pd.Series], linewidth: int = 2):
        """
        加入 EMA Ribbon（Combo 1D 風格）
        ema_dict: e.g. {'ema_5': Series, 'ema_20': Series, ...}
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        for key, series in ema_dict.items():
            try:
                period = int(key.split('_')[1])
            except (IndexError, ValueError):
                period = 0
            color = self.EMA_RIBBON_COLORS.get(period, self.COLORS.get('text', '#333'))
            self.fig.add_trace(
                go.Scatter(
                    x=self.df['date'],
                    y=series,
                    mode='lines',
                    name=f'EMA {period}',
                    line=dict(color=color, width=linewidth),
                ),
                row=1, col=1
            )
        return self.fig

    def add_maxmin(
        self,
        mm_high: pd.Series,
        mm_low: pd.Series,
        fill: bool = True,
        line_color: str = None,
        fill_color: str = 'rgba(250, 208, 58, 0.2)',
    ):
        """
        加入 Max-Min Price Range（Combo：rolling highest/lowest + 雲層）
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        line_color = line_color or '#9C27B0'
        self.fig.add_trace(
            go.Scatter(
                x=self.df['date'],
                y=mm_high,
                mode='lines',
                name='Highest',
                line=dict(color=line_color, width=1),
            ),
            row=1, col=1
        )
        self.fig.add_trace(
            go.Scatter(
                x=self.df['date'],
                y=mm_low,
                mode='lines',
                name='Lowest',
                line=dict(color=line_color, width=1),
                fill='tonexty' if fill else None,
                fillcolor=fill_color if fill else None,
            ),
            row=1, col=1
        )
        return self.fig
    
    def add_smc_signals(
        self,
        bos_bull: pd.Series = None,
        bos_bear: pd.Series = None,
        choch_bull: pd.Series = None,
        choch_bear: pd.Series = None,
    ):
        """
        加入 SMC 結構信號 (BOS / CHoCH)
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        
        # BOS Bullish
        if bos_bull is not None:
            points = self.df[bos_bull]
            if len(points) > 0:
                self.fig.add_trace(
                    go.Scatter(
                        x=points['date'],
                        y=points['high'] * 1.01,
                        mode='text',
                        name='BOS ↑',
                        text=['BOS'] * len(points),
                        textfont=dict(color=self.COLORS['bos_bull'], size=10),
                        textposition='top center',
                    ),
                    row=1, col=1
                )
        
        # BOS Bearish
        if bos_bear is not None:
            points = self.df[bos_bear]
            if len(points) > 0:
                self.fig.add_trace(
                    go.Scatter(
                        x=points['date'],
                        y=points['low'] * 0.99,
                        mode='text',
                        name='BOS ↓',
                        text=['BOS'] * len(points),
                        textfont=dict(color=self.COLORS['bos_bear'], size=10),
                        textposition='bottom center',
                    ),
                    row=1, col=1
                )
        
        # CHoCH Bullish
        if choch_bull is not None:
            points = self.df[choch_bull]
            if len(points) > 0:
                self.fig.add_trace(
                    go.Scatter(
                        x=points['date'],
                        y=points['high'] * 1.015,
                        mode='text',
                        name='CHoCH ↑',
                        text=['CHoCH'] * len(points),
                        textfont=dict(color=self.COLORS['choch_bull'], size=11, family='Arial Black'),
                        textposition='top center',
                    ),
                    row=1, col=1
                )
        
        # CHoCH Bearish
        if choch_bear is not None:
            points = self.df[choch_bear]
            if len(points) > 0:
                self.fig.add_trace(
                    go.Scatter(
                        x=points['date'],
                        y=points['low'] * 0.985,
                        mode='text',
                        name='CHoCH ↓',
                        text=['CHoCH'] * len(points),
                        textfont=dict(color=self.COLORS['choch_bear'], size=11, family='Arial Black'),
                        textposition='bottom center',
                    ),
                    row=1, col=1
                )
        
        return self.fig
    
    def add_order_blocks(self, order_blocks: List[Dict]):
        """
        加入 Order Blocks 區塊
        
        order_blocks: List of dict with keys: high, low, bar_index, bias ('bullish'/'bearish')
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        
        for ob in order_blocks[-10:]:  # 只顯示最近 10 個
            color = self.COLORS['ob_bull'] if ob.get('bias') == 'bullish' else self.COLORS['ob_bear']
            
            start_idx = ob.get('bar_index', 0)
            if start_idx < len(self.df):
                start_date = self.df['date'].iloc[start_idx]
                end_date = self.df['date'].iloc[-1]
                
                self.fig.add_shape(
                    type="rect",
                    x0=start_date,
                    x1=end_date,
                    y0=ob['low'],
                    y1=ob['high'],
                    fillcolor=color,
                    line=dict(width=0),
                    layer="below",
                    row=1, col=1
                )
        
        return self.fig
    
    def add_fvg(self, fvg_list: List[Dict]):
        """
        加入 Fair Value Gaps 區塊
        
        fvg_list: List of dict with keys: top, bottom, bar_index, bias
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        
        for fvg in fvg_list[-10:]:
            color = self.COLORS['fvg_bull'] if fvg.get('bias') == 'bullish' else self.COLORS['fvg_bear']
            
            start_idx = fvg.get('bar_index', 0)
            if start_idx < len(self.df):
                start_date = self.df['date'].iloc[start_idx]
                end_date = self.df['date'].iloc[-1]
                
                self.fig.add_shape(
                    type="rect",
                    x0=start_date,
                    x1=end_date,
                    y0=fvg['bottom'],
                    y1=fvg['top'],
                    fillcolor=color,
                    line=dict(width=1, color=color.replace('0.2', '0.5')),
                    layer="below",
                    row=1, col=1
                )
        
        return self.fig
    
    def add_horizontal_line(self, price: float, label: str, color: str = None):
        """加入水平線（支撐/壓力）"""
        if self.fig is None:
            raise ValueError("請先建立圖表")
        
        self.fig.add_hline(
            y=price,
            line_dash="dash",
            line_color=color or self.COLORS['text'],
            annotation_text=label,
            annotation_position="right",
            row=1, col=1
        )
        
        return self.fig
    
    def _apply_layout(self, height: int):
        """套用 TradingView 風格的版面配置（依 theme 選淺色/深色），圖表填滿視窗"""
        legend_bg = 'rgba(255,255,255,0.9)' if self.theme == 'light' else 'rgba(0,0,0,0.5)'
        self.fig.update_layout(
            height=height,
            width=1600,
            autosize=True,
            template=None if self.theme == 'light' else 'plotly_dark',
            paper_bgcolor=self.COLORS['bg'],
            plot_bgcolor=self.COLORS['bg'],
            font=dict(color=self.COLORS['text']),
            xaxis_rangeslider_visible=False,
            showlegend=True,
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor=legend_bg,
            ),
            margin=dict(l=50, r=50, t=50, b=50),
        )
        
        # Compute all calendar dates in range that have no trading data.
        # This covers weekends AND all public holidays (CNY, etc.) dynamically,
        # so the x-axis shows no gaps between trading days.
        trading_dates = set(self.df['date'].dt.normalize())
        all_calendar = pd.date_range(self.df['date'].min(), self.df['date'].max(), freq='D')
        non_trading = [d.strftime('%Y-%m-%d') for d in all_calendar if d not in trading_dates]

        self.fig.update_xaxes(
            gridcolor=self.COLORS['grid'],
            showgrid=True,
            zeroline=False,
            rangebreaks=[
                dict(bounds=["sat", "mon"]),   # skip weekends
                dict(values=non_trading),       # skip holidays & any other market closures
            ],
        )
        
        self.fig.update_yaxes(
            gridcolor=self.COLORS['grid'],
            showgrid=True,
            zeroline=False,
            side='right',
        )
    
    def show(self):
        """顯示圖表（填滿視窗、隨視窗縮放）"""
        if self.fig:
            self.fig.show(config={'responsive': True})
    
    def save(self, filename: str):
        """
        儲存圖表
        支援: .html, .png, .jpg, .svg, .pdf
        """
        if self.fig is None:
            raise ValueError("請先建立圖表")
        
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)
        
        if filename.endswith('.html'):
            self.fig.write_html(
                filename,
                config={'responsive': True},
                include_plotlyjs=True,
            )
        else:
            self.fig.write_image(filename)
        
        print(f"✅ 圖表已儲存: {filename}")


# ============================================================
# mplfinance 靜態圖表
# ============================================================

class MplFinanceChart:
    """
    使用 mplfinance 建立靜態圖表
    適合快速輸出和批量生成
    """
    
    def __init__(self, df: pd.DataFrame, title: str = "Stock Chart"):
        self.df = df.copy()
        self.title = title
        
        # 設定日期為索引
        if 'date' in self.df.columns:
            self.df['Date'] = pd.to_datetime(self.df['date'])
            self.df.set_index('Date', inplace=True)
        
        # 確保欄位名稱符合 mplfinance 格式
        self.df.columns = [c.capitalize() for c in self.df.columns]
        
        # TradingView 風格
        self.style = mpf.make_mpf_style(
            base_mpf_style='nightclouds',
            marketcolors=mpf.make_marketcolors(
                up='#26a69a',
                down='#ef5350',
                edge='inherit',
                wick='inherit',
                volume={'up': '#26a69a80', 'down': '#ef535080'},
            ),
            gridcolor='#1e222d',
            facecolor='#131722',
            figcolor='#131722',
            gridstyle='-',
            y_on_right=True,
            rc={'font.size': 10}
        )
    
    def plot_candlestick(
        self,
        show_volume: bool = True,
        show_ema: List[int] = [5, 20, 60],
        savefig: str = None,
        figsize: Tuple[int, int] = (14, 8)
    ):
        """繪製 K 線圖"""
        addplots = []
        
        if show_ema:
            colors = ['#f7525f', '#2196f3', '#ff9800', '#9c27b0', '#4caf50']
            for i, period in enumerate(show_ema):
                ema = self.df['Close'].ewm(span=period, adjust=False).mean()
                addplots.append(
                    mpf.make_addplot(ema, color=colors[i % len(colors)], width=1)
                )
        
        fig, axes = mpf.plot(
            self.df,
            type='candle',
            style=self.style,
            title=self.title,
            volume=show_volume,
            addplot=addplots if addplots else None,
            figsize=figsize,
            returnfig=True,
            warn_too_much_data=1000,
        )
        
        if savefig:
            os.makedirs(os.path.dirname(savefig) if os.path.dirname(savefig) else '.', exist_ok=True)
            fig.savefig(savefig, dpi=150, bbox_inches='tight', facecolor='#131722')
            print(f"✅ 圖表已儲存: {savefig}")
        
        return fig, axes
    
    def plot_heikin_ashi(
        self,
        show_volume: bool = True,
        show_ema: List[int] = [5, 20, 60],
        savefig: str = None,
        figsize: Tuple[int, int] = (14, 8)
    ):
        """繪製 Heikin Ashi 圖表"""
        ha_df = self.df.copy()
        
        # 計算 Heikin Ashi
        ha_df['Ha_close'] = (self.df['Open'] + self.df['High'] + self.df['Low'] + self.df['Close']) / 4
        
        ha_df['Ha_open'] = 0.0
        ha_df.iloc[0, ha_df.columns.get_loc('Ha_open')] = (self.df['Open'].iloc[0] + self.df['Close'].iloc[0]) / 2
        
        for i in range(1, len(ha_df)):
            ha_df.iloc[i, ha_df.columns.get_loc('Ha_open')] = (
                ha_df['Ha_open'].iloc[i-1] + ha_df['Ha_close'].iloc[i-1]
            ) / 2
        
        ha_df['Ha_high'] = ha_df[['High', 'Ha_open', 'Ha_close']].max(axis=1)
        ha_df['Ha_low'] = ha_df[['Low', 'Ha_open', 'Ha_close']].min(axis=1)
        
        ha_df['Open'] = ha_df['Ha_open']
        ha_df['High'] = ha_df['Ha_high']
        ha_df['Low'] = ha_df['Ha_low']
        ha_df['Close'] = ha_df['Ha_close']
        
        addplots = []
        
        if show_ema:
            colors = ['#f7525f', '#2196f3', '#ff9800', '#9c27b0', '#4caf50']
            for i, period in enumerate(show_ema):
                ema = self.df['Close'].ewm(span=period, adjust=False).mean()
                addplots.append(
                    mpf.make_addplot(ema, color=colors[i % len(colors)], width=1)
                )
        
        fig, axes = mpf.plot(
            ha_df,
            type='candle',
            style=self.style,
            title=f"{self.title} (Heikin Ashi)",
            volume=show_volume,
            addplot=addplots if addplots else None,
            figsize=figsize,
            returnfig=True,
            warn_too_much_data=1000,
        )
        
        if savefig:
            os.makedirs(os.path.dirname(savefig) if os.path.dirname(savefig) else '.', exist_ok=True)
            fig.savefig(savefig, dpi=150, bbox_inches='tight', facecolor='#131722')
            print(f"✅ 圖表已儲存: {savefig}")
        
        return fig, axes


# ============================================================
# 便捷函數
# ============================================================

def plot_stock(
    df: pd.DataFrame,
    stock_id: str,
    chart_type: str = 'candlestick',
    engine: str = 'plotly',
    show_volume: bool = True,
    show_ema: List[int] = [5, 20, 60],
    save_path: str = None,
    show: bool = True,
    theme: str = 'light'
):
    """
    快速繪製股票圖表
    
    參數:
    - df: OHLCV DataFrame
    - stock_id: 股票代碼
    - chart_type: 'candlestick' 或 'heikin_ashi'
    - engine: 'plotly' (互動) 或 'mplfinance' (靜態)
    - show_volume: 是否顯示成交量
    - show_ema: EMA 週期列表
    - save_path: 儲存路徑
    - show: 是否顯示圖表
    - theme: 'light' 或 'dark'（僅 plotly）
    
    範例:
    >>> plot_stock(df, '2330', chart_type='heikin_ashi')
    >>> plot_stock(df, 'AAPL', engine='mplfinance', save_path='chart.png')
    """
    title = f"{stock_id} Daily Chart"
    
    if engine == 'plotly' and PLOTLY_AVAILABLE:
        chart = PlotlyChart(df, title, theme=theme)
        
        if chart_type == 'heikin_ashi':
            chart.create_heikin_ashi_chart(show_volume=show_volume, show_ema=True, ema_periods=show_ema)
        else:
            chart.create_candlestick_chart(show_volume=show_volume, show_ema=True, ema_periods=show_ema)
        
        if save_path:
            chart.save(save_path)
        
        if show:
            chart.show()
        
        return chart.fig
    
    elif engine == 'mplfinance' and MPLFINANCE_AVAILABLE:
        chart = MplFinanceChart(df, title)
        
        if chart_type == 'heikin_ashi':
            fig, axes = chart.plot_heikin_ashi(show_volume=show_volume, show_ema=show_ema, savefig=save_path)
        else:
            fig, axes = chart.plot_candlestick(show_volume=show_volume, show_ema=show_ema, savefig=save_path)
        
        if show:
            plt.show()
        
        return fig
    
    else:
        raise ValueError(f"Engine '{engine}' not available. Install required packages.")


def plot_stock_with_indicators(
    df: pd.DataFrame,
    stock_id: str,
    ut_data: Dict = None,
    smc_data: Dict = None,
    ema_ribbon: Dict = None,
    maxmin: Dict = None,
    chart_type: str = 'candlestick',
    save_path: str = None,
    show: bool = True,
    theme: str = 'light'
):
    """
    繪製帶有 UT Bot、SMC、EMA Ribbon、MaxMin 的圖表（Combo 風格）
    
    參數:
    - df: OHLCV DataFrame
    - stock_id: 股票代碼
    - ut_data: UT Bot 資料 dict with keys: atr_trailing_stop, ut_buy, ut_sell
    - smc_data: SMC 資料 dict with keys: bos_bull, bos_bear, choch_bull, choch_bear, order_blocks, fvg
    - ema_ribbon: EMA Ribbon dict e.g. {'ema_5': Series, 'ema_20': Series, ...}
    - maxmin: Max-Min Range dict with keys: mm_high, mm_low
    - chart_type: 'candlestick' 或 'heikin_ashi'
    - save_path: 儲存路徑
    - show: 是否顯示
    - theme: 'light' 或 'dark'
    """
    if not PLOTLY_AVAILABLE:
        raise ImportError("請安裝 plotly: pip install plotly")
    
    title = f"{stock_id} - UT Bot + SMC Analysis"
    chart = PlotlyChart(df, title, theme=theme)
    
    # Combo 時用 EMA Ribbon 取代內建 3 條 EMA，避免重複
    use_combo_ema = ema_ribbon is not None and len(ema_ribbon) > 0
    if chart_type == 'heikin_ashi':
        chart.create_heikin_ashi_chart(show_volume=True, show_ema=not use_combo_ema, ema_periods=[5, 20, 60])
    else:
        chart.create_candlestick_chart(show_volume=True, show_ema=not use_combo_ema, ema_periods=[5, 20, 60])
    
    if maxmin:
        chart.add_maxmin(maxmin.get('mm_high'), maxmin.get('mm_low'), fill=True)
    if ema_ribbon:
        chart.add_ema_ribbon(ema_ribbon)
    if ut_data:
        chart.add_ut_bot(
            atr_trailing_stop=ut_data.get('atr_trailing_stop'),
            buy_signals=ut_data.get('ut_buy'),
            sell_signals=ut_data.get('ut_sell')
        )
    if smc_data:
        chart.add_smc_signals(
            bos_bull=smc_data.get('bos_bull'),
            bos_bear=smc_data.get('bos_bear'),
            choch_bull=smc_data.get('choch_bull'),
            choch_bear=smc_data.get('choch_bear')
        )
        if smc_data.get('order_blocks'):
            chart.add_order_blocks(smc_data['order_blocks'])
        if smc_data.get('fvg'):
            chart.add_fvg(smc_data['fvg'])
    
    if save_path:
        chart.save(save_path)
    if show:
        chart.show()
    return chart.fig


# ============================================================
# 測試
# ============================================================

if __name__ == "__main__":
    # 生成測試資料
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    high = close + np.abs(np.random.randn(100)) * 2
    low = close - np.abs(np.random.randn(100)) * 2
    open_price = close + np.random.randn(100)
    volume = np.random.randint(1000000, 5000000, 100)
    
    df = pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    os.makedirs("output", exist_ok=True)
    
    print("=" * 60)
    print("視覺化模組測試")
    print("=" * 60)
    
    if PLOTLY_AVAILABLE:
        print("\n📊 測試 Plotly K 線圖...")
        plot_stock(df, "TEST", chart_type='candlestick', save_path='output/test_candlestick.html', show=False)
        
        print("📊 測試 Plotly Heikin Ashi...")
        plot_stock(df, "TEST", chart_type='heikin_ashi', save_path='output/test_heikin_ashi.html', show=False)
    
    if MPLFINANCE_AVAILABLE:
        print("\n📊 測試 mplfinance K 線圖...")
        plot_stock(df, "TEST", engine='mplfinance', save_path='output/test_mpf_candlestick.png', show=False)
        
        print("📊 測試 mplfinance Heikin Ashi...")
        plot_stock(df, "TEST", chart_type='heikin_ashi', engine='mplfinance', save_path='output/test_mpf_heikin_ashi.png', show=False)
    
    print("\n🎉 測試完成！檔案儲存在 output/ 目錄")
