# zerodha_trading_gui.py - Fixed Version
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import threading
import queue
import time
import schedule
import configparser
from datetime import datetime, timedelta
import pandas as pd
import pyotp
import webbrowser
import requests
from urllib.parse import urlparse, parse_qs
import os
import logging
from kiteconnect import KiteConnect, KiteTicker
import pytz

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha Trading Dashboard v2.0")
        self.root.geometry("1600x900")
        
        # Set icon if available
        try:
            self.root.iconbitmap('icon.ico')
        except:
            pass
        
        # Initialize variables
        self.kite = None
        self.kws = None
        self.access_token = None
        self.is_connected = False
        self.instruments = []
        self.subscribed_tokens = set()
        self.live_data = {}
        self.positions_data = {}
        self.orders_data = {}
        self.totp_secret = None
        self.user_id = None
        self.user_password = None
        self.auto_login_enabled = False
        self.profit_targets = {}
        self.active_monitors = {}
        
        # API credentials (should be in config file in production)
        self.api_key = ""
        self.api_secret = ""
        
        # Create queue for thread-safe GUI updates
        self.gui_queue = queue.Queue()
        
        # Setup GUI
        self.setup_ui()
        
        # Load config if exists
        self.load_config()
        
        # Check for existing access token
        self.load_access_token()
        
        # Start queue processor
        self.process_queue()
        
        # Start background tasks
        self.start_background_tasks()
    
    def setup_ui(self):
        """Setup the main user interface"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create all tabs
        self.create_login_tab()
        self.create_dashboard_tab()
        self.create_futures_tab()
        self.create_order_tab()
        self.create_advanced_order_tab()
        self.create_positions_tab()  # Fixed version
        self.create_portfolio_tab()
        
        # Initially disable all tabs except login
        for i in range(1, self.notebook.index("end")):
            self.notebook.tab(i, state="disabled")
        
        # Status bar
        self.status_bar = tk.Label(self.root, text="Not Connected", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_login_tab(self):
        """Create login tab with auto login capabilities"""
        self.login_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.login_tab, text="🔐 Login")
        
        # Main container
        main_container = ttk.Frame(self.login_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Left frame - Manual Login
        left_frame = ttk.LabelFrame(main_container, text="Manual Login", padding=15)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        ttk.Label(left_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.api_key_var = tk.StringVar()
        api_entry = ttk.Entry(left_frame, textvariable=self.api_key_var, width=40)
        api_entry.grid(row=0, column=1, pady=5, padx=(5, 0))
        
        ttk.Label(left_frame, text="API Secret:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.api_secret_var = tk.StringVar()
        secret_entry = ttk.Entry(left_frame, textvariable=self.api_secret_var, width=40, show="*")
        secret_entry.grid(row=1, column=1, pady=5, padx=(5, 0))
        
        ttk.Label(left_frame, text="Request Token:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.request_token_var = tk.StringVar()
        ttk.Entry(left_frame, textvariable=self.request_token_var, width=40).grid(row=2, column=1, pady=5, padx=(5, 0))
        
        # Manual login buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        
        ttk.Button(btn_frame, text="Generate Login URL", 
                  command=self.generate_login_url, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Login with Token", 
                  command=self.login_with_token, width=20).pack(side=tk.LEFT, padx=5)
        
        # Right frame - Auto Login
        right_frame = ttk.LabelFrame(main_container, text="Auto Login Setup", padding=15)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        ttk.Label(right_frame, text="User ID:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.user_id_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.user_id_var, width=35).grid(row=0, column=1, pady=5, padx=(5, 0))
        
        ttk.Label(right_frame, text="Password:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.password_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.password_var, width=35, show="*").grid(row=1, column=1, pady=5, padx=(5, 0))
        
        ttk.Label(right_frame, text="TOTP Secret:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.totp_secret_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.totp_secret_var, width=35).grid(row=2, column=1, pady=5, padx=(5, 0))
        
        # Info about TOTP
        ttk.Label(right_frame, text="Note: Get TOTP secret from Zerodha security settings", 
                 font=('Arial', 8), foreground='gray').grid(row=3, column=0, columnspan=2, pady=(5, 15))
        
        # Auto login buttons
        auto_btn_frame = ttk.Frame(right_frame)
        auto_btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(auto_btn_frame, text="🔐 Auto Login", 
                  command=self.auto_login, width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(auto_btn_frame, text="💾 Save Config", 
                  command=self.save_config, width=25).pack(side=tk.LEFT, padx=5)
        
        # Login status
        status_frame = ttk.Frame(main_container)
        status_frame.pack(fill=tk.X, pady=(20, 0))
        
        self.login_status_var = tk.StringVar(value="Status: Not logged in")
        ttk.Label(status_frame, textvariable=self.login_status_var, 
                 font=('Arial', 10, 'bold')).pack()
    
    def create_dashboard_tab(self):
        """Create main dashboard tab"""
        self.dashboard_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.dashboard_tab, text="📊 Dashboard")
        
        # Main container with paned window
        main_paned = ttk.PanedWindow(self.dashboard_tab, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - Watchlist
        left_panel = ttk.Frame(main_paned)
        main_paned.add(left_panel, weight=1)
        
        # Watchlist frame
        watchlist_frame = ttk.LabelFrame(left_panel, text="📈 Watchlist", padding=10)
        watchlist_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create watchlist treeview
        columns = ("Symbol", "LTP", "Change", "Change %", "Volume", "Time")
        self.watchlist_tree = ttk.Treeview(watchlist_frame, columns=columns, show="headings", height=20)
        
        for col in columns:
            self.watchlist_tree.heading(col, text=col)
            self.watchlist_tree.column(col, width=100, anchor=tk.CENTER)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(watchlist_frame, orient=tk.VERTICAL, command=self.watchlist_tree.yview)
        self.watchlist_tree.configure(yscrollcommand=scrollbar.set)
        
        self.watchlist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Add to watchlist controls
        add_frame = ttk.Frame(left_panel)
        add_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        ttk.Label(add_frame, text="Add Symbol:").pack(side=tk.LEFT, padx=(0, 5))
        self.watchlist_symbol_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.watchlist_symbol_var, width=20).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(add_frame, text="Add", command=self.add_to_watchlist).pack(side=tk.LEFT)
        
        # Right panel - Orders and Positions
        right_panel = ttk.Frame(main_paned)
        main_paned.add(right_panel, weight=1)
        
        # Recent orders frame
        orders_frame = ttk.LabelFrame(right_panel, text="📋 Recent Orders", padding=10)
        orders_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ("Time", "Symbol", "Type", "Qty", "Price", "Status")
        self.orders_tree = ttk.Treeview(orders_frame, columns=columns, show="headings", height=10)
        
        for col in columns:
            self.orders_tree.heading(col, text=col)
            self.orders_tree.column(col, width=80)
        
        orders_scrollbar = ttk.Scrollbar(orders_frame, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=orders_scrollbar.set)
        
        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        orders_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Positions frame - FIXED VERSION
        positions_frame = ttk.LabelFrame(right_panel, text="💰 Current Positions", padding=10)
        positions_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 5))
        
        # Use simple column names
        self.positions_tree_dash = ttk.Treeview(positions_frame,
                                              columns=("col1", "col2", "col3", "col4", "col5", "col6"),
                                              show="headings",
                                              height=10)
        
        # Set headings with display text
        self.positions_tree_dash.heading("col1", text="Symbol")
        self.positions_tree_dash.heading("col2", text="Net Qty")
        self.positions_tree_dash.heading("col3", text="Avg Price")
        self.positions_tree_dash.heading("col4", text="LTP")
        self.positions_tree_dash.heading("col5", text="MTM")
        self.positions_tree_dash.heading("col6", text="P&L")
        
        # Set column widths
        self.positions_tree_dash.column("col1", width=80, anchor=tk.CENTER)
        self.positions_tree_dash.column("col2", width=60, anchor=tk.CENTER)
        self.positions_tree_dash.column("col3", width=70, anchor=tk.CENTER)
        self.positions_tree_dash.column("col4", width=70, anchor=tk.CENTER)
        self.positions_tree_dash.column("col5", width=70, anchor=tk.CENTER)
        self.positions_tree_dash.column("col6", width=70, anchor=tk.CENTER)
        
        positions_scrollbar = ttk.Scrollbar(positions_frame, orient=tk.VERTICAL, command=self.positions_tree_dash.yview)
        self.positions_tree_dash.configure(yscrollcommand=positions_scrollbar.set)
        
        self.positions_tree_dash.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        positions_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Control buttons
        control_frame = ttk.Frame(self.dashboard_tab)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(control_frame, text="🔄 Refresh All", 
                  command=self.refresh_all_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="📊 Update P&L", 
                  command=self.update_pnl_display).pack(side=tk.LEFT, padx=5)
    
    def create_futures_tab(self):
        """Create natural gas futures tab with calendar spread"""
        self.futures_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.futures_tab, text="⛽ Natural Gas")
        
        # Main container
        main_container = ttk.Frame(self.futures_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top frame - Futures table
        futures_frame = ttk.LabelFrame(main_container, text="Natural Gas Futures Contracts", padding=10)
        futures_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create futures treeview
        columns = ("Symbol", "Expiry", "Strike", "LTP", "OI", "Volume", "Change %")
        self.futures_tree = ttk.Treeview(futures_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.futures_tree.heading(col, text=col)
            self.futures_tree.column(col, width=100, anchor=tk.CENTER)
        
        # Add scrollbars
        v_scrollbar = ttk.Scrollbar(futures_frame, orient=tk.VERTICAL, command=self.futures_tree.yview)
        h_scrollbar = ttk.Scrollbar(futures_frame, orient=tk.HORIZONTAL, command=self.futures_tree.xview)
        self.futures_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.futures_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        futures_frame.grid_rowconfigure(0, weight=1)
        futures_frame.grid_columnconfigure(0, weight=1)
        
        # Bind double click for selection
        self.futures_tree.bind('<Double-1>', self.on_future_selected)
        
        # Bottom frame - Calendar spread calculator
        spread_frame = ttk.LabelFrame(main_container, text="📅 Calendar Spread Calculator", padding=10)
        spread_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Spread inputs
        input_frame = ttk.Frame(spread_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="Near Month:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.near_month_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.near_month_var, state='readonly', width=20).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Far Month:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.far_month_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.far_month_var, state='readonly', width=20).grid(row=0, column=3, padx=5, pady=5)
        
        # Spread results
        result_frame = ttk.Frame(spread_frame)
        result_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(result_frame, text="Spread Value:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.spread_value_var = tk.StringVar(value="0.00")
        ttk.Entry(result_frame, textvariable=self.spread_value_var, state='readonly', width=15, 
                 font=('Arial', 10, 'bold')).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(result_frame, text="Percentage:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.spread_percent_var = tk.StringVar(value="0.00%")
        ttk.Entry(result_frame, textvariable=self.spread_percent_var, state='readonly', width=15,
                 font=('Arial', 10, 'bold')).grid(row=0, column=3, padx=5, pady=5)
        
        # Smile threshold
        threshold_frame = ttk.Frame(spread_frame)
        threshold_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(threshold_frame, text="Smile Threshold (%):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.smile_threshold = tk.DoubleVar(value=5.0)
        ttk.Entry(threshold_frame, textvariable=self.smile_threshold, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(spread_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(button_frame, text="📊 Calculate Spread", 
                  command=self.calculate_spread).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔄 Refresh Futures", 
                  command=self.refresh_futures_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🎯 Quick Trade", 
                  command=self.quick_trade_selected).pack(side=tk.LEFT, padx=5)
    
    def create_order_tab(self):
        """Create order placement tab"""
        self.order_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.order_tab, text="📈 Place Order")
        
        # Main container
        main_container = ttk.Frame(self.order_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Order form frame
        form_frame = ttk.LabelFrame(main_container, text="Order Details", padding=15)
        form_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Form fields
        fields = [
            ("Trading Symbol:", "symbol_var", True),
            ("Transaction Type:", "transaction_var", False),
            ("Order Type:", "order_type_var", False),
            ("Quantity:", "quantity_var", True),
            ("Price:", "price_var", True),
            ("Product:", "product_var", False),
            ("Validity:", "validity_var", False),
            ("Disclosed Qty:", "disclosed_qty_var", True)
        ]
        
        self.order_vars = {}
        
        for i, (label, var_name, is_entry) in enumerate(fields):
            row = i % 5
            col = (i // 5) * 2
            
            ttk.Label(form_frame, text=label).grid(row=row, column=col, sticky=tk.W, pady=5, padx=(10, 5))
            
            if label == "Transaction Type:":
                var = tk.StringVar(value="BUY")
                combo = ttk.Combobox(form_frame, textvariable=var, 
                                    values=["BUY", "SELL"], width=25, state="readonly")
                combo.grid(row=row, column=col+1, pady=5, sticky=tk.W)
            elif label == "Order Type:":
                var = tk.StringVar(value="MARKET")
                combo = ttk.Combobox(form_frame, textvariable=var, 
                                    values=["MARKET", "LIMIT", "SL", "SL-M"], width=25, state="readonly")
                combo.grid(row=row, column=col+1, pady=5, sticky=tk.W)
            elif label == "Product:":
                var = tk.StringVar(value="MIS")
                combo = ttk.Combobox(form_frame, textvariable=var, 
                                    values=["CNC", "MIS", "NRML"], width=25, state="readonly")
                combo.grid(row=row, column=col+1, pady=5, sticky=tk.W)
            elif label == "Validity:":
                var = tk.StringVar(value="DAY")
                combo = ttk.Combobox(form_frame, textvariable=var, 
                                    values=["DAY", "IOC"], width=25, state="readonly")
                combo.grid(row=row, column=col+1, pady=5, sticky=tk.W)
            elif is_entry:
                var = tk.StringVar()
                ttk.Entry(form_frame, textvariable=var, width=28).grid(row=row, column=col+1, pady=5, sticky=tk.W)
            else:
                var = tk.StringVar(value="0")
                ttk.Entry(form_frame, textvariable=var, width=28).grid(row=row, column=col+1, pady=5, sticky=tk.W)
            
            self.order_vars[var_name] = var
        
        # Quick action buttons
        quick_frame = ttk.Frame(form_frame)
        quick_frame.grid(row=5, column=0, columnspan=4, pady=15)
        
        ttk.Button(quick_frame, text="📈 Get Quote", 
                  command=self.get_quote, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_frame, text="💰 Calculate Margin", 
                  command=self.calculate_margin, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(quick_frame, text="📊 View Chart", 
                  command=self.view_chart, width=15).pack(side=tk.LEFT, padx=5)
        
        # Order buttons
        button_frame = ttk.Frame(main_container)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(button_frame, text="✅ Place Order", 
                  command=self.place_order, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔄 Modify Order", 
                  command=self.modify_order).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="❌ Cancel Order", 
                  command=self.cancel_order).pack(side=tk.LEFT, padx=5)
        
        # Create an accent style for important buttons
        style = ttk.Style()
        style.configure("Accent.TButton", foreground="white", background="#0078D4")
        
        # Order log
        log_frame = ttk.LabelFrame(main_container, text="Order Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.order_log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.order_log_text.pack(fill=tk.BOTH, expand=True)
        
        # Clear log button
        ttk.Button(log_frame, text="Clear Log", 
                  command=lambda: self.order_log_text.delete(1.0, tk.END)).pack(anchor=tk.E, pady=5)
    
    def create_advanced_order_tab(self):
        """Create advanced order tab with basket orders and auto exit"""
        self.advanced_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.advanced_tab, text="🚀 Advanced")
        
        # Main container
        main_container = ttk.Frame(self.advanced_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Basket order frame
        basket_frame = ttk.LabelFrame(main_container, text="🛒 Basket Orders", padding=15)
        basket_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Entry frame
        entry_frame = ttk.Frame(basket_frame)
        entry_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(entry_frame, text="Symbol:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.basket_symbol_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.basket_symbol_var, width=20).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(entry_frame, text="Quantity:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.basket_qty_var = tk.StringVar(value="1")
        ttk.Entry(entry_frame, textvariable=self.basket_qty_var, width=15).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(entry_frame, text="Entry Price:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.basket_entry_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.basket_entry_var, width=15).grid(row=0, column=5, padx=5, pady=5)
        
        # Basket buttons
        basket_btn_frame = ttk.Frame(basket_frame)
        basket_btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(basket_btn_frame, text="📥 Buy & Sell Together", 
                  command=lambda: self.place_basket_order("BOTH"), width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(basket_btn_frame, text="🚪 Exit Together", 
                  command=self.exit_together, width=25).pack(side=tk.LEFT, padx=5)
        
        # Profit target frame
        target_frame = ttk.LabelFrame(main_container, text="🎯 Profit Target & Auto Exit", padding=15)
        target_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Target inputs
        target_input_frame = ttk.Frame(target_frame)
        target_input_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(target_input_frame, text="Profit Target (%):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.profit_target_var = tk.StringVar(value="2.0")
        ttk.Entry(target_input_frame, textvariable=self.profit_target_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(target_input_frame, text="Stop Loss (%):").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.stop_loss_var = tk.StringVar(value="1.0")
        ttk.Entry(target_input_frame, textvariable=self.stop_loss_var, width=10).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(target_input_frame, text="Trailing SL (%):").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.trailing_sl_var = tk.StringVar(value="0.5")
        ttk.Entry(target_input_frame, textvariable=self.trailing_sl_var, width=10).grid(row=0, column=5, padx=5, pady=5)
        
        # Auto exit controls
        auto_frame = ttk.Frame(target_frame)
        auto_frame.pack(fill=tk.X, pady=10)
        
        self.auto_exit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(auto_frame, text="Enable Auto Exit", 
                       variable=self.auto_exit_var).pack(side=tk.LEFT, padx=5)
        
        self.oco_order_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto_frame, text="Use OCO Orders", 
                       variable=self.oco_order_var).pack(side=tk.LEFT, padx=5)
        
        self.trailing_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto_frame, text="Trailing Stop Loss", 
                       variable=self.trailing_var).pack(side=tk.LEFT, padx=5)
        
        # P&L display frame
        pnl_frame = ttk.LabelFrame(main_container, text="💰 P&L Calculator", padding=15)
        pnl_frame.pack(fill=tk.BOTH, expand=True)
        
        # P&L inputs
        pnl_input_frame = ttk.Frame(pnl_frame)
        pnl_input_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(pnl_input_frame, text="Entry Price:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.pnl_entry_var = tk.StringVar()
        ttk.Entry(pnl_input_frame, textvariable=self.pnl_entry_var, width=15).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(pnl_input_frame, text="Current Price:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.pnl_current_var = tk.StringVar()
        ttk.Entry(pnl_input_frame, textvariable=self.pnl_current_var, width=15).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(pnl_input_frame, text="Quantity:").grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        self.pnl_qty_var = tk.StringVar(value="1")
        ttk.Entry(pnl_input_frame, textvariable=self.pnl_qty_var, width=15).grid(row=0, column=5, padx=5, pady=5)
        
        # P&L results
        pnl_result_frame = ttk.Frame(pnl_frame)
        pnl_result_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(pnl_result_frame, text="P&L Amount:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.pnl_amount_var = tk.StringVar(value="₹0.00")
        ttk.Label(pnl_result_frame, textvariable=self.pnl_amount_var, 
                 font=('Arial', 12, 'bold')).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        ttk.Label(pnl_result_frame, text="P&L Percentage:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.pnl_percent_var = tk.StringVar(value="0.00%")
        ttk.Label(pnl_result_frame, textvariable=self.pnl_percent_var, 
                 font=('Arial', 12, 'bold')).grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        
        # P&L buttons
        pnl_btn_frame = ttk.Frame(pnl_frame)
        pnl_btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(pnl_btn_frame, text="📊 Calculate P&L", 
                  command=self.calculate_pnl).pack(side=tk.LEFT, padx=5)
        ttk.Button(pnl_btn_frame, text="🔄 Update Prices", 
                  command=self.update_pnl_prices).pack(side=tk.LEFT, padx=5)
        ttk.Button(pnl_btn_frame, text="💾 Save P&L Report", 
                  command=self.save_pnl_report).pack(side=tk.LEFT, padx=5)
        
        # Active monitors frame
        monitor_frame = ttk.LabelFrame(main_container, text="👁️ Active Monitors", padding=10)
        monitor_frame.pack(fill=tk.BOTH, expand=True, pady=(15, 0))
        
        columns = ("Symbol", "Entry", "Target", "Current", "P&L", "Status")
        self.monitor_tree = ttk.Treeview(monitor_frame, columns=columns, show="headings", height=5)
        
        for col in columns:
            self.monitor_tree.heading(col, text=col)
            self.monitor_tree.column(col, width=80)
        
        monitor_scrollbar = ttk.Scrollbar(monitor_frame, orient=tk.VERTICAL, command=self.monitor_tree.yview)
        self.monitor_tree.configure(yscrollcommand=monitor_scrollbar.set)
        
        self.monitor_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        monitor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Monitor controls
        monitor_btn_frame = ttk.Frame(monitor_frame)
        monitor_btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(monitor_btn_frame, text="🛑 Stop Monitor", 
                  command=self.stop_monitor).pack(side=tk.LEFT, padx=5)
        ttk.Button(monitor_btn_frame, text="🔄 Refresh", 
                  command=self.refresh_monitors).pack(side=tk.LEFT, padx=5)
    
    def create_positions_tab(self):
        """Create positions management tab - FIXED VERSION"""
        self.positions_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.positions_tab, text="💼 Positions")
        
        # Main container
        main_container = ttk.Frame(self.positions_tab)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Positions treeview with correct column identifiers
        self.positions_tree = ttk.Treeview(main_container,
                                          columns=("col1", "col2", "col3", "col4", "col5", "col6"),
                                          show="headings",
                                          height=20)
        
        # Set headings with display text
        self.positions_tree.heading("col1", text="Symbol")
        self.positions_tree.heading("col2", text="Net Qty")
        self.positions_tree.heading("col3", text="Avg Price")
        self.positions_tree.heading("col4", text="LTP")
        self.positions_tree.heading("col5", text="MTM")
        self.positions_tree.heading("col6", text="P&L")
        
        # Set column widths
        self.positions_tree.column("col1", width=120, anchor=tk.CENTER)
        self.positions_tree.column("col2", width=80, anchor=tk.CENTER)
        self.positions_tree.column("col3", width=80, anchor=tk.CENTER)
        self.positions_tree.column("col4", width=80, anchor=tk.CENTER)
        self.positions_tree.column("col5", width=80, anchor=tk.CENTER)
        self.positions_tree.column("col6", width=100, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(main_container, orient=tk.VERTICAL, command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=scrollbar.set)
        
        self.positions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Control panel
        control_frame = ttk.Frame(main_container)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        ttk.Label(control_frame, text="Position Actions", font=('Arial', 10, 'bold')).pack(pady=10)
        
        ttk.Button(control_frame, text="🔄 Refresh Positions", 
                  command=self.refresh_positions, width=20).pack(pady=5, padx=10)
        ttk.Button(control_frame, text="🚪 Square Off All", 
                  command=self.square_off_all, width=20).pack(pady=5, padx=10)
        ttk.Button(control_frame, text="📊 View Details", 
                  command=self.view_position_details, width=20).pack(pady=5, padx=10)
        ttk.Button(control_frame, text="📈 View Chart", 
                  command=self.view_position_chart, width=20).pack(pady=5, padx=10)
        ttk.Button(control_frame, text="📋 Export to CSV", 
                  command=self.export_positions_csv, width=20).pack(pady=5, padx=10)
        
        # Summary frame
        summary_frame = ttk.LabelFrame(control_frame, text="Summary", padding=10)
        summary_frame.pack(pady=10, padx=10, fill=tk.X)
        
        self.total_investment_var = tk.StringVar(value="₹0.00")
        self.total_pnl_var = tk.StringVar(value="₹0.00")
        self.total_pnl_percent_var = tk.StringVar(value="0.00%")
        
        ttk.Label(summary_frame, text="Total Investment:").pack(anchor=tk.W)
        ttk.Label(summary_frame, textvariable=self.total_investment_var, 
                 font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        
        ttk.Label(summary_frame, text="Total P&L:").pack(anchor=tk.W)
        ttk.Label(summary_frame, textvariable=self.total_pnl_var, 
                 font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        
        ttk.Label(summary_frame, text="P&L %:").pack(anchor=tk.W)
        ttk.Label(summary_frame, textvariable=self.total_pnl_percent_var, 
                 font=('Arial', 10, 'bold')).pack(anchor=tk.W)
    
    def create_portfolio_tab(self):
        """Create portfolio overview tab"""
        self.portfolio_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.portfolio_tab, text="📊 Portfolio")
        
        # Main container with paned window
        main_paned = ttk.PanedWindow(self.portfolio_tab, orient=tk.VERTICAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top frame - Portfolio metrics
        metrics_frame = ttk.LabelFrame(main_paned, text="Portfolio Metrics", padding=15)
        main_paned.add(metrics_frame, weight=1)
        
        # Create metrics grid
        metrics = [
            ("Total Holdings Value:", "total_holdings_var", "₹0.00"),
            ("Total Profit/Loss:", "total_pnl_var", "₹0.00"),
            ("Available Margin:", "available_margin_var", "₹0.00"),
            ("Used Margin:", "used_margin_var", "₹0.00"),
            ("Total Collateral:", "total_collateral_var", "₹0.00"),
            ("Day's P&L:", "day_pnl_var", "₹0.00"),
            ("Realized P&L:", "realized_pnl_var", "₹0.00"),
            ("Unrealized P&L:", "unrealized_pnl_var", "₹0.00")
        ]
        
        self.metrics_vars = {}
        
        for i, (label, var_name, default) in enumerate(metrics):
            row = i // 2
            col = (i % 2) * 2
            
            ttk.Label(metrics_frame, text=label, font=('Arial', 10)).grid(
                row=row, column=col, sticky=tk.W, pady=10, padx=10)
            
            var = tk.StringVar(value=default)
            ttk.Label(metrics_frame, textvariable=var, 
                     font=('Arial', 10, 'bold')).grid(
                row=row, column=col+1, sticky=tk.W, pady=10, padx=(0, 20))
            
            self.metrics_vars[var_name] = var
        
        # Bottom frame - Historical P&L
        historical_frame = ttk.LabelFrame(main_paned, text="Historical P&L", padding=10)
        main_paned.add(historical_frame, weight=2)
        
        self.historical_tree = ttk.Treeview(historical_frame,
                                           columns=("Date", "Realized P&L", "Unrealized P&L", "Total P&L"),
                                           show="headings", height=10)
        
        for col in ("Date", "Realized P&L", "Unrealized P&L", "Total P&L"):
            self.historical_tree.heading(col, text=col)
            self.historical_tree.column(col, width=150, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(historical_frame, orient=tk.VERTICAL, command=self.historical_tree.yview)
        self.historical_tree.configure(yscrollcommand=scrollbar.set)
        
        self.historical_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Control buttons
        control_frame = ttk.Frame(self.portfolio_tab)
        control_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(control_frame, text="🔄 Refresh Portfolio", 
                  command=self.refresh_portfolio).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="📋 Generate Report", 
                  command=self.generate_portfolio_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="📈 View Analytics", 
                  command=self.view_portfolio_analytics).pack(side=tk.LEFT, padx=5)
    
    # ==================== CORE FUNCTIONALITY ====================
    
    def generate_login_url(self):
        """Generate login URL and open in browser"""
        try:
            api_key = self.api_key_var.get()
            if not api_key:
                messagebox.showerror("Error", "Please enter API Key")
                return
            
            self.kite = KiteConnect(api_key=api_key)
            login_url = self.kite.login_url()
            
            webbrowser.open(login_url)
            
            messagebox.showinfo("Login URL", 
                              "Login URL opened in browser.\n" +
                              "After login, copy the request token from URL and paste it above.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate login URL: {str(e)}")
    
    def login_with_token(self):
        """Login with request token"""
        try:
            request_token = self.request_token_var.get()
            api_key = self.api_key_var.get()
            api_secret = self.api_secret_var.get()
            
            if not all([request_token, api_key, api_secret]):
                messagebox.showerror("Error", "Please fill all fields")
                return
            
            self.kite = KiteConnect(api_key=api_key)
            data = self.kite.generate_session(request_token, api_secret=api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            
            self.is_connected = True
            self.login_status_var.set(f"Logged in as: {data['user_name']}")
            self.status_bar.config(text=f"Connected: {data['user_name']}")
            
            # Enable all tabs
            for i in range(1, self.notebook.index("end")):
                self.notebook.tab(i, state="normal")
            
            # Switch to dashboard
            self.notebook.select(1)
            
            # Save token
            self.save_access_token()
            
            # Load initial data
            threading.Thread(target=self.load_initial_data, daemon=True).start()
            
            messagebox.showinfo("Success", "Login successful!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {str(e)}")
    
    def auto_login(self):
        """Auto login with TOTP"""
        try:
            self.user_id = self.user_id_var.get()
            self.user_password = self.password_var.get()
            self.totp_secret = self.totp_secret_var.get()
            api_key = self.api_key_var.get()
            api_secret = self.api_secret_var.get()
            
            if not all([self.user_id, self.user_password, self.totp_secret, api_key, api_secret]):
                messagebox.showerror("Error", "Please fill all auto login fields")
                return
            
            # Create session
            session = requests.Session()
            
            # Get login page
            login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
            session.get(login_url)
            
            # Login with credentials
            login_data = {
                "user_id": self.user_id,
                "password": self.user_password
            }
            login_response = session.post("https://kite.zerodha.com/api/login", data=login_data)
            login_json = login_response.json()
            
            if "data" not in login_json:
                raise Exception("Login failed: Invalid credentials")
            
            request_id = login_json["data"]["request_id"]
            
            # Generate TOTP
            totp = pyotp.TOTP(self.totp_secret).now()
            
            # Submit 2FA
            twofa_data = {
                "user_id": self.user_id,
                "request_id": request_id,
                "twofa_value": totp
            }
            twofa_response = session.post("https://kite.zerodha.com/api/twofa", data=twofa_data)
            
            if twofa_response.json().get('status') != 'success':
                raise Exception("2FA failed")
            
            # Get request token
            final_response = session.get(login_url, allow_redirects=True)
            
            # Parse request token from URL
            parsed_url = urlparse(final_response.url)
            query_params = parse_qs(parsed_url.query)
            
            if 'request_token' not in query_params:
                raise Exception("Request token not found")
            
            request_token = query_params['request_token'][0]
            
            # Generate session with KiteConnect
            self.kite = KiteConnect(api_key=api_key)
            data = self.kite.generate_session(request_token, api_secret=api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            
            self.is_connected = True
            self.login_status_var.set(f"Auto logged in as: {data['user_name']}")
            self.status_bar.config(text=f"Connected: {data['user_name']}")
            
            # Enable all tabs
            for i in range(1, self.notebook.index("end")):
                self.notebook.tab(i, state="normal")
            
            # Switch to dashboard
            self.notebook.select(1)
            
            # Save config
            self.save_config()
            self.save_access_token()
            
            # Load initial data
            threading.Thread(target=self.load_initial_data, daemon=True).start()
            
            messagebox.showinfo("Success", "Auto login successful!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Auto login failed: {str(e)}")
            logger.error(f"Auto login error: {e}")
    
    def load_config(self):
        """Load configuration from file"""
        try:
            if os.path.exists('config.ini'):
                config = configparser.ConfigParser()
                config.read('config.ini')
                
                if 'ZERODHA' in config:
                    self.api_key_var.set(config['ZERODHA'].get('api_key', ''))
                    self.api_secret_var.set(config['ZERODHA'].get('api_secret', ''))
                    self.user_id_var.set(config['ZERODHA'].get('user_id', ''))
                    self.password_var.set(config['ZERODHA'].get('password', ''))
                    self.totp_secret_var.set(config['ZERODHA'].get('totp', ''))
                    
                    logger.info("Configuration loaded from config.ini")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config = configparser.ConfigParser()
            config['ZERODHA'] = {
                'api_key': self.api_key_var.get(),
                'api_secret': self.api_secret_var.get(),
                'user_id': self.user_id_var.get(),
                'password': self.password_var.get(),
                'totp': self.totp_secret_var.get()
            }
            
            with open('config.ini', 'w') as configfile:
                config.write(configfile)
            
            messagebox.showinfo("Success", "Configuration saved to config.ini")
            logger.info("Configuration saved")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {str(e)}")
    
    def load_access_token(self):
        """Load access token from file"""
        try:
            if os.path.exists('access_token.json'):
                with open('access_token.json', 'r') as f:
                    token_data = json.load(f)
                
                if 'access_token' in token_data and 'api_key' in token_data:
                    self.access_token = token_data['access_token']
                    api_key = token_data['api_key']
                    
                    self.kite = KiteConnect(api_key=api_key)
                    self.kite.set_access_token(self.access_token)
                    
                    # Test connection
                    profile = self.kite.profile()
                    self.is_connected = True
                    
                    self.login_status_var.set(f"Logged in as: {profile['user_name']}")
                    self.status_bar.config(text=f"Connected: {profile['user_name']}")
                    
                    # Enable tabs
                    for i in range(1, self.notebook.index("end")):
                        self.notebook.tab(i, state="normal")
                    
                    # Load data
                    threading.Thread(target=self.load_initial_data, daemon=True).start()
                    
                    logger.info("Loaded access token from file")
                    
        except Exception as e:
            logger.warning(f"Could not load access token: {e}")
    
    def save_access_token(self):
        """Save access token to file"""
        try:
            if self.access_token and hasattr(self.kite, 'api_key'):
                token_data = {
                    'access_token': self.access_token,
                    'api_key': self.kite.api_key,
                    'timestamp': datetime.now().isoformat()
                }
                
                with open('access_token.json', 'w') as f:
                    json.dump(token_data, f)
                
                logger.info("Access token saved")
        except Exception as e:
            logger.error(f"Error saving access token: {e}")
    
    def load_initial_data(self):
        """Load initial data after login"""
        if not self.is_connected:
            return
        
        try:
            # Load instruments
            self.instruments = self.kite.instruments()
            
            # Load holdings
            self.refresh_holdings()
            
            # Load positions - Fixed method
            self.refresh_positions()
            
            # Load portfolio
            self.refresh_portfolio()
            
            # Load orders
            self.load_recent_orders()
            
            # Load natural gas futures
            self.refresh_futures_data()
            
            # Update dashboard positions
            self.refresh_dashboard_positions()
            
            # Update status
            self.status_bar.config(text="Data loaded successfully")
            
        except Exception as e:
            self.gui_queue.put(("error", f"Failed to load initial data: {str(e)}"))
    
    def refresh_dashboard_positions(self):
        """Refresh positions on dashboard"""
        if not self.is_connected:
            return
        
        try:
            positions = self.kite.positions()
            
            # Clear dashboard positions tree
            for item in self.positions_tree_dash.get_children():
                self.positions_tree_dash.delete(item)
            
            # Populate dashboard positions
            for pos in positions['net']:
                if pos['quantity'] != 0:
                    color_tag = "green" if pos['pnl'] >= 0 else "red"
                    
                    self.positions_tree_dash.insert("", tk.END, values=(
                        pos['tradingsymbol'],
                        pos['quantity'],
                        f"{pos['average_price']:.2f}",
                        f"{pos['last_price']:.2f}",
                        f"{pos['m2m']:.2f}",
                        f"₹{pos['pnl']:+.2f}"
                    ), tags=(color_tag,))
            
            # Configure tags for dashboard
            self.positions_tree_dash.tag_configure("green", foreground="green")
            self.positions_tree_dash.tag_configure("red", foreground="red")
            
        except Exception as e:
            logger.error(f"Error refreshing dashboard positions: {e}")
    
    def refresh_futures_data(self):
        """Refresh natural gas futures data"""
        if not self.is_connected:
            return
        
        try:
            # Clear existing data
            for item in self.futures_tree.get_children():
                self.futures_tree.delete(item)
            
            # Filter natural gas futures
            ng_futures = []
            for inst in self.instruments:
                if (inst['exchange'] == 'NFO' and 
                    inst['instrument_type'] == 'FUT' and
                    'NATURALGAS' in inst['name'].upper()):
                    ng_futures.append(inst)
            
            # Sort by expiry
            ng_futures.sort(key=lambda x: x['expiry'])
            
            # Get quotes for all futures
            instruments_list = [f"NFO:{f['tradingsymbol']}" for f in ng_futures[:20]]  # Limit to 20
            
            if instruments_list:
                quotes = self.kite.quote(instruments_list)
                
                # Populate tree
                for future in ng_futures[:20]:
                    symbol = future['tradingsymbol']
                    quote_key = f"NFO:{symbol}"
                    
                    if quote_key in quotes:
                        quote = quotes[quote_key]
                        ltp = quote.get('last_price', 0)
                        oi = quote.get('oi', 0)
                        volume = quote.get('volume', 0)
                        
                        # Calculate change percentage
                        change_pct = 0
                        if 'ohlc' in quote and quote['ohlc']['close'] > 0:
                            prev_close = quote['ohlc']['close']
                            change_pct = ((ltp - prev_close) / prev_close) * 100
                        
                        # Color code based on change
                        color_tag = "green" if change_pct >= 0 else "red"
                        
                        item_id = self.futures_tree.insert("", tk.END, values=(
                            symbol,
                            future['expiry'].strftime('%d-%b-%Y'),
                            future.get('strike', 'N/A'),
                            f"{ltp:.2f}",
                            f"{oi:,}",
                            f"{volume:,}",
                            f"{change_pct:+.2f}%"
                        ))
                        
                        # Apply color tag
                        self.futures_tree.tag_configure("green", foreground="green")
                        self.futures_tree.tag_configure("red", foreground="red")
                        self.futures_tree.item(item_id, tags=(color_tag,))
            
            self.status_bar.config(text=f"Loaded {len(ng_futures[:20])} natural gas futures")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh futures: {str(e)}")
            logger.error(f"Futures refresh error: {e}")
    
    def on_future_selected(self, event):
        """Handle future selection from table"""
        selection = self.futures_tree.selection()
        if selection:
            item = self.futures_tree.item(selection[0])
            values = item['values']
            
            # Populate order form
            self.order_vars["symbol_var"].set(values[0])
            self.basket_symbol_var.set(values[0])
            
            # Set quantity based on lot size
            self.order_vars["quantity_var"].set("1250")  # Standard lot for NG
            
            # Set price from LTP
            price = float(values[3].replace(',', ''))
            self.order_vars["price_var"].set(f"{price:.2f}")
            self.basket_entry_var.set(f"{price:.2f}")
            self.pnl_entry_var.set(f"{price:.2f}")
            
            # Update current price for P&L
            self.pnl_current_var.set(f"{price:.2f}")
            
            # Switch to order tab
            self.notebook.select(3)  # Order tab
            
            # Update status
            self.status_bar.config(text=f"Selected: {values[0]}")
    
    def calculate_spread(self):
        """Calculate calendar spread between selected futures"""
        selection = self.futures_tree.selection()
        if len(selection) != 2:
            messagebox.showerror("Error", "Please select exactly two futures")
            return
        
        try:
            # Get selected items
            items = []
            for item_id in selection:
                item = self.futures_tree.item(item_id)
                items.append(item['values'])
            
            # Sort by expiry date
            items.sort(key=lambda x: datetime.strptime(x[1], '%d-%b-%Y'))
            
            # Extract prices
            near_price = float(items[0][3].replace(',', ''))
            far_price = float(items[1][3].replace(',', ''))
            
            # Calculate spread
            spread_value = far_price - near_price
            spread_percent = (spread_value / near_price) * 100
            
            # Update display
            self.near_month_var.set(items[0][0])
            self.far_month_var.set(items[1][0])
            self.spread_value_var.set(f"{spread_value:.2f}")
            self.spread_percent_var.set(f"{spread_percent:+.2f}%")
            
            # Check for smile threshold
            threshold = self.smile_threshold.get()
            if abs(spread_percent) >= threshold:
                self.show_smile_popup(spread_value, spread_percent)
            
            # Update status
            self.status_bar.config(text=f"Spread: {spread_value:.2f} ({spread_percent:+.2f}%)")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to calculate spread: {str(e)}")
    
    def show_smile_popup(self, spread_value, spread_percent):
        """Show big smile popup for significant spread"""
        popup = tk.Toplevel(self.root)
        popup.title("🎉 Calendar Spread Alert!")
        popup.geometry("500x400")
        popup.configure(bg="#FFFACD")  # Lemon Chiffon background
        
        # Center popup
        popup.transient(self.root)
        popup.grab_set()
        
        # Calculate position
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 250
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 200
        popup.geometry(f"+{x}+{y}")
        
        # Big smile emoji
        smile_label = tk.Label(popup, text="😊", font=('Arial', 100), bg="#FFFACD")
        smile_label.pack(pady=20)
        
        # Title
        title_label = tk.Label(popup, text="GREAT SPREAD OPPORTUNITY!", 
                              font=('Arial', 16, 'bold'), bg="#FFFACD", fg="#228B22")
        title_label.pack(pady=10)
        
        # Spread info
        info_frame = tk.Frame(popup, bg="#FFFACD")
        info_frame.pack(pady=20, padx=20)
        
        spread_text = f"Spread Value: {spread_value:.2f}\n"
        spread_text += f"Percentage: {spread_percent:+.2f}%\n\n"
        
        if spread_percent > 0:
            spread_text += "📈 Far month is trading at a PREMIUM!\n"
            spread_text += "Consider SELLING far month and BUYING near month."
            color = "#228B22"  # Forest green
        else:
            spread_text += "📉 Far month is trading at a DISCOUNT!\n"
            spread_text += "Consider BUYING far month and SELLING near month."
            color = "#DC143C"  # Crimson
        
        info_label = tk.Label(info_frame, text=spread_text, 
                             font=('Arial', 12), bg="#FFFACD", fg=color, justify=tk.LEFT)
        info_label.pack()
        
        # Close button with style
        button_frame = tk.Frame(popup, bg="#FFFACD")
        button_frame.pack(pady=20)
        
        close_button = tk.Button(button_frame, text="AWESOME! 🚀", 
                                font=('Arial', 12, 'bold'),
                                bg="#4CAF50", fg="white",
                                padx=20, pady=10,
                                command=popup.destroy)
        close_button.pack()
        
        # Auto close after 10 seconds
        popup.after(10000, popup.destroy)
    
    def place_basket_order(self, order_type="BOTH"):
        """Place buy and sell orders together"""
        if not self.is_connected:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            symbol = self.basket_symbol_var.get()
            quantity = int(self.basket_qty_var.get())
            entry_price = float(self.basket_entry_var.get())
            
            if not all([symbol, quantity > 0, entry_price > 0]):
                messagebox.showerror("Error", "Please enter valid symbol, quantity, and price")
                return
            
            order_ids = []
            
            # Place BUY order
            if order_type in ["BOTH", "BUY"]:
                buy_id = self.kite.place_order(
                    variety="regular",
                    exchange="NFO",
                    tradingsymbol=symbol,
                    transaction_type="BUY",
                    quantity=quantity,
                    price=entry_price,
                    product="MIS",
                    order_type="LIMIT"
                )
                order_ids.append(("BUY", buy_id))
            
            # Place SELL order
            if order_type in ["BOTH", "SELL"]:
                sell_id = self.kite.place_order(
                    variety="regular",
                    exchange="NFO",
                    tradingsymbol=symbol,
                    transaction_type="SELL",
                    quantity=quantity,
                    price=entry_price * 1.01,  # 1% higher
                    product="MIS",
                    order_type="LIMIT"
                )
                order_ids.append(("SELL", sell_id))
            
            # Log orders
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_msg = f"\n[{timestamp}] Basket Order Placed:\n"
            for order_type, order_id in order_ids:
                log_msg += f"  {order_type} Order ID: {order_id}\n"
            
            self.order_log_text.insert(tk.END, log_msg)
            self.order_log_text.see(tk.END)
            
            # Set up profit target monitoring if enabled
            if self.auto_exit_var.get() and order_type == "BOTH":
                target_percent = float(self.profit_target_var.get())
                stop_loss_percent = float(self.stop_loss_var.get())
                
                target_price = entry_price * (1 + target_percent / 100)
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
                
                # Store monitoring data
                monitor_id = f"{symbol}_{int(time.time())}"
                self.profit_targets[monitor_id] = {
                    'symbol': symbol,
                    'entry_price': entry_price,
                    'target_price': target_price,
                    'stop_loss_price': stop_loss_price,
                    'quantity': quantity,
                    'order_ids': [oid for _, oid in order_ids],
                    'entry_time': datetime.now(),
                    'trailing': self.trailing_var.get(),
                    'trailing_percent': float(self.trailing_sl_var.get())
                }
                
                # Add to monitor tree
                self.monitor_tree.insert("", tk.END, values=(
                    symbol,
                    f"{entry_price:.2f}",
                    f"{target_price:.2f}",
                    f"{entry_price:.2f}",
                    "₹0.00",
                    "Monitoring"
                ))
                
                # Start monitoring thread
                threading.Thread(
                    target=self.monitor_profit_target,
                    args=(monitor_id,),
                    daemon=True
                ).start()
                
                log_msg = f"  ⚡ Auto monitoring started\n"
                log_msg += f"  🎯 Target: {target_price:.2f} (+{target_percent}%)\n"
                log_msg += f"  🛑 Stop Loss: {stop_loss_price:.2f} (-{stop_loss_percent}%)\n"
                self.order_log_text.insert(tk.END, log_msg)
            
            messagebox.showinfo("Success", "Basket order placed successfully!")
            self.load_recent_orders()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to place basket order: {str(e)}")
            logger.error(f"Basket order error: {e}")
    
    def exit_together(self):
        """Exit all positions for selected symbol"""
        if not self.is_connected:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            symbol = self.basket_symbol_var.get()
            if not symbol:
                messagebox.showerror("Error", "Please enter a symbol")
                return
            
            # Get current positions
            positions = self.kite.positions()
            
            exit_count = 0
            exit_orders = []
            
            # Find and exit positions for this symbol
            for pos in positions['net']:
                if (pos['tradingsymbol'] == symbol and 
                    pos['quantity'] != 0 and
                    pos['exchange'] == 'NFO'):
                    
                    transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                    quantity = abs(pos['quantity'])
                    
                    try:
                        exit_id = self.kite.place_order(
                            variety="regular",
                            exchange=pos['exchange'],
                            tradingsymbol=symbol,
                            transaction_type=transaction_type,
                            quantity=quantity,
                            order_type="MARKET",
                            product=pos['product']
                        )
                        
                        exit_orders.append((transaction_type, exit_id, quantity))
                        exit_count += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to exit position: {e}")
            
            if exit_count > 0:
                # Log exits
                timestamp = datetime.now().strftime("%H:%M:%S")
                log_msg = f"\n[{timestamp}] Exit Orders:\n"
                for trans_type, order_id, qty in exit_orders:
                    log_msg += f"  {trans_type} {qty} shares - Order ID: {order_id}\n"
                
                self.order_log_text.insert(tk.END, log_msg)
                self.order_log_text.see(tk.END)
                
                messagebox.showinfo("Success", f"{exit_count} position(s) exited successfully!")
                self.refresh_positions()
                self.refresh_dashboard_positions()
            else:
                messagebox.showinfo("Info", f"No positions found for {symbol}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to exit positions: {str(e)}")
    
    def monitor_profit_target(self, monitor_id):
        """Monitor position and auto exit when target reached"""
        if monitor_id not in self.profit_targets:
            return
        
        target_data = self.profit_targets[monitor_id]
        symbol = target_data['symbol']
        
        try:
            highest_price = target_data['entry_price']
            
            while monitor_id in self.profit_targets:
                # Get current price
                quote = self.kite.quote([f"NFO:{symbol}"])
                current_price = quote[f"NFO:{symbol}"]['last_price']
                
                # Update highest price for trailing SL
                if current_price > highest_price:
                    highest_price = current_price
                
                # Calculate trailing stop loss
                stop_loss_price = target_data['stop_loss_price']
                if target_data['trailing']:
                    trailing_price = highest_price * (1 - target_data['trailing_percent'] / 100)
                    stop_loss_price = max(stop_loss_price, trailing_price)
                
                # Check conditions
                exit_reason = None
                exit_price = 0
                
                if current_price >= target_data['target_price']:
                    exit_reason = "Target Achieved"
                    exit_price = current_price
                elif current_price <= stop_loss_price:
                    exit_reason = "Stop Loss Hit"
                    exit_price = current_price
                
                # Auto exit if condition met
                if exit_reason:
                    # Place exit order
                    exit_id = self.kite.place_order(
                        variety="regular",
                        exchange="NFO",
                        tradingsymbol=symbol,
                        transaction_type="SELL",
                        quantity=target_data['quantity'],
                        order_type="MARKET",
                        product="MIS"
                    )
                    
                    # Calculate P&L
                    pnl = (exit_price - target_data['entry_price']) * target_data['quantity']
                    pnl_percent = ((exit_price - target_data['entry_price']) / target_data['entry_price']) * 100
                    
                    # Remove from monitoring
                    del self.profit_targets[monitor_id]
                    
                    # Update GUI via queue
                    log_msg = f"\n[AUTO EXIT] {exit_reason} for {symbol}!\n"
                    log_msg += f"  Entry: {target_data['entry_price']:.2f}\n"
                    log_msg += f"  Exit: {exit_price:.2f}\n"
                    log_msg += f"  P&L: ₹{pnl:.2f} ({pnl_percent:+.2f}%)\n"
                    log_msg += f"  Exit Order ID: {exit_id}\n"
                    
                    self.gui_queue.put(("log", log_msg))
                    
                    # Show notification
                    self.gui_queue.put(("notify", f"{exit_reason} - {symbol}"))
                    
                    break
                
                # Update monitor tree
                current_pnl = (current_price - target_data['entry_price']) * target_data['quantity']
                current_pnl_percent = ((current_price - target_data['entry_price']) / target_data['entry_price']) * 100
                
                # Find and update item in monitor tree
                for item in self.monitor_tree.get_children():
                    values = self.monitor_tree.item(item)['values']
                    if values[0] == symbol:
                        self.monitor_tree.item(item, values=(
                            symbol,
                            f"{target_data['entry_price']:.2f}",
                            f"{target_data['target_price']:.2f}",
                            f"{current_price:.2f}",
                            f"₹{current_pnl:.2f}",
                            f"Monitoring ({current_pnl_percent:+.2f}%)"
                        ))
                        break
                
                time.sleep(5)  # Check every 5 seconds
                
        except Exception as e:
            logger.error(f"Monitor error for {symbol}: {e}")
            if monitor_id in self.profit_targets:
                del self.profit_targets[monitor_id]
    
    def calculate_pnl(self):
        """Calculate P&L based on entered values"""
        try:
            entry_price = float(self.pnl_entry_var.get() or 0)
            current_price = float(self.pnl_current_var.get() or 0)
            quantity = int(self.pnl_qty_var.get() or 0)
            
            if entry_price <= 0 or quantity <= 0:
                messagebox.showerror("Error", "Please enter valid prices and quantity")
                return
            
            # Calculate P&L
            pnl_amount = (current_price - entry_price) * quantity
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
            
            # Update display
            self.pnl_amount_var.set(f"₹{pnl_amount:+.2f}")
            self.pnl_percent_var.set(f"{pnl_percent:+.2f}%")
            
            # Color code
            if pnl_amount >= 0:
                self.pnl_amount_var.set(f"🟢 ₹{pnl_amount:+.2f}")
                self.pnl_percent_var.set(f"🟢 {pnl_percent:+.2f}%")
            else:
                self.pnl_amount_var.set(f"🔴 ₹{pnl_amount:+.2f}")
                self.pnl_percent_var.set(f"🔴 {pnl_percent:+.2f}%")
            
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers")
    
    def update_pnl_prices(self):
        """Update current prices for P&L calculation"""
        symbol = self.basket_symbol_var.get()
        if not symbol:
            messagebox.showerror("Error", "Please enter a symbol")
            return
        
        try:
            quote = self.kite.quote([f"NFO:{symbol}"])
            current_price = quote[f"NFO:{symbol}"]['last_price']
            
            self.pnl_current_var.set(f"{current_price:.2f}")
            self.calculate_pnl()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get price: {str(e)}")
    
    def place_order(self):
        """Place a regular order"""
        if not self.is_connected:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            # Get order details from form
            symbol = self.order_vars["symbol_var"].get()
            transaction_type = self.order_vars["transaction_var"].get()
            order_type = self.order_vars["order_type_var"].get()
            quantity = int(self.order_vars["quantity_var"].get() or 0)
            price = float(self.order_vars["price_var"].get() or 0)
            product = self.order_vars["product_var"].get()
            validity = self.order_vars["validity_var"].get()
            disclosed_qty = int(self.order_vars["disclosed_qty_var"].get() or 0)
            
            # Validate inputs
            if not symbol or quantity <= 0:
                messagebox.showerror("Error", "Please enter valid symbol and quantity")
                return
            
            if order_type in ["LIMIT", "SL", "SL-M"] and price <= 0:
                messagebox.showerror("Error", "Please enter valid price for limit/SL order")
                return
            
            # Place order
            order_id = self.kite.place_order(
                variety="regular",
                exchange="NFO",
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                price=price,
                product=product,
                order_type=order_type,
                validity=validity,
                disclosed_quantity=disclosed_qty if disclosed_qty > 0 else None
            )
            
            # Log order
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_msg = f"[{timestamp}] Order placed: {symbol} {transaction_type} {quantity} @ {price} - Order ID: {order_id}\n"
            self.order_log_text.insert(tk.END, log_msg)
            self.order_log_text.see(tk.END)
            
            # Refresh orders
            self.load_recent_orders()
            
            messagebox.showinfo("Success", f"Order placed successfully! Order ID: {order_id}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to place order: {str(e)}")
            logger.error(f"Order placement error: {e}")
    
    def get_quote(self):
        """Get quote for symbol"""
        symbol = self.order_vars["symbol_var"].get()
        if not symbol:
            messagebox.showerror("Error", "Please enter a symbol")
            return
        
        try:
            quote = self.kite.quote([f"NFO:{symbol}"])
            ltp = quote[f"NFO:{symbol}"]['last_price']
            
            # Update price field
            self.order_vars["price_var"].set(f"{ltp:.2f}")
            
            # Show detailed quote in messagebox
            detail_msg = f"Symbol: {symbol}\n"
            detail_msg += f"LTP: ₹{ltp:.2f}\n"
            
            if 'ohlc' in quote[f"NFO:{symbol}"]:
                ohlc = quote[f"NFO:{symbol}"]['ohlc']
                detail_msg += f"Open: ₹{ohlc['open']:.2f}\n"
                detail_msg += f"High: ₹{ohlc['high']:.2f}\n"
                detail_msg += f"Low: ₹{ohlc['low']:.2f}\n"
                detail_msg += f"Close: ₹{ohlc['close']:.2f}\n"
            
            if 'volume' in quote[f"NFO:{symbol}"]:
                detail_msg += f"Volume: {quote[f'NFO:{symbol}']['volume']:,}\n"
            
            messagebox.showinfo("Quote", detail_msg)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get quote: {str(e)}")
    
    def refresh_positions(self):
        """Refresh positions data - FIXED VERSION"""
        if not self.is_connected:
            return
        
        try:
            positions = self.kite.positions()
            
            # Clear tree
            for item in self.positions_tree.get_children():
                self.positions_tree.delete(item)
            
            total_investment = 0
            total_pnl = 0
            
            # Populate net positions
            for pos in positions['net']:
                if pos['quantity'] != 0:
                    # Calculate current value
                    current_value = pos['quantity'] * pos['last_price']
                    investment = abs(pos['quantity']) * pos['average_price']
                    pnl = pos['pnl']
                    
                    total_investment += investment
                    total_pnl += pnl
                    
                    # Color tag based on P&L
                    color_tag = "green" if pnl >= 0 else "red"
                    
                    # Insert data - values correspond to columns in order
                    item_id = self.positions_tree.insert("", tk.END, values=(
                        pos['tradingsymbol'],
                        pos['quantity'],
                        f"{pos['average_price']:.2f}",
                        f"{pos['last_price']:.2f}",
                        f"{pos['m2m']:.2f}",
                        f"₹{pnl:+.2f}"
                    ), tags=(color_tag,))
        
            # Configure tags
            self.positions_tree.tag_configure("green", foreground="green")
            self.positions_tree.tag_configure("red", foreground="red")
            
            # Update summary
            self.total_investment_var.set(f"₹{total_investment:.2f}")
            self.total_pnl_var.set(f"₹{total_pnl:+.2f}")
            
            if total_investment > 0:
                pnl_percent = (total_pnl / total_investment) * 100
                self.total_pnl_percent_var.set(f"{pnl_percent:+.2f}%")
            
            self.status_bar.config(text=f"Positions updated: {len(positions['net'])} items")
            
            # Also update dashboard positions
            self.refresh_dashboard_positions()
            
        except Exception as e:
            logger.error(f"Error refreshing positions: {e}")
    
    def square_off_all(self):
        """Square off all positions"""
        if not self.is_connected:
            messagebox.showerror("Error", "Please login first")
            return
        
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to square off ALL positions?")
        if not confirm:
            return
        
        try:
            positions = self.kite.positions()
            square_off_count = 0
            
            for pos in positions['net']:
                if pos['quantity'] != 0:
                    transaction_type = "SELL" if pos['quantity'] > 0 else "BUY"
                    quantity = abs(pos['quantity'])
                    
                    try:
                        self.kite.place_order(
                            variety="regular",
                            exchange=pos['exchange'],
                            tradingsymbol=pos['tradingsymbol'],
                            transaction_type=transaction_type,
                            quantity=quantity,
                            order_type="MARKET",
                            product=pos['product']
                        )
                        square_off_count += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to square off {pos['tradingsymbol']}: {e}")
            
            messagebox.showinfo("Success", f"{square_off_count} position(s) squared off!")
            self.refresh_positions()
            self.refresh_dashboard_positions()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to square off positions: {str(e)}")
    
    def refresh_portfolio(self):
        """Refresh portfolio data"""
        if not self.is_connected:
            return
        
        try:
            # Get portfolio holdings
            holdings = self.kite.holdings()
            
            # Get margins
            margins = self.kite.margins()
            
            # Calculate totals
            total_holdings = sum(h['quantity'] * h['last_price'] for h in holdings)
            total_pnl = sum(h['pnl'] for h in holdings)
            
            # Update metrics
            self.metrics_vars["total_holdings_var"].set(f"₹{total_holdings:.2f}")
            self.metrics_vars["total_pnl_var"].set(f"₹{total_pnl:+.2f}")
            
            if 'equity' in margins:
                equity = margins['equity']
                self.metrics_vars["available_margin_var"].set(f"₹{equity.get('available', {}).get('cash', 0):.2f}")
                self.metrics_vars["used_margin_var"].set(f"₹{equity.get('used', {}).get('total', 0):.2f}")
            
            # Get daily P&L
            try:
                day_pnl = self.kite.margins()['equity']['used']['day_pnl']
                self.metrics_vars["day_pnl_var"].set(f"₹{day_pnl:+.2f}")
            except:
                pass
            
            self.status_bar.config(text="Portfolio updated")
            
        except Exception as e:
            logger.error(f"Error refreshing portfolio: {e}")
    
    def load_recent_orders(self):
        """Load recent orders"""
        if not self.is_connected:
            return
        
        try:
            orders = self.kite.orders()
            
            # Clear tree
            for item in self.orders_tree.get_children():
                self.orders_tree.delete(item)
            
            # Display recent orders (last 20)
            for order in orders[-20:]:
                time_str = ""
                if order['order_timestamp']:
                    try:
                        dt = datetime.strptime(order['order_timestamp'], '%Y-%m-%d %H:%M:%S')
                        time_str = dt.strftime('%H:%M:%S')
                    except:
                        time_str = order['order_timestamp'][11:19] if len(order['order_timestamp']) > 11 else ""
                
                avg_price = order.get('average_price', 0)
                if avg_price == 0:
                    avg_price = order.get('price', 0)
                
                # Color tag based on status
                status = order['status']
                if status == 'COMPLETE':
                    color_tag = "green"
                elif status in ['CANCELLED', 'REJECTED']:
                    color_tag = "red"
                else:
                    color_tag = "blue"
                
                item_id = self.orders_tree.insert("", tk.END, values=(
                    time_str,
                    order['tradingsymbol'],
                    order['transaction_type'],
                    order['quantity'],
                    f"{avg_price:.2f}",
                    status
                ), tags=(color_tag,))
            
            # Configure tags
            self.orders_tree.tag_configure("green", foreground="green")
            self.orders_tree.tag_configure("red", foreground="red")
            self.orders_tree.tag_configure("blue", foreground="blue")
            
        except Exception as e:
            logger.error(f"Error loading orders: {e}")
    
    def refresh_all_data(self):
        """Refresh all data"""
        if not self.is_connected:
            return
        
        threading.Thread(target=self.load_initial_data, daemon=True).start()
        self.status_bar.config(text="Refreshing all data...")
    
    def quick_trade_selected(self):
        """Quick trade selected future"""
        selection = self.futures_tree.selection()
        if selection:
            self.on_future_selected(None)
            self.notebook.select(4)  # Advanced tab
    
    def stop_monitor(self):
        """Stop active monitor"""
        selection = self.monitor_tree.selection()
        if selection:
            item = self.monitor_tree.item(selection[0])
            symbol = item['values'][0]
            
            # Find and remove monitor
            for monitor_id, data in list(self.profit_targets.items()):
                if data['symbol'] == symbol:
                    del self.profit_targets[monitor_id]
                    break
            
            # Update tree
            self.monitor_tree.item(selection[0], values=(
                symbol,
                item['values'][1],
                item['values'][2],
                item['values'][3],
                item['values'][4],
                "Stopped"
            ))
            
            messagebox.showinfo("Info", f"Monitoring stopped for {symbol}")
    
    def refresh_monitors(self):
        """Refresh monitor display"""
        # Clear and rebuild monitor tree
        for item in self.monitor_tree.get_children():
            self.monitor_tree.delete(item)
        
        for monitor_id, data in self.profit_targets.items():
            # Get current price
            try:
                quote = self.kite.quote([f"NFO:{data['symbol']}"])
                current_price = quote[f"NFO:{data['symbol']}"]['last_price']
                current_pnl = (current_price - data['entry_price']) * data['quantity']
                
                self.monitor_tree.insert("", tk.END, values=(
                    data['symbol'],
                    f"{data['entry_price']:.2f}",
                    f"{data['target_price']:.2f}",
                    f"{current_price:.2f}",
                    f"₹{current_pnl:.2f}",
                    "Monitoring"
                ))
            except:
                pass
    
    def process_queue(self):
        """Process messages from queue for thread-safe GUI updates"""
        try:
            while True:
                msg_type, data = self.gui_queue.get_nowait()
                
                if msg_type == "error":
                    messagebox.showerror("Error", data)
                elif msg_type == "info":
                    messagebox.showinfo("Info", data)
                elif msg_type == "log":
                    self.order_log_text.insert(tk.END, data)
                    self.order_log_text.see(tk.END)
                elif msg_type == "notify":
                    self.status_bar.config(text=data)
                    # You could add a notification system here
                
                self.gui_queue.task_done()
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.process_queue)
    
    def start_background_tasks(self):
        """Start background tasks like scheduled refreshes"""
        # Schedule periodic refreshes
        schedule.every(30).seconds.do(self.periodic_refresh)
        
        # Start scheduler in background thread
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(1)
        
        threading.Thread(target=run_scheduler, daemon=True).start()
    
    def periodic_refresh(self):
        """Periodic refresh of data"""
        if self.is_connected:
            try:
                # Refresh watchlist prices if needed
                if hasattr(self, 'watchlist_tree') and self.watchlist_tree.get_children():
                    # Implement watchlist refresh logic here
                    pass
                
                # Refresh monitor displays
                self.refresh_monitors()
                
                # Refresh positions every minute
                current_time = datetime.now()
                if current_time.second < 5:  # Refresh at the start of each minute
                    self.refresh_dashboard_positions()
                
            except Exception as e:
                logger.error(f"Periodic refresh error: {e}")
    
    # ==================== HELPER METHODS ====================
    
    def add_to_watchlist(self):
        """Add symbol to watchlist"""
        symbol = self.watchlist_symbol_var.get()
        if symbol:
            # Add to watchlist tree
            self.watchlist_tree.insert("", tk.END, values=(
                symbol, "0.00", "0.00", "0.00%", "0", "--:--:--"
            ))
            self.watchlist_symbol_var.set("")
    
    def update_pnl_display(self):
        """Update P&L display on dashboard"""
        # Implement P&L calculation for watchlist
        pass
    
    def calculate_margin(self):
        """Calculate margin requirement"""
        messagebox.showinfo("Info", "Margin calculation feature coming soon!")
    
    def view_chart(self):
        """View chart for symbol"""
        symbol = self.order_vars["symbol_var"].get()
        if symbol:
            # Open chart in browser or show in application
            chart_url = f"https://kite.zerodha.com/chart/ext/tvc/NFO/{symbol}"
            webbrowser.open(chart_url)
    
    def modify_order(self):
        """Modify existing order"""
        messagebox.showinfo("Info", "Order modification feature coming soon!")
    
    def cancel_order(self):
        """Cancel existing order"""
        messagebox.showinfo("Info", "Order cancellation feature coming soon!")
    
    def view_position_details(self):
        """View position details"""
        messagebox.showinfo("Info", "Position details feature coming soon!")
    
    def view_position_chart(self):
        """View chart for position"""
        messagebox.showinfo("Info", "Position chart feature coming soon!")
    
    def export_positions_csv(self):
        """Export positions to CSV"""
        try:
            filename = f"positions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            # Get positions data
            positions = self.kite.positions()
            
            # Prepare data for CSV
            data = []
            for pos in positions['net']:
                if pos['quantity'] != 0:
                    data.append({
                        'Symbol': pos['tradingsymbol'],
                        'Quantity': pos['quantity'],
                        'Avg Price': pos['average_price'],
                        'LTP': pos['last_price'],
                        'MTM': pos['m2m'],
                        'P&L': pos['pnl']
                    })
            
            if data:
                df = pd.DataFrame(data)
                df.to_csv(filename, index=False)
                messagebox.showinfo("Success", f"Positions exported to {filename}")
            else:
                messagebox.showinfo("Info", "No positions to export")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {str(e)}")
    
    def save_pnl_report(self):
        """Save P&L report"""
        try:
            filename = f"pnl_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            with open(filename, 'w') as f:
                f.write("P&L Report\n")
                f.write("=" * 50 + "\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"Entry Price: {self.pnl_entry_var.get()}\n")
                f.write(f"Current Price: {self.pnl_current_var.get()}\n")
                f.write(f"Quantity: {self.pnl_qty_var.get()}\n")
                f.write(f"P&L Amount: {self.pnl_amount_var.get()}\n")
                f.write(f"P&L Percentage: {self.pnl_percent_var.get()}\n")
            
            messagebox.showinfo("Success", f"Report saved to {filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save report: {str(e)}")
    
    def generate_portfolio_report(self):
        """Generate portfolio report"""
        messagebox.showinfo("Info", "Portfolio report feature coming soon!")
    
    def view_portfolio_analytics(self):
        """View portfolio analytics"""
        messagebox.showinfo("Info", "Portfolio analytics feature coming soon!")
    
    def refresh_holdings(self):
        """Refresh holdings data"""
        # This method is referenced but not defined, adding it
        try:
            if self.is_connected:
                holdings = self.kite.holdings()
                logger.info(f"Holdings refreshed: {len(holdings)} items")
        except Exception as e:
            logger.error(f"Error refreshing holdings: {e}")

def main():
    """Main application entry point"""
    # Create main window
    root = tk.Tk()
    
    # Set window icon and title
    root.title("Zerodha Trading Platform v2.0")
    
    # Create application instance
    app = ZerodhaTradingApp(root)
    
    # Start main loop
    root.mainloop()

if __name__ == "__main__":
    main()