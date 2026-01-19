import logging
import json
import threading
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import mplfinance as mpf
from kiteconnect import KiteConnect, KiteTicker
import colorama
from colorama import Fore, Back, Style
import webbrowser
import os
import sys
from typing import Dict, List, Optional

# Initialize colorama for console colors
colorama.init(autoreset=True)

# Configure logging
logging.basicConfig(level=logging.INFO)

class ProfitLossCalculator:
    """Calculate real-time profit and loss for positions"""
    
    def __init__(self):
        self.positions = {}
        self.pnl_data = {}
        
    def add_position(self, symbol: str, transaction_type: str, quantity: int, 
                    avg_price: float, instrument_token: int, segment: str = "NFO"):
        """Add a new position to track"""
        position_id = f"{symbol}_{transaction_type}_{datetime.now().timestamp()}"
        
        self.positions[position_id] = {
            'symbol': symbol,
            'transaction_type': transaction_type,  # BUY or SELL
            'quantity': quantity,
            'avg_price': avg_price,
            'instrument_token': instrument_token,
            'segment': segment,
            'timestamp': datetime.now(),
            'current_price': avg_price,
            'unrealized_pnl': 0.0,
            'realized_pnl': 0.0
        }
        return position_id
    
    def update_price(self, instrument_token: int, current_price: float):
        """Update current price and calculate unrealized P&L"""
        for position_id, position in self.positions.items():
            if position['instrument_token'] == instrument_token:
                position['current_price'] = current_price
                
                # Calculate unrealized P&L
                if position['transaction_type'] == 'BUY':
                    pnl = (current_price - position['avg_price']) * position['quantity']
                else:  # SELL
                    pnl = (position['avg_price'] - current_price) * position['quantity']
                
                # Adjust for lot size (typically 50 for Nifty, 100 for stocks)
                lot_size = 50 if 'BANKNIFTY' in position['symbol'] or 'NIFTY' in position['symbol'] else (
                    25 if 'FINNIFTY' in position['symbol'] else 100
                )
                
                position['unrealized_pnl'] = pnl * lot_size
                break
    
    def calculate_pnl(self, position_id: str, current_price: float) -> float:
        """Calculate P&L for a specific position """
        if position_id not in self.positions:
            return 0.0
        
        position = self.positions[position_id]
        
        if position['transaction_type'] == 'BUY':
            pnl = (current_price - position['avg_price']) * position['quantity']
        else:  # SELL
            pnl = (position['avg_price'] - current_price) * position['quantity']
        
        # Apply lot size multiplier
        lot_size = 50 if 'BANKNIFTY' in position['symbol'] or 'NIFTY' in position['symbol'] else (
            25 if 'FINNIFTY' in position['symbol'] else (
                100 if 'MCX' in position['segment'] else 100
            )
        )
        
        return pnl * lot_size
    
    def close_position(self, position_id: str, exit_price: float) -> float:
        """Close a position and calculate realized P&L"""
        if position_id not in self.positions:
            return 0.0
        
        position = self.positions[position_id]
        realized_pnl = self.calculate_pnl(position_id, exit_price)
        
        position['realized_pnl'] = realized_pnl
        position['exit_price'] = exit_price
        position['exit_time'] = datetime.now()
        
        # Store in P&L history
        self.pnl_data[position_id] = position.copy()
        
        # Remove from active positions
        del self.positions[position_id]
        
        return realized_pnl
    
    def get_total_pnl(self) -> Dict[str, float]:
        """Get total unrealized and realized P&L"""
        total_unrealized = sum(pos['unrealized_pnl'] for pos in self.positions.values())
        total_realized = sum(pos['realized_pnl'] for pos in self.pnl_data.values())
        
        return {
            'unrealized_pnl': total_unrealized,
            'realized_pnl': total_realized,
            'total_pnl': total_unrealized + total_realized
        }

