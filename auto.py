import tkinter as tk
from tkinter import ttk, messagebox
import configparser
import requests
import pyotp
from kiteconnect import KiteConnect, KiteTicker
from urllib.parse import urlparse, parse_qs
import logging
import threading
import json
import time
from datetime import datetime, timedelta
import queue
import os
import pickle
import webbrowser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import sys

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha Trading Tool")
        self.root.geometry("1400x900")
        
        # Initialize variables
        self.kite = None
        self.kws = None
        self.is_connected = False
        self.data_queue = queue.Queue()
        self.subscribed_tokens = set()
        self.instruments_data = {}
        self.positions_data = {}
        self.realtime_data = {}
        self.session_file = "session.pkl"
        self.config_file = "login.ini"
        self.driver = None
        self.update_interval = 10  # 1 second refresh rate
        
        # Create GUI
        self.create_gui()
        
        # Check for existing session
        self.check_existing_session()
        
        # Start queue processor
        self.process_queue()
    
    def create_gui(self):
        """Create the main GUI interface"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        
        # Create tabs
        self.tab_auto_login = ttk.Frame(self.notebook)
        self.tab_mcx_future = ttk.Frame(self.notebook)
        self.tab_mcx_option = ttk.Frame(self.notebook)
        self.tab_nfo_future = ttk.Frame(self.notebook)
        self.tab_nfo_option = ttk.Frame(self.notebook)
        self.tab_positions = ttk.Frame(self.notebook)
        self.tab_trading = ttk.Frame(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(self.tab_auto_login, text="Auto Login")
        self.notebook.add(self.tab_mcx_future, text="MCX Future")
        self.notebook.add(self.tab_mcx_option, text="MCX Option")
        self.notebook.add(self.tab_nfo_future, text="NFO Future")
        self.notebook.add(self.tab_nfo_option, text="NFO Option")
        self.notebook.add(self.tab_positions, text="Positions & P&L")
        self.notebook.add(self.tab_trading, text="Trading")
        
        self.notebook.pack(expand=True, fill="both")
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Initializing...")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken")
        status_bar.pack(side="bottom", fill="x")
        
        # Create content for each tab
        self.create_auto_login_tab()
        self.create_mcx_future_tab()
        self.create_mcx_option_tab()
        self.create_nfo_future_tab()
        self.create_nfo_option_tab()
        self.create_positions_tab()
        self.create_trading_tab()
        
        # Initially disable trading tabs
        self.disable_tabs()
    
    def create_auto_login_tab(self):
        """Create Auto Login tab with browser automation"""
        main_frame = ttk.Frame(self.tab_auto_login)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Left side - Login Configuration
        config_frame = ttk.LabelFrame(main_frame, text="Login Configuration")
        config_frame.pack(side="left", fill="both", expand=True, padx=10)
        
        # API Key
        ttk.Label(config_frame, text="API Key:").grid(row=0, column=0, sticky="w", pady=5)
        self.api_key_var = tk.StringVar()
        api_key_entry = ttk.Entry(config_frame, textvariable=self.api_key_var, width=30)
        api_key_entry.grid(row=0, column=1, pady=5, padx=5)
        
        # API Secret
        ttk.Label(config_frame, text="API Secret:").grid(row=1, column=0, sticky="w", pady=5)
        self.api_secret_var = tk.StringVar()
        api_secret_entry = ttk.Entry(config_frame, textvariable=self.api_secret_var, width=30)
        api_secret_entry.grid(row=1, column=1, pady=5, padx=5)
        
        # User ID
        ttk.Label(config_frame, text="User ID:").grid(row=2, column=0, sticky="w", pady=5)
        self.user_id_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.user_id_var, width=30).grid(row=2, column=1, pady=5, padx=5)
        
        # Password
        ttk.Label(config_frame, text="Password:").grid(row=3, column=0, sticky="w", pady=5)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(config_frame, textvariable=self.password_var, width=30, show="*")
        password_entry.grid(row=3, column=1, pady=5, padx=5)
        
        # TOTP Secret
        ttk.Label(config_frame, text="TOTP Secret:").grid(row=4, column=0, sticky="w", pady=5)
        self.totp_secret_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.totp_secret_var, width=30).grid(row=4, column=1, pady=5, padx=5)
        
        # Request Token (for manual entry)
        ttk.Label(config_frame, text="Request Token:").grid(row=5, column=0, sticky="w", pady=5)
        self.request_token_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.request_token_var, width=30).grid(row=5, column=1, pady=5, padx=5)
        
        # Buttons
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=15)
        
        ttk.Button(button_frame, text="Save Configuration", 
                  command=self.save_configuration).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Load Configuration", 
                  command=self.load_configuration).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Open Browser Login", 
                  command=self.open_browser_login).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Auto Browser Login", 
                  command=self.auto_browser_login).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Manual Token Login", 
                  command=self.manual_token_login).pack(side="left", padx=5)
        
        # Right side - Session Information
        session_frame = ttk.LabelFrame(main_frame, text="Session Information")
        session_frame.pack(side="right", fill="both", expand=True, padx=10)
        
        # Session status
        ttk.Label(session_frame, text="Session Status:").grid(row=0, column=0, sticky="w", pady=5)
        self.session_status_var = tk.StringVar(value="Not logged in")
        status_label = ttk.Label(session_frame, textvariable=self.session_status_var, 
                 font=("Arial", 10, "bold"))
        status_label.grid(row=0, column=1, sticky="w", pady=5)
        
        # Access Token
        ttk.Label(session_frame, text="Access Token:").grid(row=1, column=0, sticky="w", pady=5)
        self.access_token_var = tk.StringVar(value="Not available")
        access_token_label = ttk.Label(session_frame, textvariable=self.access_token_var, 
                                      font=("Courier", 8), wraplength=300)
        access_token_label.grid(row=1, column=1, sticky="w", pady=5)
        
        # Request Token Display
        ttk.Label(session_frame, text="Request Token:").grid(row=2, column=0, sticky="w", pady=5)
        self.request_token_display_var = tk.StringVar(value="Not available")
        ttk.Label(session_frame, textvariable=self.request_token_display_var, 
                 font=("Courier", 8)).grid(row=2, column=1, sticky="w", pady=5)
        
        # Login Time
        ttk.Label(session_frame, text="Login Time:").grid(row=3, column=0, sticky="w", pady=5)
        self.login_time_var = tk.StringVar(value="Not available")
        ttk.Label(session_frame, textvariable=self.login_time_var).grid(row=3, column=1, sticky="w", pady=5)
        
        # Browser Status
        ttk.Label(session_frame, text="Browser Status:").grid(row=4, column=0, sticky="w", pady=5)
        self.browser_status_var = tk.StringVar(value="Not started")
        ttk.Label(session_frame, textvariable=self.browser_status_var).grid(row=4, column=1, sticky="w", pady=5)
        
        # Session management buttons
        session_button_frame = ttk.Frame(session_frame)
        session_button_frame.grid(row=5, column=0, columnspan=2, pady=15)
        
        ttk.Button(session_button_frame, text="Reuse Session", 
                  command=self.reuse_session).pack(side="left", padx=5)
        ttk.Button(session_button_frame, text="Logout", 
                  command=self.logout).pack(side="left", padx=5)
        
        # Auto-login settings
        auto_frame = ttk.LabelFrame(main_frame, text="Auto-Login Settings")
        auto_frame.pack(side="bottom", fill="x", pady=10)
        
        self.auto_login_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(auto_frame, text="Enable auto-login on startup", 
                       variable=self.auto_login_var).pack(side="left", padx=5)
        
        self.save_session_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(auto_frame, text="Save session for reuse", 
                       variable=self.save_session_var).pack(side="left", padx=5)
        
        # Instructions
        instructions_frame = ttk.LabelFrame(main_frame, text="Instructions")
        instructions_frame.pack(side="bottom", fill="x", pady=10)
        
        instructions_text = """
