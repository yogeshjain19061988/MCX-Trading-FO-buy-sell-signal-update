import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect
import datetime
import threading
import time
import json
import os
from typing import Dict, List

class ZerodhaFibonacciGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha Fibonacci Trading System")
        self.root.geometry("1400x900")
        
        # Initialize API variables
        self.api_key = ""
        self.access_token = ""
        self.kite = None
        
        # Data storage
        self.instruments_df = None
        self.market_data = {}
        
        # Create main interface
        self.create_login_section()
        self.create_main_interface()
        
        # Load instruments in background
        self.load_instruments_background()
    
    def create_login_section(self):
        """Create login section"""
        login_frame = ttk.LabelFrame(self.root, text="Zerodha API Login", padding=10)
        login_frame.grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky="ew")
        
        # API Key
        ttk.Label(login_frame, text="API Key:").grid(row=0, column=0, padx=5, pady=2)
        self.api_key_entry = ttk.Entry(login_frame, width=40, show="*")
        self.api_key_entry.grid(row=0, column=1, padx=5, pady=2)
        
        # Access Token
        ttk.Label(login_frame, text="Access Token:").grid(row=0, column=2, padx=5, pady=2)
        self.access_token_entry = ttk.Entry(login_frame, width=40, show="*")
        self.access_token_entry.grid(row=0, column=3, padx=5, pady=2)
        
        # Login Button
        self.login_btn = ttk.Button(login_frame, text="Login", command=self.login)
        self.login_btn.grid(row=0, column=4, padx=10, pady=2)
        
        # Load from config
        ttk.Button(login_frame, text="Load Config", command=self.load_config).grid(row=0, column=5, padx=5, pady=2)
        ttk.Button(login_frame, text="Save Config", command=self.save_config).grid(row=0, column=6, padx=5, pady=2)
        
        # Status
        self.status_var = tk.StringVar(value="Not Connected")
        ttk.Label(login_frame, textvariable=self.status_var).grid(row=1, column=0, columnspan=7, pady=5)
    
    def create_main_interface(self):
        """Create main trading interface"""
        # Create notebook for different segments
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, columnspan=4, padx=10, pady=10, sticky="nsew")
        
        # Create tabs
        self.stock_futures_tab = ttk.Frame(self.notebook)
        self.stock_options_tab = ttk.Frame(self.notebook)
        self.mcx_futures_tab = ttk.Frame(self.notebook)
        self.mcx_options_tab = ttk.Frame(self.notebook)
        self.portfolio_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.stock_futures_tab, text="Stock Futures")
        self.notebook.add(self.stock_options_tab, text="Stock Options")
        self.notebook.add(self.mcx_futures_tab, text="MCX Futures")
        self.notebook.add(self.mcx_options_tab, text="MCX Options")
        self.notebook.add(self.portfolio_tab, text="Portfolio")
        
        # Create each tab
        self.create_stock_futures_tab()
        self.create_stock_options_tab()
        self.create_mcx_futures_tab()
        self.create_mcx_options_tab()
        self.create_portfolio_tab()
        
        # Configure grid weights
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
    
    def create_stock_futures_tab(self):
        """Create stock futures trading interface"""
        # Main frame
        main_frame = ttk.Frame(self.stock_futures_tab)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel - Controls
        left_frame = ttk.LabelFrame(main_frame, text="Stock Futures Controls", width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)
        
        # Symbol selection
        ttk.Label(left_frame, text="Select Stock:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_future_var = tk.StringVar()
        self.stock_future_combo = ttk.Combobox(left_frame, textvariable=self.stock_future_var, state="readonly")
        self.stock_future_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # Expiry selection
        ttk.Label(left_frame, text="Expiry:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_future_expiry_var = tk.StringVar()
        self.stock_future_expiry_combo = ttk.Combobox(left_frame, textvariable=self.stock_future_expiry_var, state="readonly")
        self.stock_future_expiry_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # Timeframe selection
        ttk.Label(left_frame, text="Timeframe:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_future_tf_var = tk.StringVar(value="day")
        timeframe_combo = ttk.Combobox(left_frame, textvariable=self.stock_future_tf_var, 
                                     values=["minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"])
        timeframe_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # Analysis button
        ttk.Button(left_frame, text="Analyze Fibonacci", 
                  command=lambda: self.analyze_instrument("stock_futures")).pack(pady=10)
        
        # Right panel - Results
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Results text area
        ttk.Label(right_frame, text="Fibonacci Analysis Results:").pack(anchor=tk.W)
        self.stock_future_results = tk.Text(right_frame, height=20, width=80)
        self.stock_future_results.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Signals frame
        signals_frame = ttk.LabelFrame(right_frame, text="Trading Signals")
        signals_frame.pack(fill=tk.X, pady=5)
        
        self.stock_future_signals = tk.Text(signals_frame, height=6, width=80)
        self.stock_future_signals.pack(fill=tk.X, padx=5, pady=5)
    
    def create_stock_options_tab(self):
        """Create stock options trading interface"""
        main_frame = ttk.Frame(self.stock_options_tab)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel
        left_frame = ttk.LabelFrame(main_frame, text="Stock Options Controls", width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)
        
        # Symbol selection
        ttk.Label(left_frame, text="Select Stock:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_option_var = tk.StringVar()
        self.stock_option_combo = ttk.Combobox(left_frame, textvariable=self.stock_option_var, state="readonly")
        self.stock_option_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # Option type
        ttk.Label(left_frame, text="Option Type:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_option_type_var = tk.StringVar(value="CE")
        option_type_combo = ttk.Combobox(left_frame, textvariable=self.stock_option_type_var, 
                                       values=["CE", "PE"])
        option_type_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # Strike price
        ttk.Label(left_frame, text="Strike Price:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_option_strike_var = tk.StringVar()
        self.stock_option_strike_combo = ttk.Combobox(left_frame, textvariable=self.stock_option_strike_var)
        self.stock_option_strike_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # Expiry selection
        ttk.Label(left_frame, text="Expiry:").pack(anchor=tk.W, padx=5, pady=2)
        self.stock_option_expiry_var = tk.StringVar()
        self.stock_option_expiry_combo = ttk.Combobox(left_frame, textvariable=self.stock_option_expiry_var, state="readonly")
        self.stock_option_expiry_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(left_frame, text="Analyze Fibonacci", 
                  command=lambda: self.analyze_instrument("stock_options")).pack(pady=10)
        
        # Right panel
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(right_frame, text="Fibonacci Analysis Results:").pack(anchor=tk.W)
        self.stock_option_results = tk.Text(right_frame, height=20, width=80)
        self.stock_option_results.pack(fill=tk.BOTH, expand=True, pady=5)
        
        signals_frame = ttk.LabelFrame(right_frame, text="Trading Signals")
        signals_frame.pack(fill=tk.X, pady=5)
        
        self.stock_option_signals = tk.Text(signals_frame, height=6, width=80)
        self.stock_option_signals.pack(fill=tk.X, padx=5, pady=5)
    
    def create_mcx_futures_tab(self):
        """Create MCX futures trading interface"""
        main_frame = ttk.Frame(self.mcx_futures_tab)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_frame = ttk.LabelFrame(main_frame, text="MCX Futures Controls", width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)
        
        ttk.Label(left_frame, text="Select Commodity:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_future_var = tk.StringVar()
        self.mcx_future_combo = ttk.Combobox(left_frame, textvariable=self.mcx_future_var, state="readonly")
        self.mcx_future_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(left_frame, text="Expiry:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_future_expiry_var = tk.StringVar()
        self.mcx_future_expiry_combo = ttk.Combobox(left_frame, textvariable=self.mcx_future_expiry_var, state="readonly")
        self.mcx_future_expiry_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(left_frame, text="Timeframe:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_future_tf_var = tk.StringVar(value="day")
        timeframe_combo = ttk.Combobox(left_frame, textvariable=self.mcx_future_tf_var, 
                                     values=["minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day"])
        timeframe_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(left_frame, text="Analyze Fibonacci", 
                  command=lambda: self.analyze_instrument("mcx_futures")).pack(pady=10)
        
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(right_frame, text="Fibonacci Analysis Results:").pack(anchor=tk.W)
        self.mcx_future_results = tk.Text(right_frame, height=20, width=80)
        self.mcx_future_results.pack(fill=tk.BOTH, expand=True, pady=5)
        
        signals_frame = ttk.LabelFrame(right_frame, text="Trading Signals")
        signals_frame.pack(fill=tk.X, pady=5)
        
        self.mcx_future_signals = tk.Text(signals_frame, height=6, width=80)
        self.mcx_future_signals.pack(fill=tk.X, padx=5, pady=5)
    
    def create_mcx_options_tab(self):
        """Create MCX options trading interface"""
        main_frame = ttk.Frame(self.mcx_options_tab)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_frame = ttk.LabelFrame(main_frame, text="MCX Options Controls", width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        left_frame.pack_propagate(False)
        
        ttk.Label(left_frame, text="Select Commodity:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_option_var = tk.StringVar()
        self.mcx_option_combo = ttk.Combobox(left_frame, textvariable=self.mcx_option_var, state="readonly")
        self.mcx_option_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(left_frame, text="Option Type:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_option_type_var = tk.StringVar(value="CE")
        option_type_combo = ttk.Combobox(left_frame, textvariable=self.mcx_option_type_var, 
                                       values=["CE", "PE"])
        option_type_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(left_frame, text="Strike Price:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_option_strike_var = tk.StringVar()
        self.mcx_option_strike_combo = ttk.Combobox(left_frame, textvariable=self.mcx_option_strike_var)
        self.mcx_option_strike_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(left_frame, text="Expiry:").pack(anchor=tk.W, padx=5, pady=2)
        self.mcx_option_expiry_var = tk.StringVar()
        self.mcx_option_expiry_combo = ttk.Combobox(left_frame, textvariable=self.mcx_option_expiry_var, state="readonly")
        self.mcx_option_expiry_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(left_frame, text="Analyze Fibonacci", 
                  command=lambda: self.analyze_instrument("mcx_options")).pack(pady=10)
        
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(right_frame, text="Fibonacci Analysis Results:").pack(anchor=tk.W)
        self.mcx_option_results = tk.Text(right_frame, height=20, width=80)
        self.mcx_option_results.pack(fill=tk.BOTH, expand=True, pady=5)
        
        signals_frame = ttk.LabelFrame(right_frame, text="Trading Signals")
        signals_frame.pack(fill=tk.X, pady=5)
        
        self.mcx_option_signals = tk.Text(signals_frame, height=6, width=80)
        self.mcx_option_signals.pack(fill=tk.X, padx=5, pady=5)
    
    def create_portfolio_tab(self):
        """Create portfolio management tab"""
        main_frame = ttk.Frame(self.portfolio_tab)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Portfolio overview
        overview_frame = ttk.LabelFrame(main_frame, text="Portfolio Overview")
        overview_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.portfolio_text = tk.Text(overview_frame, height=10, width=100)
        self.portfolio_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Refresh button
        ttk.Button(overview_frame, text="Refresh Portfolio", 
                  command=self.refresh_portfolio).pack(pady=5)
        
        # Positions frame
        positions_frame = ttk.LabelFrame(main_frame, text="Current Positions")
        positions_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create treeview for positions
        columns = ("Instrument", "Quantity", "Average Price", "Current Price", "P&L")
        self.positions_tree = ttk.Treeview(positions_frame, columns=columns, show="headings")
        
        for col in columns:
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=120)
        
        self.positions_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def login(self):
        """Login to Zerodha API"""
        self.api_key = self.api_key_entry.get()
        self.access_token = self.access_token_entry.get()
        
        if not self.api_key or not self.access_token:
            messagebox.showerror("Error", "Please enter API Key and Access Token")
            return
        
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Test connection
            profile = self.kite.profile()
            self.status_var.set(f"Connected: {profile['user_name']}")
            messagebox.showinfo("Success", f"Connected as {profile['user_name']}")
            
            # Enable analysis features
            self.enable_analysis_features()
            
        except Exception as e:
            messagebox.showerror("Login Failed", f"Error: {str(e)}")
            self.status_var.set("Login Failed")
    
    def load_instruments_background(self):
        """Load instruments in background thread"""
        def load_thread():
            try:
                # This would typically load from Zerodha API
                # For demo, we'll create sample data
                time.sleep(1)  # Simulate loading
                
                # Sample instruments data
                self.instruments_df = pd.DataFrame({
                    'tradingsymbol': ['RELIANCE', 'TCS', 'INFY', 'HDFC', 'ICICIBANK',
                                     'GOLD', 'SILVER', 'CRUDEOIL', 'NATURALGAS'],
                    'instrument_type': ['FUT', 'FUT', 'FUT', 'FUT', 'FUT',
                                      'FUT', 'FUT', 'FUT', 'FUT'],
                    'exchange': ['NFO', 'NFO', 'NFO', 'NFO', 'NFO',
                               'MCX', 'MCX', 'MCX', 'MCX'],
                    'segment': ['stock_futures', 'stock_futures', 'stock_futures', 
                               'stock_futures', 'stock_futures',
                               'mcx_futures', 'mcx_futures', 'mcx_futures', 'mcx_futures']
                })
                
                # Update UI in main thread
                self.root.after(0, self.update_instrument_lists)
                
            except Exception as e:
                print(f"Error loading instruments: {e}")
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def update_instrument_lists(self):
        """Update instrument dropdowns with loaded data"""
        if self.instruments_df is not None:
            # Stock futures
            stock_futures = self.instruments_df[
                self.instruments_df['segment'] == 'stock_futures'
            ]['tradingsymbol'].tolist()
            self.stock_future_combo['values'] = stock_futures
            self.stock_option_combo['values'] = stock_futures
            
            # MCX futures
            mcx_futures = self.instruments_df[
                self.instruments_df['segment'] == 'mcx_futures'
            ]['tradingsymbol'].tolist()
            self.mcx_future_combo['values'] = mcx_futures
            self.mcx_option_combo['values'] = mcx_futures
            
            # Sample expiry dates
            expiries = ["2024-01-25", "2024-02-29", "2024-03-28"]
            for combo in [self.stock_future_expiry_combo, self.stock_option_expiry_combo,
                         self.mcx_future_expiry_combo, self.mcx_option_expiry_combo]:
                combo['values'] = expiries
    
    def enable_analysis_features(self):
        """Enable analysis features after successful login"""
        # Enable all analysis buttons
        for widget in self.root.winfo_children():
            if isinstance(widget, ttk.Button):
                widget['state'] = 'normal'
    
    def analyze_instrument(self, instrument_type):
        """Analyze Fibonacci levels for selected instrument"""
        if not self.kite:
            messagebox.showerror("Error", "Please login first")
            return
        
        # Get selected parameters based on instrument type
        if instrument_type == "stock_futures":
            symbol = self.stock_future_var.get()
            expiry = self.stock_future_expiry_var.get()
            timeframe = self.stock_future_tf_var.get()
            results_widget = self.stock_future_results
            signals_widget = self.stock_future_signals
        
        elif instrument_type == "stock_options":
            symbol = self.stock_option_var.get()
            expiry = self.stock_option_expiry_var.get()
            timeframe = "day"  # Options typically analyzed daily
            results_widget = self.stock_option_results
            signals_widget = self.stock_option_signals
        
        elif instrument_type == "mcx_futures":
            symbol = self.mcx_future_var.get()
            expiry = self.mcx_future_expiry_var.get()
            timeframe = self.mcx_future_tf_var.get()
            results_widget = self.mcx_future_results
            signals_widget = self.mcx_future_signals
        
        elif instrument_type == "mcx_options":
            symbol = self.mcx_option_var.get()
            expiry = self.mcx_option_expiry_var.get()
            timeframe = "day"
            results_widget = self.mcx_option_results
            signals_widget = self.mcx_option_signals
        
        else:
            return
        
        if not symbol:
            messagebox.showerror("Error", "Please select an instrument")
            return
        
        # Run analysis in background thread
        def analysis_thread():
            try:
                # Simulate Fibonacci analysis (replace with actual analysis)
                result = self.perform_fibonacci_analysis(symbol, timeframe)
                
                # Update UI in main thread
                self.root.after(0, lambda: self.display_analysis_results(
                    result, results_widget, signals_widget, symbol
                ))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Analysis Error", f"Error analyzing {symbol}: {str(e)}"
                ))
        
        threading.Thread(target=analysis_thread, daemon=True).start()
    
    def perform_fibonacci_analysis(self, symbol, timeframe):
        """Perform Fibonacci analysis (simulated)"""
        # In real implementation, this would fetch historical data and calculate Fibonacci
        time.sleep(2)  # Simulate analysis time
        
        # Simulated Fibonacci levels
        current_price = np.random.uniform(1000, 5000)
        swing_high = current_price * 1.1
        swing_low = current_price * 0.9
        
        fib_levels = {
            '0%': swing_high,
            '23.6%': swing_high - (0.236 * (swing_high - swing_low)),
            '38.2%': swing_high - (0.382 * (swing_high - swing_low)),
            '50%': swing_high - (0.5 * (swing_high - swing_low)),
            '61.8%': swing_high - (0.618 * (swing_high - swing_low)),
            '78.6%': swing_high - (0.786 * (swing_high - swing_low)),
            '100%': swing_low
        }
        
        # Determine trend
        trend = "Uptrend" if current_price > fib_levels['50%'] else "Downtrend"
        
        # Generate signals
        signals = self.generate_trading_signals(current_price, fib_levels, trend)
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'fibonacci_levels': fib_levels,
            'trend': trend,
            'signals': signals,
            'timestamp': datetime.datetime.now()
        }
    
    def generate_trading_signals(self, current_price, fib_levels, trend):
        """Generate trading signals based on Fibonacci levels"""
        signals = []
        tolerance = current_price * 0.01  # 1% tolerance
        
        key_levels = ['38.2%', '50%', '61.8%']
        
        for level in key_levels:
            fib_price = fib_levels[level]
            if abs(current_price - fib_price) <= tolerance:
                if trend == "Uptrend":
                    if level in ['38.2%', '50%']:
                        signals.append(f"BUY opportunity near {level} retracement")
                    elif level == '61.8%':
                        signals.append(f"STRONG BUY - Deep retracement to {level}")
                else:
                    if level in ['38.2%', '50%']:
                        signals.append(f"SELL opportunity near {level} retracement")
                    elif level == '61.8%':
                        signals.append(f"STRONG SELL - Deep retracement to {level}")
        
        if not signals:
            signals.append("No strong Fibonacci signals at current levels")
        
        return signals
    
    def display_analysis_results(self, result, results_widget, signals_widget, symbol):
        """Display analysis results in the text widgets"""
        # Clear previous results
        results_widget.delete(1.0, tk.END)
        signals_widget.delete(1.0, tk.END)
        
        # Display main results
        results_widget.insert(tk.END, f"Fibonacci Analysis for {symbol}\n")
        results_widget.insert(tk.END, f"Time: {result['timestamp']}\n")
        results_widget.insert(tk.END, f"Current Price: {result['current_price']:.2f}\n")
        results_widget.insert(tk.END, f"Trend: {result['trend']}\n\n")
        results_widget.insert(tk.END, "Fibonacci Levels:\n")
        results_widget.insert(tk.END, "-" * 40 + "\n")
        
        for level, price in result['fibonacci_levels'].items():
            diff = result['current_price'] - price
            pct_diff = (diff / price) * 100
            results_widget.insert(tk.END, 
                                f"{level:>6}: {price:8.2f} | Diff: {diff:7.2f} ({pct_diff:5.1f}%)\n")
        
        # Display signals
        signals_widget.insert(tk.END, "Trading Signals:\n")
        signals_widget.insert(tk.END, "-" * 30 + "\n")
        for signal in result['signals']:
            signals_widget.insert(tk.END, f"• {signal}\n")
    
    def refresh_portfolio(self):
        """Refresh portfolio information"""
        if not self.kite:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            # Get portfolio (simulated)
            portfolio_text = "Portfolio Summary:\n"
            portfolio_text += "Total Value: ₹1,50,000\n"
            portfolio_text += "Available Cash: ₹25,000\n"
            portfolio_text += "Total P&L: ₹5,250\n"
            portfolio_text += "Unrealized P&L: ₹2,100\n"
            
            self.portfolio_text.delete(1.0, tk.END)
            self.portfolio_text.insert(tk.END, portfolio_text)
            
            # Update positions (simulated)
            self.update_positions_tree()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh portfolio: {str(e)}")
    
    def update_positions_tree(self):
        """Update positions treeview with current positions"""
        # Clear existing positions
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        
        # Add sample positions
        sample_positions = [
            ("RELIANCE-FUT", 100, 2450.50, 2480.75, "+3,025"),
            ("TCS-FUT", 50, 3450.25, 3420.50, "-1,487"),
            ("GOLD-FUT", 10, 62500.00, 62850.00, "+3,500")
        ]
        
        for pos in sample_positions:
            self.positions_tree.insert("", tk.END, values=pos)
    
    def save_config(self):
        """Save API configuration to file"""
        config = {
            'api_key': self.api_key_entry.get(),
            'access_token': self.access_token_entry.get()
        }
        
        try:
            with open('zerodha_config.json', 'w') as f:
                json.dump(config, f)
            messagebox.showinfo("Success", "Configuration saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {str(e)}")
    
    def load_config(self):
        """Load API configuration from file"""
        try:
            if os.path.exists('zerodha_config.json'):
                with open('zerodha_config.json', 'r') as f:
                    config = json.load(f)
                
                self.api_key_entry.delete(0, tk.END)
                self.api_key_entry.insert(0, config.get('api_key', ''))
                
                self.access_token_entry.delete(0, tk.END)
                self.access_token_entry.insert(0, config.get('access_token', ''))
                
                messagebox.showinfo("Success", "Configuration loaded successfully")
            else:
                messagebox.showinfo("Info", "No saved configuration found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config: {str(e)}")

# Fibonacci Analysis Engine
class FibonacciAnalyzer:
    def __init__(self, kite):
        self.kite = kite
    
    def calculate_fibonacci_levels(self, high, low):
        """Calculate Fibonacci retracement levels"""
        diff = high - low
        
        fib_levels = {
            '0%': high,
            '23.6%': high - (0.236 * diff),
            '38.2%': high - (0.382 * diff),
            '50%': high - (0.5 * diff),
            '61.8%': high - (0.618 * diff),
            '78.6%': high - (0.786 * diff),
            '100%': low,
            '127.2%': low - (0.272 * diff),
            '161.8%': low - (0.618 * diff)
        }
        
        return fib_levels
    
    def get_historical_data(self, instrument_token, from_date, to_date, interval):
        """Fetch historical data from Zerodha"""
        try:
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            return pd.DataFrame(data)
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

# Main application
def main():
    root = tk.Tk()
    app = ZerodhaFibonacciGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()