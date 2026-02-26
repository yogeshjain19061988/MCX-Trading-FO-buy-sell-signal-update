import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
from kiteconnect import KiteConnect
import pandas as pd
import threading
import time
from datetime import datetime, timedelta
import webbrowser
from threading import Thread, Event
import math
from collections import Counter

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha MCX, NFO & NSE Trading Platform")
        self.root.geometry("1800x1000")
        
        # Initialize variables
        self.kite = None
        self.is_logged_in = False
        self.live_data = {}
        self.positions = {}
        self.orders = {}
        self.profit_target = 0
        self.total_pnl = 0
        self.instruments_df = None
        self.nfo_instruments_df = None
        self.live_data_running = False
        self.futures_data_running = False
        self.options_data_running = False
        self.nfo_options_data_running = False
        self.nse_options_data_running = False
        self.selected_buy_futures = {}
        self.selected_sell_futures = {}
        self.selected_single_futures = {}
        self.selected_buy_options = {}
        self.selected_sell_options = {}
        self.selected_single_options = {}
        self.selected_nfo_buy_options = {}
        self.selected_nfo_sell_options = {}
        self.selected_nfo_single_options = {}
        self.selected_nse_buy_options = {}
        self.selected_nse_sell_options = {}
        self.selected_nse_single_options = {}
        
        # Real-time price tracking
        self.price_update_event = Event()
        self.current_prices = {}
        self.real_time_windows = []
        
        # Trailing profit variables
        self.trailing_enabled = False
        self.trailing_activation = 0
        self.trailing_type = "points"
        self.trailing_value = 0
        self.trailing_positions = {}
        

        # For MCX options
        self.options_limit_offset = tk.DoubleVar(value=0.5)
        self.options_offset_type = tk.StringVar(value="Percent")

        # For NFO options
        self.nfo_options_limit_offset = tk.DoubleVar(value=0.5)
        self.nfo_options_offset_type = tk.StringVar(value="Percent")

        # For NSE options
        self.nse_options_limit_offset = tk.DoubleVar(value=0.5)
        self.nse_options_offset_type = tk.StringVar(value="Percent")

        # Load credentials
        self.load_credentials()
        
        # Setup GUI
        self.setup_gui()
        
        # Auto login if credentials exist
        if hasattr(self, 'api_key') and hasattr(self, 'access_token'):
            self.auto_login()
    
    def load_credentials(self):
        """Load API credentials from file"""
        try:
            if os.path.exists('zerodha_credentials.json'):
                with open('zerodha_credentials.json', 'r') as f:
                    creds = json.load(f)
                    self.api_key = creds.get('api_key')
                    self.access_token = creds.get('access_token')
        except Exception as e:
            print(f"Error loading credentials: {e}")
    
    def save_credentials(self):
        """Save API credentials to file"""
        try:
            creds = {
                'api_key': self.api_key,
                'access_token': self.access_token
            }
            with open('zerodha_credentials.json', 'w') as f:
                json.dump(creds, f)
        except Exception as e:
            print(f"Error saving credentials: {e}")
    
    def load_instruments(self):
        """Load MCX instruments"""
        try:
            if self.kite and self.is_logged_in:
                all_instruments = self.kite.instruments("MCX")
                self.instruments_df = pd.DataFrame(all_instruments)
                if 'expiry' in self.instruments_df.columns and self.instruments_df['expiry'].dtype == 'object':
                    self.instruments_df['expiry'] = pd.to_datetime(self.instruments_df['expiry']).dt.date
                print(f"Loaded {len(self.instruments_df)} MCX instruments")
                self.log_message(f"Loaded {len(self.instruments_df)} MCX instruments")
        except Exception as e:
            self.log_message(f"Error loading MCX instruments: {e}")
    
    def load_nfo_instruments(self):
        """Load NFO instruments (includes indices and stocks)"""
        try:
            if self.kite and self.is_logged_in:
                all_instruments = self.kite.instruments("NFO")
                self.nfo_instruments_df = pd.DataFrame(all_instruments)
                if 'expiry' in self.nfo_instruments_df.columns and self.nfo_instruments_df['expiry'].dtype == 'object':
                    self.nfo_instruments_df['expiry'] = pd.to_datetime(self.nfo_instruments_df['expiry']).dt.date
                print(f"Loaded {len(self.nfo_instruments_df)} NFO instruments")
                self.log_message(f"Loaded {len(self.nfo_instruments_df)} NFO instruments")
        except Exception as e:
            self.log_message(f"Error loading NFO instruments: {e}")
    
    def get_all_futures(self):
        """Get all available MCX futures contracts"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            futures_df = self.instruments_df[
                (self.instruments_df['instrument_type'] == 'FUT') |
                (self.instruments_df['name'].str.contains('FUT', na=False))
            ].copy()
            futures_df = futures_df.sort_values(['name', 'expiry'])
            current_date = datetime.now().date()
            futures_df = futures_df[futures_df['expiry'] >= current_date]
            return futures_df[['tradingsymbol', 'name', 'expiry', 'lot_size']].to_dict('records')
        except Exception as e:
            self.log_message(f"Error getting futures: {e}")
            return []
    
    def get_all_options(self, base_symbol=None, min_strike=0, max_strike=0, expiry_month=None):
        """Get MCX options, optionally filtered by strike range and expiry month."""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            options_df = self.instruments_df[
                (self.instruments_df['instrument_type'] == 'CE') |
                (self.instruments_df['instrument_type'] == 'PE') |
                (self.instruments_df['name'].str.contains('CE', na=False)) |
                (self.instruments_df['name'].str.contains('PE', na=False))
            ].copy()
            if base_symbol:
                options_df = options_df[
                    options_df['tradingsymbol'].str.startswith(base_symbol)
                ]
            # Filter by expiry month if provided
            if expiry_month:
                options_df['expiry_dt'] = pd.to_datetime(options_df['expiry'])
                options_df = options_df[options_df['expiry_dt'].dt.strftime('%b %Y') == expiry_month]
            options_df = options_df.sort_values(['name', 'expiry', 'strike'])
            current_date = datetime.now().date()
            options_df = options_df[options_df['expiry'] >= current_date]
            
            # Apply strike range filter if both min and max are > 0
            if min_strike > 0 and max_strike > 0:
                options_df = options_df[
                    (options_df['strike'] >= min_strike) & (options_df['strike'] <= max_strike)
                ]
            return options_df[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
        except Exception as e:
            self.log_message(f"Error getting MCX options: {e}")
            return []
    
    def get_all_nfo_options(self, base_symbol=None, min_strike=0, max_strike=0, expiry_month=None):
        """Get NFO index options, optionally filtered by strike range and expiry month."""
        try:
            if self.nfo_instruments_df is None:
                self.load_nfo_instruments()
                if self.nfo_instruments_df is None:
                    return []
            options_df = self.nfo_instruments_df[
                (self.nfo_instruments_df['instrument_type'] == 'CE') |
                (self.nfo_instruments_df['instrument_type'] == 'PE')
            ].copy()
            if base_symbol:
                options_df = options_df[
                    options_df['tradingsymbol'].str.startswith(base_symbol)
                ]
            if expiry_month:
                options_df['expiry_dt'] = pd.to_datetime(options_df['expiry'])
                options_df = options_df[options_df['expiry_dt'].dt.strftime('%b %Y') == expiry_month]
            options_df = options_df.sort_values(['name', 'expiry', 'strike'])
            current_date = datetime.now().date()
            options_df = options_df[options_df['expiry'] >= current_date]
            
            if min_strike > 0 and max_strike > 0:
                options_df = options_df[
                    (options_df['strike'] >= min_strike) & (options_df['strike'] <= max_strike)
                ]
            return options_df[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
        except Exception as e:
            self.log_message(f"Error getting NFO options: {e}")
            return []
    
    def get_all_nse_stock_options(self, stock_symbol, min_strike=0, max_strike=0, expiry_month=None):
        """Get NSE stock options, optionally filtered by strike range and expiry month."""
        try:
            if self.nfo_instruments_df is None:
                self.load_nfo_instruments()
                if self.nfo_instruments_df is None:
                    return []
            options_df = self.nfo_instruments_df[
                ((self.nfo_instruments_df['instrument_type'] == 'CE') |
                 (self.nfo_instruments_df['instrument_type'] == 'PE')) &
                (self.nfo_instruments_df['name'] == stock_symbol)
            ].copy()
            if expiry_month:
                options_df['expiry_dt'] = pd.to_datetime(options_df['expiry'])
                options_df = options_df[options_df['expiry_dt'].dt.strftime('%b %Y') == expiry_month]
            options_df = options_df.sort_values(['name', 'expiry', 'strike'])
            current_date = datetime.now().date()
            options_df = options_df[options_df['expiry'] >= current_date]
            
            if min_strike > 0 and max_strike > 0:
                options_df = options_df[
                    (options_df['strike'] >= min_strike) & (options_df['strike'] <= max_strike)
                ]
            return options_df[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
        except Exception as e:
            self.log_message(f"Error getting NSE stock options for {stock_symbol}: {e}")
            return []
    
    def get_underlying_ltp(self, symbol, exchange):
        """Fetch current LTP for underlying symbol (index or stock)"""
        try:
            if exchange in ("NFO", "NSE"):
                underlying_exchange = "NSE"
                underlying_symbol = symbol
            elif exchange == "MCX":
                underlying_exchange = "MCX"
                underlying_symbol = symbol
            else:
                return None
            ltp_data = self.kite.ltp(f"{underlying_exchange}:{underlying_symbol}")
            return list(ltp_data.values())[0]['last_price']
        except Exception as e:
            self.log_message(f"Error fetching underlying LTP for {symbol}: {e}")
            return None
    
    def get_strike_interval(self, strikes):
        """Determine strike interval from a list of strikes (assumes sorted)"""
        if len(strikes) < 2:
            return 5  # default
        strikes = sorted(strikes)
        diffs = [strikes[i+1] - strikes[i] for i in range(len(strikes)-1)]
        counter = Counter(diffs)
        return counter.most_common(1)[0][0]
    
    def get_unique_expiry_months(self, exchange, underlying=None):
        """Return sorted list of unique expiry months (as strings) for given exchange/underlying."""
        try:
            if exchange == "MCX":
                df = self.instruments_df
            elif exchange in ("NFO", "NSE"):
                df = self.nfo_instruments_df
            else:
                return []
            if df is None:
                return []
            # Filter options only
            opts = df[df['instrument_type'].isin(['CE', 'PE'])].copy()
            if underlying:
                opts = opts[opts['tradingsymbol'].str.startswith(underlying) | (opts['name'] == underlying)]
            if opts.empty:
                return []
            opts['expiry'] = pd.to_datetime(opts['expiry'])
            months = opts['expiry'].dt.strftime('%b %Y').unique()
            months = sorted(months, key=lambda x: datetime.strptime(x, '%b %Y'))
            return months
        except Exception as e:
            self.log_message(f"Error getting expiry months: {e}")
            return []
    
    def get_nse_stock_underlyings(self):
        """Return a list of popular NSE stock symbols for options"""
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBIN", 
                "BHARTIARTL", "KOTAKBANK", "BAJFINANCE", "LT", "WIPRO", "AXISBANK", "TITAN", 
                "ASIANPAINT", "MARUTI", "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "JSWSTEEL", 
                "ONGC", "NTPC", "POWERGRID", "M&M", "ULTRACEMCO", "HCLTECH", "ADANIPORTS", 
                "GRASIM", "INDUSINDBK", "DIVISLAB", "BRITANNIA", "DRREDDY", "EICHERMOT", 
                "COALINDIA", "BPCL", "IOC", "HEROMOTOCO", "SHREECEM", "BAJAJFINSV", 
                "TECHM", "HDFCLIFE", "SBILIFE", "HINDALCO", "PIDILITIND", "ICICIPRULI", 
                "MUTHOOTFIN", "NAUKRI", "BERGEPAINT"]
    
    def get_monthly_contracts(self, base_symbol):
        """Get previous, current, and next month contracts for MCX (unchanged)"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            relevant_instruments = self.instruments_df[
                (self.instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                (self.instruments_df['tradingsymbol'].str.contains('FUT')) &
                (self.instruments_df['expiry'].notnull())
            ].copy()
            if relevant_instruments.empty:
                relevant_instruments = self.instruments_df[
                    (self.instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                    (self.instruments_df['expiry'].notnull())
                ].copy()
            if relevant_instruments.empty:
                self.log_message(f"No contracts found for {base_symbol}")
                return []
            relevant_instruments = relevant_instruments.sort_values('expiry')
            current_date = datetime.now().date()
            current_contracts = []
            next_contracts = []
            prev_contracts = []
            for _, instrument in relevant_instruments.iterrows():
                expiry_date = instrument['expiry']
                if isinstance(expiry_date, str):
                    expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                days_to_expiry = (expiry_date - current_date).days
                if days_to_expiry < 0:
                    prev_contracts.append(instrument['tradingsymbol'])
                elif days_to_expiry <= 30:
                    current_contracts.append(instrument['tradingsymbol'])
                else:
                    next_contracts.append(instrument['tradingsymbol'])
            selected_contracts = []
            if prev_contracts:
                selected_contracts.append(prev_contracts[-1])
            if current_contracts:
                selected_contracts.append(current_contracts[0])
            elif not selected_contracts and next_contracts:
                selected_contracts.append(next_contracts[0])
                if len(next_contracts) > 1:
                    selected_contracts.append(next_contracts[1])
            if next_contracts and len(selected_contracts) < 3:
                for contract in next_contracts:
                    if contract not in selected_contracts:
                        selected_contracts.append(contract)
                        break
            if not selected_contracts and not relevant_instruments.empty:
                selected_contracts = relevant_instruments['tradingsymbol'].head(3).tolist()
            self.log_message(f"Found {len(selected_contracts)} contracts for {base_symbol}")
            return selected_contracts[:3]
        except Exception as e:
            self.log_message(f"Error getting monthly contracts: {str(e)}")
            return []
    
    def setup_gui(self):
        """Setup the main GUI interface"""
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.setup_login_tab(notebook)
        self.setup_market_data_tab(notebook)
        self.setup_futures_trading_tab(notebook)
        self.setup_options_trading_tab(notebook)          # MCX Options
        self.setup_nfo_options_trading_tab(notebook)      # NFO Index Options
        self.setup_nse_options_trading_tab(notebook)      # NSE Stock Options
        self.setup_positions_tab(notebook)
        self.setup_pnl_tab(notebook)
    
    # ---------- Login Tab ----------
    def setup_login_tab(self, notebook):
        login_frame = ttk.Frame(notebook)
        notebook.add(login_frame, text="Login")
        
        ttk.Label(login_frame, text="API Key:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.api_key_entry = ttk.Entry(login_frame, width=40)
        self.api_key_entry.grid(row=0, column=1, padx=10, pady=10)
        if hasattr(self, 'api_key'):
            self.api_key_entry.insert(0, self.api_key)
        
        ttk.Label(login_frame, text="API Secret:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.api_secret_entry = ttk.Entry(login_frame, width=40, show='*')
        self.api_secret_entry.grid(row=1, column=1, padx=10, pady=10)
        
        ttk.Label(login_frame, text="Request Token:").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.request_token_entry = ttk.Entry(login_frame, width=40)
        self.request_token_entry.grid(row=2, column=1, padx=10, pady=10)
        
        ttk.Button(login_frame, text="Generate Login URL", command=self.generate_login_url).grid(row=3, column=0, padx=10, pady=10)
        ttk.Button(login_frame, text="Login", command=self.manual_login).grid(row=3, column=1, padx=10, pady=10)
        ttk.Button(login_frame, text="Auto Login", command=self.auto_login).grid(row=3, column=2, padx=10, pady=10)
        
        self.login_status = ttk.Label(login_frame, text="Not Logged In", foreground='red')
        self.login_status.grid(row=4, column=0, columnspan=3, padx=10, pady=10)
    
    def generate_login_url(self):
        try:
            self.api_key = self.api_key_entry.get()
            if not self.api_key:
                messagebox.showerror("Error", "Please enter API Key")
                return
            self.kite = KiteConnect(api_key=self.api_key)
            login_url = self.kite.login_url()
            webbrowser.open(login_url)
            messagebox.showinfo("Login URL", f"Login URL generated and opened in browser.\nIf not, copy this URL:\n{login_url}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate login URL: {e}")
    
    def manual_login(self):
        try:
            self.api_key = self.api_key_entry.get()
            api_secret = self.api_secret_entry.get()
            request_token = self.request_token_entry.get()
            if not all([self.api_key, api_secret, request_token]):
                messagebox.showerror("Error", "Please fill all fields")
                return
            self.kite = KiteConnect(api_key=self.api_key)
            data = self.kite.generate_session(request_token, api_secret=api_secret)
            self.access_token = data['access_token']
            self.kite.set_access_token(self.access_token)
            self.save_credentials()
            self.is_logged_in = True
            self.login_status.config(text="Logged In Successfully", foreground='green')
            self.load_instruments()
            self.load_nfo_instruments()
            self.start_background_tasks()
            messagebox.showinfo("Success", "Login successful!")
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {e}")
    
    def auto_login(self):
        try:
            if not hasattr(self, 'api_key') or not hasattr(self, 'access_token'):
                messagebox.showerror("Error", "No saved credentials found")
                return
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            profile = self.kite.profile()
            self.is_logged_in = True
            self.login_status.config(text=f"Auto Login Successful - {profile['user_name']}", foreground='green')
            self.load_instruments()
            self.load_nfo_instruments()
            self.start_background_tasks()
            messagebox.showinfo("Success", f"Auto login successful! Welcome {profile['user_name']}")
        except Exception as e:
            messagebox.showerror("Error", f"Auto login failed: {e}")
    
    # ---------- Market Data Tab ----------
    def setup_market_data_tab(self, notebook):
        market_frame = ttk.Frame(notebook)
        notebook.add(market_frame, text="Market Data")
        
        selection_frame = ttk.Frame(market_frame)
        selection_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(selection_frame, text="Select Instrument:").pack(side='left', padx=5)
        self.instrument_var = tk.StringVar()
        self.instrument_combo = ttk.Combobox(selection_frame, textvariable=self.instrument_var, 
                                       values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"])
        self.instrument_combo.pack(side='left', padx=5)
        self.instrument_combo.set("GOLD")
        
        ttk.Button(selection_frame, text="Load Contracts", command=self.load_contracts).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Start Live Data", command=self.start_live_data).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Stop Live Data", command=self.stop_live_data).pack(side='left', padx=10)
        
        contracts_frame = ttk.Frame(market_frame)
        contracts_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(contracts_frame, text="Select Contracts:").pack(side='left', padx=5)
        self.contracts_var = tk.StringVar()
        self.contracts_listbox = tk.Listbox(contracts_frame, selectmode='multiple', height=4, width=50)
        self.contracts_listbox.pack(side='left', padx=5, fill='x', expand=True)
        
        self.market_data_text = scrolledtext.ScrolledText(market_frame, height=20, width=150)
        self.market_data_text.pack(fill='both', expand=True, padx=10, pady=10)
    
    def load_contracts(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            base_instrument = self.instrument_var.get()
            contracts = self.get_monthly_contracts(base_instrument)
            self.contracts_listbox.delete(0, tk.END)
            for contract in contracts:
                self.contracts_listbox.insert(tk.END, contract)
            for i in range(len(contracts)):
                self.contracts_listbox.select_set(i)
            if contracts:
                self.log_message(f"Loaded {len(contracts)} contracts for {base_instrument}")
            else:
                self.log_message(f"No contracts found for {base_instrument}")
        except Exception as e:
            self.log_message(f"Error loading contracts: {e}")
    
    def start_live_data(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        selected_contracts = [self.contracts_listbox.get(i) for i in self.contracts_listbox.curselection()]
        if not selected_contracts:
            messagebox.showerror("Error", "Please select at least one contract")
            return
        self.live_data_running = True
        threading.Thread(target=self.fetch_live_data, args=(selected_contracts,), daemon=True).start()
        self.log_message(f"Started live data for {len(selected_contracts)} contracts")
    
    def fetch_live_data(self, contracts):
        try:
            while self.live_data_running and self.is_logged_in:
                try:
                    instruments = [f"MCX:{contract}" for contract in contracts]
                    ltp_data = self.kite.ltp(instruments)
                    data = []
                    for key, values in ltp_data.items():
                        contract_name = key.replace("MCX:", "")
                        data.append({
                            'Contract': contract_name,
                            'LTP': values['last_price'],
                            'Volume': values.get('volume', 0),
                            'Change': values.get('net_change', 0),
                            'OI': values.get('oi', 0),
                            'Timestamp': datetime.now().strftime("%H:%M:%S")
                        })
                    self.update_market_data_display(data)
                    time.sleep(2)
                except Exception as e:
                    self.log_message(f"Error in live data fetch: {e}")
                    time.sleep(5)
        except Exception as e:
            self.log_message(f"Live data stream stopped: {e}")
    
    def update_market_data_display(self, data):
        def update():
            self.market_data_text.delete(1.0, tk.END)
            self.market_data_text.insert(tk.END, f"{'Contract':<20} {'LTP':<15} {'Change':<15} {'Volume':<15} {'OI':<15} {'Time':<10}\n")
            self.market_data_text.insert(tk.END, "-" * 90 + "\n")
            for item in data:
                self.market_data_text.insert(tk.END, 
                    f"{item['Contract']:<20} {item['LTP']:<15.2f} {item['Change']:<15.2f} "
                    f"{item['Volume']:<15} {item['OI']:<15} {item['Timestamp']:<10}\n")
        self.root.after(0, update)
    
    def stop_live_data(self):
        self.live_data_running = False
        self.log_message("Live data stopped")
    
    # ---------- Futures Trading Tab ----------
    def setup_futures_trading_tab(self, notebook):
        futures_frame = ttk.Frame(notebook)
        notebook.add(futures_frame, text="Futures Trading")
        
        paned_window = ttk.PanedWindow(futures_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        # Futures table
        futures_table_frame = ttk.LabelFrame(left_frame, text="Available Futures Contracts (Live Prices)")
        futures_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        futures_buttons_frame = ttk.Frame(futures_table_frame)
        futures_buttons_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(futures_buttons_frame, text="Refresh Futures", command=self.refresh_futures_table).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Start Live Prices", command=self.start_futures_live_data).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Stop Live Prices", command=self.stop_futures_live_data).pack(side='left', padx=5)
        
        table_frame = ttk.Frame(futures_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.futures_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        tree_scroll.config(command=self.futures_tree.yview)
        
        self.futures_tree.heading('Symbol', text='Trading Symbol')
        self.futures_tree.heading('Name', text='Name')
        self.futures_tree.heading('Expiry', text='Expiry')
        self.futures_tree.heading('Lot Size', text='Lot Size')
        self.futures_tree.heading('LTP', text='LTP')
        self.futures_tree.heading('Change', text='Change %')
        self.futures_tree.heading('Volume', text='Volume')
        
        self.futures_tree.column('Symbol', width=150)
        self.futures_tree.column('Name', width=100)
        self.futures_tree.column('Expiry', width=100)
        self.futures_tree.column('Lot Size', width=80, anchor='center')
        self.futures_tree.column('LTP', width=100, anchor='center')
        self.futures_tree.column('Change', width=80, anchor='center')
        self.futures_tree.column('Volume', width=80, anchor='center')
        self.futures_tree.pack(fill='both', expand=True)
        
        # Order placement (right side)
        order_frame = ttk.LabelFrame(right_frame, text="Futures Order Placement")
        order_frame.pack(fill='both', expand=True, padx=5, pady=5)
        order_notebook = ttk.Notebook(order_frame)
        order_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        single_tab = ttk.Frame(order_notebook)
        order_notebook.add(single_tab, text="Single Transaction")
        pair_tab = ttk.Frame(order_notebook)
        order_notebook.add(pair_tab, text="Buy & Sell Together")
        
        self.setup_futures_single_transaction_tab(single_tab)
        self.setup_futures_buy_sell_together_tab(pair_tab)
        
        orders_log_frame = ttk.LabelFrame(right_frame, text="Futures Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.futures_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.futures_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
    
    def setup_futures_single_transaction_tab(self, parent):
        selection_frame = ttk.LabelFrame(parent, text="Futures Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(selection_frame, text="Select from Table", command=self.select_futures_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", command=self.clear_futures_single_selection).pack(side='left', padx=5, pady=5)
        self.selected_futures_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_futures_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_futures_single_text.insert(tk.END, "No futures contracts selected")
        
        params_frame = ttk.LabelFrame(parent, text="Futures Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.futures_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.futures_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.futures_transaction_type.set("BUY")
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.futures_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.futures_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.futures_order_type.set("MARKET")
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.futures_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_quantity_type.set("Lot Size")
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.futures_quantity_entry = ttk.Entry(params_frame)
        self.futures_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.futures_quantity_entry.insert(0, "1")
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.futures_price_entry = ttk.Entry(params_frame)
        self.futures_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.futures_price_entry.insert(0, "0")
        params_frame.columnconfigure(1, weight=1)
        
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(order_buttons_frame, text="Place Futures Orders with Real-time Prices", command=self.place_futures_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", command=self.validate_futures_single_selection).pack(side='left', padx=5)
    
    def setup_futures_buy_sell_together_tab(self, parent):
        pair_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pair_paned.pack(fill='both', expand=True, padx=5, pady=5)
        buy_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(buy_selection_frame, weight=1)
        sell_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(sell_selection_frame, weight=1)
        
        # BUY contracts
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Futures Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", command=self.select_futures_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", command=self.clear_futures_buy_selection).pack(padx=5, pady=5)
        self.selected_futures_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_futures_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_futures_buy_text.insert(tk.END, "No BUY futures contracts selected")
        
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.futures_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_order_type.set("MARKET")
        ttk.Label(buy_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_quantity_type = ttk.Combobox(buy_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.futures_buy_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_quantity_type.set("Lot Size")
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.futures_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_quantity_entry.insert(0, "1")
        ttk.Label(buy_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_price_entry = ttk.Entry(buy_params_frame)
        self.futures_buy_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_price_entry.insert(0, "0")
        buy_params_frame.columnconfigure(1, weight=1)
        
        # SELL contracts
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Futures Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", command=self.select_futures_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", command=self.clear_futures_sell_selection).pack(padx=5, pady=5)
        self.selected_futures_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_futures_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_futures_sell_text.insert(tk.END, "No SELL futures contracts selected")
        
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.futures_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_order_type.set("MARKET")
        ttk.Label(sell_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_quantity_type = ttk.Combobox(sell_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.futures_sell_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_quantity_type.set("Lot Size")
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.futures_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_quantity_entry.insert(0, "1")
        ttk.Label(sell_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_price_entry = ttk.Entry(sell_params_frame)
        self.futures_sell_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_price_entry.insert(0, "0")
        sell_params_frame.columnconfigure(1, weight=1)
        
        combined_button_frame = ttk.Frame(parent)
        combined_button_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(combined_button_frame, text="Place BUY & SELL Futures Orders with Real-time Prices", command=self.place_futures_buy_sell_orders).pack(pady=5)
    
    # ---------- MCX Options Tab (with month, strike range, spread) ----------
    def setup_options_trading_tab(self, notebook):
        options_frame = ttk.Frame(notebook)
        notebook.add(options_frame, text="MCX Options Trading")
        
        paned_window = ttk.PanedWindow(options_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        # Left side: options table
        options_table_frame = ttk.LabelFrame(left_frame, text="Available MCX Options Contracts (Live Prices)")
        options_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        options_controls_frame = ttk.Frame(options_table_frame)
        options_controls_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(options_controls_frame, text="Underlying:").pack(side='left', padx=5)
        self.options_underlying_var = tk.StringVar()
        self.options_underlying_combo = ttk.Combobox(options_controls_frame, textvariable=self.options_underlying_var,
                                                   values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS"])
        self.options_underlying_combo.pack(side='left', padx=5)
        self.options_underlying_combo.set("GOLD")
        
        # Min/Max Strike entries (replacing strike range combobox)
        ttk.Label(options_controls_frame, text="Min Strike:").pack(side='left', padx=2)
        self.options_min_strike_entry = ttk.Entry(options_controls_frame, width=8)
        self.options_min_strike_entry.pack(side='left', padx=2)
        self.options_min_strike_entry.insert(0, "0")
        
        ttk.Label(options_controls_frame, text="Max Strike:").pack(side='left', padx=2)
        self.options_max_strike_entry = ttk.Entry(options_controls_frame, width=8)
        self.options_max_strike_entry.pack(side='left', padx=2)
        self.options_max_strike_entry.insert(0, "0")
        
        # Month selection
        ttk.Label(options_controls_frame, text="Expiry Month:").pack(side='left', padx=5)
        self.options_month_var = tk.StringVar()
        self.options_month_combo = ttk.Combobox(options_controls_frame, textvariable=self.options_month_var, width=12)
        self.options_month_combo.pack(side='left', padx=5)
        self.options_month_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_options_table())
        
        ttk.Button(options_controls_frame, text="Refresh Options", command=self.refresh_options_table).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Start Live Prices", command=self.start_options_live_data).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Stop Live Prices", command=self.stop_options_live_data).pack(side='left', padx=5)
        
        # Treeview (unchanged)...
        table_frame = ttk.Frame(options_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.options_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        tree_scroll.config(command=self.options_tree.yview)
        # ... (headings and columns unchanged)
        self.options_tree.pack(fill='both', expand=True)
        
        # Right side: order placement (unchanged)
        order_frame = ttk.LabelFrame(right_frame, text="MCX Options Order Placement")
        order_frame.pack(fill='both', expand=True, padx=5, pady=5)
        order_notebook = ttk.Notebook(order_frame)
        order_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        single_tab = ttk.Frame(order_notebook)
        order_notebook.add(single_tab, text="Single Transaction")
        pair_tab = ttk.Frame(order_notebook)
        order_notebook.add(pair_tab, text="Buy & Sell Together")
        strategies_tab = ttk.Frame(order_notebook)
        order_notebook.add(strategies_tab, text="Options Strategies")
        
        self.setup_options_single_transaction_tab(single_tab)
        self.setup_options_buy_sell_together_tab(pair_tab)
        self.setup_options_strategies_tab(strategies_tab)
        
        orders_log_frame = ttk.LabelFrame(right_frame, text="MCX Options Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.options_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.options_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
    
    def setup_options_single_transaction_tab(self, parent):
        selection_frame = ttk.LabelFrame(parent, text="Options Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(selection_frame, text="Select from Table", command=self.select_options_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", command=self.clear_options_single_selection).pack(side='left', padx=5, pady=5)
        self.selected_options_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_options_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_options_single_text.insert(tk.END, "No options contracts selected")
        
        params_frame = ttk.LabelFrame(parent, text="Options Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.options_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.options_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.options_transaction_type.set("BUY")
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.options_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.options_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.options_order_type.set("MARKET")
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.options_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.options_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.options_quantity_type.set("Lot Size")
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.options_quantity_entry = ttk.Entry(params_frame)
        self.options_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.options_quantity_entry.insert(0, "1")
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.options_price_entry = ttk.Entry(params_frame)
        self.options_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.options_price_entry.insert(0, "0")
        params_frame.columnconfigure(1, weight=1)
        
        # Auto limit offset
        offset_frame = ttk.Frame(parent)
        offset_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(offset_frame, text="Auto Limit Offset:").pack(side='left', padx=2)
        offset_spin = ttk.Spinbox(offset_frame, from_=0.1, to=100, increment=0.1, 
                                textvariable=self.options_limit_offset, width=8)
        offset_spin.pack(side='left', padx=2)

        ttk.Combobox(offset_frame, textvariable=self.options_offset_type,
                    values=["Percent", "Points"], width=8).pack(side='left', padx=2)
        ttk.Label(offset_frame, text="(used when price=0)").pack(side='left', padx=5)

        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(order_buttons_frame, text="Place Options Orders with Real-time Prices", command=self.place_options_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", command=self.validate_options_single_selection).pack(side='left', padx=5)
    
    def setup_options_buy_sell_together_tab(self, parent):
        pair_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pair_paned.pack(fill='both', expand=True, padx=5, pady=5)
        buy_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(buy_selection_frame, weight=1)
        sell_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(sell_selection_frame, weight=1)
        
        # BUY contracts
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Options Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", command=self.select_options_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", command=self.clear_options_buy_selection).pack(padx=5, pady=5)
        self.selected_options_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_options_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_options_buy_text.insert(tk.END, "No BUY options contracts selected")
        
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.options_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.options_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.options_buy_order_type.set("MARKET")
        ttk.Label(buy_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.options_buy_quantity_type = ttk.Combobox(buy_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.options_buy_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.options_buy_quantity_type.set("Lot Size")
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.options_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.options_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.options_buy_quantity_entry.insert(0, "1")
        ttk.Label(buy_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.options_buy_price_entry = ttk.Entry(buy_params_frame)
        self.options_buy_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.options_buy_price_entry.insert(0, "0")
        buy_params_frame.columnconfigure(1, weight=1)
        ttk.Label(buy_params_frame, text="Auto Offset:").grid(row=4, column=0, padx=5, pady=2, sticky='w')
        self.options_buy_offset_value = tk.DoubleVar(value=0.5)
        self.options_buy_offset_type = tk.StringVar(value="Percent")
        offset_buy_spin = ttk.Spinbox(buy_params_frame, from_=0.1, to=100, increment=0.1,
                                    textvariable=self.options_buy_offset_value, width=8)
        offset_buy_spin.grid(row=4, column=1, padx=2, pady=2, sticky='w')
        ttk.Combobox(buy_params_frame, textvariable=self.options_buy_offset_type,
                    values=["Percent", "Points"], width=8).grid(row=4, column=2, padx=2, pady=2, sticky='w')
        
        # SELL contracts
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Options Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", command=self.select_options_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", command=self.clear_options_sell_selection).pack(padx=5, pady=5)
        self.selected_options_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_options_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_options_sell_text.insert(tk.END, "No SELL options contracts selected")
        
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.options_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.options_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.options_sell_order_type.set("MARKET")
        ttk.Label(sell_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.options_sell_quantity_type = ttk.Combobox(sell_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.options_sell_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.options_sell_quantity_type.set("Lot Size")
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.options_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.options_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.options_sell_quantity_entry.insert(0, "1")
        ttk.Label(sell_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.options_sell_price_entry = ttk.Entry(sell_params_frame)
        self.options_sell_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.options_sell_price_entry.insert(0, "0")
        sell_params_frame.columnconfigure(1, weight=1)
        ttk.Label(sell_params_frame, text="Auto Offset:").grid(row=4, column=0, padx=5, pady=2, sticky='w')
        self.options_sell_offset_value = tk.DoubleVar(value=0.5)
        self.options_sell_offset_type = tk.StringVar(value="Percent")
        offset_sell_spin = ttk.Spinbox(sell_params_frame, from_=0.1, to=100, increment=0.1,
        textvariable=self.options_sell_offset_value, width=8)
        offset_sell_spin.grid(row=4, column=1, padx=2, pady=2, sticky='w')
        ttk.Combobox(sell_params_frame, textvariable=self.options_sell_offset_type,
        values=["Percent", "Points"], width=8).grid(row=4, column=2, padx=2, pady=2, sticky='w')
        
        # Spread management frame (NEW)
        spread_frame = ttk.LabelFrame(parent, text="Spread Management")
        spread_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Label(spread_frame, text="Max Margin (₹):").pack(side='left', padx=5)
        self.mcx_spread_margin_entry = ttk.Entry(spread_frame, width=12)
        self.mcx_spread_margin_entry.pack(side='left', padx=5)
        self.mcx_spread_margin_entry.insert(0, "5000")
        
        ttk.Button(spread_frame, text="Place Spread (Buy & Sell)", 
                   command=self.place_mcx_spread_order).pack(side='left', padx=5)
        ttk.Button(spread_frame, text="Exit Spread", 
                   command=self.exit_mcx_spread).pack(side='left', padx=5)
    
    def setup_options_strategies_tab(self, parent):
        strategies_frame = ttk.Frame(parent)
        strategies_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        strategy_selection_frame = ttk.LabelFrame(strategies_frame, text="Options Strategies")
        strategy_selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(strategy_selection_frame, text="Select Strategy:").pack(side='left', padx=5, pady=5)
        self.strategy_var = tk.StringVar()
        strategy_combo = ttk.Combobox(strategy_selection_frame, textvariable=self.strategy_var,
                                    values=["Long Call", "Long Put", "Short Call", "Short Put", 
                                           "Bull Call Spread", "Bear Put Spread", "Straddle", "Strangle"])
        strategy_combo.pack(side='left', padx=5, pady=5)
        strategy_combo.set("Long Call")
        ttk.Button(strategy_selection_frame, text="Explain Strategy", command=self.explain_strategy).pack(side='left', padx=5, pady=5)
        
        params_frame = ttk.LabelFrame(strategies_frame, text="Strategy Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Underlying:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.strategy_underlying_var = tk.StringVar()
        self.strategy_underlying_combo = ttk.Combobox(params_frame, textvariable=self.strategy_underlying_var,
                                                    values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS"])
        self.strategy_underlying_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.strategy_underlying_combo.set("GOLD")
        ttk.Label(params_frame, text="Strike Price:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.strike_price_entry = ttk.Entry(params_frame)
        self.strike_price_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.strike_price_entry.insert(0, "0")
        ttk.Label(params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.strategy_quantity_entry = ttk.Entry(params_frame)
        self.strategy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.strategy_quantity_entry.insert(0, "1")
        params_frame.columnconfigure(1, weight=1)
        
        desc_frame = ttk.LabelFrame(strategies_frame, text="Strategy Description")
        desc_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.strategy_desc_text = scrolledtext.ScrolledText(desc_frame, height=8)
        self.strategy_desc_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        execute_frame = ttk.Frame(strategies_frame)
        execute_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(execute_frame, text="Execute Strategy with Real-time Prices", command=self.execute_options_strategy).pack(pady=5)
        
        self.explain_strategy()
    
    def explain_strategy(self):
        strategy = self.strategy_var.get()
        descriptions = {
            "Long Call": "Buy a call option. Bullish strategy. Profit when underlying price rises above strike price + premium.",
            "Long Put": "Buy a put option. Bearish strategy. Profit when underlying price falls below strike price - premium.",
            "Short Call": "Sell a call option. Bearish or neutral strategy. Profit when underlying price stays below strike price.",
            "Short Put": "Sell a put option. Bullish or neutral strategy. Profit when underlying price stays above strike price.",
            "Bull Call Spread": "Buy lower strike call, sell higher strike call. Limited risk, limited reward bullish strategy.",
            "Bear Put Spread": "Buy higher strike put, sell lower strike put. Limited risk, limited reward bearish strategy.",
            "Straddle": "Buy both call and put at same strike. Profitable when large price movement in either direction.",
            "Strangle": "Buy out-of-the-money call and put. Cheaper than straddle, needs larger price movement."
        }
        description = descriptions.get(strategy, "Select a strategy to see description.")
        self.strategy_desc_text.delete(1.0, tk.END)
        self.strategy_desc_text.insert(tk.END, description)
    
    # ---------- NFO Options Tab (with month, strike range, spread) ----------
    def setup_nfo_options_trading_tab(self, notebook):
        nfo_options_frame = ttk.Frame(notebook)
        notebook.add(nfo_options_frame, text="NFO Index Options")
        
        paned_window = ttk.PanedWindow(nfo_options_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        options_table_frame = ttk.LabelFrame(left_frame, text="Available NFO Index Options (Live Prices)")
        options_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        options_controls_frame = ttk.Frame(options_table_frame)
        options_controls_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(options_controls_frame, text="Underlying:").pack(side='left', padx=5)
        self.nfo_options_underlying_var = tk.StringVar()
        self.nfo_options_underlying_combo = ttk.Combobox(options_controls_frame, textvariable=self.nfo_options_underlying_var,
                                                   values=["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
        self.nfo_options_underlying_combo.pack(side='left', padx=5)
        self.nfo_options_underlying_combo.set("NIFTY")
        
        # Min/Max Strike entries
        ttk.Label(options_controls_frame, text="Min Strike:").pack(side='left', padx=2)
        self.nfo_min_strike_entry = ttk.Entry(options_controls_frame, width=8)
        self.nfo_min_strike_entry.pack(side='left', padx=2)
        self.nfo_min_strike_entry.insert(0, "0")
        
        ttk.Label(options_controls_frame, text="Max Strike:").pack(side='left', padx=2)
        self.nfo_max_strike_entry = ttk.Entry(options_controls_frame, width=8)
        self.nfo_max_strike_entry.pack(side='left', padx=2)
        self.nfo_max_strike_entry.insert(0, "0")
        
        # Month selection
        ttk.Label(options_controls_frame, text="Expiry Month:").pack(side='left', padx=5)
        self.nfo_options_month_var = tk.StringVar()
        self.nfo_options_month_combo = ttk.Combobox(options_controls_frame, textvariable=self.nfo_options_month_var, width=12)
        self.nfo_options_month_combo.pack(side='left', padx=5)
        self.nfo_options_month_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_nfo_options_table())
        
        ttk.Button(options_controls_frame, text="Refresh NFO Options", command=self.refresh_nfo_options_table).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Start Live Prices", command=self.start_nfo_options_live_data).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Stop Live Prices", command=self.stop_nfo_options_live_data).pack(side='left', padx=5)
        
        # Treeview (unchanged)...
        table_frame = ttk.Frame(options_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.nfo_options_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        tree_scroll.config(command=self.nfo_options_tree.yview)
        # ... (headings and columns)
        self.nfo_options_tree.pack(fill='both', expand=True)
        
        # Right side: order placement (unchanged)
        order_frame = ttk.LabelFrame(right_frame, text="NFO Index Options Order Placement")
        order_frame.pack(fill='both', expand=True, padx=5, pady=5)
        order_notebook = ttk.Notebook(order_frame)
        order_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        single_tab = ttk.Frame(order_notebook)
        order_notebook.add(single_tab, text="Single Transaction")
        pair_tab = ttk.Frame(order_notebook)
        order_notebook.add(pair_tab, text="Buy & Sell Together")
        strategies_tab = ttk.Frame(order_notebook)
        order_notebook.add(strategies_tab, text="Options Strategies")
        
        self.setup_nfo_options_single_transaction_tab(single_tab)
        self.setup_nfo_options_buy_sell_together_tab(pair_tab)
        self.setup_nfo_options_strategies_tab(strategies_tab)
        
        orders_log_frame = ttk.LabelFrame(right_frame, text="NFO Options Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.nfo_options_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.nfo_options_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
    
    def setup_nfo_options_single_transaction_tab(self, parent):
        selection_frame = ttk.LabelFrame(parent, text="NFO Options Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(selection_frame, text="Select from Table", command=self.select_nfo_options_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", command=self.clear_nfo_options_single_selection).pack(side='left', padx=5, pady=5)
        self.selected_nfo_options_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_nfo_options_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_nfo_options_single_text.insert(tk.END, "No NFO options contracts selected")
        
        params_frame = ttk.LabelFrame(parent, text="NFO Options Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.nfo_options_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_transaction_type.set("BUY")
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.nfo_options_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_order_type.set("MARKET")
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.nfo_options_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_quantity_type.set("Lot Size")
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_quantity_entry = ttk.Entry(params_frame)
        self.nfo_options_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_quantity_entry.insert(0, "1")
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_price_entry = ttk.Entry(params_frame)
        self.nfo_options_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_price_entry.insert(0, "0")
        params_frame.columnconfigure(1, weight=1)
        
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(order_buttons_frame, text="Place NFO Options Orders with Real-time Prices", command=self.place_nfo_options_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", command=self.validate_nfo_options_single_selection).pack(side='left', padx=5)
    
    def setup_nfo_options_buy_sell_together_tab(self, parent):
        pair_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pair_paned.pack(fill='both', expand=True, padx=5, pady=5)
        buy_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(buy_selection_frame, weight=1)
        sell_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(sell_selection_frame, weight=1)
        
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY NFO Options Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", command=self.select_nfo_options_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", command=self.clear_nfo_options_buy_selection).pack(padx=5, pady=5)
        self.selected_nfo_options_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_nfo_options_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_nfo_options_buy_text.insert(tk.END, "No BUY NFO options contracts selected")
        
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.nfo_options_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_buy_order_type.set("MARKET")
        ttk.Label(buy_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_buy_quantity_type = ttk.Combobox(buy_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.nfo_options_buy_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_buy_quantity_type.set("Lot Size")
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.nfo_options_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_buy_quantity_entry.insert(0, "1")
        ttk.Label(buy_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_buy_price_entry = ttk.Entry(buy_params_frame)
        self.nfo_options_buy_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_buy_price_entry.insert(0, "0")
        buy_params_frame.columnconfigure(1, weight=1)
        
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL NFO Options Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", command=self.select_nfo_options_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", command=self.clear_nfo_options_sell_selection).pack(padx=5, pady=5)
        self.selected_nfo_options_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_nfo_options_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_nfo_options_sell_text.insert(tk.END, "No SELL NFO options contracts selected")
        
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.nfo_options_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_sell_order_type.set("MARKET")
        ttk.Label(sell_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_sell_quantity_type = ttk.Combobox(sell_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.nfo_options_sell_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_sell_quantity_type.set("Lot Size")
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.nfo_options_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_sell_quantity_entry.insert(0, "1")
        ttk.Label(sell_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.nfo_options_sell_price_entry = ttk.Entry(sell_params_frame)
        self.nfo_options_sell_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_options_sell_price_entry.insert(0, "0")
        sell_params_frame.columnconfigure(1, weight=1)
        
        # Spread management (NEW)
        spread_frame = ttk.LabelFrame(parent, text="Spread Management")
        spread_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Label(spread_frame, text="Max Margin (₹):").pack(side='left', padx=5)
        self.nfo_spread_margin_entry = ttk.Entry(spread_frame, width=12)
        self.nfo_spread_margin_entry.pack(side='left', padx=5)
        self.nfo_spread_margin_entry.insert(0, "5000")
        
        ttk.Button(spread_frame, text="Place Spread (Buy & Sell)", 
                   command=self.place_nfo_spread_order).pack(side='left', padx=5)
        ttk.Button(spread_frame, text="Exit Spread", 
                   command=self.exit_nfo_spread).pack(side='left', padx=5)
    
    def setup_nfo_options_strategies_tab(self, parent):
        strategies_frame = ttk.Frame(parent)
        strategies_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        strategy_selection_frame = ttk.LabelFrame(strategies_frame, text="NFO Options Strategies")
        strategy_selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(strategy_selection_frame, text="Select Strategy:").pack(side='left', padx=5, pady=5)
        self.nfo_strategy_var = tk.StringVar()
        strategy_combo = ttk.Combobox(strategy_selection_frame, textvariable=self.nfo_strategy_var,
                                    values=["Long Call", "Long Put", "Short Call", "Short Put", 
                                           "Bull Call Spread", "Bear Put Spread", "Straddle", "Strangle"])
        strategy_combo.pack(side='left', padx=5, pady=5)
        strategy_combo.set("Long Call")
        ttk.Button(strategy_selection_frame, text="Explain Strategy", command=self.explain_nfo_strategy).pack(side='left', padx=5, pady=5)
        
        params_frame = ttk.LabelFrame(strategies_frame, text="Strategy Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Underlying:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nfo_strategy_underlying_var = tk.StringVar()
        self.nfo_strategy_underlying_combo = ttk.Combobox(params_frame, textvariable=self.nfo_strategy_underlying_var,
                                                    values=["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"])
        self.nfo_strategy_underlying_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_strategy_underlying_combo.set("NIFTY")
        ttk.Label(params_frame, text="Strike Price:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nfo_strike_price_entry = ttk.Entry(params_frame)
        self.nfo_strike_price_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_strike_price_entry.insert(0, "0")
        ttk.Label(params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nfo_strategy_quantity_entry = ttk.Entry(params_frame)
        self.nfo_strategy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nfo_strategy_quantity_entry.insert(0, "1")
        params_frame.columnconfigure(1, weight=1)
        
        desc_frame = ttk.LabelFrame(strategies_frame, text="Strategy Description")
        desc_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.nfo_strategy_desc_text = scrolledtext.ScrolledText(desc_frame, height=8)
        self.nfo_strategy_desc_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        execute_frame = ttk.Frame(strategies_frame)
        execute_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(execute_frame, text="Execute NFO Strategy with Real-time Prices", command=self.execute_nfo_options_strategy).pack(pady=5)
        
        self.explain_nfo_strategy()
    
    def explain_nfo_strategy(self):
        strategy = self.nfo_strategy_var.get()
        descriptions = {
            "Long Call": "Buy a call option. Bullish strategy. Profit when underlying price rises above strike price + premium.",
            "Long Put": "Buy a put option. Bearish strategy. Profit when underlying price falls below strike price - premium.",
            "Short Call": "Sell a call option. Bearish or neutral strategy. Profit when underlying price stays below strike price.",
            "Short Put": "Sell a put option. Bullish or neutral strategy. Profit when underlying price stays above strike price.",
            "Bull Call Spread": "Buy lower strike call, sell higher strike call. Limited risk, limited reward bullish strategy.",
            "Bear Put Spread": "Buy higher strike put, sell lower strike put. Limited risk, limited reward bearish strategy.",
            "Straddle": "Buy both call and put at same strike. Profitable when large price movement in either direction.",
            "Strangle": "Buy out-of-the-money call and put. Cheaper than straddle, needs larger price movement."
        }
        description = descriptions.get(strategy, "Select a strategy to see description.")
        self.nfo_strategy_desc_text.delete(1.0, tk.END)
        self.nfo_strategy_desc_text.insert(tk.END, description)
    
    # ---------- NSE Stock Options Tab (with month, strike range, spread) ----------
    def setup_nse_options_trading_tab(self, notebook):
        nse_options_frame = ttk.Frame(notebook)
        notebook.add(nse_options_frame, text="NSE Stock Options")
        
        paned_window = ttk.PanedWindow(nse_options_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        options_table_frame = ttk.LabelFrame(left_frame, text="Available NSE Stock Options (Live Prices)")
        options_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        options_controls_frame = ttk.Frame(options_table_frame)
        options_controls_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(options_controls_frame, text="Stock Symbol:").pack(side='left', padx=5)
        self.nse_options_underlying_var = tk.StringVar()
        self.nse_options_underlying_combo = ttk.Combobox(options_controls_frame, textvariable=self.nse_options_underlying_var,
                                                   values=self.get_nse_stock_underlyings(), width=15)
        self.nse_options_underlying_combo.pack(side='left', padx=5)
        self.nse_options_underlying_combo.set("RELIANCE")
        
        # Min/Max Strike entries
        ttk.Label(options_controls_frame, text="Min Strike:").pack(side='left', padx=2)
        self.nse_min_strike_entry = ttk.Entry(options_controls_frame, width=8)
        self.nse_min_strike_entry.pack(side='left', padx=2)
        self.nse_min_strike_entry.insert(0, "0")
        
        ttk.Label(options_controls_frame, text="Max Strike:").pack(side='left', padx=2)
        self.nse_max_strike_entry = ttk.Entry(options_controls_frame, width=8)
        self.nse_max_strike_entry.pack(side='left', padx=2)
        self.nse_max_strike_entry.insert(0, "0")
        
        # Month selection
        ttk.Label(options_controls_frame, text="Expiry Month:").pack(side='left', padx=5)
        self.nse_options_month_var = tk.StringVar()
        self.nse_options_month_combo = ttk.Combobox(options_controls_frame, textvariable=self.nse_options_month_var, width=12)
        self.nse_options_month_combo.pack(side='left', padx=5)
        self.nse_options_month_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_nse_options_table())
        
        ttk.Button(options_controls_frame, text="Refresh NSE Options", command=self.refresh_nse_options_table).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Start Live Prices", command=self.start_nse_options_live_data).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Stop Live Prices", command=self.stop_nse_options_live_data).pack(side='left', padx=5)
        
        # Treeview (unchanged)...
        table_frame = ttk.Frame(options_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.nse_options_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        tree_scroll.config(command=self.nse_options_tree.yview)
        # ... (headings and columns)
        self.nse_options_tree.pack(fill='both', expand=True)
        
        # Right side: order placement (unchanged)
        order_frame = ttk.LabelFrame(right_frame, text="NSE Stock Options Order Placement")
        order_frame.pack(fill='both', expand=True, padx=5, pady=5)
        order_notebook = ttk.Notebook(order_frame)
        order_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        single_tab = ttk.Frame(order_notebook)
        order_notebook.add(single_tab, text="Single Transaction")
        pair_tab = ttk.Frame(order_notebook)
        order_notebook.add(pair_tab, text="Buy & Sell Together")
        strategies_tab = ttk.Frame(order_notebook)
        order_notebook.add(strategies_tab, text="Options Strategies")
        
        self.setup_nse_options_single_transaction_tab(single_tab)
        self.setup_nse_options_buy_sell_together_tab(pair_tab)
        self.setup_nse_options_strategies_tab(strategies_tab)
        
        orders_log_frame = ttk.LabelFrame(right_frame, text="NSE Options Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.nse_options_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.nse_options_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
    
    def setup_nse_options_single_transaction_tab(self, parent):
        selection_frame = ttk.LabelFrame(parent, text="NSE Options Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(selection_frame, text="Select from Table", command=self.select_nse_options_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", command=self.clear_nse_options_single_selection).pack(side='left', padx=5, pady=5)
        self.selected_nse_options_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_nse_options_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_nse_options_single_text.insert(tk.END, "No NSE options contracts selected")
        
        params_frame = ttk.LabelFrame(parent, text="NSE Options Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.nse_options_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_transaction_type.set("BUY")
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.nse_options_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_order_type.set("MARKET")
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.nse_options_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_quantity_type.set("Lot Size")
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_quantity_entry = ttk.Entry(params_frame)
        self.nse_options_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_quantity_entry.insert(0, "1")
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_price_entry = ttk.Entry(params_frame)
        self.nse_options_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_price_entry.insert(0, "0")
        params_frame.columnconfigure(1, weight=1)
        
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(order_buttons_frame, text="Place NSE Options Orders with Real-time Prices", command=self.place_nse_options_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", command=self.validate_nse_options_single_selection).pack(side='left', padx=5)
    
    def setup_nse_options_buy_sell_together_tab(self, parent):
        pair_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pair_paned.pack(fill='both', expand=True, padx=5, pady=5)
        buy_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(buy_selection_frame, weight=1)
        sell_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(sell_selection_frame, weight=1)
        
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY NSE Options Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", command=self.select_nse_options_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", command=self.clear_nse_options_buy_selection).pack(padx=5, pady=5)
        self.selected_nse_options_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_nse_options_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_nse_options_buy_text.insert(tk.END, "No BUY NSE options contracts selected")
        
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.nse_options_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_buy_order_type.set("MARKET")
        ttk.Label(buy_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_buy_quantity_type = ttk.Combobox(buy_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.nse_options_buy_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_buy_quantity_type.set("Lot Size")
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.nse_options_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_buy_quantity_entry.insert(0, "1")
        ttk.Label(buy_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_buy_price_entry = ttk.Entry(buy_params_frame)
        self.nse_options_buy_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_buy_price_entry.insert(0, "0")
        buy_params_frame.columnconfigure(1, weight=1)
        
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL NSE Options Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", command=self.select_nse_options_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", command=self.clear_nse_options_sell_selection).pack(padx=5, pady=5)
        self.selected_nse_options_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_nse_options_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_nse_options_sell_text.insert(tk.END, "No SELL NSE options contracts selected")
        
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.nse_options_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_sell_order_type.set("MARKET")
        ttk.Label(sell_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_sell_quantity_type = ttk.Combobox(sell_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.nse_options_sell_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_sell_quantity_type.set("Lot Size")
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.nse_options_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_sell_quantity_entry.insert(0, "1")
        ttk.Label(sell_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.nse_options_sell_price_entry = ttk.Entry(sell_params_frame)
        self.nse_options_sell_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.nse_options_sell_price_entry.insert(0, "0")
        sell_params_frame.columnconfigure(1, weight=1)
        
        # Spread management (NEW)
        spread_frame = ttk.LabelFrame(parent, text="Spread Management")
        spread_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Label(spread_frame, text="Max Margin (₹):").pack(side='left', padx=5)
        self.nse_spread_margin_entry = ttk.Entry(spread_frame, width=12)
        self.nse_spread_margin_entry.pack(side='left', padx=5)
        self.nse_spread_margin_entry.insert(0, "5000")
        
        ttk.Button(spread_frame, text="Place Spread (Buy & Sell)", 
                   command=self.place_nse_spread_order).pack(side='left', padx=5)
        ttk.Button(spread_frame, text="Exit Spread", 
                   command=self.exit_nse_spread).pack(side='left', padx=5)
    
    def setup_nse_options_strategies_tab(self, parent):
        strategies_frame = ttk.Frame(parent)
        strategies_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        strategy_selection_frame = ttk.LabelFrame(strategies_frame, text="NSE Options Strategies")
        strategy_selection_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(strategy_selection_frame, text="Select Strategy:").pack(side='left', padx=5, pady=5)
        self.nse_strategy_var = tk.StringVar()
        strategy_combo = ttk.Combobox(strategy_selection_frame, textvariable=self.nse_strategy_var,
                                    values=["Long Call", "Long Put", "Short Call", "Short Put", 
                                           "Bull Call Spread", "Bear Put Spread", "Straddle", "Strangle"])
        strategy_combo.pack(side='left', padx=5, pady=5)
        strategy_combo.set("Long Call")
        ttk.Button(strategy_selection_frame, text="Explain Strategy", command=self.explain_nse_strategy).pack(side='left', padx=5, pady=5)
        
        params_frame = ttk.LabelFrame(strategies_frame, text="Strategy Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(params_frame, text="Stock Symbol:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.nse_strategy_underlying_var = tk.StringVar()
        self.nse_strategy_underlying_combo = ttk.Combobox(params_frame, textvariable=self.nse_strategy_underlying_var,
                                                    values=self.get_nse_stock_underlyings())
        self.nse_strategy_underlying_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.nse_strategy_underlying_combo.set("RELIANCE")
        ttk.Label(params_frame, text="Strike Price:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.nse_strike_price_entry = ttk.Entry(params_frame)
        self.nse_strike_price_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.nse_strike_price_entry.insert(0, "0")
        ttk.Label(params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.nse_strategy_quantity_entry = ttk.Entry(params_frame)
        self.nse_strategy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.nse_strategy_quantity_entry.insert(0, "1")
        params_frame.columnconfigure(1, weight=1)
        
        desc_frame = ttk.LabelFrame(strategies_frame, text="Strategy Description")
        desc_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.nse_strategy_desc_text = scrolledtext.ScrolledText(desc_frame, height=8)
        self.nse_strategy_desc_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        execute_frame = ttk.Frame(strategies_frame)
        execute_frame.pack(fill='x', padx=5, pady=10)
        ttk.Button(execute_frame, text="Execute NSE Strategy with Real-time Prices", command=self.execute_nse_options_strategy).pack(pady=5)
        
        self.explain_nse_strategy()
    
    def explain_nse_strategy(self):
        strategy = self.nse_strategy_var.get()
        descriptions = {
            "Long Call": "Buy a call option. Bullish strategy. Profit when underlying price rises above strike price + premium.",
            "Long Put": "Buy a put option. Bearish strategy. Profit when underlying price falls below strike price - premium.",
            "Short Call": "Sell a call option. Bearish or neutral strategy. Profit when underlying price stays below strike price.",
            "Short Put": "Sell a put option. Bullish or neutral strategy. Profit when underlying price stays above strike price.",
            "Bull Call Spread": "Buy lower strike call, sell higher strike call. Limited risk, limited reward bullish strategy.",
            "Bear Put Spread": "Buy higher strike put, sell lower strike put. Limited risk, limited reward bearish strategy.",
            "Straddle": "Buy both call and put at same strike. Profitable when large price movement in either direction.",
            "Strangle": "Buy out-of-the-money call and put. Cheaper than straddle, needs larger price movement."
        }
        description = descriptions.get(strategy, "Select a strategy to see description.")
        self.nse_strategy_desc_text.delete(1.0, tk.END)
        self.nse_strategy_desc_text.insert(tk.END, description)
    
    # ---------- Futures selection methods ----------
    def select_futures_from_table_single(self):
        self.open_futures_selection_window('single')
    
    def select_futures_buy_contracts(self):
        self.open_futures_selection_window('buy')
    
    def select_futures_sell_contracts(self):
        self.open_futures_selection_window('sell')
    
    def open_futures_selection_window(self, order_type):
        selection_window = tk.Toplevel(self.root)
        selection_window.title(f"Select Futures Contracts for {order_type.upper()} Orders")
        selection_window.geometry("800x600")
        
        selection_frame = ttk.Frame(selection_window)
        selection_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tree_scroll = ttk.Scrollbar(selection_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        select_tree = ttk.Treeview(selection_frame, columns=(
            'Select', 'Symbol', 'Name', 'Expiry', 'Lot Size', 'LTP'
        ), show='headings', yscrollcommand=tree_scroll.set, height=20)
        
        tree_scroll.config(command=select_tree.yview)
        
        select_tree.heading('Select', text='✓')
        select_tree.heading('Symbol', text='Symbol')
        select_tree.heading('Name', text='Name')
        select_tree.heading('Expiry', text='Expiry')
        select_tree.heading('Lot Size', text='Lot Size')
        select_tree.heading('LTP', text='LTP')
        
        select_tree.column('Select', width=50, anchor='center')
        select_tree.column('Symbol', width=150)
        select_tree.column('Name', width=100)
        select_tree.column('Expiry', width=100)
        select_tree.column('Lot Size', width=80, anchor='center')
        select_tree.column('LTP', width=100, anchor='center')
        
        select_tree.pack(fill='both', expand=True)
        
        for item in self.futures_tree.get_children():
            values = self.futures_tree.item(item, 'values')
            if values:
                select_tree.insert('', 'end', values=('□',) + values, tags=('unselected',))
        
        select_tree.bind('<Button-1>', lambda e: self.on_futures_selection_tree_click(e, select_tree, order_type))
        
        button_frame = ttk.Frame(selection_window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Select All", 
                  command=lambda: self.select_all_futures_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear All", 
                  command=lambda: self.clear_all_futures_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Confirm Selection", 
                  command=lambda: self.confirm_futures_selection(select_tree, selection_window, order_type)).pack(side='right', padx=5)
    
    def on_futures_selection_tree_click(self, event, tree, order_type):
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        
        if item and column == '#1':
            values = tree.item(item, 'values')
            symbol = values[1]
            
            if order_type == 'single':
                current_selection = self.selected_single_futures
            elif order_type == 'buy':
                current_selection = self.selected_buy_futures
            else:
                current_selection = self.selected_sell_futures
            
            if symbol in current_selection:
                tree.set(item, 'Select', '□')
                tree.item(item, tags=('unselected',))
                del current_selection[symbol]
            else:
                tree.set(item, 'Select', '✓')
                tree.item(item, tags=('selected',))
                current_selection[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'lot_size': values[4],
                    'ltp': values[5] if len(values) > 5 else 'N/A'
                }
    
    def select_all_futures_in_tree(self, tree, order_type):
        for item in tree.get_children():
            values = tree.item(item, 'values')
            symbol = values[1]
            
            tree.set(item, 'Select', '✓')
            tree.item(item, tags=('selected',))
            
            if order_type == 'single':
                self.selected_single_futures[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'lot_size': values[4],
                    'ltp': values[5] if len(values) > 5 else 'N/A'
                }
            elif order_type == 'buy':
                self.selected_buy_futures[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'lot_size': values[4],
                    'ltp': values[5] if len(values) > 5 else 'N/A'
                }
            else:
                self.selected_sell_futures[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'lot_size': values[4],
                    'ltp': values[5] if len(values) > 5 else 'N/A'
                }
    
    def clear_all_futures_in_tree(self, tree, order_type):
        for item in tree.get_children():
            tree.set(item, 'Select', '□')
            tree.item(item, tags=('unselected',))
        
        if order_type == 'single':
            self.selected_single_futures.clear()
        elif order_type == 'buy':
            self.selected_buy_futures.clear()
        else:
            self.selected_sell_futures.clear()
    
    def confirm_futures_selection(self, tree, window, order_type):
        if order_type == 'single':
            self.update_futures_single_selection_display()
            message = f"{len(self.selected_single_futures)} futures contracts selected for trading"
        elif order_type == 'buy':
            self.update_futures_buy_selection_display()
            message = f"{len(self.selected_buy_futures)} futures contracts selected for BUY orders"
        else:
            self.update_futures_sell_selection_display()
            message = f"{len(self.selected_sell_futures)} futures contracts selected for SELL orders"
        
        window.destroy()
        messagebox.showinfo("Selection Complete", message)
    
    def update_futures_single_selection_display(self):
        self.selected_futures_single_text.delete(1.0, tk.END)
        if not self.selected_single_futures:
            self.selected_futures_single_text.insert(tk.END, "No futures contracts selected")
            return
        for symbol, details in self.selected_single_futures.items():
            self.selected_futures_single_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_futures_buy_selection_display(self):
        self.selected_futures_buy_text.delete(1.0, tk.END)
        if not self.selected_buy_futures:
            self.selected_futures_buy_text.insert(tk.END, "No BUY futures contracts selected")
            return
        for symbol, details in self.selected_buy_futures.items():
            self.selected_futures_buy_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_futures_sell_selection_display(self):
        self.selected_futures_sell_text.delete(1.0, tk.END)
        if not self.selected_sell_futures:
            self.selected_futures_sell_text.insert(tk.END, "No SELL futures contracts selected")
            return
        for symbol, details in self.selected_sell_futures.items():
            self.selected_futures_sell_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def clear_futures_single_selection(self):
        self.selected_single_futures.clear()
        self.update_futures_single_selection_display()
    
    def clear_futures_buy_selection(self):
        self.selected_buy_futures.clear()
        self.update_futures_buy_selection_display()
    
    def clear_futures_sell_selection(self):
        self.selected_sell_futures.clear()
        self.update_futures_sell_selection_display()
    
    def validate_futures_single_selection(self):
        if not self.selected_single_futures:
            messagebox.showwarning("Warning", "No futures contracts selected")
            return
        messagebox.showinfo("Selection Valid", f"{len(self.selected_single_futures)} futures contracts selected and ready for trading")
    
    # ---------- MCX Options selection methods ----------
    def select_options_from_table_single(self):
        self.open_options_selection_window('single')
    
    def select_options_buy_contracts(self):
        self.open_options_selection_window('buy')
    
    def select_options_sell_contracts(self):
        self.open_options_selection_window('sell')
    
    def open_options_selection_window(self, order_type):
        selection_window = tk.Toplevel(self.root)
        selection_window.title(f"Select MCX Options Contracts for {order_type.upper()} Orders")
        selection_window.geometry("900x600")
        
        selection_frame = ttk.Frame(selection_window)
        selection_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tree_scroll = ttk.Scrollbar(selection_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        select_tree = ttk.Treeview(selection_frame, columns=(
            'Select', 'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP'
        ), show='headings', yscrollcommand=tree_scroll.set, height=20)
        
        tree_scroll.config(command=select_tree.yview)
        
        select_tree.heading('Select', text='✓')
        select_tree.heading('Symbol', text='Symbol')
        select_tree.heading('Name', text='Name')
        select_tree.heading('Expiry', text='Expiry')
        select_tree.heading('Strike', text='Strike')
        select_tree.heading('Type', text='Type')
        select_tree.heading('Lot Size', text='Lot Size')
        select_tree.heading('LTP', text='LTP')
        
        select_tree.column('Select', width=50, anchor='center')
        select_tree.column('Symbol', width=150)
        select_tree.column('Name', width=100)
        select_tree.column('Expiry', width=100)
        select_tree.column('Strike', width=80, anchor='center')
        select_tree.column('Type', width=60, anchor='center')
        select_tree.column('Lot Size', width=80, anchor='center')
        select_tree.column('LTP', width=80, anchor='center')
        
        select_tree.pack(fill='both', expand=True)
        
        for item in self.options_tree.get_children():
            values = self.options_tree.item(item, 'values')
            if values:
                select_tree.insert('', 'end', values=('□',) + values, tags=('unselected',))
        
        select_tree.bind('<Button-1>', lambda e: self.on_options_selection_tree_click(e, select_tree, order_type))
        
        button_frame = ttk.Frame(selection_window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Select All", 
                  command=lambda: self.select_all_options_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear All", 
                  command=lambda: self.clear_all_options_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Confirm Selection", 
                  command=lambda: self.confirm_options_selection(select_tree, selection_window, order_type)).pack(side='right', padx=5)
    
    def on_options_selection_tree_click(self, event, tree, order_type):
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        
        if item and column == '#1':
            values = tree.item(item, 'values')
            symbol = values[1]
            
            if order_type == 'single':
                current_selection = self.selected_single_options
            elif order_type == 'buy':
                current_selection = self.selected_buy_options
            else:
                current_selection = self.selected_sell_options
            
            if symbol in current_selection:
                tree.set(item, 'Select', '□')
                tree.item(item, tags=('unselected',))
                del current_selection[symbol]
            else:
                tree.set(item, 'Select', '✓')
                tree.item(item, tags=('selected',))
                current_selection[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'strike': values[4],
                    'type': values[5],
                    'lot_size': values[6],
                    'ltp': values[7] if len(values) > 7 else 'N/A'
                }
    
    def select_all_options_in_tree(self, tree, order_type):
        for item in tree.get_children():
            values = tree.item(item, 'values')
            symbol = values[1]
            
            tree.set(item, 'Select', '✓')
            tree.item(item, tags=('selected',))
            
            contract_data = {
                'symbol': symbol,
                'name': values[2],
                'expiry': values[3],
                'strike': values[4],
                'type': values[5],
                'lot_size': values[6],
                'ltp': values[7] if len(values) > 7 else 'N/A'
            }
            
            if order_type == 'single':
                self.selected_single_options[symbol] = contract_data
            elif order_type == 'buy':
                self.selected_buy_options[symbol] = contract_data
            else:
                self.selected_sell_options[symbol] = contract_data
    
    def clear_all_options_in_tree(self, tree, order_type):
        for item in tree.get_children():
            tree.set(item, 'Select', '□')
            tree.item(item, tags=('unselected',))
        
        if order_type == 'single':
            self.selected_single_options.clear()
        elif order_type == 'buy':
            self.selected_buy_options.clear()
        else:
            self.selected_sell_options.clear()
    
    def confirm_options_selection(self, tree, window, order_type):
        if order_type == 'single':
            self.update_options_single_selection_display()
            message = f"{len(self.selected_single_options)} MCX options contracts selected for trading"
        elif order_type == 'buy':
            self.update_options_buy_selection_display()
            message = f"{len(self.selected_buy_options)} MCX options contracts selected for BUY orders"
        else:
            self.update_options_sell_selection_display()
            message = f"{len(self.selected_sell_options)} MCX options contracts selected for SELL orders"
        
        window.destroy()
        messagebox.showinfo("Selection Complete", message)
    
    def update_options_single_selection_display(self):
        self.selected_options_single_text.delete(1.0, tk.END)
        if not self.selected_single_options:
            self.selected_options_single_text.insert(tk.END, "No MCX options contracts selected")
            return
        for symbol, details in self.selected_single_options.items():
            self.selected_options_single_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_options_buy_selection_display(self):
        self.selected_options_buy_text.delete(1.0, tk.END)
        if not self.selected_buy_options:
            self.selected_options_buy_text.insert(tk.END, "No BUY MCX options contracts selected")
            return
        for symbol, details in self.selected_buy_options.items():
            self.selected_options_buy_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_options_sell_selection_display(self):
        self.selected_options_sell_text.delete(1.0, tk.END)
        if not self.selected_sell_options:
            self.selected_options_sell_text.insert(tk.END, "No SELL MCX options contracts selected")
            return
        for symbol, details in self.selected_sell_options.items():
            self.selected_options_sell_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def clear_options_single_selection(self):
        self.selected_single_options.clear()
        self.update_options_single_selection_display()
    
    def clear_options_buy_selection(self):
        self.selected_buy_options.clear()
        self.update_options_buy_selection_display()
    
    def clear_options_sell_selection(self):
        self.selected_sell_options.clear()
        self.update_options_sell_selection_display()
    
    def validate_options_single_selection(self):
        if not self.selected_single_options:
            messagebox.showwarning("Warning", "No MCX options contracts selected")
            return
        messagebox.showinfo("Selection Valid", f"{len(self.selected_single_options)} MCX options contracts selected and ready for trading")
    
    # ---------- NFO Options selection methods ----------
    def select_nfo_options_from_table_single(self):
        self.open_nfo_options_selection_window('single')
    
    def select_nfo_options_buy_contracts(self):
        self.open_nfo_options_selection_window('buy')
    
    def select_nfo_options_sell_contracts(self):
        self.open_nfo_options_selection_window('sell')
    
    def open_nfo_options_selection_window(self, order_type):
        selection_window = tk.Toplevel(self.root)
        selection_window.title(f"Select NFO Options Contracts for {order_type.upper()} Orders")
        selection_window.geometry("900x600")
        
        selection_frame = ttk.Frame(selection_window)
        selection_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tree_scroll = ttk.Scrollbar(selection_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        select_tree = ttk.Treeview(selection_frame, columns=(
            'Select', 'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP'
        ), show='headings', yscrollcommand=tree_scroll.set, height=20)
        
        tree_scroll.config(command=select_tree.yview)
        
        select_tree.heading('Select', text='✓')
        select_tree.heading('Symbol', text='Symbol')
        select_tree.heading('Name', text='Name')
        select_tree.heading('Expiry', text='Expiry')
        select_tree.heading('Strike', text='Strike')
        select_tree.heading('Type', text='Type')
        select_tree.heading('Lot Size', text='Lot Size')
        select_tree.heading('LTP', text='LTP')
        
        select_tree.column('Select', width=50, anchor='center')
        select_tree.column('Symbol', width=150)
        select_tree.column('Name', width=100)
        select_tree.column('Expiry', width=100)
        select_tree.column('Strike', width=80, anchor='center')
        select_tree.column('Type', width=60, anchor='center')
        select_tree.column('Lot Size', width=80, anchor='center')
        select_tree.column('LTP', width=80, anchor='center')
        
        select_tree.pack(fill='both', expand=True)
        
        for item in self.nfo_options_tree.get_children():
            values = self.nfo_options_tree.item(item, 'values')
            if values:
                select_tree.insert('', 'end', values=('□',) + values, tags=('unselected',))
        
        select_tree.bind('<Button-1>', lambda e: self.on_nfo_options_selection_tree_click(e, select_tree, order_type))
        
        button_frame = ttk.Frame(selection_window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Select All", 
                  command=lambda: self.select_all_nfo_options_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear All", 
                  command=lambda: self.clear_all_nfo_options_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Confirm Selection", 
                  command=lambda: self.confirm_nfo_options_selection(select_tree, selection_window, order_type)).pack(side='right', padx=5)
    
    def on_nfo_options_selection_tree_click(self, event, tree, order_type):
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        
        if item and column == '#1':
            values = tree.item(item, 'values')
            symbol = values[1]
            
            if order_type == 'single':
                current_selection = self.selected_nfo_single_options
            elif order_type == 'buy':
                current_selection = self.selected_nfo_buy_options
            else:
                current_selection = self.selected_nfo_sell_options
            
            if symbol in current_selection:
                tree.set(item, 'Select', '□')
                tree.item(item, tags=('unselected',))
                del current_selection[symbol]
            else:
                tree.set(item, 'Select', '✓')
                tree.item(item, tags=('selected',))
                current_selection[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'strike': values[4],
                    'type': values[5],
                    'lot_size': values[6],
                    'ltp': values[7] if len(values) > 7 else 'N/A'
                }
    
    def select_all_nfo_options_in_tree(self, tree, order_type):
        for item in tree.get_children():
            values = tree.item(item, 'values')
            symbol = values[1]
            
            tree.set(item, 'Select', '✓')
            tree.item(item, tags=('selected',))
            
            contract_data = {
                'symbol': symbol,
                'name': values[2],
                'expiry': values[3],
                'strike': values[4],
                'type': values[5],
                'lot_size': values[6],
                'ltp': values[7] if len(values) > 7 else 'N/A'
            }
            
            if order_type == 'single':
                self.selected_nfo_single_options[symbol] = contract_data
            elif order_type == 'buy':
                self.selected_nfo_buy_options[symbol] = contract_data
            else:
                self.selected_nfo_sell_options[symbol] = contract_data
    
    def clear_all_nfo_options_in_tree(self, tree, order_type):
        for item in tree.get_children():
            tree.set(item, 'Select', '□')
            tree.item(item, tags=('unselected',))
        
        if order_type == 'single':
            self.selected_nfo_single_options.clear()
        elif order_type == 'buy':
            self.selected_nfo_buy_options.clear()
        else:
            self.selected_nfo_sell_options.clear()
    
    def confirm_nfo_options_selection(self, tree, window, order_type):
        if order_type == 'single':
            self.update_nfo_options_single_selection_display()
            message = f"{len(self.selected_nfo_single_options)} NFO options contracts selected for trading"
        elif order_type == 'buy':
            self.update_nfo_options_buy_selection_display()
            message = f"{len(self.selected_nfo_buy_options)} NFO options contracts selected for BUY orders"
        else:
            self.update_nfo_options_sell_selection_display()
            message = f"{len(self.selected_nfo_sell_options)} NFO options contracts selected for SELL orders"
        
        window.destroy()
        messagebox.showinfo("Selection Complete", message)
    
    def update_nfo_options_single_selection_display(self):
        self.selected_nfo_options_single_text.delete(1.0, tk.END)
        if not self.selected_nfo_single_options:
            self.selected_nfo_options_single_text.insert(tk.END, "No NFO options contracts selected")
            return
        for symbol, details in self.selected_nfo_single_options.items():
            self.selected_nfo_options_single_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_nfo_options_buy_selection_display(self):
        self.selected_nfo_options_buy_text.delete(1.0, tk.END)
        if not self.selected_nfo_buy_options:
            self.selected_nfo_options_buy_text.insert(tk.END, "No BUY NFO options contracts selected")
            return
        for symbol, details in self.selected_nfo_buy_options.items():
            self.selected_nfo_options_buy_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_nfo_options_sell_selection_display(self):
        self.selected_nfo_options_sell_text.delete(1.0, tk.END)
        if not self.selected_nfo_sell_options:
            self.selected_nfo_options_sell_text.insert(tk.END, "No SELL NFO options contracts selected")
            return
        for symbol, details in self.selected_nfo_sell_options.items():
            self.selected_nfo_options_sell_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def clear_nfo_options_single_selection(self):
        self.selected_nfo_single_options.clear()
        self.update_nfo_options_single_selection_display()
    
    def clear_nfo_options_buy_selection(self):
        self.selected_nfo_buy_options.clear()
        self.update_nfo_options_buy_selection_display()
    
    def clear_nfo_options_sell_selection(self):
        self.selected_nfo_sell_options.clear()
        self.update_nfo_options_sell_selection_display()
    
    def validate_nfo_options_single_selection(self):
        if not self.selected_nfo_single_options:
            messagebox.showwarning("Warning", "No NFO options contracts selected")
            return
        messagebox.showinfo("Selection Valid", f"{len(self.selected_nfo_single_options)} NFO options contracts selected and ready for trading")
    
    # ---------- NSE Options selection methods ----------
    def select_nse_options_from_table_single(self):
        self.open_nse_options_selection_window('single')
    
    def select_nse_options_buy_contracts(self):
        self.open_nse_options_selection_window('buy')
    
    def select_nse_options_sell_contracts(self):
        self.open_nse_options_selection_window('sell')
    
    def open_nse_options_selection_window(self, order_type):
        selection_window = tk.Toplevel(self.root)
        selection_window.title(f"Select NSE Options Contracts for {order_type.upper()} Orders")
        selection_window.geometry("900x600")
        
        selection_frame = ttk.Frame(selection_window)
        selection_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        tree_scroll = ttk.Scrollbar(selection_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        select_tree = ttk.Treeview(selection_frame, columns=(
            'Select', 'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP'
        ), show='headings', yscrollcommand=tree_scroll.set, height=20)
        
        tree_scroll.config(command=select_tree.yview)
        
        select_tree.heading('Select', text='✓')
        select_tree.heading('Symbol', text='Symbol')
        select_tree.heading('Name', text='Name')
        select_tree.heading('Expiry', text='Expiry')
        select_tree.heading('Strike', text='Strike')
        select_tree.heading('Type', text='Type')
        select_tree.heading('Lot Size', text='Lot Size')
        select_tree.heading('LTP', text='LTP')
        
        select_tree.column('Select', width=50, anchor='center')
        select_tree.column('Symbol', width=150)
        select_tree.column('Name', width=100)
        select_tree.column('Expiry', width=100)
        select_tree.column('Strike', width=80, anchor='center')
        select_tree.column('Type', width=60, anchor='center')
        select_tree.column('Lot Size', width=80, anchor='center')
        select_tree.column('LTP', width=80, anchor='center')
        
        select_tree.pack(fill='both', expand=True)
        
        for item in self.nse_options_tree.get_children():
            values = self.nse_options_tree.item(item, 'values')
            if values:
                select_tree.insert('', 'end', values=('□',) + values, tags=('unselected',))
        
        select_tree.bind('<Button-1>', lambda e: self.on_nse_options_selection_tree_click(e, select_tree, order_type))
        
        button_frame = ttk.Frame(selection_window)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text="Select All", 
                  command=lambda: self.select_all_nse_options_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear All", 
                  command=lambda: self.clear_all_nse_options_in_tree(select_tree, order_type)).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Confirm Selection", 
                  command=lambda: self.confirm_nse_options_selection(select_tree, selection_window, order_type)).pack(side='right', padx=5)
    
    def on_nse_options_selection_tree_click(self, event, tree, order_type):
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        
        if item and column == '#1':
            values = tree.item(item, 'values')
            symbol = values[1]
            
            if order_type == 'single':
                current_selection = self.selected_nse_single_options
            elif order_type == 'buy':
                current_selection = self.selected_nse_buy_options
            else:
                current_selection = self.selected_nse_sell_options
            
            if symbol in current_selection:
                tree.set(item, 'Select', '□')
                tree.item(item, tags=('unselected',))
                del current_selection[symbol]
            else:
                tree.set(item, 'Select', '✓')
                tree.item(item, tags=('selected',))
                current_selection[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'strike': values[4],
                    'type': values[5],
                    'lot_size': values[6],
                    'ltp': values[7] if len(values) > 7 else 'N/A'
                }
    
    def select_all_nse_options_in_tree(self, tree, order_type):
        for item in tree.get_children():
            values = tree.item(item, 'values')
            symbol = values[1]
            
            tree.set(item, 'Select', '✓')
            tree.item(item, tags=('selected',))
            
            contract_data = {
                'symbol': symbol,
                'name': values[2],
                'expiry': values[3],
                'strike': values[4],
                'type': values[5],
                'lot_size': values[6],
                'ltp': values[7] if len(values) > 7 else 'N/A'
            }
            
            if order_type == 'single':
                self.selected_nse_single_options[symbol] = contract_data
            elif order_type == 'buy':
                self.selected_nse_buy_options[symbol] = contract_data
            else:
                self.selected_nse_sell_options[symbol] = contract_data
    
    def clear_all_nse_options_in_tree(self, tree, order_type):
        for item in tree.get_children():
            tree.set(item, 'Select', '□')
            tree.item(item, tags=('unselected',))
        
        if order_type == 'single':
            self.selected_nse_single_options.clear()
        elif order_type == 'buy':
            self.selected_nse_buy_options.clear()
        else:
            self.selected_nse_sell_options.clear()
    
    def confirm_nse_options_selection(self, tree, window, order_type):
        if order_type == 'single':
            self.update_nse_options_single_selection_display()
            message = f"{len(self.selected_nse_single_options)} NSE options contracts selected for trading"
        elif order_type == 'buy':
            self.update_nse_options_buy_selection_display()
            message = f"{len(self.selected_nse_buy_options)} NSE options contracts selected for BUY orders"
        else:
            self.update_nse_options_sell_selection_display()
            message = f"{len(self.selected_nse_sell_options)} NSE options contracts selected for SELL orders"
        
        window.destroy()
        messagebox.showinfo("Selection Complete", message)
    
    def update_nse_options_single_selection_display(self):
        self.selected_nse_options_single_text.delete(1.0, tk.END)
        if not self.selected_nse_single_options:
            self.selected_nse_options_single_text.insert(tk.END, "No NSE options contracts selected")
            return
        for symbol, details in self.selected_nse_single_options.items():
            self.selected_nse_options_single_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_nse_options_buy_selection_display(self):
        self.selected_nse_options_buy_text.delete(1.0, tk.END)
        if not self.selected_nse_buy_options:
            self.selected_nse_options_buy_text.insert(tk.END, "No BUY NSE options contracts selected")
            return
        for symbol, details in self.selected_nse_buy_options.items():
            self.selected_nse_options_buy_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def update_nse_options_sell_selection_display(self):
        self.selected_nse_options_sell_text.delete(1.0, tk.END)
        if not self.selected_nse_sell_options:
            self.selected_nse_options_sell_text.insert(tk.END, "No SELL NSE options contracts selected")
            return
        for symbol, details in self.selected_nse_sell_options.items():
            self.selected_nse_options_sell_text.insert(tk.END, 
                f"Symbol: {symbol}\nName: {details['name']}\nExpiry: {details['expiry']}\nStrike: {details['strike']}\nType: {details['type']}\nLot Size: {details['lot_size']}\nLTP: {details.get('ltp', 'N/A')}\n{'-'*40}\n")
    
    def clear_nse_options_single_selection(self):
        self.selected_nse_single_options.clear()
        self.update_nse_options_single_selection_display()
    
    def clear_nse_options_buy_selection(self):
        self.selected_nse_buy_options.clear()
        self.update_nse_options_buy_selection_display()
    
    def clear_nse_options_sell_selection(self):
        self.selected_nse_sell_options.clear()
        self.update_nse_options_sell_selection_display()
    
    def validate_nse_options_single_selection(self):
        if not self.selected_nse_single_options:
            messagebox.showwarning("Warning", "No NSE options contracts selected")
            return
        messagebox.showinfo("Selection Valid", f"{len(self.selected_nse_single_options)} NSE options contracts selected and ready for trading")
    
    # ---------- Real-time Price Methods ----------
    def get_current_price(self, symbol, exchange="MCX"):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ltp_data = self.kite.ltp(f"{exchange}:{symbol}")
                price = list(ltp_data.values())[0]['last_price']
                self.current_prices[symbol] = price
                return price
            except Exception as e:
                self.log_message(f"Price fetch attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        return None
    
    def start_price_updates_for_order(self, symbols, exchange="MCX"):
        self.price_update_event.clear()
        Thread(target=self._update_prices_continuously, args=(symbols, exchange), daemon=True).start()
    
    def stop_price_updates(self):
        self.price_update_event.set()
    
    def _update_prices_continuously(self, symbols, exchange="MCX"):
        while not self.price_update_event.is_set() and self.is_logged_in:
            try:
                batch_size = 10
                for i in range(0, len(symbols), batch_size):
                    batch_symbols = symbols[i:i + batch_size]
                    instruments = [f"{exchange}:{symbol}" for symbol in batch_symbols]
                    ltp_data = self.kite.ltp(instruments)
                    for instrument_key, data in ltp_data.items():
                        symbol = instrument_key.replace(f"{exchange}:", "")
                        self.current_prices[symbol] = data['last_price']
                    time.sleep(0.2)
                time.sleep(1)
            except Exception as e:
                self.log_message(f"Error in continuous price update: {e}")
                time.sleep(2)
    
    # ---------- Futures Order Placement Methods ----------
    def place_futures_single_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_single_futures:
            messagebox.showwarning("Warning", "No futures contracts selected")
            return
        try:
            transaction = self.futures_transaction_type.get()
            order_type = self.futures_order_type.get()
            quantity_type = self.futures_quantity_type.get()
            base_quantity = int(self.futures_quantity_entry.get())
            price = float(self.futures_price_entry.get()) if self.futures_price_entry.get() and float(self.futures_price_entry.get()) > 0 else 0
            symbols = list(self.selected_single_futures.keys())
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(symbols, "MCX")
            self.show_futures_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting futures order placement: {e}")
    
    def place_futures_buy_sell_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_buy_futures and not self.selected_sell_futures:
            messagebox.showwarning("Warning", "No futures contracts selected for BUY or SELL")
            return
        try:
            buy_order_type = self.futures_buy_order_type.get()
            buy_quantity_type = self.futures_buy_quantity_type.get()
            buy_quantity = int(self.futures_buy_quantity_entry.get())
            buy_price = float(self.futures_buy_price_entry.get()) if self.futures_buy_price_entry.get() and float(self.futures_buy_price_entry.get()) > 0 else 0
            sell_order_type = self.futures_sell_order_type.get()
            sell_quantity_type = self.futures_sell_quantity_type.get()
            sell_quantity = int(self.futures_sell_quantity_entry.get())
            sell_price = float(self.futures_sell_price_entry.get()) if self.futures_sell_price_entry.get() and float(self.futures_sell_price_entry.get()) > 0 else 0
            buy_symbols = list(self.selected_buy_futures.keys())
            sell_symbols = list(self.selected_sell_futures.keys())
            all_symbols = buy_symbols + sell_symbols
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(all_symbols, "MCX")
            self.show_futures_buy_sell_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                sell_order_type, sell_quantity_type, sell_quantity, sell_price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting futures buy/sell order placement: {e}")
    
    # ---------- MCX Options Order Placement Methods ----------
    def place_options_single_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_single_options:
            messagebox.showwarning("Warning", "No MCX options contracts selected")
            return
        try:
            transaction = self.options_transaction_type.get()
            order_type = self.options_order_type.get()
            quantity_type = self.options_quantity_type.get()
            base_quantity = int(self.options_quantity_entry.get())
            price = float(self.options_price_entry.get()) if self.options_price_entry.get() and float(self.options_price_entry.get()) > 0 else 0
            symbols = list(self.selected_single_options.keys())
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(symbols, "MCX")
            self.show_options_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting options order placement: {e}")
    
    def place_options_buy_sell_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_buy_options and not self.selected_sell_options:
            messagebox.showwarning("Warning", "No MCX options contracts selected for BUY or SELL")
            return
        try:
            buy_order_type = self.options_buy_order_type.get()
            buy_quantity_type = self.options_buy_quantity_type.get()
            buy_quantity = int(self.options_buy_quantity_entry.get())
            buy_price = float(self.options_buy_price_entry.get()) if self.options_buy_price_entry.get() and float(self.options_buy_price_entry.get()) > 0 else 0
            sell_order_type = self.options_sell_order_type.get()
            sell_quantity_type = self.options_sell_quantity_type.get()
            sell_quantity = int(self.options_sell_quantity_entry.get())
            sell_price = float(self.options_sell_price_entry.get()) if self.options_sell_price_entry.get() and float(self.options_sell_price_entry.get()) > 0 else 0
            buy_symbols = list(self.selected_buy_options.keys())
            sell_symbols = list(self.selected_sell_options.keys())
            all_symbols = buy_symbols + sell_symbols
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(all_symbols, "MCX")
            self.show_options_buy_sell_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                sell_order_type, sell_quantity_type, sell_quantity, sell_price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting options buy/sell order placement: {e}")
    
    # ---------- NFO Options Order Placement Methods ----------
    def place_nfo_options_single_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_nfo_single_options:
            messagebox.showwarning("Warning", "No NFO options contracts selected")
            return
        try:
            transaction = self.nfo_options_transaction_type.get()
            order_type = self.nfo_options_order_type.get()
            quantity_type = self.nfo_options_quantity_type.get()
            base_quantity = int(self.nfo_options_quantity_entry.get())
            price = float(self.nfo_options_price_entry.get()) if self.nfo_options_price_entry.get() and float(self.nfo_options_price_entry.get()) > 0 else 0
            symbols = list(self.selected_nfo_single_options.keys())
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(symbols, "NFO")
            self.show_nfo_options_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting NFO options order placement: {e}")
    
    def place_nfo_options_buy_sell_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_nfo_buy_options and not self.selected_nfo_sell_options:
            messagebox.showwarning("Warning", "No NFO options contracts selected for BUY or SELL")
            return
        try:
            buy_order_type = self.nfo_options_buy_order_type.get()
            buy_quantity_type = self.nfo_options_buy_quantity_type.get()
            buy_quantity = int(self.nfo_options_buy_quantity_entry.get())
            buy_price = float(self.nfo_options_buy_price_entry.get()) if self.nfo_options_buy_price_entry.get() and float(self.nfo_options_buy_price_entry.get()) > 0 else 0
            sell_order_type = self.nfo_options_sell_order_type.get()
            sell_quantity_type = self.nfo_options_sell_quantity_type.get()
            sell_quantity = int(self.nfo_options_sell_quantity_entry.get())
            sell_price = float(self.nfo_options_sell_price_entry.get()) if self.nfo_options_sell_price_entry.get() and float(self.nfo_options_sell_price_entry.get()) > 0 else 0
            buy_symbols = list(self.selected_nfo_buy_options.keys())
            sell_symbols = list(self.selected_nfo_sell_options.keys())
            all_symbols = buy_symbols + sell_symbols
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(all_symbols, "NFO")
            self.show_nfo_options_buy_sell_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                sell_order_type, sell_quantity_type, sell_quantity, sell_price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting NFO options buy/sell order placement: {e}")
    
    # ---------- NSE Options Order Placement Methods ----------
    def place_nse_options_single_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_nse_single_options:
            messagebox.showwarning("Warning", "No NSE options contracts selected")
            return
        try:
            transaction = self.nse_options_transaction_type.get()
            order_type = self.nse_options_order_type.get()
            quantity_type = self.nse_options_quantity_type.get()
            base_quantity = int(self.nse_options_quantity_entry.get())
            price = float(self.nse_options_price_entry.get()) if self.nse_options_price_entry.get() and float(self.nse_options_price_entry.get()) > 0 else 0
            symbols = list(self.selected_nse_single_options.keys())
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(symbols, "NFO")
            self.show_nse_options_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting NSE options order placement: {e}")
    
    def place_nse_options_buy_sell_orders(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not self.selected_nse_buy_options and not self.selected_nse_sell_options:
            messagebox.showwarning("Warning", "No NSE options contracts selected for BUY or SELL")
            return
        try:
            buy_order_type = self.nse_options_buy_order_type.get()
            buy_quantity_type = self.nse_options_buy_quantity_type.get()
            buy_quantity = int(self.nse_options_buy_quantity_entry.get())
            buy_price = float(self.nse_options_buy_price_entry.get()) if self.nse_options_buy_price_entry.get() and float(self.nse_options_buy_price_entry.get()) > 0 else 0
            sell_order_type = self.nse_options_sell_order_type.get()
            sell_quantity_type = self.nse_options_sell_quantity_type.get()
            sell_quantity = int(self.nse_options_sell_quantity_entry.get())
            sell_price = float(self.nse_options_sell_price_entry.get()) if self.nse_options_sell_price_entry.get() and float(self.nse_options_sell_price_entry.get()) > 0 else 0
            buy_symbols = list(self.selected_nse_buy_options.keys())
            sell_symbols = list(self.selected_nse_sell_options.keys())
            all_symbols = buy_symbols + sell_symbols
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            self.start_price_updates_for_order(all_symbols, "NFO")
            self.show_nse_options_buy_sell_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                sell_order_type, sell_quantity_type, sell_quantity, sell_price)
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting NSE options buy/sell order placement: {e}")
    
    # ---------- Spread Order Methods ----------
    def place_mcx_spread_order(self):
        self._place_spread_order("MCX", self.selected_buy_options, self.selected_sell_options,
                                 self.options_buy_order_type, self.options_buy_quantity_type, self.options_buy_quantity_entry,
                                 self.options_buy_price_entry, self.options_sell_order_type, self.options_sell_quantity_type,
                                 self.options_sell_quantity_entry, self.options_sell_price_entry,
                                 self.mcx_spread_margin_entry, self.log_options_message)
    
    def exit_mcx_spread(self):
        self._exit_spread("MCX", self.selected_buy_options, self.selected_sell_options, self.log_options_message)
    
    def place_nfo_spread_order(self):
        self._place_spread_order("NFO", self.selected_nfo_buy_options, self.selected_nfo_sell_options,
                                 self.nfo_options_buy_order_type, self.nfo_options_buy_quantity_type, self.nfo_options_buy_quantity_entry,
                                 self.nfo_options_buy_price_entry, self.nfo_options_sell_order_type, self.nfo_options_sell_quantity_type,
                                 self.nfo_options_sell_quantity_entry, self.nfo_options_sell_price_entry,
                                 self.nfo_spread_margin_entry, self.log_nfo_options_message)
    
    def exit_nfo_spread(self):
        self._exit_spread("NFO", self.selected_nfo_buy_options, self.selected_nfo_sell_options, self.log_nfo_options_message)
    
    def place_nse_spread_order(self):
        self._place_spread_order("NFO", self.selected_nse_buy_options, self.selected_nse_sell_options,
                                 self.nse_options_buy_order_type, self.nse_options_buy_quantity_type, self.nse_options_buy_quantity_entry,
                                 self.nse_options_buy_price_entry, self.nse_options_sell_order_type, self.nse_options_sell_quantity_type,
                                 self.nse_options_sell_quantity_entry, self.nse_options_sell_price_entry,
                                 self.nse_spread_margin_entry, self.log_nse_options_message)
    
    def exit_nse_spread(self):
        self._exit_spread("NFO", self.selected_nse_buy_options, self.selected_nse_sell_options, self.log_nse_options_message)
    
    def _place_spread_order(self, exchange, buy_dict, sell_dict,
                            buy_order_type_var, buy_qty_type_var, buy_qty_entry,
                            buy_price_entry, sell_order_type_var, sell_qty_type_var,
                            sell_qty_entry, sell_price_entry, margin_entry, log_func):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        if not buy_dict or not sell_dict:
            messagebox.showwarning("Warning", "Please select both a BUY and a SELL contract")
            return
        try:
            margin = float(margin_entry.get())
        except:
            messagebox.showerror("Error", "Invalid margin value")
            return
        
        # Take only the first selected buy and sell (simplify)
        buy_symbol = list(buy_dict.keys())[0]
        sell_symbol = list(sell_dict.keys())[0]
        buy_details = buy_dict[buy_symbol]
        sell_details = sell_dict[sell_symbol]
        
        # Get order parameters
        buy_order_type = buy_order_type_var.get()
        buy_quantity_type = buy_qty_type_var.get()
        buy_qty = int(buy_qty_entry.get())
        buy_price = float(buy_price_entry.get()) if buy_price_entry.get() and float(buy_price_entry.get()) > 0 else 0
        
        sell_order_type = sell_order_type_var.get()
        sell_quantity_type = sell_qty_type_var.get()
        sell_qty = int(sell_qty_entry.get())
        sell_price = float(sell_price_entry.get()) if sell_price_entry.get() and float(sell_price_entry.get()) > 0 else 0
        
        symbols = [buy_symbol, sell_symbol]
        self.start_price_updates_for_order(symbols, exchange)
        
        # Show confirmation window
        self.show_spread_confirmation_window(
            buy_symbol, buy_details, buy_order_type, buy_quantity_type, buy_qty, buy_price,
            sell_symbol, sell_details, sell_order_type, sell_quantity_type, sell_qty, sell_price,
            margin, exchange, log_func)
    
    def show_spread_confirmation_window(self, buy_symbol, buy_details, buy_otype, buy_qtype, buy_qty, buy_price,
                                        sell_symbol, sell_details, sell_otype, sell_qtype, sell_qty, sell_price,
                                        margin, exchange, log_func):
        window = tk.Toplevel(self.root)
        window.title("Spread Order Confirmation")
        window.geometry("600x500")
        window.transient(self.root)
        window.grab_set()
        self.real_time_windows.append(window)
        
        main_frame = ttk.Frame(window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        ttk.Label(main_frame, text="Real-time Prices for Spread", font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Buy leg
        buy_frame = ttk.LabelFrame(main_frame, text="BUY Leg")
        buy_frame.pack(fill='x', pady=5)
        ttk.Label(buy_frame, text=f"Symbol: {buy_symbol}").pack(anchor='w', padx=5)
        self.buy_price_label = ttk.Label(buy_frame, text="Fetching...", foreground='blue')
        self.buy_price_label.pack(anchor='w', padx=5)
        ttk.Label(buy_frame, text=f"Qty: {buy_qty} ({buy_qtype}), Type: {buy_otype}").pack(anchor='w', padx=5)
        
        # Sell leg
        sell_frame = ttk.LabelFrame(main_frame, text="SELL Leg")
        sell_frame.pack(fill='x', pady=5)
        ttk.Label(sell_frame, text=f"Symbol: {sell_symbol}").pack(anchor='w', padx=5)
        self.sell_price_label = ttk.Label(sell_frame, text="Fetching...", foreground='red')
        self.sell_price_label.pack(anchor='w', padx=5)
        ttk.Label(sell_frame, text=f"Qty: {sell_qty} ({sell_qtype}), Type: {sell_otype}").pack(anchor='w', padx=5)
        
        ttk.Label(main_frame, text=f"Max Margin: ₹{margin:.2f}").pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10)
        
        def confirm():
            window.destroy()
            self.real_time_windows.remove(window)
            self.stop_price_updates()
            self._execute_spread_order(
                buy_symbol, buy_details, buy_otype, buy_qtype, buy_qty, buy_price,
                sell_symbol, sell_details, sell_otype, sell_qtype, sell_qty, sell_price,
                exchange, log_func)
        
        def cancel():
            window.destroy()
            self.real_time_windows.remove(window)
            self.stop_price_updates()
            log_func("Spread order cancelled")
        
        ttk.Button(button_frame, text="Confirm Spread", command=confirm).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel).pack(side='left', padx=5)
        
        # Update prices periodically
        self.update_spread_price_display(window)
    
    def update_spread_price_display(self, window):
        if not window.winfo_exists():
            return
        try:
            # We need to know the symbols from the window's labels - we stored them in instance vars for simplicity
            if hasattr(self, 'buy_price_label') and self.buy_price_label.winfo_exists():
                # Extract symbol from parent label text
                parent = self.buy_price_label.master
                for child in parent.winfo_children():
                    if isinstance(child, ttk.Label) and "Symbol:" in child.cget("text"):
                        buy_sym = child.cget("text").replace("Symbol: ", "").strip()
                        break
                else:
                    buy_sym = None
                if buy_sym:
                    buy_price = self.current_prices.get(buy_sym)
                    if buy_price:
                        self.buy_price_label.config(text=f"LTP: ₹{buy_price:.2f}")
                    else:
                        self.buy_price_label.config(text="LTP: Unavailable")
            if hasattr(self, 'sell_price_label') and self.sell_price_label.winfo_exists():
                parent = self.sell_price_label.master
                for child in parent.winfo_children():
                    if isinstance(child, ttk.Label) and "Symbol:" in child.cget("text"):
                        sell_sym = child.cget("text").replace("Symbol: ", "").strip()
                        break
                else:
                    sell_sym = None
                if sell_sym:
                    sell_price = self.current_prices.get(sell_sym)
                    if sell_price:
                        self.sell_price_label.config(text=f"LTP: ₹{sell_price:.2f}")
                    else:
                        self.sell_price_label.config(text="LTP: Unavailable")
        except:
            pass
        if window.winfo_exists():
            window.after(1000, lambda: self.update_spread_price_display(window))
    
    def _execute_spread_order(self, buy_symbol, buy_details, buy_otype, buy_qtype, buy_qty, buy_price,
                               sell_symbol, sell_details, sell_otype, sell_qtype, sell_qty, sell_price,
                               exchange, log_func):
        # Get current prices
        buy_ltp = self.current_prices.get(buy_symbol)
        sell_ltp = self.current_prices.get(sell_symbol)
        if not buy_ltp or not sell_ltp:
            log_func("❌ Prices not available for both legs, aborting spread")
            messagebox.showerror("Error", "Could not fetch current prices")
            return
        
        # Calculate quantities
        if buy_qtype == "Lot Size":
            buy_quantity = buy_qty * int(buy_details['lot_size'])
        else:
            buy_quantity = buy_qty
        
        if sell_qtype == "Lot Size":
            sell_quantity = sell_qty * int(sell_details['lot_size'])
        else:
            sell_quantity = sell_qty
        
        # Determine final limit prices
        buy_final = buy_price if buy_otype == "LIMIT" and buy_price > 0 else None
        sell_final = sell_price if sell_otype == "LIMIT" and sell_price > 0 else None
        
        # Place orders
        try:
            buy_order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=buy_symbol,
                transaction_type="BUY",
                quantity=buy_quantity,
                order_type=buy_otype,
                product=self.kite.PRODUCT_NRML,
                price=buy_final
            )
            log_func(f"Spread BUY placed: {buy_symbol} {buy_quantity} @ {buy_final if buy_final else 'MARKET'} - ID: {buy_order_id}")
            
            sell_order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=sell_symbol,
                transaction_type="SELL",
                quantity=sell_quantity,
                order_type=sell_otype,
                product=self.kite.PRODUCT_NRML,
                price=sell_final
            )
            log_func(f"Spread SELL placed: {sell_symbol} {sell_quantity} @ {sell_final if sell_final else 'MARKET'} - ID: {sell_order_id}")
            
            messagebox.showinfo("Spread Orders Placed", f"BUY ID: {buy_order_id}\nSELL ID: {sell_order_id}")
        except Exception as e:
            log_func(f"❌ Spread order failed: {e}")
            messagebox.showerror("Error", f"Spread order failed: {e}")
    
    def _exit_spread(self, exchange, buy_dict, sell_dict, log_func):
        """Square off both legs by placing opposite market orders."""
        if not self.is_logged_in:
            return
        if not buy_dict or not sell_dict:
            messagebox.showwarning("Warning", "Please select the spread contracts you want to exit")
            return
        buy_symbol = list(buy_dict.keys())[0]
        sell_symbol = list(sell_dict.keys())[0]
        
        # Get current positions for these symbols
        try:
            positions = self.kite.positions()
            # Find net position for each symbol
            buy_position_qty = 0
            sell_position_qty = 0
            for pos in positions['net']:
                if pos['tradingsymbol'] == buy_symbol and pos['quantity'] != 0:
                    buy_position_qty = pos['quantity']  # positive if long
                if pos['tradingsymbol'] == sell_symbol and pos['quantity'] != 0:
                    sell_position_qty = pos['quantity']  # negative if short
            
            # Exit buy leg: if long, sell
            if buy_position_qty > 0:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=exchange,
                    tradingsymbol=buy_symbol,
                    transaction_type="SELL",
                    quantity=abs(buy_position_qty),
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_NRML
                )
                log_func(f"Exited BUY leg: {buy_symbol} SELL {abs(buy_position_qty)} - ID: {order_id}")
            else:
                log_func(f"No long position found for {buy_symbol}")
            
            # Exit sell leg: if short, buy
            if sell_position_qty < 0:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=exchange,
                    tradingsymbol=sell_symbol,
                    transaction_type="BUY",
                    quantity=abs(sell_position_qty),
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    product=self.kite.PRODUCT_NRML
                )
                log_func(f"Exited SELL leg: {sell_symbol} BUY {abs(sell_position_qty)} - ID: {order_id}")
            else:
                log_func(f"No short position found for {sell_symbol}")
            
            messagebox.showinfo("Spread Exit", "Exit orders placed. Check log for details.")
        except Exception as e:
            log_func(f"❌ Error exiting spread: {e}")
            messagebox.showerror("Error", f"Exit failed: {e}")
    
    # ---------- Strategy Execution ----------
    def execute_options_strategy(self):
        strategy = self.strategy_var.get()
        underlying = self.strategy_underlying_var.get()
        try:
            strike_price = float(self.strike_price_entry.get())
            quantity = int(self.strategy_quantity_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid strike price and quantity")
            return
        messagebox.showinfo("Strategy Execution", 
                          f"Preparing to execute {strategy} strategy for MCX {underlying}\n"
                          f"Strike: {strike_price}, Quantity: {quantity}\n\n"
                          f"This would place the appropriate options orders based on the selected strategy.")
    
    def execute_nfo_options_strategy(self):
        strategy = self.nfo_strategy_var.get()
        underlying = self.nfo_strategy_underlying_var.get()
        try:
            strike_price = float(self.nfo_strike_price_entry.get())
            quantity = int(self.nfo_strategy_quantity_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid strike price and quantity")
            return
        messagebox.showinfo("NFO Strategy Execution", 
                          f"Preparing to execute {strategy} strategy for NFO {underlying}\n"
                          f"Strike: {strike_price}, Quantity: {quantity}\n\n"
                          f"This would place the appropriate options orders based on the selected strategy.")
    
    def execute_nse_options_strategy(self):
        strategy = self.nse_strategy_var.get()
        underlying = self.nse_strategy_underlying_var.get()
        try:
            strike_price = float(self.nse_strike_price_entry.get())
            quantity = int(self.nse_strategy_quantity_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid strike price and quantity")
            return
        messagebox.showinfo("NSE Strategy Execution", 
                          f"Preparing to execute {strategy} strategy for NSE {underlying}\n"
                          f"Strike: {strike_price}, Quantity: {quantity}\n\n"
                          f"This would place the appropriate options orders based on the selected strategy.")
    
    # ---------- Real-time Price Windows ----------
    def show_futures_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time Futures Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time Futures Prices (Updating every 1 second)", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='blue', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="Futures Order Information")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='green').pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_futures_single_orders_with_current_prices,
                   args=(transaction, order_type, quantity_type, base_quantity, price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_futures_message("Futures order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place Futures Orders Now", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_futures_price_display(price_labels, price_window)
    
    def update_futures_price_display(self, price_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in price_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='blue')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating futures price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_futures_price_display(price_labels, window))
    
    def show_futures_buy_sell_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity_type, 
                                             buy_quantity, buy_price, sell_order_type, sell_quantity_type, 
                                             sell_quantity, sell_price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time Futures Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time Futures Prices for BUY & SELL Orders", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        buy_frame = ttk.LabelFrame(paned_window, text="BUY Futures Contracts")
        paned_window.add(buy_frame, weight=1)
        sell_frame = ttk.LabelFrame(paned_window, text="SELL Futures Contracts")
        paned_window.add(sell_frame, weight=1)
        
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            buy_price_labels[symbol] = price_label
        
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            sell_price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="Futures Order Summary")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='blue').pack(pady=2)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_futures_buy_sell_orders_with_current_prices,
                   args=(buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                         sell_order_type, sell_quantity_type, sell_quantity, sell_price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_futures_message("Futures BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY & SELL Futures Orders", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_futures_buy_sell_price_display(buy_price_labels, sell_price_labels, price_window)
    
    def update_futures_buy_sell_price_display(self, buy_labels, sell_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in buy_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            for symbol, label in sell_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating futures buy/sell price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_futures_buy_sell_price_display(buy_labels, sell_labels, window))
    
    def show_options_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time MCX Options Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time MCX Options Prices (Updating every 1 second)", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='blue', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="Options Order Information")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='green').pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_options_single_orders_with_current_prices,
                   args=(transaction, order_type, quantity_type, base_quantity, price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_options_message("MCX options order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place MCX Options Orders Now", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_options_price_display(price_labels, price_window)
    
    def update_options_price_display(self, price_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in price_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='blue')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating options price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_options_price_display(price_labels, window))
    
    def show_options_buy_sell_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity_type, 
                                             buy_quantity, buy_price, sell_order_type, sell_quantity_type, 
                                             sell_quantity, sell_price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time MCX Options Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time MCX Options Prices for BUY & SELL Orders", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        buy_frame = ttk.LabelFrame(paned_window, text="BUY MCX Options Contracts")
        paned_window.add(buy_frame, weight=1)
        sell_frame = ttk.LabelFrame(paned_window, text="SELL MCX Options Contracts")
        paned_window.add(sell_frame, weight=1)
        
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            buy_price_labels[symbol] = price_label
        
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            sell_price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="MCX Options Order Summary")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='blue').pack(pady=2)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_options_buy_sell_orders_with_current_prices,
                   args=(buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                         sell_order_type, sell_quantity_type, sell_quantity, sell_price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_options_message("MCX options BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY & SELL MCX Options Orders", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_options_buy_sell_price_display(buy_price_labels, sell_price_labels, price_window)
    
    def update_options_buy_sell_price_display(self, buy_labels, sell_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in buy_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            for symbol, label in sell_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating options buy/sell price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_options_buy_sell_price_display(buy_labels, sell_labels, window))
    
    def show_nfo_options_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time NFO Options Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        title_label = ttk.Label(main_frame, text="Real-time NFO Options Prices (Updating every 1 second)", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='blue', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="NFO Options Order Information")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='green').pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_nfo_options_single_orders_with_current_prices,
                   args=(transaction, order_type, quantity_type, base_quantity, price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_nfo_options_message("NFO options order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place NFO Options Orders Now", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_nfo_options_price_display(price_labels, price_window)
    
    def update_nfo_options_price_display(self, price_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in price_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='blue')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating NFO options price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_nfo_options_price_display(price_labels, window))
    
    def show_nfo_options_buy_sell_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity_type, 
                                                 buy_quantity, buy_price, sell_order_type, sell_quantity_type, 
                                                 sell_quantity, sell_price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time NFO Options Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        title_label = ttk.Label(main_frame, text="Real-time NFO Options Prices for BUY & SELL Orders", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        buy_frame = ttk.LabelFrame(paned_window, text="BUY NFO Options Contracts")
        paned_window.add(buy_frame, weight=1)
        sell_frame = ttk.LabelFrame(paned_window, text="SELL NFO Options Contracts")
        paned_window.add(sell_frame, weight=1)
        
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            buy_price_labels[symbol] = price_label
        
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            sell_price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="NFO Options Order Summary")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='blue').pack(pady=2)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_nfo_options_buy_sell_orders_with_current_prices,
                   args=(buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                         sell_order_type, sell_quantity_type, sell_quantity, sell_price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_nfo_options_message("NFO options BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY & SELL NFO Options Orders", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_nfo_options_buy_sell_price_display(buy_price_labels, sell_price_labels, price_window)
    
    def update_nfo_options_buy_sell_price_display(self, buy_labels, sell_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in buy_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            for symbol, label in sell_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating NFO options buy/sell price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_nfo_options_buy_sell_price_display(buy_labels, sell_labels, window))
    
    def show_nse_options_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time NSE Options Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        title_label = ttk.Label(main_frame, text="Real-time NSE Options Prices (Updating every 1 second)", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='blue', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="NSE Options Order Information")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='green').pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_nse_options_single_orders_with_current_prices,
                   args=(transaction, order_type, quantity_type, base_quantity, price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_nse_options_message("NSE options order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place NSE Options Orders Now", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_nse_options_price_display(price_labels, price_window)
    
    def update_nse_options_price_display(self, price_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in price_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='blue')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating NSE options price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_nse_options_price_display(price_labels, window))
    
    def show_nse_options_buy_sell_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity_type, 
                                                 buy_quantity, buy_price, sell_order_type, sell_quantity_type, 
                                                 sell_quantity, sell_price):
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time NSE Options Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        title_label = ttk.Label(main_frame, text="Real-time NSE Options Prices for BUY & SELL Orders", font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        buy_frame = ttk.LabelFrame(paned_window, text="BUY NSE Options Contracts")
        paned_window.add(buy_frame, weight=1)
        sell_frame = ttk.LabelFrame(paned_window, text="SELL NSE Options Contracts")
        paned_window.add(sell_frame, weight=1)
        
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            buy_price_labels[symbol] = price_label
        
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            sell_price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="NSE Options Order Summary")
        info_frame.pack(fill='x', pady=10)
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", foreground='blue').pack(pady=2)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            Thread(target=self.execute_nse_options_buy_sell_orders_with_current_prices,
                   args=(buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                         sell_order_type, sell_quantity_type, sell_quantity, sell_price), daemon=True).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_nse_options_message("NSE options BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY & SELL NSE Options Orders", command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_orders).pack(side='left', padx=5)
        
        self.update_nse_options_buy_sell_price_display(buy_price_labels, sell_price_labels, price_window)
    
    def update_nse_options_buy_sell_price_display(self, buy_labels, sell_labels, window):
        if not window.winfo_exists():
            return
        try:
            for symbol, label in buy_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            for symbol, label in sell_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating NSE options buy/sell price display: {e}")
        if window.winfo_exists():
            window.after(1000, lambda: self.update_nse_options_buy_sell_price_display(buy_labels, sell_labels, window))
    
    # ---------- Order Execution Methods ----------
    def execute_futures_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        orders_placed = 0
        total_orders = len(self.selected_single_futures)
        self.log_futures_message(f"Starting to place {total_orders} {transaction} futures orders with real-time prices...")
        for symbol, details in self.selected_single_futures.items():
            try:
                current_price = self.current_prices.get(symbol)
                if not current_price:
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_futures_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_futures_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                final_price = price
                if order_type == "LIMIT":
                    if price == 0:
                        if transaction == "BUY":
                            final_price = current_price * 0.995
                        else:
                            final_price = current_price * 1.005
                    else:
                        final_price = price
                    self.log_futures_message(f"Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange="MCX",
                    tradingsymbol=symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    order_type=order_type,
                    product=self.kite.PRODUCT_NRML,
                    price=final_price if order_type == "LIMIT" else None
                )
                orders_placed += 1
                self.log_futures_message(f"✅ {transaction} Futures Order {orders_placed}/{total_orders}: {symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                time.sleep(1)
            except Exception as e:
                self.log_futures_message(f"❌ Failed to place {transaction} futures order for {symbol}: {e}")
        self.log_futures_message(f"{transaction} futures order placement completed: {orders_placed}/{total_orders} successful")
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} futures orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", f"{orders_placed} out of {total_orders} {transaction} futures orders placed successfully")
        self.root.after(0, show_summary)
    
    def execute_futures_buy_sell_orders_with_current_prices(self, buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                                                          sell_order_type, sell_quantity_type, sell_quantity, sell_price):
        total_buy_orders = len(self.selected_buy_futures)
        total_sell_orders = len(self.selected_sell_futures)
        buy_orders_placed = 0
        sell_orders_placed = 0
        self.log_futures_message(f"Starting to place {total_buy_orders} BUY and {total_sell_orders} SELL futures orders with real-time prices...")
        if total_buy_orders > 0:
            self.log_futures_message("=== PLACING BUY FUTURES ORDERS ===")
            for symbol, details in self.selected_buy_futures.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_futures_message(f"❌ Could not fetch LTP for BUY {symbol}, skipping...")
                            continue
                    if buy_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = buy_quantity * lot_size
                    else:
                        quantity = buy_quantity
                    final_price = buy_price
                    if buy_order_type == "LIMIT":
                        if buy_price == 0:
                            final_price = current_price * 0.995
                        self.log_futures_message(f"BUY Futures Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="MCX",
                        tradingsymbol=symbol,
                        transaction_type="BUY",
                        quantity=quantity,
                        order_type=buy_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if buy_order_type == "LIMIT" else None
                    )
                    buy_orders_placed += 1
                    self.log_futures_message(f"✅ BUY Futures Order {buy_orders_placed}/{total_buy_orders}: {symbol} {quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_futures_message(f"❌ Failed to place BUY futures order for {symbol}: {e}")
        if total_sell_orders > 0:
            self.log_futures_message("=== PLACING SELL FUTURES ORDERS ===")
            for symbol, details in self.selected_sell_futures.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_futures_message(f"❌ Could not fetch LTP for SELL {symbol}, skipping...")
                            continue
                    if sell_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = sell_quantity * lot_size
                    else:
                        quantity = sell_quantity
                    final_price = sell_price
                    if sell_order_type == "LIMIT":
                        if sell_price == 0:
                            final_price = current_price * 1.005
                        self.log_futures_message(f"SELL Futures Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="MCX",
                        tradingsymbol=symbol,
                        transaction_type="SELL",
                        quantity=quantity,
                        order_type=sell_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if sell_order_type == "LIMIT" else None
                    )
                    sell_orders_placed += 1
                    self.log_futures_message(f"✅ SELL Futures Order {sell_orders_placed}/{total_sell_orders}: {symbol} {quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_futures_message(f"❌ Failed to place SELL futures order for {symbol}: {e}")
        self.log_futures_message("=== FUTURES ORDER PLACEMENT SUMMARY ===")
        self.log_futures_message(f"BUY Futures Orders: {buy_orders_placed}/{total_buy_orders} successful")
        self.log_futures_message(f"SELL Futures Orders: {sell_orders_placed}/{total_sell_orders} successful")
        def show_final_summary():
            messagebox.showinfo("Buy & Sell Futures Orders Completed",
                f"BUY Futures Orders: {buy_orders_placed}/{total_buy_orders} successful\nSELL Futures Orders: {sell_orders_placed}/{total_sell_orders} successful")
        self.root.after(0, show_final_summary)
    
    def execute_options_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        orders_placed = 0
        total_orders = len(self.selected_single_options)
        self.log_options_message(f"Starting to place {total_orders} {transaction} MCX options orders with real-time prices...")
        for symbol, details in self.selected_single_options.items():
            try:
                current_price = self.current_prices.get(symbol)
                if not current_price:
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_options_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_options_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                final_price = price
                if order_type == "LIMIT":
                    if price == 0:  # Auto limit based on offset
                        if self.options_offset_type.get() == "Percent":
                            offset_factor = self.options_limit_offset.get() / 100.0
                            if transaction == "BUY":
                                final_price = current_price * (1 - offset_factor)
                            else:
                                final_price = current_price * (1 + offset_factor)
                        else:  # Points
                            offset_points = self.options_limit_offset.get()
                            if transaction == "BUY":
                                final_price = current_price - offset_points
                            else:
                                final_price = current_price + offset_points
                        self.log_options_message(f"Auto limit for {symbol}: Using {self.options_offset_type.get()} offset {self.options_limit_offset.get()} -> price {final_price:.2f} (LTP: {current_price:.2f})")
                    else:
                        final_price = price
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange="MCX",
                    tradingsymbol=symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    order_type=order_type,
                    product=self.kite.PRODUCT_NRML,
                    price=final_price if order_type == "LIMIT" else None
                )
                orders_placed += 1
                self.log_options_message(f"✅ {transaction} MCX Options Order {orders_placed}/{total_orders}: {symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                time.sleep(1)
            except Exception as e:
                self.log_options_message(f"❌ Failed to place {transaction} MCX options order for {symbol}: {e}")
        self.log_options_message(f"{transaction} MCX options order placement completed: {orders_placed}/{total_orders} successful")
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} MCX options orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", f"{orders_placed} out of {total_orders} {transaction} MCX options orders placed successfully")
        self.root.after(0, show_summary)
    
    def execute_options_buy_sell_orders_with_current_prices(self, buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                                                          sell_order_type, sell_quantity_type, sell_quantity, sell_price):
        total_buy_orders = len(self.selected_buy_options)
        total_sell_orders = len(self.selected_sell_options)
        buy_orders_placed = 0
        sell_orders_placed = 0
        self.log_options_message(f"Starting to place {total_buy_orders} BUY and {total_sell_orders} SELL MCX options orders with real-time prices...")
        if total_buy_orders > 0:
            self.log_options_message("=== PLACING BUY MCX OPTIONS ORDERS ===")
            for symbol, details in self.selected_buy_options.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_options_message(f"❌ Could not fetch LTP for BUY {symbol}, skipping...")
                            continue
                    if buy_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = buy_quantity * lot_size
                    else:
                        quantity = buy_quantity
                    final_price = buy_price
                    if buy_order_type == "LIMIT":
                        if buy_price == 0:
                            final_price = current_price * 0.995
                        self.log_options_message(f"BUY MCX Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="MCX",
                        tradingsymbol=symbol,
                        transaction_type="BUY",
                        quantity=quantity,
                        order_type=buy_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if buy_order_type == "LIMIT" else None
                    )
                    buy_orders_placed += 1
                    self.log_options_message(f"✅ BUY MCX Options Order {buy_orders_placed}/{total_buy_orders}: {symbol} {quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_options_message(f"❌ Failed to place BUY MCX options order for {symbol}: {e}")
        if total_sell_orders > 0:
            self.log_options_message("=== PLACING SELL MCX OPTIONS ORDERS ===")
            for symbol, details in self.selected_sell_options.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_options_message(f"❌ Could not fetch LTP for SELL {symbol}, skipping...")
                            continue
                    if sell_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = sell_quantity * lot_size
                    else:
                        quantity = sell_quantity
                    final_price = sell_price
                    if sell_order_type == "LIMIT":
                        if sell_price == 0:
                            final_price = current_price * 1.005
                        self.log_options_message(f"SELL MCX Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="MCX",
                        tradingsymbol=symbol,
                        transaction_type="SELL",
                        quantity=quantity,
                        order_type=sell_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if sell_order_type == "LIMIT" else None
                    )
                    sell_orders_placed += 1
                    self.log_options_message(f"✅ SELL MCX Options Order {sell_orders_placed}/{total_sell_orders}: {symbol} {quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_options_message(f"❌ Failed to place SELL MCX options order for {symbol}: {e}")
        self.log_options_message("=== MCX OPTIONS ORDER PLACEMENT SUMMARY ===")
        self.log_options_message(f"BUY MCX Options Orders: {buy_orders_placed}/{total_buy_orders} successful")
        self.log_options_message(f"SELL MCX Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        def show_final_summary():
            messagebox.showinfo("Buy & Sell MCX Options Orders Completed",
                f"BUY MCX Options Orders: {buy_orders_placed}/{total_buy_orders} successful\nSELL MCX Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        self.root.after(0, show_final_summary)
    
    # NFO order execution
    def execute_nfo_options_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        orders_placed = 0
        total_orders = len(self.selected_nfo_single_options)
        self.log_nfo_options_message(f"Starting to place {total_orders} {transaction} NFO options orders with real-time prices...")
        for symbol, details in self.selected_nfo_single_options.items():
            try:
                current_price = self.current_prices.get(symbol)
                if not current_price:
                    try:
                        ltp_data = self.kite.ltp(f"NFO:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_nfo_options_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_nfo_options_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                final_price = price
                if order_type == "LIMIT":
                    if price == 0:
                        if transaction == "BUY":
                            final_price = current_price * 0.995
                        else:
                            final_price = current_price * 1.005
                    else:
                        final_price = price
                    self.log_nfo_options_message(f"Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange="NFO",
                    tradingsymbol=symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    order_type=order_type,
                    product=self.kite.PRODUCT_NRML,
                    price=final_price if order_type == "LIMIT" else None
                )
                orders_placed += 1
                self.log_nfo_options_message(f"✅ {transaction} NFO Options Order {orders_placed}/{total_orders}: {symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                time.sleep(1)
            except Exception as e:
                self.log_nfo_options_message(f"❌ Failed to place {transaction} NFO options order for {symbol}: {e}")
        self.log_nfo_options_message(f"{transaction} NFO options order placement completed: {orders_placed}/{total_orders} successful")
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} NFO options orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", f"{orders_placed} out of {total_orders} {transaction} NFO options orders placed successfully")
        self.root.after(0, show_summary)
    
    def execute_nfo_options_buy_sell_orders_with_current_prices(self, buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                                                              sell_order_type, sell_quantity_type, sell_quantity, sell_price):
        total_buy_orders = len(self.selected_nfo_buy_options)
        total_sell_orders = len(self.selected_nfo_sell_options)
        buy_orders_placed = 0
        sell_orders_placed = 0
        self.log_nfo_options_message(f"Starting to place {total_buy_orders} BUY and {total_sell_orders} SELL NFO options orders with real-time prices...")
        if total_buy_orders > 0:
            self.log_nfo_options_message("=== PLACING BUY NFO OPTIONS ORDERS ===")
            for symbol, details in self.selected_nfo_buy_options.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"NFO:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_nfo_options_message(f"❌ Could not fetch LTP for BUY {symbol}, skipping...")
                            continue
                    if buy_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = buy_quantity * lot_size
                    else:
                        quantity = buy_quantity
                    final_price = buy_price
                    if buy_order_type == "LIMIT":
                        if buy_price == 0:
                            final_price = current_price * 0.995
                        self.log_nfo_options_message(f"BUY NFO Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="NFO",
                        tradingsymbol=symbol,
                        transaction_type="BUY",
                        quantity=quantity,
                        order_type=buy_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if buy_order_type == "LIMIT" else None
                    )
                    buy_orders_placed += 1
                    self.log_nfo_options_message(f"✅ BUY NFO Options Order {buy_orders_placed}/{total_buy_orders}: {symbol} {quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_nfo_options_message(f"❌ Failed to place BUY NFO options order for {symbol}: {e}")
        if total_sell_orders > 0:
            self.log_nfo_options_message("=== PLACING SELL NFO OPTIONS ORDERS ===")
            for symbol, details in self.selected_nfo_sell_options.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"NFO:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_nfo_options_message(f"❌ Could not fetch LTP for SELL {symbol}, skipping...")
                            continue
                    if sell_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = sell_quantity * lot_size
                    else:
                        quantity = sell_quantity
                    final_price = sell_price
                    if sell_order_type == "LIMIT":
                        if sell_price == 0:
                            final_price = current_price * 1.005
                        self.log_nfo_options_message(f"SELL NFO Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="NFO",
                        tradingsymbol=symbol,
                        transaction_type="SELL",
                        quantity=quantity,
                        order_type=sell_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if sell_order_type == "LIMIT" else None
                    )
                    sell_orders_placed += 1
                    self.log_nfo_options_message(f"✅ SELL NFO Options Order {sell_orders_placed}/{total_sell_orders}: {symbol} {quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_nfo_options_message(f"❌ Failed to place SELL NFO options order for {symbol}: {e}")
        self.log_nfo_options_message("=== NFO OPTIONS ORDER PLACEMENT SUMMARY ===")
        self.log_nfo_options_message(f"BUY NFO Options Orders: {buy_orders_placed}/{total_buy_orders} successful")
        self.log_nfo_options_message(f"SELL NFO Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        def show_final_summary():
            messagebox.showinfo("Buy & Sell NFO Options Orders Completed",
                f"BUY NFO Options Orders: {buy_orders_placed}/{total_buy_orders} successful\nSELL NFO Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        self.root.after(0, show_final_summary)
    
    # NSE order execution
    def execute_nse_options_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        orders_placed = 0
        total_orders = len(self.selected_nse_single_options)
        self.log_nse_options_message(f"Starting to place {total_orders} {transaction} NSE options orders with real-time prices...")
        for symbol, details in self.selected_nse_single_options.items():
            try:
                current_price = self.current_prices.get(symbol)
                if not current_price:
                    try:
                        ltp_data = self.kite.ltp(f"NFO:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_nse_options_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_nse_options_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                final_price = price
                if order_type == "LIMIT":
                    if price == 0:
                        if transaction == "BUY":
                            final_price = current_price * 0.995
                        else:
                            final_price = current_price * 1.005
                    else:
                        final_price = price
                    self.log_nse_options_message(f"Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange="NFO",
                    tradingsymbol=symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    order_type=order_type,
                    product=self.kite.PRODUCT_NRML,
                    price=final_price if order_type == "LIMIT" else None
                )
                orders_placed += 1
                self.log_nse_options_message(f"✅ {transaction} NSE Options Order {orders_placed}/{total_orders}: {symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                time.sleep(1)
            except Exception as e:
                self.log_nse_options_message(f"❌ Failed to place {transaction} NSE options order for {symbol}: {e}")
        self.log_nse_options_message(f"{transaction} NSE options order placement completed: {orders_placed}/{total_orders} successful")
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} NSE options orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", f"{orders_placed} out of {total_orders} {transaction} NSE options orders placed successfully")
        self.root.after(0, show_summary)
    
    def execute_nse_options_buy_sell_orders_with_current_prices(self, buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                                                              sell_order_type, sell_quantity_type, sell_quantity, sell_price):
        total_buy_orders = len(self.selected_nse_buy_options)
        total_sell_orders = len(self.selected_nse_sell_options)
        buy_orders_placed = 0
        sell_orders_placed = 0
        self.log_nse_options_message(f"Starting to place {total_buy_orders} BUY and {total_sell_orders} SELL NSE options orders with real-time prices...")
        if total_buy_orders > 0:
            self.log_nse_options_message("=== PLACING BUY NSE OPTIONS ORDERS ===")
            for symbol, details in self.selected_nse_buy_options.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"NFO:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_nse_options_message(f"❌ Could not fetch LTP for BUY {symbol}, skipping...")
                            continue
                    if buy_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = buy_quantity * lot_size
                    else:
                        quantity = buy_quantity
                    final_price = buy_price
                    if buy_order_type == "LIMIT":
                        if buy_price == 0:
                            final_price = current_price * 0.995
                        self.log_nse_options_message(f"BUY NSE Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="NFO",
                        tradingsymbol=symbol,
                        transaction_type="BUY",
                        quantity=quantity,
                        order_type=buy_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if buy_order_type == "LIMIT" else None
                    )
                    buy_orders_placed += 1
                    self.log_nse_options_message(f"✅ BUY NSE Options Order {buy_orders_placed}/{total_buy_orders}: {symbol} {quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_nse_options_message(f"❌ Failed to place BUY NSE options order for {symbol}: {e}")
        if total_sell_orders > 0:
            self.log_nse_options_message("=== PLACING SELL NSE OPTIONS ORDERS ===")
            for symbol, details in self.selected_nse_sell_options.items():
                try:
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"NFO:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_nse_options_message(f"❌ Could not fetch LTP for SELL {symbol}, skipping...")
                            continue
                    if sell_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = sell_quantity * lot_size
                    else:
                        quantity = sell_quantity
                    final_price = sell_price
                    if sell_order_type == "LIMIT":
                        if sell_price == 0:
                            final_price = current_price * 1.005
                        self.log_nse_options_message(f"SELL NSE Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="NFO",
                        tradingsymbol=symbol,
                        transaction_type="SELL",
                        quantity=quantity,
                        order_type=sell_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if sell_order_type == "LIMIT" else None
                    )
                    sell_orders_placed += 1
                    self.log_nse_options_message(f"✅ SELL NSE Options Order {sell_orders_placed}/{total_sell_orders}: {symbol} {quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    time.sleep(1)
                except Exception as e:
                    self.log_nse_options_message(f"❌ Failed to place SELL NSE options order for {symbol}: {e}")
        self.log_nse_options_message("=== NSE OPTIONS ORDER PLACEMENT SUMMARY ===")
        self.log_nse_options_message(f"BUY NSE Options Orders: {buy_orders_placed}/{total_buy_orders} successful")
        self.log_nse_options_message(f"SELL NSE Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        def show_final_summary():
            messagebox.showinfo("Buy & Sell NSE Options Orders Completed",
                f"BUY NSE Options Orders: {buy_orders_placed}/{total_buy_orders} successful\nSELL NSE Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        self.root.after(0, show_final_summary)
    
    # ---------- Data Refresh Methods ----------
    def refresh_futures_table(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            futures = self.get_all_futures()
            for item in self.futures_tree.get_children():
                self.futures_tree.delete(item)
            for future in futures:
                self.futures_tree.insert('', 'end', values=(
                    future['tradingsymbol'],
                    future['name'],
                    future['expiry'],
                    future['lot_size'],
                    'Loading...', 'Loading...', 'Loading...'))
            self.log_futures_message(f"Loaded {len(futures)} futures contracts")
            if not self.futures_data_running:
                self.start_futures_live_data()
        except Exception as e:
            self.log_futures_message(f"Error refreshing futures table: {e}")
    
    def refresh_options_table(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            underlying = self.options_underlying_var.get()
            min_strike = float(self.options_min_strike_entry.get()) if self.options_min_strike_entry.get() else 0
            max_strike = float(self.options_max_strike_entry.get()) if self.options_max_strike_entry.get() else 0
            # Update month combobox
            months = self.get_unique_expiry_months("MCX", underlying)
            self.options_month_combo['values'] = months
            if months and not self.options_month_var.get():
                self.options_month_var.set(months[0])
            selected_month = self.options_month_var.get()
            options = self.get_all_options(underlying, min_strike, max_strike, selected_month)
            for item in self.options_tree.get_children():
                self.options_tree.delete(item)
            for option in options:
                self.options_tree.insert('', 'end', values=(
                    option['tradingsymbol'],
                    option['name'],
                    option['expiry'],
                    option['strike'],
                    option['instrument_type'],
                    option['lot_size'],
                    'Loading...', 'Loading...', 'Loading...'))
            self.log_options_message(f"Loaded {len(options)} MCX options contracts for {underlying} (strike {min_strike}-{max_strike}, month {selected_month})")
            if not self.options_data_running:
                self.start_options_live_data()
        except Exception as e:
            self.log_options_message(f"Error refreshing MCX options table: {e}")

    def refresh_nfo_options_table(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            underlying = self.nfo_options_underlying_var.get()
            min_strike = float(self.nfo_min_strike_entry.get()) if self.nfo_min_strike_entry.get() else 0
            max_strike = float(self.nfo_max_strike_entry.get()) if self.nfo_max_strike_entry.get() else 0
            months = self.get_unique_expiry_months("NFO", underlying)
            self.nfo_options_month_combo['values'] = months
            if months and not self.nfo_options_month_var.get():
                self.nfo_options_month_var.set(months[0])
            selected_month = self.nfo_options_month_var.get()
            options = self.get_all_nfo_options(underlying, min_strike, max_strike, selected_month)
            for item in self.nfo_options_tree.get_children():
                self.nfo_options_tree.delete(item)
            for option in options:
                self.nfo_options_tree.insert('', 'end', values=(
                    option['tradingsymbol'],
                    option['name'],
                    option['expiry'],
                    option['strike'],
                    option['instrument_type'],
                    option['lot_size'],
                    'Loading...', 'Loading...', 'Loading...'))
            self.log_nfo_options_message(f"Loaded {len(options)} NFO options contracts for {underlying} (strike {min_strike}-{max_strike}, month {selected_month})")
            if not self.nfo_options_data_running:
                self.start_nfo_options_live_data()
        except Exception as e:
            self.log_nfo_options_message(f"Error refreshing NFO options table: {e}")

    def refresh_nse_options_table(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            stock_symbol = self.nse_options_underlying_var.get()
            min_strike = float(self.nse_min_strike_entry.get()) if self.nse_min_strike_entry.get() else 0
            max_strike = float(self.nse_max_strike_entry.get()) if self.nse_max_strike_entry.get() else 0
            months = self.get_unique_expiry_months("NSE", stock_symbol)
            self.nse_options_month_combo['values'] = months
            if months and not self.nse_options_month_var.get():
                self.nse_options_month_var.set(months[0])
            selected_month = self.nse_options_month_var.get()
            options = self.get_all_nse_stock_options(stock_symbol, min_strike, max_strike, selected_month)
            for item in self.nse_options_tree.get_children():
                self.nse_options_tree.delete(item)
            for option in options:
                self.nse_options_tree.insert('', 'end', values=(
                    option['tradingsymbol'],
                    option['name'],
                    option['expiry'],
                    option['strike'],
                    option['instrument_type'],
                    option['lot_size'],
                    'Loading...', 'Loading...', 'Loading...'))
            self.log_nse_options_message(f"Loaded {len(options)} NSE options contracts for {stock_symbol} (strike {min_strike}-{max_strike}, month {selected_month})")
            if not self.nse_options_data_running:
                self.start_nse_options_live_data()
        except Exception as e:
            self.log_nse_options_message(f"Error refreshing NSE options table: {e}")
    
    def refresh_nfo_options_table(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            underlying = self.nfo_options_underlying_var.get()
            strike_range = self.nfo_strike_range_var.get()
            months = self.get_unique_expiry_months("NFO", underlying)
            self.nfo_options_month_combo['values'] = months
            if months and not self.nfo_options_month_var.get():
                self.nfo_options_month_var.set(months[0])
            selected_month = self.nfo_options_month_var.get()
            options = self.get_all_nfo_options(underlying, strike_range, selected_month)
            for item in self.nfo_options_tree.get_children():
                self.nfo_options_tree.delete(item)
            for option in options:
                self.nfo_options_tree.insert('', 'end', values=(
                    option['tradingsymbol'],
                    option['name'],
                    option['expiry'],
                    option['strike'],
                    option['instrument_type'],
                    option['lot_size'],
                    'Loading...', 'Loading...', 'Loading...'))
            self.log_nfo_options_message(f"Loaded {len(options)} NFO options contracts for {underlying} (strike ±{strike_range}, month {selected_month})")
            if not self.nfo_options_data_running:
                self.start_nfo_options_live_data()
        except Exception as e:
            self.log_nfo_options_message(f"Error refreshing NFO options table: {e}")
    
    def refresh_nse_options_table(self):
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        try:
            stock_symbol = self.nse_options_underlying_var.get()
            strike_range = self.nse_strike_range_var.get()
            months = self.get_unique_expiry_months("NSE", stock_symbol)
            self.nse_options_month_combo['values'] = months
            if months and not self.nse_options_month_var.get():
                self.nse_options_month_var.set(months[0])
            selected_month = self.nse_options_month_var.get()
            options = self.get_all_nse_stock_options(stock_symbol, strike_range, selected_month)
            for item in self.nse_options_tree.get_children():
                self.nse_options_tree.delete(item)
            for option in options:
                self.nse_options_tree.insert('', 'end', values=(
                    option['tradingsymbol'],
                    option['name'],
                    option['expiry'],
                    option['strike'],
                    option['instrument_type'],
                    option['lot_size'],
                    'Loading...', 'Loading...', 'Loading...'))
            self.log_nse_options_message(f"Loaded {len(options)} NSE options contracts for {stock_symbol} (strike ±{strike_range}, month {selected_month})")
            if not self.nse_options_data_running:
                self.start_nse_options_live_data()
        except Exception as e:
            self.log_nse_options_message(f"Error refreshing NSE options table: {e}")
    
    def start_futures_live_data(self):
        if not self.is_logged_in:
            return
        self.futures_data_running = True
        threading.Thread(target=self.update_futures_live_data, daemon=True).start()
        self.log_futures_message("Started live prices for futures table")
    
    def stop_futures_live_data(self):
        self.futures_data_running = False
        self.log_futures_message("Stopped live prices for futures table")
    
    def start_options_live_data(self):
        if not self.is_logged_in:
            return
        self.options_data_running = True
        threading.Thread(target=self.update_options_live_data, daemon=True).start()
        self.log_options_message("Started live prices for MCX options table")
    
    def stop_options_live_data(self):
        self.options_data_running = False
        self.log_options_message("Stopped live prices for MCX options table")
    
    def start_nfo_options_live_data(self):
        if not self.is_logged_in:
            return
        self.nfo_options_data_running = True
        threading.Thread(target=self.update_nfo_options_live_data, daemon=True).start()
        self.log_nfo_options_message("Started live prices for NFO options table")
    
    def stop_nfo_options_live_data(self):
        self.nfo_options_data_running = False
        self.log_nfo_options_message("Stopped live prices for NFO options table")
    
    def start_nse_options_live_data(self):
        if not self.is_logged_in:
            return
        self.nse_options_data_running = True
        threading.Thread(target=self.update_nse_options_live_data, daemon=True).start()
        self.log_nse_options_message("Started live prices for NSE options table")
    
    def stop_nse_options_live_data(self):
        self.nse_options_data_running = False
        self.log_nse_options_message("Stopped live prices for NSE options table")
    
    def update_futures_live_data(self):
        while self.futures_data_running and self.is_logged_in:
            try:
                symbols = []
                for item in self.futures_tree.get_children():
                    values = self.futures_tree.item(item, 'values')
                    if values and len(values) > 0:
                        symbols.append(values[0])
                if not symbols:
                    time.sleep(5)
                    continue
                instruments = [f"MCX:{symbol}" for symbol in symbols]
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("MCX:", "")
                            for item in self.futures_tree.get_children():
                                item_values = self.futures_tree.item(item, 'values')
                                if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                    ltp = data['last_price']
                                    change = data.get('net_change', 0)
                                    change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                    volume = data.get('volume', 0)
                                    new_values = (
                                        item_values[0], item_values[1], item_values[2], item_values[3],
                                        f"{ltp:.2f}", f"{change_percent:+.2f}%", f"{volume:,}")
                                    self.futures_tree.item(item, values=new_values)
                                    break
                    except Exception as e:
                        self.log_futures_message(f"Error updating futures batch {i//batch_size + 1}: {e}")
                time.sleep(3)
            except Exception as e:
                self.log_futures_message(f"Error in futures live data update: {e}")
                time.sleep(10)
    
    def update_options_live_data(self):
        while self.options_data_running and self.is_logged_in:
            try:
                symbols = []
                for item in self.options_tree.get_children():
                    values = self.options_tree.item(item, 'values')
                    if values and len(values) > 0:
                        symbols.append(values[0])
                if not symbols:
                    time.sleep(5)
                    continue
                instruments = [f"MCX:{symbol}" for symbol in symbols]
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("MCX:", "")
                            for item in self.options_tree.get_children():
                                item_values = self.options_tree.item(item, 'values')
                                if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                    ltp = data['last_price']
                                    change = data.get('net_change', 0)
                                    change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                    volume = data.get('volume', 0)
                                    new_values = (
                                        item_values[0], item_values[1], item_values[2], item_values[3],
                                        item_values[4], item_values[5],
                                        f"{ltp:.2f}", f"{change_percent:+.2f}%", f"{volume:,}")
                                    self.options_tree.item(item, values=new_values)
                                    break
                    except Exception as e:
                        self.log_options_message(f"Error updating MCX options batch {i//batch_size + 1}: {e}")
                time.sleep(3)
            except Exception as e:
                self.log_options_message(f"Error in MCX options live data update: {e}")
                time.sleep(10)
    
    def update_nfo_options_live_data(self):
        while self.nfo_options_data_running and self.is_logged_in:
            try:
                symbols = []
                for item in self.nfo_options_tree.get_children():
                    values = self.nfo_options_tree.item(item, 'values')
                    if values and len(values) > 0:
                        symbols.append(values[0])
                if not symbols:
                    time.sleep(5)
                    continue
                instruments = [f"NFO:{symbol}" for symbol in symbols]
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("NFO:", "")
                            for item in self.nfo_options_tree.get_children():
                                item_values = self.nfo_options_tree.item(item, 'values')
                                if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                    ltp = data['last_price']
                                    change = data.get('net_change', 0)
                                    change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                    volume = data.get('volume', 0)
                                    new_values = (
                                        item_values[0], item_values[1], item_values[2], item_values[3],
                                        item_values[4], item_values[5],
                                        f"{ltp:.2f}", f"{change_percent:+.2f}%", f"{volume:,}")
                                    self.nfo_options_tree.item(item, values=new_values)
                                    break
                    except Exception as e:
                        self.log_nfo_options_message(f"Error updating NFO options batch {i//batch_size + 1}: {e}")
                time.sleep(3)
            except Exception as e:
                self.log_nfo_options_message(f"Error in NFO options live data update: {e}")
                time.sleep(10)
    
    def update_nse_options_live_data(self):
        while self.nse_options_data_running and self.is_logged_in:
            try:
                symbols = []
                for item in self.nse_options_tree.get_children():
                    values = self.nse_options_tree.item(item, 'values')
                    if values and len(values) > 0:
                        symbols.append(values[0])
                if not symbols:
                    time.sleep(5)
                    continue
                instruments = [f"NFO:{symbol}" for symbol in symbols]
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("NFO:", "")
                            for item in self.nse_options_tree.get_children():
                                item_values = self.nse_options_tree.item(item, 'values')
                                if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                    ltp = data['last_price']
                                    change = data.get('net_change', 0)
                                    change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                    volume = data.get('volume', 0)
                                    new_values = (
                                        item_values[0], item_values[1], item_values[2], item_values[3],
                                        item_values[4], item_values[5],
                                        f"{ltp:.2f}", f"{change_percent:+.2f}%", f"{volume:,}")
                                    self.nse_options_tree.item(item, values=new_values)
                                    break
                    except Exception as e:
                        self.log_nse_options_message(f"Error updating NSE options batch {i//batch_size + 1}: {e}")
                time.sleep(3)
            except Exception as e:
                self.log_nse_options_message(f"Error in NSE options live data update: {e}")
                time.sleep(10)
    
    # ---------- Positions and P&L ----------
    def setup_positions_tab(self, notebook):
        positions_frame = ttk.Frame(notebook)
        notebook.add(positions_frame, text="Positions")
        self.positions_tree = ttk.Treeview(positions_frame, columns=(
            'Instrument', 'Quantity', 'Avg Price', 'LTP', 'P&L', 'Day P&L'
        ), show='headings')
        for col in self.positions_tree['columns']:
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=120)
        self.positions_tree.pack(fill='both', expand=True, padx=10, pady=10)
        ttk.Button(positions_frame, text="Refresh Positions", command=self.refresh_positions).pack(pady=10)
    
    def setup_pnl_tab(self, notebook):
        pnl_frame = ttk.Frame(notebook)
        notebook.add(pnl_frame, text="P&L")
        
        summary_frame = ttk.LabelFrame(pnl_frame, text="P&L Summary")
        summary_frame.pack(fill='x', padx=10, pady=10)
        self.total_pnl_label = ttk.Label(summary_frame, text="Total P&L: ₹0.00", font=('Arial', 14, 'bold'))
        self.total_pnl_label.pack(pady=10)
        self.day_pnl_label = ttk.Label(summary_frame, text="Day P&L: ₹0.00", font=('Arial', 12))
        self.day_pnl_label.pack(pady=5)
        self.realized_pnl_label = ttk.Label(summary_frame, text="Realized P&L: ₹0.00", font=('Arial', 12))
        self.realized_pnl_label.pack(pady=5)
        
        profit_target_frame = ttk.Frame(summary_frame)
        profit_target_frame.pack(fill='x', pady=5)
        ttk.Label(profit_target_frame, text="Auto Exit Profit Target: ₹").pack(side='left', padx=5)
        self.profit_target_entry = ttk.Entry(profit_target_frame, width=10)
        self.profit_target_entry.pack(side='left', padx=5)
        self.profit_target_entry.insert(0, "1000")
        ttk.Button(profit_target_frame, text="Set Target", command=self.set_profit_target).pack(side='left', padx=5)
        ttk.Button(profit_target_frame, text="Auto Exit All", command=self.auto_exit_positions).pack(side='left', padx=5)
        
        trailing_frame = ttk.LabelFrame(summary_frame, text="Trailing Profit")
        trailing_frame.pack(fill='x', pady=5)
        self.trailing_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(trailing_frame, text="Enable Trailing Profit", variable=self.trailing_enabled_var, command=self.toggle_trailing).pack(side='left', padx=5)
        ttk.Label(trailing_frame, text="Activation Profit: ₹").pack(side='left', padx=5)
        self.trailing_activation_entry = ttk.Entry(trailing_frame, width=10)
        self.trailing_activation_entry.pack(side='left', padx=5)
        self.trailing_activation_entry.insert(0, "500")
        ttk.Label(trailing_frame, text="Trail Type:").pack(side='left', padx=5)
        self.trailing_type_combo = ttk.Combobox(trailing_frame, values=["points", "percentage"], width=10)
        self.trailing_type_combo.pack(side='left', padx=5)
        self.trailing_type_combo.set("points")
        ttk.Label(trailing_frame, text="Trail Value:").pack(side='left', padx=5)
        self.trailing_value_entry = ttk.Entry(trailing_frame, width=10)
        self.trailing_value_entry.pack(side='left', padx=5)
        self.trailing_value_entry.insert(0, "200")
        
        history_frame = ttk.LabelFrame(pnl_frame, text="P&L History")
        history_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.pnl_tree = ttk.Treeview(history_frame, columns=('Date', 'Instrument', 'Quantity', 'Buy Price', 'Sell Price', 'P&L'), show='headings')
        for col in self.pnl_tree['columns']:
            self.pnl_tree.heading(col, text=col)
            self.pnl_tree.column(col, width=100)
        self.pnl_tree.pack(fill='both', expand=True, padx=10, pady=10)
    
    def toggle_trailing(self):
        self.trailing_enabled = self.trailing_enabled_var.get()
        if self.trailing_enabled:
            self.log_message("Trailing profit enabled")
        else:
            self.log_message("Trailing profit disabled")
            self.trailing_positions.clear()
    
    def update_trailing_settings(self):
        try:
            self.trailing_activation = float(self.trailing_activation_entry.get())
            self.trailing_type = self.trailing_type_combo.get()
            self.trailing_value = float(self.trailing_value_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid trailing profit values")
            return False
        return True
    
    def start_background_tasks(self):
        threading.Thread(target=self.update_positions_loop, daemon=True).start()
        threading.Thread(target=self.update_pnl_loop, daemon=True).start()
        threading.Thread(target=self.monitor_profit_target, daemon=True).start()
        if self.is_logged_in:
            self.root.after(2000, self.refresh_futures_table)
            self.root.after(3000, self.refresh_options_table)
            self.root.after(4000, self.refresh_nfo_options_table)
            self.root.after(5000, self.refresh_nse_options_table)
    
    def update_positions_loop(self):
        while self.is_logged_in:
            try:
                self.refresh_positions()
                time.sleep(5)
            except Exception as e:
                self.log_message(f"Error updating positions: {e}")
                time.sleep(30)
    
    def refresh_positions(self):
        if not self.is_logged_in:
            return
        try:
            positions = self.kite.positions()
            def update_gui():
                for item in self.positions_tree.get_children():
                    self.positions_tree.delete(item)
                for position in positions['net']:
                    if position['quantity'] != 0:
                        self.positions_tree.insert('', 'end', values=(
                            position['tradingsymbol'],
                            position['quantity'],
                            position['average_price'],
                            position['last_price'],
                            position['pnl'],
                            position.get('day_pnl', 0)))
            self.root.after(0, update_gui)
        except Exception as e:
            self.log_message(f"Error refreshing positions: {e}")
    
    def update_pnl_loop(self):
        while self.is_logged_in:
            try:
                self.update_pnl()
                self.check_trailing_profit()
                time.sleep(10)
            except Exception as e:
                self.log_message(f"Error updating P&L: {e}")
                time.sleep(30)
    
    def update_pnl(self):
        if not self.is_logged_in:
            return
        try:
            positions = self.kite.positions()
            total_pnl = 0
            day_pnl = 0
            realized_pnl = 0
            for position in positions['net']:
                total_pnl += position.get('pnl', 0)
                day_pnl += position.get('day_pnl', 0)
            for position in positions['day']:
                realized_pnl += position.get('realised', 0)
            self.total_pnl = total_pnl
            def update_gui():
                self.total_pnl_label.config(text=f"Total P&L: ₹{total_pnl:.2f}")
                self.day_pnl_label.config(text=f"Day P&L: ₹{day_pnl:.2f}")
                self.realized_pnl_label.config(text=f"Realized P&L: ₹{realized_pnl:.2f}")
                color = 'green' if total_pnl >= 0 else 'red'
                self.total_pnl_label.config(foreground=color)
            self.root.after(0, update_gui)
        except Exception as e:
            self.log_message(f"Error updating P&L: {e}")
    
    def set_profit_target(self):
        try:
            self.profit_target = float(self.profit_target_entry.get())
            self.log_message(f"Profit target set to: ₹{self.profit_target}")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid profit target")
    
    def monitor_profit_target(self):
        while self.is_logged_in:
            try:
                if self.profit_target > 0 and self.total_pnl >= self.profit_target:
                    self.log_message(f"Profit target reached! Total P&L: ₹{self.total_pnl}")
                    self.auto_exit_positions()
                    self.profit_target = 0
                time.sleep(10)
            except Exception as e:
                self.log_message(f"Error monitoring profit target: {e}")
                time.sleep(30)
    
    def check_trailing_profit(self):
        if not self.is_logged_in or not self.trailing_enabled:
            return
        if not self.update_trailing_settings():
            return
        try:
            positions = self.kite.positions()
            net_positions = positions['net']
            current_symbols = {p['tradingsymbol'] for p in net_positions if p['quantity'] != 0}
            for symbol in list(self.trailing_positions.keys()):
                if symbol not in current_symbols:
                    del self.trailing_positions[symbol]
            for position in net_positions:
                if position['quantity'] == 0:
                    continue
                symbol = position['tradingsymbol']
                pnl = position['pnl']
                if symbol not in self.trailing_positions:
                    self.trailing_positions[symbol] = {'peak_pnl': pnl, 'activated': False}
                track = self.trailing_positions[symbol]
                if not track['activated']:
                    if pnl >= self.trailing_activation:
                        track['activated'] = True
                        track['peak_pnl'] = pnl
                        self.log_message(f"Trailing activated for {symbol} at P&L ₹{pnl:.2f}")
                else:
                    if pnl > track['peak_pnl']:
                        track['peak_pnl'] = pnl
                    if self.trailing_type == "points":
                        if pnl <= track['peak_pnl'] - self.trailing_value:
                            self.log_message(f"Trailing stop triggered for {symbol}: peak ₹{track['peak_pnl']:.2f}, current ₹{pnl:.2f}")
                            self.exit_position(position)
                    else:
                        threshold = track['peak_pnl'] * (1 - self.trailing_value / 100)
                        if pnl <= threshold:
                            self.log_message(f"Trailing stop triggered for {symbol}: peak ₹{track['peak_pnl']:.2f}, current ₹{pnl:.2f}")
                            self.exit_position(position)
        except Exception as e:
            self.log_message(f"Error in trailing profit check: {e}")
    
    def exit_position(self, position):
        try:
            transaction = 'SELL' if position['quantity'] > 0 else 'BUY'
            quantity = abs(position['quantity'])
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=position['exchange'],
                tradingsymbol=position['tradingsymbol'],
                transaction_type=transaction,
                quantity=quantity,
                order_type=self.kite.ORDER_TYPE_MARKET,
                product=self.kite.PRODUCT_NRML
            )
            self.log_message(f"Trailing exit: {position['tradingsymbol']} {transaction} {quantity} - Order ID: {order_id}")
            if position['tradingsymbol'] in self.trailing_positions:
                del self.trailing_positions[position['tradingsymbol']]
        except Exception as e:
            self.log_message(f"Error exiting position {position['tradingsymbol']}: {e}")
    
    def auto_exit_positions(self):
        if not self.is_logged_in:
            return
        try:
            positions = self.kite.positions()
            orders_placed = 0
            for position in positions['net']:
                if position['quantity'] != 0:
                    transaction = 'SELL' if position['quantity'] > 0 else 'BUY'
                    quantity = abs(position['quantity'])
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange=position['exchange'],
                        tradingsymbol=position['tradingsymbol'],
                        transaction_type=transaction,
                        quantity=quantity,
                        order_type=self.kite.ORDER_TYPE_MARKET,
                        product=self.kite.PRODUCT_NRML
                    )
                    orders_placed += 1
                    self.log_message(f"Auto exit: {position['tradingsymbol']} {transaction} {quantity} - Order ID: {order_id}")
                    if position['tradingsymbol'] in self.trailing_positions:
                        del self.trailing_positions[position['tradingsymbol']]
            if orders_placed > 0:
                self.log_message(f"Auto exit completed for {orders_placed} positions")
            else:
                self.log_message("No positions to exit")
        except Exception as e:
            self.log_message(f"Error in auto exit: {e}")
    
    # ---------- Logging methods ----------
    def log_message(self, message):
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.market_data_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.market_data_text.see(tk.END)
        self.root.after(0, update_log)
    
    def log_futures_message(self, message):
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.futures_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.futures_orders_text.see(tk.END)
        self.root.after(0, update_log)
    
    def log_options_message(self, message):
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.options_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.options_orders_text.see(tk.END)
        self.root.after(0, update_log)
    
    def log_nfo_options_message(self, message):
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.nfo_options_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.nfo_options_orders_text.see(tk.END)
        self.root.after(0, update_log)
    
    def log_nse_options_message(self, message):
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.nse_options_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.nse_options_orders_text.see(tk.END)
        self.root.after(0, update_log)

def main():
    root = tk.Tk()
    app = ZerodhaTradingApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()