1. 'Open Browser Login' - Opens browser for manual login, paste the final URL in Request Token field
2. 'Auto Browser Login' - Automatically logs in using Selenium (requires Chrome)
3. 'Manual Token Login' - Uses manually entered request token
4. 'Reuse Session' - Reuses previously saved session
        """
        ttk.Label(instructions_frame, text=instructions_text, justify="left").pack(padx=5, pady=5)
        
        # Load existing configuration
        self.load_configuration()
    
    def create_mcx_future_tab(self):
        """Create MCX Future tab content"""
        # Frame for controls
        control_frame = ttk.Frame(self.tab_mcx_future)
        control_frame.pack(pady=10)
        
        ttk.Button(control_frame, text="Refresh Instruments", 
                  command=self.refresh_mcx_future).pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="Subscribe All", 
                  command=lambda: self.subscribe_segment("MCX", "FUT")).pack(side="left", padx=5)
        
        # Search frame
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side="left", padx=20)
        
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.mcx_future_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.mcx_future_search_var, width=20)
        search_entry.pack(side="left", padx=5)
        search_entry.bind('<KeyRelease>', lambda e: self.search_instruments("mcx_future"))
        
        # Treeview for displaying data
        columns = ("Symbol", "LTP", "Change %", "Volume", "OI", "Timestamp")
        self.mcx_future_tree = ttk.Treeview(self.tab_mcx_future, columns=columns, show="headings", height=25)
        
        # Configure columns
        for col in columns:
            self.mcx_future_tree.heading(col, text=col)
            self.mcx_future_tree.column(col, width=120)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.tab_mcx_future, orient="vertical", 
                                 command=self.mcx_future_tree.yview)
        self.mcx_future_tree.configure(yscrollcommand=scrollbar.set)
        
        self.mcx_future_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        # Bind double click to subscribe
        self.mcx_future_tree.bind("<Double-1>", lambda e: self.subscribe_selected_instrument("mcx_future"))
    
    def create_mcx_option_tab(self):
        """Create MCX Option tab content"""
        control_frame = ttk.Frame(self.tab_mcx_option)
        control_frame.pack(pady=10)
        
        ttk.Button(control_frame, text="Refresh Instruments", 
                  command=self.refresh_mcx_option).pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="Subscribe All", 
                  command=lambda: self.subscribe_segment("MCX", "OPT")).pack(side="left", padx=5)
        
        # Search frame
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side="left", padx=20)
        
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.mcx_option_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.mcx_option_search_var, width=20)
        search_entry.pack(side="left", padx=5)
        search_entry.bind('<KeyRelease>', lambda e: self.search_instruments("mcx_option"))
        
        columns = ("Symbol", "LTP", "Change %", "Volume", "OI", "IV", "Timestamp")
        self.mcx_option_tree = ttk.Treeview(self.tab_mcx_option, columns=columns, show="headings", height=25)
        
        for col in columns:
            self.mcx_option_tree.heading(col, text=col)
            self.mcx_option_tree.column(col, width=110)
        
        scrollbar = ttk.Scrollbar(self.tab_mcx_option, orient="vertical", 
                                 command=self.mcx_option_tree.yview)
        self.mcx_option_tree.configure(yscrollcommand=scrollbar.set)
        
        self.mcx_option_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        self.mcx_option_tree.bind("<Double-1>", lambda e: self.subscribe_selected_instrument("mcx_option"))
    
    def create_nfo_future_tab(self):
        """Create NFO Future tab content"""
        control_frame = ttk.Frame(self.tab_nfo_future)
        control_frame.pack(pady=10)
        
        ttk.Button(control_frame, text="Refresh Instruments", 
                  command=self.refresh_nfo_future).pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="Subscribe All", 
                  command=lambda: self.subscribe_segment("NFO", "FUT")).pack(side="left", padx=5)
        
        # Search frame
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side="left", padx=20)
        
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.nfo_future_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.nfo_future_search_var, width=20)
        search_entry.pack(side="left", padx=5)
        search_entry.bind('<KeyRelease>', lambda e: self.search_instruments("nfo_future"))
        
        columns = ("Symbol", "LTP", "Change %", "Volume", "OI", "Timestamp")
        self.nfo_future_tree = ttk.Treeview(self.tab_nfo_future, columns=columns, show="headings", height=25)
        
        for col in columns:
            self.nfo_future_tree.heading(col, text=col)
            self.nfo_future_tree.column(col, width=120)
        
        scrollbar = ttk.Scrollbar(self.tab_nfo_future, orient="vertical", 
                                 command=self.nfo_future_tree.yview)
        self.nfo_future_tree.configure(yscrollcommand=scrollbar.set)
        
        self.nfo_future_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        self.nfo_future_tree.bind("<Double-1>", lambda e: self.subscribe_selected_instrument("nfo_future"))
    
    def create_nfo_option_tab(self):
        """Create NFO Option tab content"""
        control_frame = ttk.Frame(self.tab_nfo_option)
        control_frame.pack(pady=10)
        
        ttk.Button(control_frame, text="Refresh Instruments", 
                  command=self.refresh_nfo_option).pack(side="left", padx=5)
        
        ttk.Button(control_frame, text="Subscribe All", 
                  command=lambda: self.subscribe_segment("NFO", "OPT")).pack(side="left", padx=5)
        
        # Search frame
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side="left", padx=20)
        
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.nfo_option_search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.nfo_option_search_var, width=20)
        search_entry.pack(side="left", padx=5)
        search_entry.bind('<KeyRelease>', lambda e: self.search_instruments("nfo_option"))
        
        columns = ("Symbol", "LTP", "Change %", "Volume", "OI", "IV", "Timestamp")
        self.nfo_option_tree = ttk.Treeview(self.tab_nfo_option, columns=columns, show="headings", height=25)
        
        for col in columns:
            self.nfo_option_tree.heading(col, text=col)
            self.nfo_option_tree.column(col, width=110)
        
        scrollbar = ttk.Scrollbar(self.tab_nfo_option, orient="vertical", 
                                 command=self.nfo_option_tree.yview)
        self.nfo_option_tree.configure(yscrollcommand=scrollbar.set)
        
        self.nfo_option_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        self.nfo_option_tree.bind("<Double-1>", lambda e: self.subscribe_selected_instrument("nfo_option"))
    
    def create_positions_tab(self):
        """Create Positions and P&L tab"""
        # P&L Summary
        summary_frame = ttk.LabelFrame(self.tab_positions, text="P&L Summary")
        summary_frame.pack(pady=10, padx=10, fill="x")
        
        ttk.Label(summary_frame, text="Total P&L:").grid(row=0, column=0, padx=5)
        self.total_pnl_var = tk.StringVar(value="0.00")
        ttk.Label(summary_frame, textvariable=self.total_pnl_var, 
                 font=("Arial", 12, "bold")).grid(row=0, column=1, padx=5)
        
        ttk.Label(summary_frame, text="Realized P&L:").grid(row=0, column=2, padx=5)
        self.realized_pnl_var = tk.StringVar(value="0.00")
        ttk.Label(summary_frame, textvariable=self.realized_pnl_var).grid(row=0, column=3, padx=5)
        
        ttk.Label(summary_frame, text="Unrealized P&L:").grid(row=0, column=4, padx=5)
        self.unrealized_pnl_var = tk.StringVar(value="0.00")
        ttk.Label(summary_frame, textvariable=self.unrealized_pnl_var).grid(row=0, column=5, padx=5)
        
        # Refresh button
        ttk.Button(summary_frame, text="Refresh Positions", 
                  command=self.refresh_positions).grid(row=0, column=6, padx=10)
        
        ttk.Button(summary_frame, text="Close All Positions", 
                  command=self.close_all_positions).grid(row=0, column=7, padx=10)
        
        # Positions treeview
        columns = ("Symbol", "Quantity", "Avg Price", "LTP", "P&L", "Change %", "Action")
        self.positions_tree = ttk.Treeview(self.tab_positions, columns=columns, show="headings", height=20)
        
        for col in columns:
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=100)
        
        scrollbar = ttk.Scrollbar(self.tab_positions, orient="vertical", 
                                 command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=scrollbar.set)
        
        self.positions_tree.pack(fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y")
        
        # Bind click event for closing positions
        self.positions_tree.bind("<Double-1>", self.close_selected_position)
    
    def create_trading_tab(self):
        """Create Trading tab"""
        main_frame = ttk.Frame(self.tab_trading)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left side - Single Order
        left_frame = ttk.LabelFrame(main_frame, text="Single Order")
        left_frame.pack(side="left", fill="both", expand=True, padx=5)
        
        ttk.Label(left_frame, text="Instrument:").grid(row=0, column=0, sticky="w", pady=2)
        self.instrument_var = tk.StringVar()
        ttk.Entry(left_frame, textvariable=self.instrument_var, width=20).grid(row=0, column=1, pady=2)
        
        ttk.Label(left_frame, text="Quantity:").grid(row=1, column=0, sticky="w", pady=2)
        self.quantity_var = tk.StringVar(value="1")
        ttk.Entry(left_frame, textvariable=self.quantity_var, width=20).grid(row=1, column=1, pady=2)
        
        ttk.Label(left_frame, text="Price Type:").grid(row=2, column=0, sticky="w", pady=2)
        self.price_type_var = tk.StringVar(value="MARKET")
        price_combo = ttk.Combobox(left_frame, textvariable=self.price_type_var, 
                                  values=["MARKET", "LIMIT"], width=18)
        price_combo.grid(row=2, column=1, pady=2)
        
        ttk.Label(left_frame, text="Price:").grid(row=3, column=0, sticky="w", pady=2)
        self.price_var = tk.StringVar(value="0")
        ttk.Entry(left_frame, textvariable=self.price_var, width=20).grid(row=3, column=1, pady=2)
        
        # Order buttons
        button_frame = ttk.Frame(left_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="BUY", command=self.place_buy_order,
                  style="Buy.TButton").pack(side="left", padx=5)
        ttk.Button(button_frame, text="SELL", command=self.place_sell_order,
                  style="Sell.TButton").pack(side="left", padx=5)
        
        # Right side - Basket Order
        right_frame = ttk.LabelFrame(main_frame, text="Basket Order")
        right_frame.pack(side="right", fill="both", expand=True, padx=5)
        
        ttk.Label(right_frame, text="Buy Instrument:").grid(row=0, column=0, sticky="w", pady=2)
        self.buy_instrument_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.buy_instrument_var, width=20).grid(row=0, column=1, pady=2)
        
        ttk.Label(right_frame, text="Sell Instrument:").grid(row=1, column=0, sticky="w", pady=2)
        self.sell_instrument_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.sell_instrument_var, width=20).grid(row=1, column=1, pady=2)
        
        ttk.Label(right_frame, text="Quantity:").grid(row=2, column=0, sticky="w", pady=2)
        self.basket_quantity_var = tk.StringVar(value="1")
        ttk.Entry(right_frame, textvariable=self.basket_quantity_var, width=20).grid(row=2, column=1, pady=2)
        
        ttk.Button(right_frame, text="BUY & SELL TOGETHER", 
                  command=self.place_basket_order).grid(row=3, column=0, columnspan=2, pady=10)
        
        # Order book
        order_frame = ttk.LabelFrame(main_frame, text="Order Book")
        order_frame.pack(side="bottom", fill="x", pady=10)
        
        columns = ("Order ID", "Instrument", "Transaction", "Qty", "Price", "Status")
        self.order_tree = ttk.Treeview(order_frame, columns=columns, show="headings", height=6)
        
        for col in columns:
            self.order_tree.heading(col, text=col)
            self.order_tree.column(col, width=100)
        
        scrollbar = ttk.Scrollbar(order_frame, orient="vertical", command=self.order_tree.yview)
        self.order_tree.configure(yscrollcommand=scrollbar.set)
        
        self.order_tree.pack(fill="both", expand=True, side="left")
        scrollbar.pack(side="right", fill="y")
        
        # Configure styles for buy/sell buttons
        style = ttk.Style()
        style.configure("Buy.TButton", foreground="white", background="green")
        style.configure("Sell.TButton", foreground="white", background="red")
    
    def open_browser_login(self):
        """Open browser for manual login and token retrieval"""
        try:
            api_key = self.api_key_var.get()
            if not api_key:
                messagebox.showerror("Error", "Please enter API Key first")
                return
            
            self.kite = KiteConnect(api_key=api_key)
            login_url = self.kite.login_url()
            
            # Open the login URL in default browser
            webbrowser.open(login_url)
            
            self.status_var.set("Browser opened - Please login and paste the final URL")
            self.browser_status_var.set("Browser opened - waiting for token")
            
            # Show instructions
            messagebox.showinfo("Instructions", 
                              "1. Login to Zerodha in the browser\n"
                              "2. After login, copy the ENTIRE URL from address bar\n"
                              "3. Paste the URL in the Request Token field\n"
                              "4. Click 'Manual Token Login'")
            
        except Exception as e:
            logger.error(f"Error opening browser: {e}")
            messagebox.showerror("Error", f"Failed to open browser: {str(e)}")
    
    def auto_browser_login(self):
        """Automatically login using Selenium browser automation"""
        threading.Thread(target=self._auto_browser_login, daemon=True).start()
    
    def _auto_browser_login(self):
        """Perform automatic browser login"""
        try:
            api_key = self.api_key_var.get()
            user_id = self.user_id_var.get()
            password = self.password_var.get()
            totp_secret = self.totp_secret_var.get()
            
            if not all([api_key, user_id, password, totp_secret]):
                messagebox.showerror("Error", "Please fill all credentials for auto login")
                return
            
            self.status_var.set("Starting auto browser login...")
            self.browser_status_var.set("Initializing browser...")
            
            # Setup Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument("--start-maximized")
            
            # Initialize driver
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.kite = KiteConnect(api_key=api_key)
            login_url = self.kite.login_url()
            
            self.browser_status_var.set("Navigating to login page...")
            self.driver.get(login_url)
            
            # Step 1: Enter user ID and password
            self.browser_status_var.set("Entering credentials...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "userid"))
            ).send_keys(user_id)
            
            self.driver.find_element(By.ID, "password").send_keys(password)
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            
            # Step 2: Enter TOTP
            self.browser_status_var.set("Entering TOTP...")
            time.sleep(2)  # Wait for TOTP field to appear
            
            totp = pyotp.TOTP(totp_secret).now()
            totp_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "totp"))
            )
            totp_field.send_keys(totp)
            
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            
            # Step 3: Wait for redirect and extract request token
            self.browser_status_var.set("Waiting for login completion...")
            WebDriverWait(self.driver, 30).until(
                EC.url_contains("request_token=")
            )
            
            # Extract request token from URL
            current_url = self.driver.current_url
            parsed_url = urlparse(current_url)
            request_token = parse_qs(parsed_url.query)["request_token"][0]
            
            self.browser_status_var.set("Login successful!")
            self.request_token_var.set(request_token)
            self.request_token_display_var.set(request_token)
            
            # Close browser
            self.driver.quit()
            self.driver = None
            
            # Generate session with the obtained request token
            self.generate_session(request_token)
            
        except Exception as e:
            logger.error(f"Auto browser login failed: {e}")
            self.browser_status_var.set(f"Failed: {str(e)}")
            if self.driver:
                self.driver.quit()
                self.driver = None
            messagebox.showerror("Auto Login Error", f"Auto browser login failed: {str(e)}")
    
    def manual_token_login(self):
        """Login using manually provided request token"""
        try:
            api_key = self.api_key_var.get()
            api_secret = self.api_secret_var.get()
            request_token = self.request_token_var.get()
            
            if not all([api_key, api_secret, request_token]):
                messagebox.showerror("Error", "Please provide API Key, API Secret and Request Token")
                return
            
            # Check if it's a URL or direct token
            if "http" in request_token:
                # Extract token from URL
                parsed_url = urlparse(request_token)
                request_token = parse_qs(parsed_url.query)["request_token"][0]
                self.request_token_var.set(request_token)
            
            self.generate_session(request_token)
            
        except Exception as e:
            logger.error(f"Manual token login failed: {e}")
            messagebox.showerror("Login Error", f"Manual token login failed: {str(e)}")
    
    def generate_session(self, request_token):
        """Generate session using request token"""
        try:
            api_key = self.api_key_var.get()
            api_secret = self.api_secret_var.get()
            
            self.status_var.set("Generating session...")
            self.session_status_var.set("Generating session...")
            
            self.kite = KiteConnect(api_key=api_key)
            session_data = self.kite.generate_session(request_token, api_secret=api_secret)
            
            self.kite.set_access_token(session_data["access_token"])
            
            # Update session info
            self.access_token_var.set(f"{session_data['access_token'][:50]}...")
            self.request_token_display_var.set(request_token)
            self.login_time_var.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.session_status_var.set("Logged in - Session active")
            self.browser_status_var.set("Ready")
            
            # Save session if enabled
            if self.save_session_var.get():
                self.save_session()
            
            self.status_var.set("Login successful - Starting real-time data...")
            logger.info("Login successful")
            
            # Initialize real-time data
            self.initialize_realtime_data()
            
            # Load initial data
            self.refresh_positions()
            self.refresh_orders()
            self.load_all_instruments()
            
            # Enable other tabs
            self.enable_tabs()
            
            messagebox.showinfo("Success", "Login successful!")
            
        except Exception as e:
            logger.error(f"Session generation failed: {e}")
            self.session_status_var.set("Session generation failed")
            messagebox.showerror("Session Error", f"Failed to generate session: {str(e)}")
    
    def save_configuration(self):
        """Save login configuration to file"""
        try:
            config = configparser.ConfigParser()
            config["ZERODHA"] = {
                "api_key": self.api_key_var.get(),
                "api_secret": self.api_secret_var.get(),
                "user_id": self.user_id_var.get(),
                "password": self.password_var.get(),
                "totp_secret": self.totp_secret_var.get(),
                "auto_login": str(self.auto_login_var.get()),
                "save_session": str(self.save_session_var.get())
            }
            
            with open(self.config_file, 'w') as f:
                config.write(f)
            
            messagebox.showinfo("Success", "Configuration saved successfully!")
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            messagebox.showerror("Error", f"Failed to save configuration: {str(e)}")
    
    def load_configuration(self):
        """Load login configuration from file"""
        try:
            if not os.path.exists(self.config_file):
                return
                
            config = configparser.ConfigParser()
            config.read(self.config_file)
            
            if "ZERODHA" in config:
                zerodha_config = config["ZERODHA"]
                self.api_key_var.set(zerodha_config.get("api_key", ""))
                self.api_secret_var.set(zerodha_config.get("api_secret", ""))
                self.user_id_var.set(zerodha_config.get("user_id", ""))
                self.password_var.set(zerodha_config.get("password", ""))
                self.totp_secret_var.set(zerodha_config.get("totp_secret", ""))
                self.auto_login_var.set(zerodha_config.get("auto_login", "True") == "True")
                self.save_session_var.set(zerodha_config.get("save_session", "True") == "True")
                
            self.status_var.set("Configuration loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
    
    def save_session(self):
        """Save session data to file"""
        if not self.save_session_var.get() or not self.kite:
            return
            
        try:
            session_data = {
                'access_token': self.kite.access_token,
                'api_key': self.api_key_var.get(),
                'login_time': datetime.now().isoformat(),
                'user_id': self.user_id_var.get(),
                'request_token': self.request_token_display_var.get()
            }
            
            with open(self.session_file, 'wb') as f:
                pickle.dump(session_data, f)
                
            logger.info("Session saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving session: {e}")
    
    def load_session(self):
        """Load session data from file"""
        if not os.path.exists(self.session_file):
            return None
            
        try:
            with open(self.session_file, 'rb') as f:
                session_data = pickle.load(f)
            
            # Check if session is less than 1 day old
            login_time = datetime.fromisoformat(session_data['login_time'])
            if datetime.now() - login_time < timedelta(hours=24):
                return session_data
            else:
                logger.info("Session expired, needs fresh login")
                return None
                
        except Exception as e:
            logger.error(f"Error loading session: {e}")
            return None
    
    def check_existing_session(self):
        """Check for existing valid session"""
        if not self.auto_login_var.get():
            return
            
        session_data = self.load_session()
        if session_data:
            self.api_key_var.set(session_data.get('api_key', ''))
            self.reuse_session()
    
    def reuse_session(self):
        """Reuse existing session token"""
        try:
            session_data = self.load_session()
            if not session_data:
                messagebox.showwarning("Session Expired", "No valid session found. Please login manually.")
                return
            
            api_key = session_data['api_key']
            access_token = session_data['access_token']
            request_token = session_data.get('request_token', '')
            
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
            
            # Test the session
            profile = self.kite.profile()
            
            # Update session info
            self.access_token_var.set(f"{access_token[:50]}...")
            self.request_token_display_var.set(request_token)
            self.login_time_var.set("Reused from saved session")
            self.session_status_var.set("Session reused - Active")
            
            self.status_var.set("Session reused successfully")
            logger.info("Session reused successfully")
            
            # Initialize real-time data
            self.initialize_realtime_data()
            
            # Load initial data
            self.refresh_positions()
            self.refresh_orders()
            self.load_all_instruments()
            
            # Enable other tabs
            self.enable_tabs()
            
        except Exception as e:
            logger.error(f"Session reuse failed: {e}")
            self.session_status_var.set("Session reuse failed")
            messagebox.showerror("Session Error", f"Failed to reuse session: {str(e)}")
            
            # Remove invalid session file
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
    
    def logout(self):
        """Logout and clear session"""
        try:
            if self.kws:
                self.kws.close()
                self.kws = None
            
            if self.driver:
                self.driver.quit()
                self.driver = None
            
            # Clear session file
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            
            self.kite = None
            self.session_status_var.set("Logged out")
            self.access_token_var.set("Not available")
            self.request_token_display_var.set("Not available")
            self.login_time_var.set("Not available")
            self.browser_status_var.set("Not started")
            self.status_var.set("Logged out successfully")
            
            # Disable other tabs
            self.disable_tabs()
            
            # Clear all treeviews
            self.clear_all_treeviews()
            
            logger.info("Logged out successfully")
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
    
    def enable_tabs(self):
        """Enable all trading tabs"""
        for i in range(1, self.notebook.index("end")):
            self.notebook.tab(i, state="normal")
    
    def disable_tabs(self):
        """Disable all trading tabs (except Auto Login)"""
        for i in range(1, self.notebook.index("end")):
            self.notebook.tab(i, state="disabled")
    
    def clear_all_treeviews(self):
        """Clear all treeview data"""
        trees = [
            self.mcx_future_tree, self.mcx_option_tree,
            self.nfo_future_tree, self.nfo_option_tree,
            self.positions_tree, self.order_tree
        ]
        
        for tree in trees:
            for item in tree.get_children():
                tree.delete(item)
    
    def initialize_realtime_data(self):
        """Initialize real-time data streaming"""
        try:
            self.kws = KiteTicker(
                self.kite.api_key, 
                self.kite.access_token
            )
            
            # Set callback functions
            self.kws.on_ticks = self.on_ticks
            self.kws.on_connect = self.on_connect
            self.kws.on_close = self.on_close
            
            # Start WebSocket in a separate thread
            self.ws_thread = threading.Thread(target=self.kws.connect, daemon=True)
            self.ws_thread.start()
            
        except Exception as e:
            logger.error(f"WebSocket initialization failed: {e}")
    
    def on_connect(self, ws, response):
        """WebSocket connect callback"""
        self.is_connected = True
        self.status_var.set("WebSocket connected - Ready for trading")
        logger.info("WebSocket connected")
    
    def on_close(self, ws, code, reason):
        """WebSocket close callback"""
        self.is_connected = False
        self.status_var.set("WebSocket disconnected")
        logger.info("WebSocket disconnected")
    
    def on_ticks(self, ws, ticks):
        """WebSocket ticks callback"""
        for tick in ticks:
            self.data_queue.put(tick)
    
    def process_queue(self):
        """Process data from the queue"""
        try:
            while True:
                try:
                    tick = self.data_queue.get_nowait()
                    self.update_realtime_data(tick)
                except queue.Empty:
                    break
        except Exception as e:
            logger.error(f"Error processing queue: {e}")
        
        # Schedule next processing
        self.root.after(100, self.process_queue)
    
    def update_realtime_data(self, tick):
        """Update real-time data in GUI"""
        try:
            instrument_token = tick['instrument_token']
            ltp = tick.get('last_price', 0)
            volume = tick.get('volume', 0)
            oi = tick.get('oi', 0)
            change_percent = tick.get('change', 0)
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Store the data
            self.realtime_data[instrument_token] = {
                'ltp': ltp,
                'volume': volume,
                'oi': oi,
                'change_percent': change_percent,
                'timestamp': timestamp
            }
            
            # Update all treeviews
            self.update_all_treeviews()
            
        except Exception as e:
            logger.error(f"Error updating real-time data: {e}")
    
    def update_all_treeviews(self):
        """Update all treeviews with latest data"""
        # This would be called to refresh all market data displays
        pass
    
    def load_all_instruments(self):
        """Load all instruments for all segments"""
        try:
            if not self.kite:
                return
                
            self.status_var.set("Loading instruments...")
            instruments = self.kite.instruments()
            
            # Store instruments by segment and type
            self.instruments_data = {
                'MCX_FUT': [inst for inst in instruments if inst['segment'] == 'MCX' and inst['instrument_type'] == 'FUT'],
                'MCX_OPT': [inst for inst in instruments if inst['segment'] == 'MCX' and inst['instrument_type'] == 'OPT'],
                'NFO_FUT': [inst for inst in instruments if inst['segment'] == 'NFO' and inst['instrument_type'] == 'FUT'],
                'NFO_OPT': [inst for inst in instruments if inst['segment'] == 'NFO' and inst['instrument_type'] == 'OPT']
            }
            
            # Populate initial data
            self.refresh_mcx_future()
            self.refresh_mcx_option()
            self.refresh_nfo_future()
            self.refresh_nfo_option()
            
            self.status_var.set("Instruments loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading instruments: {e}")
            self.status_var.set(f"Error loading instruments: {str(e)}")
    
    def refresh_mcx_future(self):
        """Refresh MCX Future instruments"""
        try:
            for item in self.mcx_future_tree.get_children():
                self.mcx_future_tree.delete(item)
            
            instruments = self.instruments_data.get('MCX_FUT', [])
            for inst in instruments[:50]:  # Show first 50 instruments
                token = inst['instrument_token']
                realtime = self.realtime_data.get(token, {})
                
                self.mcx_future_tree.insert("", "end", values=(
                    inst['tradingsymbol'],
                    realtime.get('ltp', '0.00'),
                    f"{realtime.get('change_percent', '0.00')}%",
                    realtime.get('volume', '0'),
                    realtime.get('oi', '0'),
                    realtime.get('timestamp', '--:--:--')
                ))
                
        except Exception as e:
            logger.error(f"Error refreshing MCX futures: {e}")
    
    def refresh_mcx_option(self):
        """Refresh MCX Option instruments"""
        try:
            for item in self.mcx_option_tree.get_children():
                self.mcx_option_tree.delete(item)
            
            instruments = self.instruments_data.get('MCX_OPT', [])
            for inst in instruments[:50]:  # Show first 50 instruments
                token = inst['instrument_token']
                realtime = self.realtime_data.get(token, {})
                
                self.mcx_option_tree.insert("", "end", values=(
                    inst['tradingsymbol'],
                    realtime.get('ltp', '0.00'),
                    f"{realtime.get('change_percent', '0.00')}%",
                    realtime.get('volume', '0'),
                    realtime.get('oi', '0'),
                    '0.00',  # IV - would need calculation
                    realtime.get('timestamp', '--:--:--')
                ))
                
        except Exception as e:
            logger.error(f"Error refreshing MCX options: {e}")
    
    def refresh_nfo_future(self):
        """Refresh NFO Future instruments"""
        try:
            for item in self.nfo_future_tree.get_children():
                self.nfo_future_tree.delete(item)
            
            instruments = self.instruments_data.get('NFO_FUT', [])
            for inst in instruments[:50]:  # Show first 50 instruments
                token = inst['instrument_token']
                realtime = self.realtime_data.get(token, {})
                
                self.nfo_future_tree.insert("", "end", values=(
                    inst['tradingsymbol'],
                    realtime.get('ltp', '0.00'),
                    f"{realtime.get('change_percent', '0.00')}%",
                    realtime.get('volume', '0'),
                    realtime.get('oi', '0'),
                    realtime.get('timestamp', '--:--:--')
                ))
                
        except Exception as e:
            logger.error(f"Error refreshing NFO futures: {e}")
    
    def refresh_nfo_option(self):
        """Refresh NFO Option instruments"""
        try:
            for item in self.nfo_option_tree.get_children():
                self.nfo_option_tree.delete(item)
            
            instruments = self.instruments_data.get('NFO_OPT', [])
            for inst in instruments[:50]:  # Show first 50 instruments
                token = inst['instrument_token']
                realtime = self.realtime_data.get(token, {})
                
                self.nfo_option_tree.insert("", "end", values=(
                    inst['tradingsymbol'],
                    realtime.get('ltp', '0.00'),
                    f"{realtime.get('change_percent', '0.00')}%",
                    realtime.get('volume', '0'),
                    realtime.get('oi', '0'),
                    '0.00',  # IV - would need calculation
                    realtime.get('timestamp', '--:--:--')
                ))
                
        except Exception as e:
            logger.error(f"Error refreshing NFO options: {e}")
    
    def search_instruments(self, tree_type):
        """Search instruments in the specified tree"""
        # Implementation for search functionality
        pass
    
    def subscribe_selected_instrument(self, tree_type):
        """Subscribe to selected instrument"""
        try:
            if tree_type == "mcx_future":
                tree = self.mcx_future_tree
            elif tree_type == "mcx_option":
                tree = self.mcx_option_tree
            elif tree_type == "nfo_future":
                tree = self.nfo_future_tree
            elif tree_type == "nfo_option":
                tree = self.nfo_option_tree
            else:
                return
            
            selection = tree.selection()
            if selection:
                item = tree.item(selection[0])
                symbol = item['values'][0]
                
                # Find instrument token
                for seg_type, instruments in self.instruments_data.items():
                    for inst in instruments:
                        if inst['tradingsymbol'] == symbol:
                            if self.kws and self.is_connected:
                                self.kws.subscribe([inst['instrument_token']])
                                self.kws.set_mode(self.kws.MODE_LTP, [inst['instrument_token']])
                                self.status_var.set(f"Subscribed to {symbol}")
                            break
            
        except Exception as e:
            logger.error(f"Error subscribing to instrument: {e}")
    
    def subscribe_segment(self, segment, inst_type):
        """Subscribe to all instruments in a segment"""
        try:
            key = f"{segment}_{inst_type}"
            instruments = self.instruments_data.get(key, [])
            
            if instruments and self.kws and self.is_connected:
                tokens = [inst['instrument_token'] for inst in instruments[:50]]  # Limit to 50
                self.kws.subscribe(tokens)
                self.kws.set_mode(self.kws.MODE_LTP, tokens)
                self.status_var.set(f"Subscribed to {len(tokens)} {segment} {inst_type} instruments")
            
        except Exception as e:
            logger.error(f"Error subscribing to segment: {e}")
    
    def refresh_positions(self):
        """Refresh positions and P&L"""
        try:
            if not self.kite:
                return
                
            positions = self.kite.positions()
            net_positions = positions['net']
            
            # Clear existing positions
            for item in self.positions_tree.get_children():
                self.positions_tree.delete(item)
            
            total_pnl = 0
            realized_pnl = 0
            unrealized_pnl = 0
            
            for position in net_positions:
                if position['quantity'] != 0:
                    # Calculate P&L
                    pnl = position['pnl']
                    total_pnl += pnl
                    
                    if pnl > 0:
                        realized_pnl += pnl
                    else:
                        unrealized_pnl += pnl
                    
                    # Calculate change percentage
                    avg_price = position['average_price']
                    ltp = position['last_price']
                    change_pct = ((ltp - avg_price) / avg_price * 100) if avg_price > 0 else 0
                    
                    # Add to treeview
                    self.positions_tree.insert("", "end", values=(
                        position['tradingsymbol'],
                        position['quantity'],
                        f"{avg_price:.2f}",
                        f"{ltp:.2f}",
                        f"{pnl:.2f}",
                        f"{change_pct:.2f}%",
                        "Close"
                    ))
            
            # Update P&L display
            self.total_pnl_var.set(f"₹{total_pnl:.2f}")
            self.realized_pnl_var.set(f"₹{realized_pnl:.2f}")
            self.unrealized_pnl_var.set(f"₹{unrealized_pnl:.2f}")
            
            self.status_var.set("Positions refreshed")
            
        except Exception as e:
            logger.error(f"Error refreshing positions: {e}")
            self.status_var.set(f"Error refreshing positions: {str(e)}")
    
    def close_selected_position(self, event):
        """Close selected position on double click"""
        try:
            selection = self.positions_tree.selection()
            if selection:
                item = self.positions_tree.item(selection[0])
                values = item['values']
                symbol = values[0]
                quantity = int(values[1])
                
                # Determine transaction type based on quantity
                transaction_type = "SELL" if quantity > 0 else "BUY"
                quantity = abs(quantity)
                
                # Place order to close position
                order_id = self.kite.place_order(
                    tradingsymbol=symbol,
                    exchange=self.kite.EXCHANGE_NFO if "NFO" in symbol else self.kite.EXCHANGE_MCX,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_NRML,
                    variety=self.kite.VARIETY_REGULAR
                )
                
                self.status_var.set(f"Closing position: {symbol} - Order ID: {order_id}")
                self.refresh_positions()
                self.refresh_orders()
                
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            messagebox.showerror("Error", f"Failed to close position: {str(e)}")
    
    def close_all_positions(self):
        """Close all open positions"""
        try:
            if not self.kite:
                return
                
            positions = self.kite.positions()['net']
            closed_count = 0
            
            for position in positions:
                if position['quantity'] != 0:
                    symbol = position['tradingsymbol']
                    quantity = abs(position['quantity'])
                    transaction_type = "SELL" if position['quantity'] > 0 else "BUY"
                    
                    order_id = self.kite.place_order(
                        tradingsymbol=symbol,
                        exchange=position['exchange'],
                        transaction_type=transaction_type,
                        quantity=quantity,
                        order_type=self.kite.ORDER_TYPE_MARKET,
                        product=self.kite.PRODUCT_NRML
                    )
                    
                    closed_count += 1
                    logger.info(f"Closed position: {symbol} - Order ID: {order_id}")
            
            self.status_var.set(f"Closed {closed_count} positions")
            self.refresh_positions()
            self.refresh_orders()
            messagebox.showinfo("Success", f"Closed {closed_count} positions")
            
        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            messagebox.showerror("Error", f"Failed to close positions: {str(e)}")
    
    def refresh_orders(self):
        """Refresh order book"""
        try:
            if not self.kite:
                return
                
            orders = self.kite.orders()
            
            # Clear existing orders
            for item in self.order_tree.get_children():
                self.order_tree.delete(item)
            
            for order in orders[-20:]:  # Show last 20 orders
                if order['status'] in ['TRIGGER PENDING', 'OPEN', 'COMPLETE', 'REJECTED']:
                    self.order_tree.insert("", "end", values=(
                        order['order_id'],
                        order['tradingsymbol'],
                        order['transaction_type'],
                        order['quantity'],
                        order['price'],
                        order['status']
                    ))
                    
        except Exception as e:
            logger.error(f"Error refreshing orders: {e}")
    
    def place_buy_order(self):
        """Place a buy order"""
        self.place_order("BUY")
    
    def place_sell_order(self):
        """Place a sell order"""
        self.place_order("SELL")
    
    def place_order(self, transaction_type):
        """Place an order"""
        try:
            if not self.kite:
                messagebox.showerror("Error", "Not logged in")
                return
                
            instrument = self.instrument_var.get()
            quantity = int(self.quantity_var.get())
            price_type = self.price_type_var.get()
            price = float(self.price_var.get()) if price_type == "LIMIT" and self.price_var.get() else 0
            
            if not instrument:
                messagebox.showerror("Error", "Please enter instrument symbol")
                return
            
            # Determine exchange
            exchange = self.kite.EXCHANGE_NFO if "NFO" in instrument else self.kite.EXCHANGE_MCX
            
            if price_type == "MARKET":
                order_id = self.kite.place_order(
                    tradingsymbol=instrument,
                    exchange=exchange,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_NRML,
                    variety=self.kite.VARIETY_REGULAR
                )
            else:
                if price <= 0:
                    messagebox.showerror("Error", "Please enter valid price for limit order")
                    return
                    
                order_id = self.kite.place_order(
                    tradingsymbol=instrument,
                    exchange=exchange,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_LIMIT,
                    price=price,
                    product=self.kite.PRODUCT_NRML,
                    variety=self.kite.VARIETY_REGULAR
                )
            
            self.status_var.set(f"{transaction_type} order placed: {order_id}")
            self.refresh_orders()
            messagebox.showinfo("Success", f"{transaction_type} order placed successfully!\nOrder ID: {order_id}")
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            self.status_var.set(f"Order error: {str(e)}")
            messagebox.showerror("Order Error", f"Failed to place order: {str(e)}")
    
    def place_basket_order(self):
        """Place basket order (buy and sell together)"""
        try:
            if not self.kite:
                messagebox.showerror("Error", "Not logged in")
                return
                
            buy_instrument = self.buy_instrument_var.get()
            sell_instrument = self.sell_instrument_var.get()
            quantity = int(self.basket_quantity_var.get())
            
            if not buy_instrument and not sell_instrument:
                messagebox.showerror("Error", "Please enter at least one instrument")
                return
            
            order_ids = []
            
            # Place buy order
            if buy_instrument:
                buy_exchange = self.kite.EXCHANGE_NFO if "NFO" in buy_instrument else self.kite.EXCHANGE_MCX
                buy_order_id = self.kite.place_order(
                    tradingsymbol=buy_instrument,
                    exchange=buy_exchange,
                    transaction_type="BUY",
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_NRML
                )
                order_ids.append(f"BUY: {buy_order_id}")
            
            # Place sell order
            if sell_instrument:
                sell_exchange = self.kite.EXCHANGE_NFO if "NFO" in sell_instrument else self.kite.EXCHANGE_MCX
                sell_order_id = self.kite.place_order(
                    tradingsymbol=sell_instrument,
                    exchange=sell_exchange,
                    transaction_type="SELL",
                    quantity=quantity,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_NRML
                )
                order_ids.append(f"SELL: {sell_order_id}")
            
            self.status_var.set("Basket order placed successfully")
            self.refresh_orders()
            messagebox.showinfo("Success", f"Basket order placed!\nOrder IDs: {', '.join(order_ids)}")
            
        except Exception as e:
            logger.error(f"Error placing basket order: {e}")
            self.status_var.set(f"Basket order error: {str(e)}")
            messagebox.showerror("Basket Order Error", f"Failed to place basket order: {str(e)}")

def main():
    """Main function to start the application"""
    try:
        root = tk.Tk()
        app = ZerodhaTradingApp(root)
        
        # Set window icon and title
        root.title("Zerodha Trading Terminal - Complete Edition")
        
        # Start the application
        root.mainloop()
        
    except Exception as e:
        logger.error(f"Application failed to start: {e}")
        messagebox.showerror("Startup Error", f"Application failed to start: {str(e)}")

if __name__ == "__main__":
    main()