class KiteTokenGenerator:
    def __init__(self, api_key, api_secret, redirect_url="http://localhost:8000"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.redirect_url = redirect_url
        self.kite = KiteConnect(api_key=api_key)
        self.request_token = None
        self.access_token = None
        
    def generate_login_url(self):
        """Generate login URL and open in browser"""
        login_url = self.kite.login_url()
        print(f"Opening login URL: {login_url}")
        
        # Open the login URL in default browser
        webbrowser.open(login_url)
        
        return login_url
    
    def generate_access_token(self, request_token):
        """Generate access token using request token"""
        try:
            # Generate session data
            data = self.kite.generate_session(request_token, self.api_secret)
            self.access_token = data["access_token"]
            
            # Set access token for the kite instance
            self.kite.set_access_token(self.access_token)
            
            print("Access token generated successfully!")
            print(f"Access Token: {self.access_token}")
            
            # Get user profile to verify authentication
            profile = self.kite.profile()
            print(f"Authenticated as: {profile['user_name']}")
            
            return self.access_token
            
        except Exception as e:
            print(f"Error generating access_token: {e}")
            return None
    
    def get_kite_instance(self):
        """Get authenticated KiteConnect instance"""
        if self.access_token:
            return self.kite
        else:
            raise Exception("Not authenticated. Please generate access token first.")

class FuturesOptionsManager:
    """Manage Futures and Options instruments for Nifty50 and MCX"""
    
    def __init__(self, kite_instance):
        self.kite = kite_instance
        self.nifty_instruments = []
        self.mcx_instruments = []
        self.loaded = False
        
    def load_instruments(self):
        """Load F&O instruments for Nifty50 and MCX"""
        try:
            all_instruments = self.kite.instruments()
            
            # Filter Nifty50 F&O instruments
            self.nifty_instruments = [
                inst for inst in all_instruments 
                if inst['segment'] == 'NFO-OPT' or inst['segment'] == 'NFO-FUT'
            ]
            
            # Filter MCX instruments
            self.mcx_instruments = [
                inst for inst in all_instruments 
                if inst['segment'] == 'MCX-FUT' or inst['segment'] == 'MCX-OPT'
            ]
            
            self.loaded = True
            logging.info(f"Loaded {len(self.nifty_instruments)} Nifty F&O instruments")
            logging.info(f"Loaded {len(self.mcx_instruments)} MCX instruments")
            
        except Exception as e:
            logging.error(f"Failed to load F&O instruments: {e}")
    
    def get_nifty_options(self, expiry: str = None):
        """Get Nifty50 options instruments"""
        if not self.loaded:
            self.load_instruments()
            
        nifty_options = [
            inst for inst in self.nifty_instruments 
            if inst['segment'] == 'NFO-OPT' and 'NIFTY' in inst['name']
        ]
        
        if expiry:
            nifty_options = [inst for inst in nifty_options if inst['expiry'] == expiry]
            
        return nifty_options
    
    def get_nifty_futures(self, expiry: str = None):
        """Get Nifty50 futures instruments"""
        if not self.loaded:
            self.load_instruments()
            
        nifty_futures = [
            inst for inst in self.nifty_instruments 
            if inst['segment'] == 'NFO-FUT' and 'NIFTY' in inst['name']
        ]
        
        if expiry:
            nifty_futures = [inst for inst in nifty_futures if inst['expiry'] == expiry]
            
        return nifty_futures
    
    def get_mcx_futures(self):
        """Get MCX futures instruments"""
        if not self.loaded:
            self.load_instruments()
            
        return [inst for inst in self.mcx_instruments if inst['segment'] == 'MCX-FUT']
    
    def get_mcx_options(self):
        """Get MCX options instruments"""
        if not self.loaded:
            self.load_instruments()
            
        return [inst for inst in self.mcx_instruments if inst['segment'] == 'MCX-OPT']

class ColorfulTradingTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced Zerodha Trading Tool - F&O + P&L Tracking")
        self.root.geometry("1600x1000")
        self.root.configure(bg='#2c3e50')
        
        # Kite Connect variables
        self.kite = None
        self.kws = None
        self.api_key = ""
        self.api_secret = ""
        self.access_token = ""
        self.is_connected = False
        self.token_generator = None
        
        # New modules
        self.pnl_calculator = ProfitLossCalculator()
        self.fo_manager = None
        
        # Data storage
        self.instruments = None
        self.watchlist_data = {}
        self.portfolio_data = {}
        self.order_book = []
        self.position_book = []
        
        # Real-time data
        self.subscribed_tokens = set()
        self.last_ticks = {}
        
        # F&O tracking
        self.active_positions = {}
        self.selected_segment = "NFO"  # Default to Nifty F&O
        
        # Color schemes
        self.colors = {
            'profit': '#2ecc71',
            'loss': '#e74c3c',
            'neutral': '#3498db',
            'background': '#2c3e50',
            'panel_bg': '#34495e',
            'text_light': '#ecf0f1',
            'text_dark': '#2c3e50',
            'buy': '#27ae60',
            'sell': '#c0392b',
            'hold': '#f39c12',
            'nifty': '#9b59b6',
            'mcx': '#e67e22'
        }
        
        self.setup_gui()
        self.load_config()
        
    def setup_gui(self):
        """Setup the main GUI interface"""
        # Create main frames
        self.main_frame = tk.Frame(self.root, bg=self.colors['background'])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top frame for connection and controls
        self.top_frame = tk.Frame(self.main_frame, bg=self.colors['panel_bg'], relief=tk.RAISED, bd=2)
        self.top_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.setup_connection_frame()
        self.setup_control_frame()
        
        # Middle frames for data display
        self.middle_frame = tk.Frame(self.main_frame, bg=self.colors['background'])
        self.middle_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left panel for watchlist and portfolio
        self.left_frame = tk.Frame(self.middle_frame, bg=self.colors['panel_bg'], relief=tk.RAISED, bd=1)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Right panel for charts, orders, and F&O
        self.right_frame = tk.Frame(self.middle_frame, bg=self.colors['panel_bg'], relief=tk.RAISED, bd=1)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.setup_watchlist_frame()
        self.setup_portfolio_frame()
        self.setup_futures_options_frame()
        self.setup_chart_frame()
        self.setup_order_frame()
        
        # Bottom frame for logs and P&L
        self.setup_log_frame()
        self.setup_pnl_frame()
        
    def setup_connection_frame(self):
        """Setup connection configuration frame"""
        conn_frame = tk.Frame(self.top_frame, bg=self.colors['panel_bg'])
        conn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # API Key
        tk.Label(conn_frame, text="API Key:", bg=self.colors['panel_bg'], 
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        self.api_key_entry = tk.Entry(conn_frame, width=25, show="*")
        self.api_key_entry.grid(row=0, column=1, padx=5, pady=2)
        
        # API Secret
        tk.Label(conn_frame, text="API Secret:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.api_secret_entry = tk.Entry(conn_frame, width=25, show="*")
        self.api_secret_entry.grid(row=0, column=3, padx=5, pady=2)
        
        # Access Token
        tk.Label(conn_frame, text="Access Token:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.access_token_entry = tk.Entry(conn_frame, width=25, show="*")
        self.access_token_entry.grid(row=1, column=1, padx=5, pady=2)
        
        # Buttons
        self.generate_token_btn = tk.Button(conn_frame, text="Generate Token", command=self.generate_token,
                                          bg=self.colors['buy'], fg='white', font=('Arial', 10, 'bold'))
        self.generate_token_btn.grid(row=0, column=4, padx=5)
        
        self.connect_btn = tk.Button(conn_frame, text="Connect", command=self.connect_kite,
                                   bg=self.colors['neutral'], fg='white', font=('Arial', 10, 'bold'))
        self.connect_btn.grid(row=0, column=5, padx=5)
        
        self.manual_token_btn = tk.Button(conn_frame, text="Use Manual Token", command=self.connect_with_token,
                                        bg=self.colors['hold'], fg='white', font=('Arial', 10, 'bold'))
        self.manual_token_btn.grid(row=1, column=4, columnspan=2, padx=5, pady=2)
        
        self.connection_status = tk.Label(conn_frame, text="Disconnected", 
                                        fg='white', bg='red', font=('Arial', 10, 'bold'))
        self.connection_status.grid(row=0, column=6, padx=10)
        
        # Token status
        self.token_status = tk.Label(conn_frame, text="Token: Not Generated", 
                                   fg='white', bg='orange', font=('Arial', 9))
        self.token_status.grid(row=1, column=6, padx=10)
        
    def setup_control_frame(self):
        """Setup control buttons frame"""
        control_frame = tk.Frame(self.top_frame, bg=self.colors['panel_bg'])
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        buttons = [
            ("Refresh Data", self.refresh_data, self.colors['neutral']),
            ("Load F&O Instruments", self.load_fo_instruments, self.colors['nifty']),
            ("Start Real-time", self.start_real_time, self.colors['buy']),
            ("Stop Real-time", self.stop_real_time, self.colors['sell']),
            ("Show Profile", self.show_profile, self.colors['profit']),
            ("Save Token", self.save_token, self.colors['neutral']),
            ("Calculate P&L", self.calculate_total_pnl, self.colors['mcx']),
        ]
        
        for i, (text, command, color) in enumerate(buttons):
            tk.Button(control_frame, text=text, command=command,
                     bg=color, fg='white', font=('Arial', 9, 'bold')).grid(row=0, column=i, padx=5)
    
    def setup_futures_options_frame(self):
        """Setup Futures and Options trading frame"""
        fo_frame = tk.Frame(self.right_frame, bg=self.colors['panel_bg'])
        fo_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # F&O header
        header = tk.Frame(fo_frame, bg=self.colors['nifty'])
        header.pack(fill=tk.X)
        tk.Label(header, text="FUTURES & OPTIONS TRADING", bg=self.colors['nifty'], 
                fg='white', font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Segment selection
        segment_frame = tk.Frame(fo_frame, bg=self.colors['panel_bg'])
        segment_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(segment_frame, text="Segment:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).pack(side=tk.LEFT)
        
        self.segment_var = tk.StringVar(value="NFO")
        tk.Radiobutton(segment_frame, text="Nifty50 F&O", variable=self.segment_var,
                      value="NFO", bg=self.colors['panel_bg'], 
                      fg=self.colors['text_light'], command=self.on_segment_change).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(segment_frame, text="MCX", variable=self.segment_var,
                      value="MCX", bg=self.colors['panel_bg'],
                      fg=self.colors['text_light'], command=self.on_segment_change).pack(side=tk.LEFT, padx=10)
        
        # Instrument selection
        instrument_frame = tk.Frame(fo_frame, bg=self.colors['panel_bg'])
        instrument_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(instrument_frame, text="Instrument:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=0, column=0, sticky=tk.W)
        
        self.instrument_type_var = tk.StringVar(value="FUT")
        tk.OptionMenu(instrument_frame, self.instrument_type_var, "FUT", "OPT").grid(row=0, column=1, padx=5)
        
        self.symbol_var = tk.StringVar()
        self.symbol_combo = ttk.Combobox(instrument_frame, textvariable=self.symbol_var, width=20)
        self.symbol_combo.grid(row=0, column=2, padx=5)
        
        tk.Button(instrument_frame, text="Refresh", command=self.refresh_instruments,
                 bg=self.colors['neutral'], fg='white').grid(row=0, column=3, padx=5)
        
        # Order form for F&O
        order_form_frame = tk.Frame(fo_frame, bg=self.colors['panel_bg'])
        order_form_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Symbol
        tk.Label(order_form_frame, text="Trading Symbol:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.fo_symbol_entry = tk.Entry(order_form_frame, width=20)
        self.fo_symbol_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=5)
        
        # Transaction type
        tk.Label(order_form_frame, text="Transaction:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.fo_transaction_var = tk.StringVar(value="BUY")
        tk.OptionMenu(order_form_frame, self.fo_transaction_var, "BUY", "SELL").grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)
        
        # Quantity
        tk.Label(order_form_frame, text="Quantity:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.fo_quantity_entry = tk.Entry(order_form_frame, width=10)
        self.fo_quantity_entry.grid(row=2, column=1, sticky=tk.W, pady=2, padx=5)
        self.fo_quantity_entry.insert(0, "50")
        
        # Order type
        tk.Label(order_form_frame, text="Order Type:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=3, column=0, sticky=tk.W, pady=2)
        self.fo_order_type_var = tk.StringVar(value="MARKET")
        tk.OptionMenu(order_form_frame, self.fo_order_type_var, "MARKET", "LIMIT").grid(row=3, column=1, sticky=tk.W, pady=2, padx=5)
        
        # Price
        tk.Label(order_form_frame, text="Price:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=4, column=0, sticky=tk.W, pady=2)
        self.fo_price_entry = tk.Entry(order_form_frame, width=10)
        self.fo_price_entry.grid(row=4, column=1, sticky=tk.W, pady=2, padx=5)
        
        # Product type
        tk.Label(order_form_frame, text="Product:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=5, column=0, sticky=tk.W, pady=2)
        self.fo_product_var = tk.StringVar(value="MIS")
        tk.OptionMenu(order_form_frame, self.fo_product_var, "MIS", "NRML", "CNC").grid(row=5, column=1, sticky=tk.W, pady=2, padx=5)
        
        # Buttons
        button_frame = tk.Frame(order_form_frame, bg=self.colors['panel_bg'])
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        tk.Button(button_frame, text="Place F&O Order", command=self.place_fo_order,
                 bg=self.colors['buy'], fg='white', font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Get Quote", command=self.get_fo_quote,
                 bg=self.colors['neutral'], fg='white').pack(side=tk.LEFT, padx=5)
        
        # Positions display
        positions_frame = tk.Frame(fo_frame, bg=self.colors['panel_bg'])
        positions_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Positions treeview
        columns = ('Symbol', 'Type', 'Qty', 'Avg Price', 'LTP', 'P&L', 'Segment')
        self.positions_tree = ttk.Treeview(positions_frame, columns=columns, show='headings', height=8)
        
        for col in columns:
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=80)
        
        self.positions_tree.pack(fill=tk.BOTH, expand=True)
        
        # Bind double click to close position
        self.positions_tree.bind('<Double-1>', self.on_position_double_click)
    
    def setup_pnl_frame(self):
        """Setup P&L display frame"""
        pnl_frame = tk.Frame(self.main_frame, bg=self.colors['panel_bg'], relief=tk.RAISED, bd=1)
        pnl_frame.pack(fill=tk.X, pady=(10, 0))
        
        # P&L header
        header = tk.Frame(pnl_frame, bg=self.colors['mcx'])
        header.pack(fill=tk.X)
        tk.Label(header, text="PROFIT & LOSS DASHBOARD", bg=self.colors['mcx'],
                fg='white', font=('Arial', 10, 'bold')).pack(fill=tk.X, pady=2)
        
        # P&L metrics
        metrics_frame = tk.Frame(pnl_frame, bg=self.colors['panel_bg'])
        metrics_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Realized P&L
        tk.Label(metrics_frame, text="Realized P&L:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        self.realized_pnl_label = tk.Label(metrics_frame, text="₹0.00", bg=self.colors['panel_bg'],
                                          fg=self.colors['profit'], font=('Arial', 10, 'bold'))
        self.realized_pnl_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        # Unrealized P&L
        tk.Label(metrics_frame, text="Unrealized P&L:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.unrealized_pnl_label = tk.Label(metrics_frame, text="₹0.00", bg=self.colors['panel_bg'],
                                            fg=self.colors['neutral'], font=('Arial', 10, 'bold'))
        self.unrealized_pnl_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # Total P&L
        tk.Label(metrics_frame, text="Total P&L:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light'], font=('Arial', 10, 'bold')).grid(row=0, column=4, sticky=tk.W, padx=(20,0))
        self.total_pnl_label = tk.Label(metrics_frame, text="₹0.00", bg=self.colors['panel_bg'],
                                       fg=self.colors['profit'], font=('Arial', 12, 'bold'))
        self.total_pnl_label.grid(row=0, column=5, sticky=tk.W, padx=10)
        
        # P&L history treeview
        history_frame = tk.Frame(pnl_frame, bg=self.colors['panel_bg'])
        history_frame.pack(fill=tk.X, padx=10, pady=5)
        
        columns = ('Time', 'Symbol', 'Type', 'Qty', 'Entry', 'Exit', 'P&L')
        self.pnl_history_tree = ttk.Treeview(history_frame, columns=columns, show='headings', height=4)
        
        for col in columns:
            self.pnl_history_tree.heading(col, text=col)
        self.pnl_history_tree.pack(fill=tk.X)
    
    def setup_watchlist_frame(self):
        """Setup watchlist display frame"""
        watchlist_frame = tk.Frame(self.left_frame, bg=self.colors['panel_bg'])
        watchlist_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Watchlist header
        header = tk.Frame(watchlist_frame, bg=self.colors['neutral'])
        header.pack(fill=tk.X)
        tk.Label(header, text="WATCHLIST", bg=self.colors['neutral'], 
                fg='white', font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Watchlist controls
        control_frame = tk.Frame(watchlist_frame, bg=self.colors['panel_bg'])
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(control_frame, text="Add Symbol:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).pack(side=tk.LEFT)
        self.symbol_entry = tk.Entry(control_frame, width=15)
        self.symbol_entry.pack(side=tk.LEFT, padx=5)
        self.symbol_entry.insert(0, "RELIANCE")
        
        tk.Button(control_frame, text="Add", command=self.add_to_watchlist,
                 bg=self.colors['buy'], fg='white').pack(side=tk.LEFT, padx=5)
        
        # Predefined symbols including F&O
        preset_frame = tk.Frame(watchlist_frame, bg=self.colors['panel_bg'])
        preset_frame.pack(fill=tk.X, padx=5, pady=2)
        
        preset_symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "TATASTEEL", "GOLDBEES"]
        for symbol in preset_symbols:
            btn = tk.Button(preset_frame, text=symbol, 
                          command=lambda s=symbol: self.add_preset_symbol(s),
                          bg=self.colors['neutral'], fg='white', font=('Arial', 8))
            btn.pack(side=tk.LEFT, padx=2)
        
        # Watchlist treeview
        columns = ('Symbol', 'LTP', 'Change', 'Change%', 'Volume', 'Color')
        self.watchlist_tree = ttk.Treeview(watchlist_frame, columns=columns, show='headings', height=12)
        
        for col in columns:
            self.watchlist_tree.heading(col, text=col)
            self.watchlist_tree.column(col, width=80)
        
        self.watchlist_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Bind double click to show chart
        self.watchlist_tree.bind('<Double-1>', self.on_watchlist_double_click)
    
    def setup_portfolio_frame(self):
        """Setup portfolio display frame"""
        portfolio_frame = tk.Frame(self.left_frame, bg=self.colors['panel_bg'])
        portfolio_frame.pack(fill=tk.BOTH, expand=True)
        
        # Portfolio header
        header = tk.Frame(portfolio_frame, bg=self.colors['hold'])
        header.pack(fill=tk.X)
        tk.Label(header, text="PORTFOLIO & ORDERS", bg=self.colors['hold'], 
                fg='white', font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Notebook for portfolio and orders
        self.portfolio_notebook = ttk.Notebook(portfolio_frame)
        self.portfolio_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Holdings tab
        self.holdings_frame = tk.Frame(self.portfolio_notebook, bg=self.colors['panel_bg'])
        self.portfolio_notebook.add(self.holdings_frame, text="Holdings")
        
        holdings_columns = ('Symbol', 'Quantity', 'Avg Price', 'LTP', 'P&L', 'P&L%')
        self.holdings_tree = ttk.Treeview(self.holdings_frame, columns=holdings_columns, show='headings', height=8)
        
        for col in holdings_columns:
            self.holdings_tree.heading(col, text=col)
        self.holdings_tree.pack(fill=tk.BOTH, expand=True)
        
        # Orders tab
        self.orders_frame = tk.Frame(self.portfolio_notebook, bg=self.colors['panel_bg'])
        self.portfolio_notebook.add(self.orders_frame, text="Orders")
        
        orders_columns = ('Order ID', 'Symbol', 'Transaction', 'Quantity', 'Price', 'Status')
        self.orders_tree = ttk.Treeview(self.orders_frame, columns=orders_columns, show='headings', height=8)
        
        for col in orders_columns:
            self.orders_tree.heading(col, text=col)
        self.orders_tree.pack(fill=tk.BOTH, expand=True)
    
    def setup_chart_frame(self):
        """Setup chart display frame"""
        chart_frame = tk.Frame(self.right_frame, bg=self.colors['panel_bg'])
        chart_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Chart header
        header = tk.Frame(chart_frame, bg=self.colors['neutral'])
        header.pack(fill=tk.X)
        tk.Label(header, text="CHART & ANALYSIS", bg=self.colors['neutral'], 
                fg='white', font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Chart controls
        control_frame = tk.Frame(chart_frame, bg=self.colors['panel_bg'])
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(control_frame, text="Timeframe:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).pack(side=tk.LEFT)
        
        self.timeframe_var = tk.StringVar(value="day")
        timeframes = [("1 Minute", "1minute"), ("5 Minute", "5minute"), 
                     ("15 Minute", "15minute"), ("1 Hour", "60minute"), 
                     ("1 Day", "day")]
        
        for text, value in timeframes:
            tk.Radiobutton(control_frame, text=text, variable=self.timeframe_var,
                          value=value, bg=self.colors['panel_bg'], 
                          fg=self.colors['text_light']).pack(side=tk.LEFT, padx=5)
        
        # Chart canvas
        self.chart_fig = Figure(figsize=(8, 6), facecolor=self.colors['panel_bg'])
        self.chart_ax = self.chart_fig.add_subplot(111)
        self.chart_ax.set_facecolor(self.colors['panel_bg'])
        self.chart_canvas = FigureCanvasTkAgg(self.chart_fig, chart_frame)
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def setup_order_frame(self):
        """Setup order placement frame"""
        order_frame = tk.Frame(self.right_frame, bg=self.colors['panel_bg'])
        order_frame.pack(fill=tk.BOTH, expand=True)
        
        # Order header
        header = tk.Frame(order_frame, bg=self.colors['hold'])
        header.pack(fill=tk.X)
        tk.Label(header, text="QUICK ORDER", bg=self.colors['hold'], 
                fg='white', font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Order form
        form_frame = tk.Frame(order_frame, bg=self.colors['panel_bg'])
        form_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Symbol
        tk.Label(form_frame, text="Symbol:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.order_symbol = tk.Entry(form_frame, width=15)
        self.order_symbol.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)
        self.order_symbol.insert(0, "RELIANCE")
        
        # Transaction type
        tk.Label(form_frame, text="Transaction:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.transaction_var = tk.StringVar(value="BUY")
        tk.OptionMenu(form_frame, self.transaction_var, "BUY", "SELL").grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Quantity
        tk.Label(form_frame, text="Quantity:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.quantity_entry = tk.Entry(form_frame, width=15)
        self.quantity_entry.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)
        self.quantity_entry.insert(0, "1")
        
        # Order type
        tk.Label(form_frame, text="Order Type:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=3, column=0, sticky=tk.W, pady=5)
        self.order_type_var = tk.StringVar(value="MARKET")
        tk.OptionMenu(form_frame, self.order_type_var, "MARKET", "LIMIT").grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Price (for limit orders)
        tk.Label(form_frame, text="Price:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=4, column=0, sticky=tk.W, pady=5)
        self.price_entry = tk.Entry(form_frame, width=15)
        self.price_entry.grid(row=4, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Product type
        tk.Label(form_frame, text="Product:", bg=self.colors['panel_bg'],
                fg=self.colors['text_light']).grid(row=5, column=0, sticky=tk.W, pady=5)
        self.product_var = tk.StringVar(value="CNC")
        tk.OptionMenu(form_frame, self.product_var, "CNC", "MIS", "NRML").grid(row=5, column=1, sticky=tk.W, pady=5, padx=5)
        
        # Buttons
        button_frame = tk.Frame(form_frame, bg=self.colors['panel_bg'])
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        tk.Button(button_frame, text="Place Buy Order", command=lambda: self.place_order("BUY"),
                 bg=self.colors['buy'], fg='white', font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        
        tk.Button(button_frame, text="Place Sell Order", command=lambda: self.place_order("SELL"),
                 bg=self.colors['sell'], fg='white', font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
    
    def setup_log_frame(self):
        """Setup logging frame"""
        log_frame = tk.Frame(self.main_frame, bg=self.colors['panel_bg'], relief=tk.RAISED, bd=1)
        log_frame.pack(fill=tk.X, pady=(10, 0))
        
        tk.Label(log_frame, text="TRADING LOGS", bg=self.colors['neutral'],
                fg='white', font=('Arial', 10, 'bold')).pack(fill=tk.X, pady=2)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, bg='black', fg='white')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Configure tag colors for logs
        self.log_text.tag_config('SUCCESS', foreground='green')
        self.log_text.tag_config('ERROR', foreground='red')
        self.log_text.tag_config('INFO', foreground='cyan')
        self.log_text.tag_config('WARNING', foreground='yellow')
        self.log_text.tag_config('TOKEN', foreground='magenta')
        self.log_text.tag_config('P&L', foreground='orange')
    
    def load_config(self):
        """Load configuration from file"""
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.api_key_entry.insert(0, config.get('api_key', ''))
                self.api_secret_entry.insert(0, config.get('api_secret', ''))
                self.access_token_entry.insert(0, config.get('access_token', ''))
                
                # Check if we have a valid access token
                if config.get('access_token'):
                    self.token_status.config(text="Token: Available", bg='lightgreen')
                    
        except FileNotFoundError:
            self.log_message("Config file not found. Using default configuration.", 'WARNING')
    
    def save_config(self):
        """Save configuration to file"""
        config = {
            'api_key': self.api_key_entry.get(),
            'api_secret': self.api_secret_entry.get(),
            'access_token': self.access_token_entry.get()
        }
        with open('config.json', 'w') as f:
            json.dump(config, f)
        self.log_message("Configuration saved to config.json", 'SUCCESS')
    
    def generate_token(self):
        """Generate access token using API key and secret"""
        try:
            api_key = self.api_key_entry.get().strip()
            api_secret = self.api_secret_entry.get().strip()
            
            if not api_key or not api_secret:
                messagebox.showerror("Error", "Please enter both API Key and API Secret")
                return
            
            self.log_message("Initializing token generation...", 'INFO')
            self.token_status.config(text="Generating...", bg='orange')
            
            # Initialize token generator
            self.token_generator = KiteTokenGenerator(
                api_key=api_key,
                api_secret=api_secret
            )
            
            # Generate and open login URL
            login_url = self.token_generator.generate_login_url()
            
            self.log_message("Login URL opened in browser. Please complete the login process.", 'INFO')
            self.log_message(f"Login URL: {login_url}", 'TOKEN')
            
            # Show instructions
            messagebox.showinfo("Login Required", 
                              "A browser window has been opened for Zerodha login.\n\n"
                              "After logging in, you will be redirected to a URL.\n"
                              "Copy the 'request_token' parameter from that URL and enter it in the next prompt.")
            
            # Ask for request token
            request_token = simpledialog.askstring("Request Token", 
                                                 "Enter the request token from the redirect URL:")
            
            if not request_token:
                self.log_message("Token generation cancelled by user", 'WARNING')
                self.token_status.config(text="Token: Cancelled", bg='orange')
                return
            
            self.log_message(f"Received request token: {request_token}", 'TOKEN')
            
            # Generate access token
            access_token = self.token_generator.generate_access_token(request_token)
            
            if access_token:
                self.access_token_entry.delete(0, tk.END)
                self.access_token_entry.insert(0, access_token)
                
                self.token_status.config(text="Token: Generated", bg='green')
                self.log_message("Access token generated successfully!", 'SUCCESS')
                self.log_message(f"Access Token: {access_token}", 'TOKEN')
                
                # Save configuration
                self.save_config()
                
                # Auto-connect after token generation
                self.connect_with_token()
            else:
                self.token_status.config(text="Token: Failed", bg='red')
                self.log_message("Failed to generate access token", 'ERROR')
                
        except Exception as e:
            error_msg = f"Token generation failed: {str(e)}"
            self.log_message(error_msg, 'ERROR')
            self.token_status.config(text="Token: Error", bg='red')
            messagebox.showerror("Token Generation Error", error_msg)
    
    def connect_kite(self):
        """Connect to Kite Connect using API key and secret with token generation"""
        # First generate token, then connect
        self.generate_token()
    
    def connect_with_token(self):
        """Connect using existing access token"""
        try:
            api_key = self.api_key_entry.get().strip()
            access_token = self.access_token_entry.get().strip()
            
            if not api_key or not access_token:
                messagebox.showerror("Error", "Please enter both API Key and Access Token")
                return
            
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
            
            # Test connection
            profile = self.kite.profile()
            self.is_connected = True
            
            # Initialize F&O manager
            self.fo_manager = FuturesOptionsManager(self.kite)
            
            self.connection_status.config(text=f"Connected: {profile['user_name']}", bg='green')
            self.token_status.config(text="Token: Valid", bg='green')
            self.log_message(f"Successfully connected as {profile['user_name']}", 'SUCCESS')
            self.log_message(f"User ID: {profile['user_id']}", 'INFO')
            
            self.save_config()
            self.load_instruments()
            self.refresh_data()
            self.add_default_watchlist()
            
            # Load F&O instruments
            self.load_fo_instruments()
            
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            self.log_message(error_msg, 'ERROR')
            self.connection_status.config(text="Connection Failed", bg='red')
            self.token_status.config(text="Token: Invalid", bg='red')
            messagebox.showerror("Connection Error", 
                               f"{error_msg}\n\nPlease generate a new access token.")
    
    def load_fo_instruments(self):
        """Load Futures and Options instruments"""
        if not self.is_connected or not self.fo_manager:
            return
        
        try:
            self.fo_manager.load_instruments()
            self.log_message("F&O instruments loaded successfully", 'SUCCESS')
            self.refresh_instruments()
        except Exception as e:
            self.log_message(f"Failed to load F&O instruments: {str(e)}", 'ERROR')
    
    def refresh_instruments(self):
        """Refresh instrument list based on selected segment"""
        if not self.fo_manager or not self.fo_manager.loaded:
            return
        
        try:
            symbols = []
            if self.segment_var.get() == "NFO":
                if self.instrument_type_var.get() == "FUT":
                    instruments = self.fo_manager.get_nifty_futures()
                else:
                    instruments = self.fo_manager.get_nifty_options()
            else:  # MCX
                if self.instrument_type_var.get() == "FUT":
                    instruments = self.fo_manager.get_mcx_futures()
                else:
                    instruments = self.fo_manager.get_mcx_options()
            
            symbols = [f"{inst['tradingsymbol']}" for inst in instruments[:100]]  # Limit to 100
            
            self.symbol_combo['values'] = symbols
            if symbols:
                self.symbol_combo.set(symbols[0])
            
        except Exception as e:
            self.log_message(f"Failed to refresh instruments: {str(e)}", 'ERROR')
    
    def on_segment_change(self):
        """Handle segment change"""
        self.refresh_instruments()
        segment = self.segment_var.get()
        color = self.colors['nifty'] if segment == "NFO" else self.colors['mcx']
        self.log_message(f"Segment changed to: {segment}", 'INFO')
    
    def place_fo_order(self):
        """Place Futures and Options order"""
        if not self.is_connected:
            messagebox.showerror("Error", "Not connected to Kite")
            return
        
        try:
            symbol = self.fo_symbol_entry.get().strip().upper()
            quantity = int(self.fo_quantity_entry.get())
            order_type = self.fo_order_type_var.get()
            product = self.fo_product_var.get()
            transaction_type = self.fo_transaction_var.get()
            segment = self.segment_var.get()
            
            if not symbol:
                messagebox.showerror("Error", "Please enter a symbol")
                return
            
            # Determine exchange based on segment
            exchange = self.kite.EXCHANGE_NFO if segment == "NFO" else self.kite.EXCHANGE_MCX
            
            order_params = {
                "tradingsymbol": symbol,
                "exchange": exchange,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
                "variety": self.kite.VARIETY_REGULAR
            }
            
            # Add price for limit orders
            if order_type == "LIMIT":
                price = float(self.fo_price_entry.get())
                order_params["price"] = price
            
            order_id = self.kite.place_order(**order_params)
            
            self.log_message(f"F&O Order placed: {transaction_type} {quantity} {symbol} | ID: {order_id}", 'SUCCESS')
            messagebox.showinfo("F&O Order Placed", f"Order ID: {order_id}")
            
            # Add to position tracking
            self.track_new_position(symbol, transaction_type, quantity, 
                                  float(self.fo_price_entry.get()) if self.fo_price_entry.get() else 0,
                                  segment)
            
            # Refresh orders and positions
            self.refresh_orders()
            self.refresh_positions()
            
        except Exception as e:
            error_msg = f"F&O Order placement failed: {str(e)}"
            self.log_message(error_msg, 'ERROR')
            messagebox.showerror("F&O Order Error", error_msg)
    
    def track_new_position(self, symbol: str, transaction_type: str, quantity: int, 
                          price: float, segment: str):
        """Track a new position for P&L calculation"""
        try:
            # Get instrument token (simplified - in real implementation, look up from instruments)
            instruments = self.kite.instruments()
            instrument = next((inst for inst in instruments 
                             if inst['tradingsymbol'] == symbol and 
                             inst['exchange'] == (self.kite.EXCHANGE_NFO if segment == "NFO" else self.kite.EXCHANGE_MCX)), None)
            
            if instrument:
                position_id = self.pnl_calculator.add_position(
                    symbol=symbol,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    avg_price=price,
                    instrument_token=instrument['instrument_token'],
                    segment=segment
                )
                
                self.active_positions[position_id] = {
                    'symbol': symbol,
                    'instrument_token': instrument['instrument_token']
                }
                
                # Subscribe to real-time data
                if self.kws:
                    self.kws.subscribe([instrument['instrument_token']])
                
                self.log_message(f"Started tracking position: {symbol} {transaction_type} {quantity}", 'P&L')
                
        except Exception as e:
            self.log_message(f"Failed to track position: {str(e)}", 'ERROR')
    
    def get_fo_quote(self):
        """Get F&O instrument quote"""
        if not self.is_connected:
            return
        
        try:
            symbol = self.symbol_combo.get().strip()
            if not symbol:
                return
            
            segment = self.segment_var.get()
            exchange = self.kite.EXCHANGE_NFO if segment == "NFO" else self.kite.EXCHANGE_MCX
            
            quote = self.kite.quote(f"{exchange}:{symbol}")
            ltp = quote[f"{exchange}:{symbol}"]['last_price']
            
            self.fo_price_entry.delete(0, tk.END)
            self.fo_price_entry.insert(0, str(ltp))
            self.fo_symbol_entry.delete(0, tk.END)
            self.fo_symbol_entry.insert(0, symbol)
            
            self.log_message(f"{symbol} LTP: {ltp}", 'INFO')
            
        except Exception as e:
            self.log_message(f"Failed to get F&O quote: {str(e)}", 'ERROR')
    
    def refresh_positions(self):
        """Refresh positions display"""
        # Clear existing data
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        
        # Add active positions
        for position_id, position_data in self.pnl_calculator.positions.items():
            position = position_data
            pnl = position['unrealized_pnl']
            
            tags = ('profit',) if pnl >= 0 else ('loss',)
            
            self.positions_tree.insert('', 'end', values=(
                position['symbol'],
                position['transaction_type'],
                position['quantity'],
                f"{position['avg_price']:.2f}",
                f"{position['current_price']:.2f}",
                f"{pnl:.2f}",
                position['segment']
            ), tags=tags)
    
    def on_position_double_click(self, event):
        """Handle position double click to close position"""
        selection = self.positions_tree.selection()
        if selection:
            item = selection[0]
            values = self.positions_tree.item(item)['values']
            symbol = values[0]
            
            # Implement position closing logic here
            response = messagebox.askyesno("Close Position", f"Close position for {symbol}?")
            if response:
                self.log_message(f"Closing position for {symbol}", 'P&L')
    
    def calculate_total_pnl(self):
        """Calculate and display total P&L"""
        try:
            total_pnl = self.pnl_calculator.get_total_pnl()
            
            # Update P&L labels
            self.realized_pnl_label.config(text=f"₹{total_pnl['realized_pnl']:.2f}")
            self.unrealized_pnl_label.config(text=f"₹{total_pnl['unrealized_pnl']:.2f}")
            self.total_pnl_label.config(text=f"₹{total_pnl['total_pnl']:.2f}")
            
            # Color code total P&L
            if total_pnl['total_pnl'] >= 0:
                self.total_pnl_label.config(fg=self.colors['profit'])
            else:
                self.total_pnl_label.config(fg=self.colors['loss'])
            
            self.log_message(f"P&L Calculated - Realized: ₹{total_pnl['realized_pnl']:.2f}, "
                           f"Unrealized: ₹{total_pnl['unrealized_pnl']:.2f}, "
                           f"Total: ₹{total_pnl['total_pnl']:.2f}", 'P&L')
            
        except Exception as e:
            self.log_message(f"Failed to calculate P&L: {str(e)}", 'ERROR')
    
    def save_token(self):
        """Save access token to file"""
        access_token = self.access_token_entry.get().strip()
        if access_token:
            with open("access_token.txt", "w") as f:
                f.write(access_token)
            self.log_message("Access token saved to access_token.txt", 'SUCCESS')
        else:
            self.log_message("No access token to save", 'WARNING')
    
    def add_default_watchlist(self):
        """Add default symbols to watchlist"""
        default_symbols = ["RELIANCE", "TCS", "INFY", "NIFTY", "BANKNIFTY"]
        for symbol in default_symbols:
            nse_symbol = f"NSE:{symbol}" if symbol not in ["NIFTY", "BANKNIFTY"] else f"NFO:{symbol}"
            if nse_symbol not in self.watchlist_data:
                self.watchlist_data[nse_symbol] = {'added_time': datetime.now()}
        
        self.refresh_watchlist()
        self.log_message(f"Added default watchlist: {', '.join(default_symbols)}", 'INFO')
    
    def add_preset_symbol(self, symbol):
        """Add preset symbol to watchlist"""
        self.symbol_entry.delete(0, tk.END)
        self.symbol_entry.insert(0, symbol)
        self.add_to_watchlist()
    
    def load_instruments(self):
        """Load instruments master"""
        if not self.is_connected:
            return
            
        try:
            self.instruments = pd.DataFrame(self.kite.instruments())
            self.log_message(f"Loaded {len(self.instruments)} instruments", 'INFO')
        except Exception as e:
            self.log_message(f"Failed to load instruments: {str(e)}", 'ERROR')
    
    def refresh_data(self):
        """Refresh all data"""
        if not self.is_connected:
            return
            
        try:
            # Refresh portfolio
            self.refresh_portfolio()
            
            # Refresh orders
            self.refresh_orders()
            
            # Refresh watchlist
            self.refresh_watchlist()
            
            # Refresh positions
            self.refresh_positions()
            
            # Calculate P&L
            self.calculate_total_pnl()
            
            self.log_message("Data refreshed successfully", 'SUCCESS')
            
        except Exception as e:
            self.log_message(f"Data refresh failed: {str(e)}", 'ERROR')
    
    def refresh_portfolio(self):
        """Refresh portfolio data"""
        try:
            holdings = self.kite.holdings()
            positions = self.kite.positions()
            
            # Clear existing data
            for item in self.holdings_tree.get_children():
                self.holdings_tree.delete(item)
            
            # Add holdings
            for holding in holdings:
                pnl = holding['pnl']
                pnl_percent = (pnl / holding['average_price']) * 100 if holding['average_price'] else 0
                
                tags = ('profit',) if pnl >= 0 else ('loss',)
                
                self.holdings_tree.insert('', 'end', values=(
                    holding['tradingsymbol'],
                    holding['quantity'],
                    f"{holding['average_price']:.2f}",
                    f"{holding['last_price']:.2f}",
                    f"{pnl:.2f}",
                    f"{pnl_percent:.2f}%"
                ), tags=tags)
            
        except Exception as e:
            self.log_message(f"Portfolio refresh failed: {str(e)}", 'ERROR')
    
    def refresh_orders(self):
        """Refresh orders data"""
        try:
            orders = self.kite.orders()
            
            # Clear existing data
            for item in self.orders_tree.get_children():
                self.orders_tree.delete(item)
            
            # Add orders
            for order in orders[-20:]:  # Last 20 orders
                self.orders_tree.insert('', 'end', values=(
                    order['order_id'],
                    order['tradingsymbol'],
                    order['transaction_type'],
                    order['quantity'],
                    order['price'],
                    order['status']
                ))
            
        except Exception as e:
            self.log_message(f"Orders refresh failed: {str(e)}", 'ERROR')
    
    def refresh_watchlist(self):
        """Refresh watchlist data"""
        if not self.watchlist_data:
            return
            
        try:
            # Clear existing data
            for item in self.watchlist_tree.get_children():
                self.watchlist_tree.delete(item)
            
            symbols = list(self.watchlist_data.keys())
            if symbols:
                quotes = self.kite.quote(symbols)
                
                for symbol, data in quotes.items():
                    ltp = data['last_price']
                    previous_close = data['ohlc']['close']
                    change = ltp - previous_close
                    change_percent = (change / previous_close) * 100
                    volume = data['volume']
                    
                    # Determine color based on change
                    if change > 0:
                        color_tag = 'profit'
                        color_display = '🟢'
                    elif change < 0:
                        color_tag = 'loss'
                        color_display = '🔴'
                    else:
                        color_tag = 'neutral'
                        color_display = '🟡'
                    
                    self.watchlist_tree.insert('', 'end', values=(
                        symbol.split(':')[1],
                        f"{ltp:.2f}",
                        f"{change:+.2f}",
                        f"{change_percent:+.2f}%",
                        volume,
                        color_display
                    ), tags=(color_tag,))
            
        except Exception as e:
            self.log_message(f"Watchlist refresh failed: {str(e)}", 'ERROR')
    
    def add_to_watchlist(self):
        """Add symbol to watchlist"""
        symbol = self.symbol_entry.get().strip().upper()
        if not symbol:
            return
            
        try:
            # Add NSE prefix
            nse_symbol = f"NSE:{symbol}"
            
            if nse_symbol not in self.watchlist_data:
                self.watchlist_data[nse_symbol] = {'added_time': datetime.now()}
                self.log_message(f"Added {symbol} to watchlist", 'INFO')
                self.refresh_watchlist()
                
                # Subscribe to real-time data if connected
                if self.kws and self.is_connected:
                    self.subscribe_symbol(nse_symbol)
                    
            self.symbol_entry.delete(0, tk.END)
            
        except Exception as e:
            self.log_message(f"Failed to add {symbol} to watchlist: {str(e)}", 'ERROR')
    
    def place_order(self, transaction_type):
        """Place an order"""
        if not self.is_connected:
            messagebox.showerror("Error", "Not connected to Kite")
            return
            
        try:
            symbol = self.order_symbol.get().strip().upper()
            quantity = int(self.quantity_entry.get())
            order_type = self.order_type_var.get()
            product = self.product_var.get()
            
            if not symbol or quantity <= 0:
                messagebox.showerror("Error", "Invalid symbol or quantity")
                return
            
            order_params = {
                "tradingsymbol": symbol,
                "exchange": self.kite.EXCHANGE_NSE,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
                "variety": self.kite.VARIETY_REGULAR
            }
            
            # Add price for limit orders
            if order_type == "LIMIT":
                price = float(self.price_entry.get())
                order_params["price"] = price
            
            order_id = self.kite.place_order(**order_params)
            
            self.log_message(f"Order placed: {transaction_type} {quantity} {symbol} | ID: {order_id}", 'SUCCESS')
            messagebox.showinfo("Order Placed", f"Order ID: {order_id}")
            
            # Refresh orders
            self.refresh_orders()
            
        except Exception as e:
            error_msg = f"Order placement failed: {str(e)}"
            self.log_message(error_msg, 'ERROR')
            messagebox.showerror("Order Error", error_msg)
    
    def show_profile(self):
        """Show user profile information"""
        if not self.is_connected:
            return
            
        try:
            profile = self.kite.profile()
            margins = self.kite.margins()
            
            profile_info = f"""
User Profile:
------------
Name: {profile['user_name']}
User ID: {profile['user_id']}
Email: {profile['email']}
Products: {', '.join(profile['products'])}
Exchanges: {', '.join(profile['exchanges'])}

Margin Details:
---------------
Equity: {margins['equity']['available']['live_balance']:.2f}
Commodity: {margins['commodity']['available']['live_balance']:.2f}
"""
            self.log_message("Profile information retrieved", 'INFO')
            messagebox.showinfo("User Profile", profile_info)
            
        except Exception as e:
            self.log_message(f"Failed to get profile: {str(e)}", 'ERROR')
    
    def start_real_time(self):
        """Start real-time data streaming"""
        if not self.is_connected:
            return
            
        try:
            self.kws = KiteTicker(self.api_key_entry.get(), self.access_token_entry.get())
            
            # Set callback functions
            self.kws.on_ticks = self.on_ticks
            self.kws.on_connect = self.on_connect
            self.kws.on_close = self.on_close
            
            # Start WebSocket in a separate thread
            self.ws_thread = threading.Thread(target=self.kws.connect, daemon=True)
            self.ws_thread.start()
            
            self.log_message("Real-time streaming started", 'INFO')
            
        except Exception as e:
            self.log_message(f"Real-time start failed: {str(e)}", 'ERROR')
    
    def stop_real_time(self):
        """Stop real-time data streaming"""
        if self.kws:
            self.kws.close()
            self.log_message("Real-time streaming stopped", 'INFO')
    
    def on_connect(self, ws, response):
        """WebSocket connect callback"""
        self.log_message("WebSocket connected", 'SUCCESS')
        
        # Subscribe to watchlist symbols
        if self.watchlist_data:
            tokens = []
            for symbol in self.watchlist_data.keys():
                # Extract instrument token from symbol
                try:
                    if 'NSE:' in symbol:
                        stock_symbol = symbol.replace('NSE:', '')
                        instrument = self.instruments[
                            (self.instruments['tradingsymbol'] == stock_symbol) & 
                            (self.instruments['exchange'] == 'NSE')
                        ]
                        if not instrument.empty:
                            tokens.append(instrument.iloc[0]['instrument_token'])
                    elif 'NFO:' in symbol:
                        stock_symbol = symbol.replace('NFO:', '')
                        instrument = self.instruments[
                            (self.instruments['tradingsymbol'] == stock_symbol) & 
                            (self.instruments['exchange'] == 'NFO')
                        ]
                        if not instrument.empty:
                            tokens.append(instrument.iloc[0]['instrument_token'])
                except Exception as e:
                    continue
            
            if tokens:
                self.kws.subscribe(tokens)
                self.kws.set_mode(self.kws.MODE_LTP, tokens)
    
    def on_close(self, ws, code, reason):
        """WebSocket close callback"""
        self.log_message(f"WebSocket closed: {reason}", 'WARNING')
    
    def on_ticks(self, ws, ticks):
        """WebSocket ticks callback"""
        for tick in ticks:
            try:
                symbol = self.kite.instrument_token_to_symbol(tick['instrument_token'])
                self.last_ticks[symbol] = tick
                
                # Update P&L calculator with new price
                self.pnl_calculator.update_price(tick['instrument_token'], tick['last_price'])
                
                # Update watchlist in GUI thread
                self.root.after(0, self.update_watchlist_tick, symbol, tick)
                
                # Update positions in GUI thread
                self.root.after(0, self.refresh_positions)
                self.root.after(0, self.calculate_total_pnl)
                
            except Exception as e:
                continue
    
    def update_watchlist_tick(self, symbol, tick):
        """Update watchlist with real-time data"""
        for item in self.watchlist_tree.get_children():
            values = self.watchlist_tree.item(item)['values']
            if values[0] == symbol.split(':')[1]:
                ltp = tick['last_price']
                # You would need to calculate change from previous close
                # This is simplified - in real implementation, store previous close
                change = 0  # Calculate properly
                change_percent = 0  # Calculate properly
                
                color_display = '🟢' if change >= 0 else '🔴'
                
                self.watchlist_tree.item(item, values=(
                    symbol.split(':')[1],
                    f"{ltp:.2f}",
                    f"{change:+.2f}",
                    f"{change_percent:+.2f}%",
                    tick.get('volume', 0),
                    color_display
                ))
                break
    
    def subscribe_symbol(self, symbol):
        """Subscribe symbol to real-time data"""
        if self.kws:
            # Extract instrument token
            try:
                if 'NSE:' in symbol:
                    stock_symbol = symbol.replace('NSE:', '')
                    instrument = self.instruments[
                        (self.instruments['tradingsymbol'] == stock_symbol) & 
                        (self.instruments['exchange'] == 'NSE')
                    ]
                    if not instrument.empty:
                        self.kws.subscribe([instrument.iloc[0]['instrument_token']])
                        self.log_message(f"Subscribed to real-time: {symbol}", 'INFO')
            except Exception as e:
                self.log_message(f"Failed to subscribe to {symbol}: {str(e)}", 'ERROR')
    
    def on_watchlist_double_click(self, event):
        """Handle watchlist double click to show chart"""
        selection = self.watchlist_tree.selection()
        if selection:
            item = selection[0]
            symbol = self.watchlist_tree.item(item)['values'][0]
            self.show_chart(symbol)
    
    def show_chart(self, symbol):
        """Show chart for symbol"""
        if not self.is_connected:
            return
            
        try:
            # Get historical data
            from_date = datetime.now() - timedelta(days=30)
            to_date = datetime.now()
            
            # Get instrument token
            instrument_token = self.get_instrument_token(symbol)
            if not instrument_token:
                self.log_message(f"Could not find instrument token for {symbol}", 'WARNING')
                return
            
            historical_data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=self.timeframe_var.get()
            )
            
            if not historical_data:
                self.log_message(f"No historical data for {symbol}", 'WARNING')
                return
            
            # Convert to DataFrame
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            # Clear previous chart
            self.chart_ax.clear()
            
            # Create candlestick chart
            mpf.plot(df, type='candle', style='charles', 
                    ax=self.chart_ax,
                    volume=False,
                    returnfig=False)
            
            self.chart_ax.set_title(f"{symbol} Price Chart", color='white', fontsize=14)
            self.chart_ax.set_facecolor(self.colors['panel_bg'])
            self.chart_ax.tick_params(colors='white')
            self.chart_ax.yaxis.label.set_color('white')
            
            self.chart_canvas.draw()
            
            self.log_message(f"Chart loaded for {symbol}", 'INFO')
            
        except Exception as e:
            self.log_message(f"Chart loading failed for {symbol}: {str(e)}", 'ERROR')
    
    def get_instrument_token(self, symbol):
        """Get instrument token for symbol"""
        if self.instruments is not None:
            # Try NSE first
            instrument = self.instruments[
                (self.instruments['tradingsymbol'] == symbol) & 
                (self.instruments['exchange'] == 'NSE')
            ]
            if not instrument.empty:
                return instrument.iloc[0]['instrument_token']
            
            # Try NFO if not found in NSE
            instrument = self.instruments[
                (self.instruments['tradingsymbol'] == symbol) & 
                (self.instruments['exchange'] == 'NFO')
            ]
            if not instrument.empty:
                return instrument.iloc[0]['instrument_token']
        return None
    
    def log_message(self, message, level='INFO'):
        """Add message to log with color coding"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}\n"
        
        self.log_text.insert(tk.END, log_entry, level)
        self.log_text.see(tk.END)
        
        # Also print to console with colors
        color_map = {
            'SUCCESS': Fore.GREEN,
            'ERROR': Fore.RED,
            'INFO': Fore.CYAN,
            'WARNING': Fore.YELLOW,
            'TOKEN': Fore.MAGENTA,
            'P&L': Fore.ORANGE
        }
        print(f"{color_map.get(level, '')}[{timestamp}] {level}: {message}{Style.RESET_ALL}")
    
    def on_closing(self):
        """Handle application closing"""
        self.stop_real_time()
        self.root.destroy()

def main():
    """Main application entry point"""
    root = tk.Tk()
    app = ColorfulTradingTool(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Configure treeview styles
    style = ttk.Style()
    style.configure("Treeview", background=app.colors['panel_bg'], 
                   fieldbackground=app.colors['panel_bg'], foreground=app.colors['text_light'])
    style.configure("Treeview.Heading", background=app.colors['neutral'], 
                   foreground='white', font=('Arial', 10, 'bold'))
    
    # Configure tag colors for treeview
    app.watchlist_tree.tag_configure('profit', background='#d4edda', foreground='#155724')
    app.watchlist_tree.tag_configure('loss', background='#f8d7da', foreground='#721c24')
    app.watchlist_tree.tag_configure('neutral', background='#d1ecf1', foreground='#0c5460')
    
    app.holdings_tree.tag_configure('profit', background='#d4edda', foreground='#155724')
    app.holdings_tree.tag_configure('loss', background='#f8d7da', foreground='#721c24')
    
    app.positions_tree.tag_configure('profit', background='#d4edda', foreground='#155724')
    app.positions_tree.tag_configure('loss', background='#f8d7da', foreground='#721c24')
    
    root.mainloop()

if __name__ == "__main__":
    main()