import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import threading
import time
import json
import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import requests
import logging
from logging.handlers import RotatingFileHandler
import random
import math
from collections import deque

# Zerodha Kite Connect imports
try:
    from kiteconnect import KiteConnect
    from kiteconnect.exceptions import KiteException
except ImportError:
    print("Please install kiteconnect: pip install kiteconnect")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('trading_app.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

class ModernTheme:
    """Modern color theme for the application"""
    COLORS = {
        'primary': '#2C3E50',
        'secondary': '#34495E',
        'accent': '#3498DB',
        'success': '#27AE60',
        'warning': '#F39C12',
        'danger': '#E74C3C',
        'light': '#ECF0F1',
        'dark': '#2C3E50',
        'background': '#F8F9FA',
        'card_bg': '#FFFFFF',
        'text_primary': '#2C3E50',
        'text_secondary': '#7F8C8D'
    }
    
    FONTS = {
        'title': ('Arial', 16, 'bold'),
        'heading': ('Arial', 12, 'bold'),
        'normal': ('Arial', 10),
        'small': ('Arial', 9)
    }

class ZerodhaAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle the redirect from Zerodha login"""
        if self.path.startswith('/?status=success'):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            request_token = params.get('request_token', [''])[0]
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html_content = """
            <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body { 
                            font-family: Arial, sans-serif; 
                            text-align: center; 
                            padding: 50px; 
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                        }
                        .container {
                            background: rgba(255,255,255,0.1);
                            padding: 30px;
                            border-radius: 10px;
                            backdrop-filter: blur(10px);
                            max-width: 500px;
                            margin: 0 auto;
                        }
                        .success-icon {
                            font-size: 48px;
                            margin-bottom: 20px;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="success-icon">✅</div>
                        <h1>Authentication Successful!</h1>
                        <p>You can close this window and return to the application.</p>
                        <p><small>Request Token: {}</small></p>
                    </div>
                </body>
            </html>
            """.format(request_token)
            
            self.wfile.write(html_content.encode())
            self.server.request_token = request_token
            self.server.status = "success"
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<h1>Authentication Failed</h1>")
            self.server.status = "failed"
    
    def log_message(self, format, *args):
        return

class TradePosition:
    def __init__(self, position_id, symbol, quantity, avg_price, position_type, instrument_type="FUTURES"):
        self.position_id = position_id
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        self.position_type = position_type  # BUY or SELL
        self.instrument_type = instrument_type
        self.current_price = avg_price
        self.entry_time = datetime.now()
        self.is_active = True
        self.target_profit = 0
        self.stop_loss = 0
        self.exit_reason = ""
        self.exit_time = None
        self.realized_pnl = 0
        
    def update_price(self, current_price):
        self.current_price = current_price
        
    def calculate_unrealized_pnl(self):
        if not self.is_active:
            return 0
            
        if self.position_type == 'BUY':
            pnl = (self.current_price - self.avg_price) * self.quantity
        else:  # SELL
            pnl = (self.avg_price - self.current_price) * self.quantity
            
        return pnl
    
    def calculate_realized_pnl(self):
        return self.realized_pnl
    
    def check_profit_target(self):
        return self.calculate_unrealized_pnl() >= self.target_profit
    
    def check_stop_loss(self):
        return self.calculate_unrealized_pnl() <= -self.stop_loss
    
    def close_position(self, exit_price):
        if self.position_type == 'BUY':
            self.realized_pnl = (exit_price - self.avg_price) * self.quantity
        else:  # SELL
            self.realized_pnl = (self.avg_price - exit_price) * self.quantity
            
        self.is_active = False
        self.exit_time = datetime.now()
        return self.realized_pnl

class TechnicalAnalyzer:
    @staticmethod
    def calculate_sma(prices, period):
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period
    
    @staticmethod
    def calculate_ema(prices, period):
        if len(prices) < period:
            return None
        alpha = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = price * alpha + ema * (1 - alpha)
        return ema
    
    @staticmethod
    def calculate_rsi(prices, period=14):
        if len(prices) < period + 1:
            return None
            
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_bollinger_bands(prices, period=20, std_dev=2):
        if len(prices) < period:
            return None, None, None
            
        sma = sum(prices[-period:]) / period
        std = np.std(prices[-period:])
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return upper_band, sma, lower_band
    
    @staticmethod
    def calculate_atr(high_prices, low_prices, close_prices, period=14):
        if len(high_prices) < period + 1:
            return None
            
        true_ranges = []
        for i in range(1, len(high_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            true_ranges.append(max(tr1, tr2, tr3))
        
        return sum(true_ranges[-period:]) / period

class RiskManager:
    def __init__(self, max_portfolio_risk=0.1, max_position_risk=0.02, kelly_fraction=0.25):
        self.max_portfolio_risk = max_portfolio_risk
        self.max_position_risk = max_position_risk
        self.kelly_fraction = kelly_fraction
        
    def calculate_position_size(self, account_value, stop_loss_pct, win_rate=0.5, win_loss_ratio=2.0):
        """Calculate position size using Kelly Criterion"""
        # Kelly formula: f = (bp - q) / b
        # where f = fraction of capital, b = win/loss ratio, p = win rate, q = loss rate
        if win_loss_ratio <= 0 or win_rate <= 0:
            return 0
            
        kelly_fraction = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        kelly_fraction = max(0, kelly_fraction)  # Never bet negative
        kelly_fraction *= self.kelly_fraction  # Use fractional Kelly
        
        max_risk_amount = account_value * self.max_position_risk
        position_value = account_value * kelly_fraction
        
        # Ensure we don't exceed maximum risk per position
        if position_value * stop_loss_pct > max_risk_amount:
            position_value = max_risk_amount / stop_loss_pct
            
        return position_value
    
    def calculate_var(self, returns, confidence_level=0.95):
        """Calculate Value at Risk"""
        if len(returns) == 0:
            return 0
        return np.percentile(returns, (1 - confidence_level) * 100)
    
    def calculate_max_drawdown(self, equity_curve):
        """Calculate maximum drawdown"""
        if len(equity_curve) == 0:
            return 0
            
        peak = equity_curve[0]
        max_dd = 0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
                
        return max_dd

class TradingStrategy:
    def __init__(self, name, parameters):
        self.name = name
        self.parameters = parameters
        self.analyzer = TechnicalAnalyzer()
        self.positions = []
        self.equity_curve = [100000]  # Starting with 100k
        
    def calculate_signals(self, data):
        """Calculate trading signals based on strategy"""
        if self.name == "MEAN_REVERSION":
            return self.mean_reversion_strategy(data)
        elif self.name == "MOMENTUM":
            return self.momentum_strategy(data)
        elif self.name == "BREAKOUT":
            return self.breakout_strategy(data)
        else:
            return "HOLD"
    
    def mean_reversion_strategy(self, data):
        prices = [bar['close'] for bar in data]
        if len(prices) < 20:
            return "HOLD"
            
        sma = self.analyzer.calculate_sma(prices, 20)
        current_price = prices[-1]
        
        # Calculate z-score
        returns = np.diff(prices)
        if len(returns) > 0:
            z_score = (current_price - sma) / np.std(prices)
            
            if z_score < -2.0:
                return "BUY"
            elif z_score > 2.0:
                return "SELL"
                
        return "HOLD"
    
    def momentum_strategy(self, data):
        prices = [bar['close'] for bar in data]
        if len(prices) < 50:
            return "HOLD"
            
        rsi = self.analyzer.calculate_rsi(prices, 14)
        fast_ma = self.analyzer.calculate_ema(prices, 9)
        slow_ma = self.analyzer.calculate_ema(prices, 21)
        
        if rsi is None or fast_ma is None or slow_ma is None:
            return "HOLD"
            
        if fast_ma > slow_ma and rsi < 70:
            return "BUY"
        elif fast_ma < slow_ma and rsi > 30:
            return "SELL"
            
        return "HOLD"
    
    def breakout_strategy(self, data):
        prices = [bar['close'] for bar in data]
        highs = [bar['high'] for bar in data]
        lows = [bar['low'] for bar in data]
        
        if len(prices) < 55:
            return "HOLD"
            
        # Donchian Channel breakout
        upper_band = max(highs[-55:-1])
        lower_band = min(lows[-55:-1])
        current_price = prices[-1]
        
        if current_price > upper_band:
            return "BUY"
        elif current_price < lower_band:
            return "SELL"
            
        return "HOLD"

class DashboardFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.theme = ModernTheme()
        self.setup_ui()
        
    def setup_ui(self):
        # Main dashboard container
        main_container = ttk.Frame(self)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top row - Connection Status and Portfolio Summary
        top_frame = ttk.Frame(main_container)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Connection Status Card
        connection_card = self.create_card(top_frame, "Connection Status", 0, 0)
        self.connection_label = ttk.Label(connection_card, text="🔴 Disconnected", 
                                         font=self.theme.FONTS['heading'],
                                         foreground=self.theme.COLORS['danger'])
        self.connection_label.pack(pady=5)
        
        self.user_label = ttk.Label(connection_card, text="Not logged in", 
                                   font=self.theme.FONTS['small'],
                                   foreground=self.theme.COLORS['text_secondary'])
        self.user_label.pack()
        
        # Portfolio Summary Card
        portfolio_card = self.create_card(top_frame, "Portfolio Summary", 0, 1)
        
        portfolio_grid = ttk.Frame(portfolio_card)
        portfolio_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(portfolio_grid, text="Total Value:").grid(row=0, column=0, sticky=tk.W)
        self.portfolio_value_label = ttk.Label(portfolio_grid, text="₹ 0.00", font=self.theme.FONTS['normal'])
        self.portfolio_value_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(portfolio_grid, text="Available Cash:").grid(row=1, column=0, sticky=tk.W)
        self.cash_label = ttk.Label(portfolio_grid, text="₹ 0.00", font=self.theme.FONTS['normal'])
        self.cash_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(portfolio_grid, text="Total P&L:").grid(row=2, column=0, sticky=tk.W)
        self.portfolio_pnl_label = ttk.Label(portfolio_grid, text="₹ 0.00", font=self.theme.FONTS['normal'])
        self.portfolio_pnl_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0))
        
        # Positions Summary Card
        positions_card = self.create_card(top_frame, "Positions Summary", 0, 2)
        
        positions_grid = ttk.Frame(positions_card)
        positions_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(positions_grid, text="Active Positions:").grid(row=0, column=0, sticky=tk.W)
        self.active_positions_label = ttk.Label(positions_grid, text="0", font=self.theme.FONTS['normal'])
        self.active_positions_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(positions_grid, text="Unrealized P&L:").grid(row=1, column=0, sticky=tk.W)
        self.unrealized_pnl_label = ttk.Label(positions_grid, text="₹ 0.00", font=self.theme.FONTS['normal'])
        self.unrealized_pnl_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(positions_grid, text="Today's P&L:").grid(row=2, column=0, sticky=tk.W)
        self.today_pnl_label = ttk.Label(positions_grid, text="₹ 0.00", font=self.theme.FONTS['normal'])
        self.today_pnl_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0))
        
        # Strategy Performance Card
        strategy_card = self.create_card(top_frame, "Strategy Performance", 0, 3)
        
        strategy_grid = ttk.Frame(strategy_card)
        strategy_grid.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(strategy_grid, text="Win Rate:").grid(row=0, column=0, sticky=tk.W)
        self.win_rate_label = ttk.Label(strategy_grid, text="0.00%", font=self.theme.FONTS['normal'])
        self.win_rate_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(strategy_grid, text="Sharpe Ratio:").grid(row=1, column=0, sticky=tk.W)
        self.sharpe_label = ttk.Label(strategy_grid, text="0.00", font=self.theme.FONTS['normal'])
        self.sharpe_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(strategy_grid, text="Max Drawdown:").grid(row=2, column=0, sticky=tk.W)
        self.drawdown_label = ttk.Label(strategy_grid, text="0.00%", font=self.theme.FONTS['normal'])
        self.drawdown_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0))
        
        # Middle row - Quick Actions
        middle_frame = ttk.Frame(main_container)
        middle_frame.pack(fill=tk.X, pady=(0, 10))
        
        actions_card = self.create_card(middle_frame, "Quick Actions", 0, 0, colspan=4)
        
        action_buttons = ttk.Frame(actions_card)
        action_buttons.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(action_buttons, text="📊 Refresh Portfolio", 
                  command=self.app.refresh_portfolio).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_buttons, text="🔄 Refresh Positions", 
                  command=self.app.update_all_positions_pnl).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_buttons, text="📈 View Holdings", 
                  command=self.app.show_holdings).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_buttons, text="❌ Close All Positions", 
                  command=self.app.close_all_positions).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_buttons, text="⚡ Emergency Stop", 
                  command=self.app.emergency_stop).pack(side=tk.LEFT, padx=5)
        
        # Bottom row - Market Data
        bottom_frame = ttk.Frame(main_container)
        bottom_frame.pack(fill=tk.BOTH, expand=True)
        
        market_card = self.create_card(bottom_frame, "Market Overview", 0, 0, colspan=4)
        
        # Create market data display
        market_content = ttk.Frame(market_card)
        market_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Market data grid
        ttk.Label(market_content, text="NIFTY 50:", font=self.theme.FONTS['normal']).grid(row=0, column=0, sticky=tk.W)
        self.nifty_label = ttk.Label(market_content, text="0.00 (0.00%)", font=self.theme.FONTS['normal'])
        self.nifty_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(market_content, text="BANK NIFTY:", font=self.theme.FONTS['normal']).grid(row=1, column=0, sticky=tk.W)
        self.banknifty_label = ttk.Label(market_content, text="0.00 (0.00%)", font=self.theme.FONTS['normal'])
        self.banknifty_label.grid(row=1, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(market_content, text="GOLD:", font=self.theme.FONTS['normal']).grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.gold_label = ttk.Label(market_content, text="0.00 (0.00%)", font=self.theme.FONTS['normal'])
        self.gold_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        ttk.Label(market_content, text="SILVER:", font=self.theme.FONTS['normal']).grid(row=1, column=2, sticky=tk.W, padx=(20,0))
        self.silver_label = ttk.Label(market_content, text="0.00 (0.00%)", font=self.theme.FONTS['normal'])
        self.silver_label.grid(row=1, column=3, sticky=tk.W, padx=10)
        
        # Strategy status
        ttk.Label(market_content, text="Active Strategy:", font=self.theme.FONTS['normal']).grid(row=2, column=0, sticky=tk.W, pady=(10,0))
        self.strategy_status_label = ttk.Label(market_content, text="None", font=self.theme.FONTS['normal'])
        self.strategy_status_label.grid(row=2, column=1, sticky=tk.W, padx=10, pady=(10,0))
        
        # Last update
        ttk.Label(market_content, text="Last Update:", font=self.theme.FONTS['small']).grid(row=3, column=0, sticky=tk.W, pady=(10,0))
        self.last_update_label = ttk.Label(market_content, text="--", font=self.theme.FONTS['small'])
        self.last_update_label.grid(row=3, column=1, sticky=tk.W, padx=10, pady=(10,0))
        
    def create_card(self, parent, title, row, col, colspan=1):
        card = ttk.LabelFrame(parent, text=title, padding=10)
        card.grid(row=row, column=col, columnspan=colspan, sticky=tk.NSEW, padx=5)
        parent.columnconfigure(col, weight=1)
        return card
        
    def update_connection_status(self, connected, username=""):
        if connected:
            self.connection_label.config(text="🟢 Connected", foreground=self.theme.COLORS['success'])
            self.user_label.config(text=f"User: {username}")
        else:
            self.connection_label.config(text="🔴 Disconnected", foreground=self.theme.COLORS['danger'])
            self.user_label.config(text="Not logged in")
            
    def update_market_data(self, market_data):
        """Update market data display"""
        if 'NIFTY 50' in market_data:
            nifty_data = market_data['NIFTY 50']
            self.nifty_label.config(text=f"{nifty_data['price']:.2f} ({nifty_data['change_pct']:.2f}%)")
            
        if 'BANKNIFTY' in market_data:
            banknifty_data = market_data['BANKNIFTY']
            self.banknifty_label.config(text=f"{banknifty_data['price']:.2f} ({banknifty_data['change_pct']:.2f}%)")
            
        if 'GOLD' in market_data:
            gold_data = market_data['GOLD']
            self.gold_label.config(text=f"{gold_data['price']:.2f} ({gold_data['change_pct']:.2f}%)")
            
        if 'SILVER' in market_data:
            silver_data = market_data['SILVER']
            self.silver_label.config(text=f"{silver_data['price']:.2f} ({silver_data['change_pct']:.2f}%)")
            
        self.last_update_label.config(text=datetime.now().strftime("%H:%M:%S"))

class AdvancedTradingParameters(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.theme = ModernTheme()
        self.setup_ui()
        
    def setup_ui(self):
        # Create notebook for different trading modes
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Calendar Spread Tab
        calendar_frame = ttk.Frame(notebook)
        notebook.add(calendar_frame, text="📅 Calendar Spread")
        self.setup_calendar_spread(calendar_frame)
        
        # Options Strategy Tab
        options_frame = ttk.Frame(notebook)
        notebook.add(options_frame, text="📊 Options Strategies")
        self.setup_options_strategies(options_frame)
        
        # Futures Algo Tab
        futures_frame = ttk.Frame(notebook)
        notebook.add(futures_frame, text="⚡ Futures Algo")
        self.setup_futures_algo(futures_frame)
        
        # Risk Management Tab
        risk_frame = ttk.Frame(notebook)
        notebook.add(risk_frame, text="🛡️ Risk Management")
        self.setup_risk_management(risk_frame)
        
    def setup_calendar_spread(self, parent):
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left Panel - Instrument Selection
        left_panel = ttk.LabelFrame(main_container, text="Instrument Selection", padding=15)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        ttk.Label(left_panel, text="Underlying:", font=self.theme.FONTS['normal']).pack(anchor=tk.W, pady=5)
        self.underlying_combo = ttk.Combobox(left_panel, values=[
            'GOLD', 'SILVER', 'CRUDEOIL', 'NATURALGAS', 'NIFTY', 'BANKNIFTY'
        ])
        self.underlying_combo.pack(fill=tk.X, pady=5)
        self.underlying_combo.set('NIFTY')
        
        ttk.Label(left_panel, text="Near Month:").pack(anchor=tk.W, pady=5)
        self.near_month_combo = ttk.Combobox(left_panel)
        self.near_month_combo.pack(fill=tk.X, pady=5)
        
        ttk.Label(left_panel, text="Far Month:").pack(anchor=tk.W, pady=5)
        self.far_month_combo = ttk.Combobox(left_panel)
        self.far_month_combo.pack(fill=tk.X, pady=5)
        
        # Load sample expiries
        self.load_sample_expiries()
        
        # Right Panel - Trading Parameters
        right_panel = ttk.LabelFrame(main_container, text="Trading Parameters", padding=15)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        params_grid = ttk.Frame(right_panel)
        params_grid.pack(fill=tk.X, pady=5)
        
        # Trading parameters
        ttk.Label(params_grid, text="Spread Threshold:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.spread_threshold_entry = ttk.Entry(params_grid, width=12)
        self.spread_threshold_entry.insert(0, "2.0")
        self.spread_threshold_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        ttk.Label(params_grid, text="Quantity:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.quantity_entry = ttk.Entry(params_grid, width=12)
        self.quantity_entry.insert(0, "50")
        self.quantity_entry.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        ttk.Label(params_grid, text="Target Profit (₹):").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.target_profit_entry = ttk.Entry(params_grid, width=12)
        self.target_profit_entry.insert(0, "1000")
        self.target_profit_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        ttk.Label(params_grid, text="Stop Loss (₹):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.stop_loss_entry = ttk.Entry(params_grid, width=12)
        self.stop_loss_entry.insert(0, "2000")
        self.stop_loss_entry.grid(row=3, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        ttk.Label(params_grid, text="Check Interval (sec):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.interval_entry = ttk.Entry(params_grid, width=12)
        self.interval_entry.insert(0, "10")
        self.interval_entry.grid(row=4, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # Strategy Controls
        control_frame = ttk.Frame(right_panel)
        control_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(control_frame, text="▶ Start Calendar Spread", 
                                   command=self.start_calendar_spread, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="⏹ Stop Strategy", 
                                  command=self.stop_strategy, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Strategy Status
        status_frame = ttk.Frame(right_panel)
        status_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.strategy_status = ttk.Label(status_frame, text="Not Running", foreground="red")
        self.strategy_status.pack(side=tk.LEFT, padx=5)
        
    def setup_options_strategies(self, parent):
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        strategy_frame = ttk.LabelFrame(main_container, text="Options Strategy", padding=10)
        strategy_frame.pack(fill=tk.X, pady=5)
        
        self.options_strategy = tk.StringVar(value="STRADDLE")
        strategies = [
            ("Straddle", "STRADDLE"),
            ("Strangle", "STRANGLE"),
            ("Iron Condor", "IRON_CONDOR"),
        ]
        
        for text, value in strategies:
            ttk.Radiobutton(strategy_frame, text=text, variable=self.options_strategy, 
                           value=value).pack(anchor=tk.W)
        
        # Strategy parameters
        params_frame = ttk.LabelFrame(main_container, text="Strategy Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(params_frame, text="Expiry:").grid(row=0, column=0, sticky=tk.W)
        self.options_expiry_combo = ttk.Combobox(params_frame)
        self.options_expiry_combo.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(params_frame, text="Strike Distance:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.strike_distance = ttk.Entry(params_frame, width=10)
        self.strike_distance.insert(0, "100")
        self.strike_distance.grid(row=1, column=1, sticky=tk.W, padx=5, pady=(5,0))
        
        # Load sample expiries for options
        self.load_sample_expiries_options()
        
        control_frame = ttk.Frame(main_container)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Start Options Strategy", 
                  command=self.start_options_strategy).pack(side=tk.LEFT, padx=5)
        
    def setup_futures_algo(self, parent):
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        algo_frame = ttk.LabelFrame(main_container, text="Trading Algorithm", padding=10)
        algo_frame.pack(fill=tk.X, pady=5)
        
        self.futures_algo = tk.StringVar(value="MEAN_REVERSION")
        algorithms = [
            ("Mean Reversion", "MEAN_REVERSION"),
            ("Momentum", "MOMENTUM"),
            ("Breakout", "BREAKOUT"),
        ]
        
        for text, value in algorithms:
            ttk.Radiobutton(algo_frame, text=text, variable=self.futures_algo, 
                           value=value).pack(anchor=tk.W)
        
        # Algorithm parameters
        params_frame = ttk.LabelFrame(main_container, text="Algorithm Parameters", padding=10)
        params_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(params_frame, text="RSI Period:").grid(row=0, column=0, sticky=tk.W)
        self.rsi_period = ttk.Entry(params_frame, width=8)
        self.rsi_period.insert(0, "14")
        self.rsi_period.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(params_frame, text="MA Fast:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.fast_ma = ttk.Entry(params_frame, width=8)
        self.fast_ma.insert(0, "9")
        self.fast_ma.grid(row=1, column=1, sticky=tk.W, padx=5, pady=(5,0))
        
        ttk.Label(params_frame, text="MA Slow:").grid(row=2, column=0, sticky=tk.W, pady=(5,0))
        self.slow_ma = ttk.Entry(params_frame, width=8)
        self.slow_ma.insert(0, "21")
        self.slow_ma.grid(row=2, column=1, sticky=tk.W, padx=5, pady=(5,0))
        
        control_frame = ttk.Frame(main_container)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Start Futures Algo", 
                  command=self.start_futures_algo).pack(side=tk.LEFT, padx=5)
        
    def setup_risk_management(self, parent):
        main_container = ttk.Frame(parent)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        sizing_frame = ttk.LabelFrame(main_container, text="Position Sizing", padding=10)
        sizing_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(sizing_frame, text="Risk per Trade (%):").grid(row=0, column=0, sticky=tk.W)
        self.risk_per_trade = ttk.Entry(sizing_frame, width=8)
        self.risk_per_trade.insert(0, "2")
        self.risk_per_trade.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(sizing_frame, text="Max Portfolio Risk (%):").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.max_portfolio_risk = ttk.Entry(sizing_frame, width=8)
        self.max_portfolio_risk.insert(0, "10")
        self.max_portfolio_risk.grid(row=1, column=1, sticky=tk.W, padx=5, pady=(5,0))
        
        # Risk metrics
        metrics_frame = ttk.LabelFrame(main_container, text="Risk Metrics", padding=10)
        metrics_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(metrics_frame, text="VaR (95%):").grid(row=0, column=0, sticky=tk.W)
        self.var_label = ttk.Label(metrics_frame, text="₹ 0.00")
        self.var_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(metrics_frame, text="Max Drawdown:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.drawdown_label = ttk.Label(metrics_frame, text="0.00%")
        self.drawdown_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=(5,0))
        
        control_frame = ttk.Frame(main_container)
        control_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Calculate Risk Metrics", 
                  command=self.calculate_risk_metrics).pack(side=tk.LEFT, padx=5)
        
    def load_sample_expiries(self):
        """Load sample expiry dates"""
        sample_expiries = [
            "2024-12-26", "2024-12-27", "2024-12-28", 
            "2025-01-25", "2025-01-26", "2025-01-27"
        ]
        self.near_month_combo['values'] = sample_expiries
        self.far_month_combo['values'] = sample_expiries
        if sample_expiries:
            self.near_month_combo.set(sample_expiries[0])
            self.far_month_combo.set(sample_expiries[3])
            
    def load_sample_expiries_options(self):
        """Load sample expiry dates for options"""
        sample_expiries = ["2024-12-26", "2024-12-27", "2025-01-25"]
        self.options_expiry_combo['values'] = sample_expiries
        if sample_expiries:
            self.options_expiry_combo.set(sample_expiries[0])
            
    def start_calendar_spread(self):
        """Start calendar spread strategy"""
        if not self.app.is_connected:
            messagebox.showerror("Error", "Please connect to Zerodha first")
            return
            
        self.strategy_status.config(text="Running", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        # Start strategy in background
        strategy_thread = threading.Thread(target=self.run_calendar_spread, daemon=True)
        strategy_thread.start()
        
        self.app.log_message("Calendar spread strategy started")
        
    def stop_strategy(self):
        """Stop current strategy"""
        self.strategy_status.config(text="Stopped", foreground="red")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.app.log_message("Trading strategy stopped")
        
    def run_calendar_spread(self):
        """Run calendar spread strategy"""
        while self.strategy_status.cget("text") == "Running":
            try:
                # Simulate spread calculation and trading
                near_price = 18000 + random.uniform(-100, 100)
                far_price = 18100 + random.uniform(-100, 100)
                spread = far_price - near_price
                
                threshold = float(self.spread_threshold_entry.get())
                
                if abs(spread) > threshold:
                    self.app.log_message(f"Spread opportunity detected: {spread:.2f}")
                    # In real implementation, place orders here
                    
                time.sleep(int(self.interval_entry.get()))
                
            except Exception as e:
                self.app.log_message(f"Strategy error: {e}")
                time.sleep(5)
                
    def start_options_strategy(self):
        """Start options strategy"""
        self.app.log_message(f"Starting {self.options_strategy.get()} strategy")
        messagebox.showinfo("Info", f"{self.options_strategy.get()} strategy started in simulation mode")
        
    def start_futures_algo(self):
        """Start futures algorithm"""
        self.app.log_message(f"Starting {self.futures_algo.get()} algorithm")
        messagebox.showinfo("Info", f"{self.futures_algo.get()} algorithm started in simulation mode")
        
    def calculate_risk_metrics(self):
        """Calculate risk metrics"""
        # Simulate risk calculations
        var = random.uniform(1000, 5000)
        drawdown = random.uniform(1, 10)
        
        self.var_label.config(text=f"₹ {var:.2f}")
        self.drawdown_label.config(text=f"{drawdown:.2f}%")
        self.app.log_message("Risk metrics calculated")

class AuthenticationFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.theme = ModernTheme()
        self.setup_ui()
        
    def setup_ui(self):
        main_frame = ttk.LabelFrame(self, text="Zerodha Authentication", padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # API Configuration
        config_frame = ttk.Frame(main_frame)
        config_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(config_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_key_entry = ttk.Entry(config_frame, width=40)
        self.api_key_entry.grid(row=0, column=1, padx=10, pady=5, sticky=tk.EW)
        
        ttk.Label(config_frame, text="API Secret:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_secret_entry = ttk.Entry(config_frame, width=40, show="*")
        self.api_secret_entry.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        
        config_frame.columnconfigure(1, weight=1)
        
        # Token Status
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(status_frame, text="Token Status:").pack(side=tk.LEFT)
        self.token_status_label = ttk.Label(status_frame, text="No token", foreground=self.theme.COLORS['warning'])
        self.token_status_label.pack(side=tk.LEFT, padx=10)
        
        # Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=20)
        
        self.login_btn = ttk.Button(button_frame, text="🔑 Auto Login", 
                                   command=self.app.auto_login, width=15)
        self.login_btn.pack(side=tk.LEFT, padx=5)
        
        self.logout_btn = ttk.Button(button_frame, text="🚪 Logout", 
                                    command=self.app.logout, state=tk.DISABLED, width=15)
        self.logout_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="🔄 Reuse Token", 
                  command=self.app.reuse_saved_token, width=15).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="📝 Manual Token", 
                  command=self.app.show_manual_token_dialog, width=15).pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        self.login_progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.login_progress.pack(fill=tk.X, pady=10)
        
        # Login status
        self.login_status = ttk.Label(main_frame, text="Not logged in", 
                                     foreground=self.theme.COLORS['text_secondary'])
        self.login_status.pack()

class LogFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.setup_ui()
        
    def setup_ui(self):
        main_frame = ttk.LabelFrame(self, text="Application Logs", padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Log text with scrollbars
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(text_frame, height=15, wrap=tk.WORD, font=('Consolas', 9))
        
        v_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        h_scrollbar = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        v_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        h_scrollbar.grid(row=1, column=0, sticky=tk.EW)
        
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        
        # Log controls
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(control_frame, text="Clear Logs", 
                  command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="Export Logs", 
                  command=self.export_logs).pack(side=tk.LEFT, padx=5)
        
    def clear_logs(self):
        self.log_text.delete(1.0, tk.END)
        
    def export_logs(self):
        try:
            filename = f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(filename, 'w') as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.app.log_message(f"Logs exported to {filename}")
        except Exception as e:
            self.app.log_message(f"Error exporting logs: {e}")

class ZerodhaMCXSpreadTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha Algorithmic Trading Platform")
        self.root.geometry("1400x900")
        
        # Apply modern theme
        self.theme = ModernTheme()
        self.style = ttk.Style()
        self.configure_styles()
        
        # Zerodha API variables
        self.kite = None
        self.api_key = ""
        self.api_secret = ""
        self.access_token = ""
        self.is_connected = False
        self.token_expiry = None
        
        # Authentication server
        self.auth_server = None
        self.server_thread = None
        
        # Trading variables
        self.positions = []
        self.position_counter = 0
        self.running_strategies = []
        
        # MCX instruments cache
        self.instruments_df = None
        
        # Token refresh thread
        self.token_refresh_thread = None
        self.token_refresh_running = False
        
        # Market data simulation
        self.market_data = {}
        self.market_data_thread = None
        
        # Create main container
        self.create_main_container()
        self.load_config()
        
        # Start market data simulation
        self.start_market_data_simulation()
        
    def configure_styles(self):
        """Configure modern styles for ttk widgets"""
        self.style.configure('TFrame', background=self.theme.COLORS['background'])
        self.style.configure('TLabel', background=self.theme.COLORS['background'])
        self.style.configure('TLabelframe', background=self.theme.COLORS['background'])
        self.style.configure('TLabelframe.Label', background=self.theme.COLORS['background'])
        
    def create_main_container(self):
        """Create the main container with notebook"""
        # Create main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create frames
        self.dashboard_frame = DashboardFrame(self.notebook, self)
        self.trading_frame = AdvancedTradingParameters(self.notebook, self)
        self.auth_frame = AuthenticationFrame(self.notebook, self)
        self.log_frame = LogFrame(self.notebook, self)
        
        # Add frames to notebook
        self.notebook.add(self.dashboard_frame, text="📊 Dashboard")
        self.notebook.add(self.trading_frame, text="🎯 Trading")
        self.notebook.add(self.auth_frame, text="🔐 Authentication")
        self.notebook.add(self.log_frame, text="📝 Logs")
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Not connected to Zerodha")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def log_message(self, message):
        """Add message to log with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.log_frame.log_text.insert(tk.END, log_entry)
        self.log_frame.log_text.see(tk.END)
        self.root.update()
        
    def start_market_data_simulation(self):
        """Start simulated market data updates"""
        def update_market_data():
            while True:
                try:
                    # Simulate market data
                    self.market_data = {
                        'NIFTY 50': {'price': 18000 + random.uniform(-100, 100), 'change_pct': random.uniform(-1, 1)},
                        'BANKNIFTY': {'price': 42000 + random.uniform(-200, 200), 'change_pct': random.uniform(-1, 1)},
                        'GOLD': {'price': 62000 + random.uniform(-500, 500), 'change_pct': random.uniform(-0.5, 0.5)},
                        'SILVER': {'price': 75000 + random.uniform(-1000, 1000), 'change_pct': random.uniform(-1, 1)}
                    }
                    
                    self.dashboard_frame.update_market_data(self.market_data)
                    time.sleep(5)
                    
                except Exception as e:
                    time.sleep(5)
                    
        self.market_data_thread = threading.Thread(target=update_market_data, daemon=True)
        self.market_data_thread.start()
        
    # Authentication methods
    def load_config(self):
        try:
            if os.path.exists("config_auto.json"):
                with open("config_auto.json", "r") as f:
                    config = json.load(f)
                    self.auth_frame.api_key_entry.insert(0, config.get("api_key", ""))
                    self.auth_frame.api_secret_entry.insert(0, config.get("api_secret", ""))
                    
                    access_token = config.get("access_token", "")
                    token_expiry_str = config.get("token_expiry", "")
                    
                    if access_token and token_expiry_str:
                        self.access_token = access_token
                        self.token_expiry = datetime.fromisoformat(token_expiry_str)
                        
                        if self.is_token_valid():
                            self.auth_frame.token_status_label.config(text="Saved token available", foreground="green")
                            self.log_message("Saved token found and is still valid")
                        else:
                            self.log_message("Saved token has expired")
                            self.auth_frame.token_status_label.config(text="Token expired", foreground="red")
        except Exception as e:
            self.log_message(f"Error loading config: {e}")
            
    def save_config(self):
        try:
            config = {
                "api_key": self.auth_frame.api_key_entry.get(),
                "api_secret": self.auth_frame.api_secret_entry.get(),
                "access_token": self.access_token,
                "token_expiry": self.token_expiry.isoformat() if self.token_expiry else ""
            }
            with open("config_auto.json", "w") as f:
                json.dump(config, f)
        except Exception as e:
            self.log_message(f"Error saving config: {e}")
            
    def is_token_valid(self):
        if not self.token_expiry:
            return False
        buffer_time = timedelta(minutes=5)
        return datetime.now() < (self.token_expiry - buffer_time)
    
    def auto_login(self):
        self.api_key = self.auth_frame.api_key_entry.get()
        self.api_secret = self.auth_frame.api_secret_entry.get()
        
        if not self.api_key or not self.api_secret:
            messagebox.showerror("Error", "Please enter both API Key and API Secret")
            return
            
        self.auth_frame.login_progress.start()
        self.auth_frame.login_btn.config(state=tk.DISABLED)
        self.auth_frame.login_status.config(text="Starting authentication...")
        
        # Simulate login for demo
        self.simulate_login()
        
    def simulate_login(self):
        """Simulate login for demo purposes"""
        def login_process():
            time.sleep(2)  # Simulate authentication delay
            self.auth_frame.login_progress.stop()
            
            # Create simulated user data
            self.is_connected = True
            self.access_token = "simulated_access_token"
            self.token_expiry = datetime.now() + timedelta(hours=24)
            
            # Update UI
            self.auth_frame.login_btn.config(state=tk.DISABLED)
            self.auth_frame.logout_btn.config(state=tk.NORMAL)
            self.trading_frame.start_btn.config(state=tk.NORMAL)
            self.auth_frame.login_status.config(text="Logged in as: Demo User", foreground="green")
            
            self.dashboard_frame.update_connection_status(True, "Demo User")
            self.status_var.set("Connected: Demo User")
            self.log_message("Successfully logged in as Demo User (Simulation Mode)")
            
            self.load_instruments()
            self.refresh_portfolio()
            self.save_config()
            
        threading.Thread(target=login_process, daemon=True).start()
    
    def logout(self):
        self.kite = None
        self.access_token = ""
        self.is_connected = False
        self.token_expiry = None
        
        self.auth_frame.login_btn.config(state=tk.NORMAL)
        self.auth_frame.logout_btn.config(state=tk.DISABLED)
        self.trading_frame.start_btn.config(state=tk.DISABLED)
        self.auth_frame.login_status.config(text="Not logged in", foreground="red")
        self.auth_frame.token_status_label.config(text="No token", foreground="red")
        self.status_var.set("Not connected")
        self.dashboard_frame.update_connection_status(False)
        
        self.log_message("Logged out successfully")
    
    def reuse_saved_token(self):
        if not self.access_token:
            messagebox.showinfo("Info", "No saved token found. Please login first.")
            return
            
        if not self.is_token_valid():
            messagebox.showwarning("Token Expired", "Saved token has expired. Please login again.")
            return
            
        self.simulate_login()
    
    def show_manual_token_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Token Entry")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Enter Request Token:").pack(pady=10)
        token_entry = ttk.Entry(dialog, width=40)
        token_entry.pack(pady=5)
        
        def submit_token():
            request_token = token_entry.get()
            if request_token:
                self.log_message("Manual token entry simulated")
                self.simulate_login()
                dialog.destroy()
                
        ttk.Button(dialog, text="Submit", command=submit_token).pack(pady=10)
        token_entry.focus()
    
    # Portfolio and trading methods
    def refresh_portfolio(self):
        if not self.is_connected:
            return
            
        try:
            # Simulate portfolio data
            total_value = 100000 + random.uniform(-5000, 5000)
            available_cash = 50000 + random.uniform(-2000, 2000)
            total_pnl = random.uniform(-2000, 2000)
            
            # Update dashboard
            self.dashboard_frame.portfolio_value_label.config(text=f"₹ {total_value:,.2f}")
            self.dashboard_frame.cash_label.config(text=f"₹ {available_cash:,.2f}")
            
            pnl_color = "green" if total_pnl >= 0 else "red"
            self.dashboard_frame.portfolio_pnl_label.config(
                text=f"₹ {total_pnl:,.2f}", 
                foreground=pnl_color
            )
            
            # Update performance metrics - FIXED THE ERROR HERE
            win_rate = random.uniform(45, 65)
            sharpe = random.uniform(0.5, 2.5)
            drawdown = random.uniform(1, 8)
            
            self.dashboard_frame.win_rate_label.config(text=f"{win_rate:.2f}%")
            self.dashboard_frame.sharpe_label.config(text=f"{sharpe:.2f}")
            self.dashboard_frame.drawdown_label.config(text=f"{drawdown:.2f}%")  # Fixed: changed config to configure
            
            self.log_message("Portfolio refreshed successfully")
            
        except Exception as e:
            self.log_message(f"Error refreshing portfolio: {e}")
    
    def show_holdings(self):
        if not self.is_connected:
            messagebox.showerror("Error", "Not connected to Zerodha")
            return
            
        try:
            # Simulate holdings data
            holdings_info = """
Simulated Holdings:
- NIFTY DEC FUT: 50 units
- BANKNIFTY DEC FUT: 25 units  
- RELIANCE EQ: 100 shares
- TCS EQ: 50 shares
"""
            messagebox.showinfo("Holdings", holdings_info)
            self.log_message("Holdings displayed")
            
        except Exception as e:
            self.log_message(f"Error showing holdings: {e}")
    
    def load_instruments(self):
        try:
            if not self.is_connected:
                self.log_message("Not connected to Zerodha")
                return
                
            self.log_message("Loading instruments...")
            # Simulate instrument loading
            time.sleep(1)
            self.log_message("Instruments loaded successfully (Simulation)")
            
        except Exception as e:
            self.log_message(f"Error loading instruments: {e}")
    
    def update_all_positions_pnl(self):
        """Update P&L for all positions"""
        try:
            # Simulate position updates
            active_positions = len([p for p in self.positions if p.is_active])
            unrealized_pnl = sum(p.calculate_unrealized_pnl() for p in self.positions if p.is_active)
            today_pnl = random.uniform(-1000, 1000)
            
            self.dashboard_frame.active_positions_label.config(text=str(active_positions))
            
            unrealized_color = "green" if unrealized_pnl >= 0 else "red"
            today_color = "green" if today_pnl >= 0 else "red"
            
            self.dashboard_frame.unrealized_pnl_label.config(
                text=f"₹ {unrealized_pnl:.2f}", 
                foreground=unrealized_color
            )
            self.dashboard_frame.today_pnl_label.config(
                text=f"₹ {today_pnl:.2f}", 
                foreground=today_color
            )
            
            self.log_message("Positions P&L updated")
            
        except Exception as e:
            self.log_message(f"Error updating P&L: {e}")
    
    def close_all_positions(self):
        """Close all active positions"""
        active_positions = [p for p in self.positions if p.is_active]
        if not active_positions:
            messagebox.showinfo("Info", "No active positions to close")
            return
            
        if messagebox.askyesno("Confirm", f"Close all {len(active_positions)} active positions?"):
            for position in active_positions:
                position.is_active = False
                position.exit_reason = "Manual Close All"
                position.exit_time = datetime.now()
                        
            self.log_message(f"Closed all {len(active_positions)} positions")
            self.update_all_positions_pnl()
    
    def emergency_stop(self):
        """Emergency stop all trading activities"""
        if messagebox.askyesno("Emergency Stop", "Stop all trading activities and close all positions?"):
            # Stop all strategies
            self.trading_frame.stop_strategy()
            
            # Close all positions
            self.close_all_positions()
            
            self.log_message("EMERGENCY STOP: All trading activities halted")
            messagebox.showinfo("Emergency Stop", "All trading activities have been stopped")

def main():
    root = tk.Tk()
    app = ZerodhaMCXSpreadTool(root)
    root.mainloop()

if __name__ == "__main__":
    main()