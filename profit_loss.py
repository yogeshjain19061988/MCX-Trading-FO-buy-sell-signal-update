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

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha Trading Platform - MCX & NFO")
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
        self.mcx_instruments_df = None
        self.nse_instruments_df = None
        self.live_data_running = False
        self.futures_data_running = False
        self.options_data_running = False
        self.nifty_futures_data_running = False
        self.nifty_options_data_running = False
        
        # Selection dictionaries
        self.selected_buy_futures = {}
        self.selected_sell_futures = {}
        self.selected_single_futures = {}
        self.selected_buy_options = {}
        self.selected_sell_options = {}
        self.selected_single_options = {}
        self.selected_buy_nifty_futures = {}
        self.selected_sell_nifty_futures = {}
        self.selected_single_nifty_futures = {}
        self.selected_buy_nifty_options = {}
        self.selected_sell_nifty_options = {}
        self.selected_single_nifty_options = {}
        
        # Real-time price tracking
        self.price_update_event = Event()
        self.current_prices = {}
        self.real_time_windows = []
        
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
    
    def generate_login_url(self):
        """Generate login URL for Zerodha"""
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
        """Manual login with request token"""
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
            
            # Save credentials
            self.save_credentials()
            
            self.is_logged_in = True
            self.login_status.config(text="Logged In Successfully", foreground='green')
            
            # Load instruments
            self.load_instruments()
            
            # Start background tasks
            self.start_background_tasks()
            
            messagebox.showinfo("Success", "Login successful!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {e}")
    
    def auto_login(self):
        """Auto login with saved credentials"""
        try:
            if not hasattr(self, 'api_key') or not hasattr(self, 'access_token'):
                messagebox.showerror("Error", "No saved credentials found")
                return
            
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Test connection
            profile = self.kite.profile()
            
            self.is_logged_in = True
            self.login_status.config(text=f"Auto Login Successful - {profile['user_name']}", foreground='green')
            
            # Load instruments
            self.load_instruments()
            
            # Start background tasks
            self.start_background_tasks()
            
            messagebox.showinfo("Success", f"Auto login successful! Welcome {profile['user_name']}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Auto login failed: {e}")
    
    def load_instruments(self):
        """Load MCX and NSE instruments"""
        try:
            if self.kite and self.is_logged_in:
                # Get all instruments for both exchanges
                mcx_instruments = self.kite.instruments("MCX")
                nse_instruments = self.kite.instruments("NSE")
                
                self.mcx_instruments_df = pd.DataFrame(mcx_instruments)
                self.nse_instruments_df = pd.DataFrame(nse_instruments)
                
                # Combine for general use
                self.instruments_df = pd.concat([self.mcx_instruments_df, self.nse_instruments_df], ignore_index=True)
                
                # Convert expiry to datetime if it's string
                for df in [self.mcx_instruments_df, self.nse_instruments_df, self.instruments_df]:
                    if 'expiry' in df.columns and df['expiry'].dtype == 'object':
                        df['expiry'] = pd.to_datetime(df['expiry']).dt.date
                
                print(f"Loaded {len(self.mcx_instruments_df)} MCX instruments and {len(self.nse_instruments_df)} NSE instruments")
                self.log_message(f"Loaded {len(self.mcx_instruments_df)} MCX and {len(self.nse_instruments_df)} NSE instruments")
                
        except Exception as e:
            self.log_message(f"Error loading instruments: {e}")
    
    def get_all_futures(self, exchange="MCX"):
        """Get all available futures contracts for specified exchange"""
        try:
            if exchange == "MCX":
                instruments_df = self.mcx_instruments_df
            else:  # NSE
                instruments_df = self.nse_instruments_df
                
            if instruments_df is None:
                self.load_instruments()
                if instruments_df is None:
                    return []
            
            # Filter only futures contracts
            futures_df = instruments_df[
                (instruments_df['instrument_type'] == 'FUT') |
                (instruments_df['name'].str.contains('FUT', na=False))
            ].copy()
            
            # Sort by name and expiry
            futures_df = futures_df.sort_values(['name', 'expiry'])
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            futures_df = futures_df[futures_df['expiry'] >= current_date]
            
            return futures_df[['tradingsymbol', 'name', 'expiry', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting {exchange} futures: {e}")
            return []
    
    def get_all_options(self, base_symbol=None, exchange="MCX"):
        """Get all available options contracts for specified exchange"""
        try:
            if exchange == "MCX":
                instruments_df = self.mcx_instruments_df
            else:  # NSE
                instruments_df = self.nse_instruments_df
                
            if instruments_df is None:
                self.load_instruments()
                if instruments_df is None:
                    return []
            
            # Filter only options contracts
            options_df = instruments_df[
                (instruments_df['instrument_type'] == 'CE') |
                (instruments_df['instrument_type'] == 'PE') |
                (instruments_df['name'].str.contains('CE', na=False)) |
                (instruments_df['name'].str.contains('PE', na=False))
            ].copy()
            
            # Filter by base symbol if provided
            if base_symbol:
                options_df = options_df[
                    options_df['tradingsymbol'].str.startswith(base_symbol)
                ]
            
            # Sort by name, expiry, and strike
            options_df = options_df.sort_values(['name', 'expiry', 'strike'])
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            options_df = options_df[options_df['expiry'] >= current_date]
            
            return options_df[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting {exchange} options: {e}")
            return []
    
    def get_nifty_futures(self):
        """Get Nifty 50 futures contracts"""
        try:
            if self.nse_instruments_df is None:
                self.load_instruments()
                if self.nse_instruments_df is None:
                    return []
            
            # Filter Nifty futures
            nifty_futures = self.nse_instruments_df[
                (self.nse_instruments_df['name'] == 'NIFTY') &
                (self.nse_instruments_df['instrument_type'] == 'FUT')
            ].copy()
            
            # Sort by expiry
            nifty_futures = nifty_futures.sort_values('expiry')
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            nifty_futures = nifty_futures[nifty_futures['expiry'] >= current_date]
            
            return nifty_futures[['tradingsymbol', 'name', 'expiry', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting Nifty futures: {e}")
            return []
    
    def get_nifty_options(self):
        """Get Nifty 50 options contracts"""
        try:
            if self.nse_instruments_df is None:
                self.load_instruments()
                if self.nse_instruments_df is None:
                    return []
            
            # Filter Nifty options
            nifty_options = self.nse_instruments_df[
                (self.nse_instruments_df['name'] == 'NIFTY') &
                ((self.nse_instruments_df['instrument_type'] == 'CE') | 
                 (self.nse_instruments_df['instrument_type'] == 'PE'))
            ].copy()
            
            # Sort by expiry and strike
            nifty_options = nifty_options.sort_values(['expiry', 'strike'])
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            nifty_options = nifty_options[nifty_options['expiry'] >= current_date]
            
            return nifty_options[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting Nifty options: {e}")
            return []
    
    def get_monthly_contracts(self, base_symbol, exchange="MCX"):
        """Get previous, current, and next month contracts"""
        try:
            if exchange == "MCX":
                instruments_df = self.mcx_instruments_df
            else:  # NSE
                instruments_df = self.nse_instruments_df
                
            if instruments_df is None:
                self.load_instruments()
                if instruments_df is None:
                    return []
            
            # Filter instruments for the base symbol (futures)
            relevant_instruments = instruments_df[
                (instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                (instruments_df['tradingsymbol'].str.contains('FUT')) &
                (instruments_df['expiry'].notnull())
            ].copy()
            
            if relevant_instruments.empty:
                self.log_message(f"No FUT contracts found for {base_symbol} on {exchange}")
                # Try without FUT filter
                relevant_instruments = instruments_df[
                    (instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                    (instruments_df['expiry'].notnull())
                ].copy()
            
            if relevant_instruments.empty:
                self.log_message(f"No contracts found for {base_symbol} on {exchange}")
                return []
            
            # Sort by expiry
            relevant_instruments = relevant_instruments.sort_values('expiry')
            
            # Get current date
            current_date = datetime.now().date()
            
            # Find contracts for previous, current, and next months
            current_contracts = []
            next_contracts = []
            prev_contracts = []
            
            for _, instrument in relevant_instruments.iterrows():
                expiry_date = instrument['expiry']
                
                if isinstance(expiry_date, str):
                    expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                
                days_to_expiry = (expiry_date - current_date).days
                
                if days_to_expiry < 0:
                    # Expired contract
                    prev_contracts.append(instrument['tradingsymbol'])
                elif days_to_expiry <= 30:
                    # Current month (expiring within 30 days)
                    current_contracts.append(instrument['tradingsymbol'])
                else:
                    # Future contract
                    next_contracts.append(instrument['tradingsymbol'])
            
            # Select the most relevant contracts
            selected_contracts = []
            
            # Previous month: get the most recent expired contract
            if prev_contracts:
                selected_contracts.append(prev_contracts[-1])
            
            # Current month: get the nearest expiry
            if current_contracts:
                selected_contracts.append(current_contracts[0])
            elif not selected_contracts and next_contracts:
                # If no current contracts, use the nearest future as current
                selected_contracts.append(next_contracts[0])
                if len(next_contracts) > 1:
                    selected_contracts.append(next_contracts[1])
            
            # Next month: get the next expiry after current
            if next_contracts and len(selected_contracts) < 3:
                for contract in next_contracts:
                    if contract not in selected_contracts:
                        selected_contracts.append(contract)
                        break
            
            # Ensure we have at least one contract
            if not selected_contracts and not relevant_instruments.empty:
                # Fallback: just get the first few contracts
                selected_contracts = relevant_instruments['tradingsymbol'].head(3).tolist()
            
            self.log_message(f"Found {len(selected_contracts)} contracts for {base_symbol} on {exchange}")
            return selected_contracts[:3]  # Return max 3 contracts
            
        except Exception as e:
            self.log_message(f"Error getting monthly contracts for {exchange}: {str(e)}")
            return []
    
    def setup_gui(self):
        """Setup the main GUI interface"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Login Tab
        self.setup_login_tab(notebook)
        
        # Market Data Tab
        self.setup_market_data_tab(notebook)
        
        # MCX Futures Trading Tab
        self.setup_mcx_futures_trading_tab(notebook)
        
        # MCX Options Trading Tab
        self.setup_mcx_options_trading_tab(notebook)
        
        # Nifty 50 Trading Tab
        self.setup_nifty_trading_tab(notebook)
        
        # Positions Tab
        self.setup_positions_tab(notebook)
        
        # P&L Tab
        self.setup_pnl_tab(notebook)
    
    def setup_login_tab(self, notebook):
        """Setup login tab"""
        login_frame = ttk.Frame(notebook)
        notebook.add(login_frame, text="Login")
        
        # API Key
        ttk.Label(login_frame, text="API Key:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.api_key_entry = ttk.Entry(login_frame, width=40)
        self.api_key_entry.grid(row=0, column=1, padx=10, pady=10)
        if hasattr(self, 'api_key'):
            self.api_key_entry.insert(0, self.api_key)
        
        # API Secret
        ttk.Label(login_frame, text="API Secret:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.api_secret_entry = ttk.Entry(login_frame, width=40, show='*')
        self.api_secret_entry.grid(row=1, column=1, padx=10, pady=10)
        
        # Request Token
        ttk.Label(login_frame, text="Request Token:").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.request_token_entry = ttk.Entry(login_frame, width=40)
        self.request_token_entry.grid(row=2, column=1, padx=10, pady=10)
        
        # Buttons
        ttk.Button(login_frame, text="Generate Login URL", 
                  command=self.generate_login_url).grid(row=3, column=0, padx=10, pady=10)
        ttk.Button(login_frame, text="Login", 
                  command=self.manual_login).grid(row=3, column=1, padx=10, pady=10)
        ttk.Button(login_frame, text="Auto Login", 
                  command=self.auto_login).grid(row=3, column=2, padx=10, pady=10)
        
        # Status
        self.login_status = ttk.Label(login_frame, text="Not Logged In", foreground='red')
        self.login_status.grid(row=4, column=0, columnspan=3, padx=10, pady=10)

    def setup_market_data_tab(self, notebook):
        """Setup market data tab"""
        market_frame = ttk.Frame(notebook)
        notebook.add(market_frame, text="Market Data")
        
        # Create notebook for MCX and NSE market data
        market_notebook = ttk.Notebook(market_frame)
        market_notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # MCX Market Data Tab
        mcx_market_tab = ttk.Frame(market_notebook)
        market_notebook.add(mcx_market_tab, text="MCX Market Data")
        
        # NSE Market Data Tab
        nse_market_tab = ttk.Frame(market_notebook)
        market_notebook.add(nse_market_tab, text="NSE Market Data")
        
        # Setup MCX Market Data
        self.setup_mcx_market_data_tab(mcx_market_tab)
        
        # Setup NSE Market Data
        self.setup_nse_market_data_tab(nse_market_tab)
    
    def setup_mcx_market_data_tab(self, parent):
        """Setup MCX market data tab"""
        # Instrument selection
        selection_frame = ttk.Frame(parent)
        selection_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(selection_frame, text="Select Instrument:").pack(side='left', padx=5)
        
        self.mcx_instrument_var = tk.StringVar()
        self.mcx_instrument_combo = ttk.Combobox(selection_frame, textvariable=self.mcx_instrument_var, 
                                       values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"])
        self.mcx_instrument_combo.pack(side='left', padx=5)
        self.mcx_instrument_combo.set("GOLD")
        
        ttk.Button(selection_frame, text="Load Contracts", 
                  command=self.load_mcx_contracts).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Start Live Data", 
                  command=self.start_mcx_live_data).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Stop Live Data", 
                  command=self.stop_mcx_live_data).pack(side='left', padx=10)
        
        # Contracts selection
        contracts_frame = ttk.Frame(parent)
        contracts_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(contracts_frame, text="Select Contracts:").pack(side='left', padx=5)
        
        self.mcx_contracts_listbox = tk.Listbox(contracts_frame, selectmode='multiple', height=4, width=50)
        self.mcx_contracts_listbox.pack(side='left', padx=5, fill='x', expand=True)
        
        # Market data display
        self.mcx_market_data_text = scrolledtext.ScrolledText(parent, height=20, width=150)
        self.mcx_market_data_text.pack(fill='both', expand=True, padx=10, pady=10)
    
    def setup_nse_market_data_tab(self, parent):
        """Setup NSE market data tab"""
        # Instrument selection
        selection_frame = ttk.Frame(parent)
        selection_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(selection_frame, text="Select Instrument:").pack(side='left', padx=5)
        
        self.nse_instrument_var = tk.StringVar()
        self.nse_instrument_combo = ttk.Combobox(selection_frame, textvariable=self.nse_instrument_var, 
                                       values=["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"])
        self.nse_instrument_combo.pack(side='left', padx=5)
        self.nse_instrument_combo.set("NIFTY")
        
        ttk.Button(selection_frame, text="Load Contracts", 
                  command=self.load_nse_contracts).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Start Live Data", 
                  command=self.start_nse_live_data).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Stop Live Data", 
                  command=self.stop_nse_live_data).pack(side='left', padx=10)
        
        # Contracts selection
        contracts_frame = ttk.Frame(parent)
        contracts_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(contracts_frame, text="Select Contracts:").pack(side='left', padx=5)
        
        self.nse_contracts_listbox = tk.Listbox(contracts_frame, selectmode='multiple', height=4, width=50)
        self.nse_contracts_listbox.pack(side='left', padx=5, fill='x', expand=True)
        
        # Market data display
        self.nse_market_data_text = scrolledtext.ScrolledText(parent, height=20, width=150)
        self.nse_market_data_text.pack(fill='both', expand=True, padx=10, pady=10)
    
    def load_mcx_contracts(self):
        """Load available contracts for selected MCX instrument"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            base_instrument = self.mcx_instrument_var.get()
            contracts = self.get_monthly_contracts(base_instrument, "MCX")
            
            self.mcx_contracts_listbox.delete(0, tk.END)
            for contract in contracts:
                self.mcx_contracts_listbox.insert(tk.END, contract)
            
            # Select all contracts by default
            for i in range(len(contracts)):
                self.mcx_contracts_listbox.select_set(i)
            
            if contracts:
                self.log_message(f"Loaded {len(contracts)} contracts for {base_instrument}")
            else:
                self.log_message(f"No contracts found for {base_instrument}")
            
        except Exception as e:
            self.log_message(f"Error loading MCX contracts: {e}")
    
    def load_nse_contracts(self):
        """Load available contracts for selected NSE instrument"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            base_instrument = self.nse_instrument_var.get()
            contracts = self.get_monthly_contracts(base_instrument, "NSE")
            
            self.nse_contracts_listbox.delete(0, tk.END)
            for contract in contracts:
                self.nse_contracts_listbox.insert(tk.END, contract)
            
            # Select all contracts by default
            for i in range(len(contracts)):
                self.nse_contracts_listbox.select_set(i)
            
            if contracts:
                self.log_message(f"Loaded {len(contracts)} contracts for {base_instrument}")
            else:
                self.log_message(f"No contracts found for {base_instrument}")
            
        except Exception as e:
            self.log_message(f"Error loading NSE contracts: {e}")
    
    def start_mcx_live_data(self):
        """Start live data streaming for selected MCX contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        selected_contracts = [self.mcx_contracts_listbox.get(i) for i in self.mcx_contracts_listbox.curselection()]
        if not selected_contracts:
            messagebox.showerror("Error", "Please select at least one contract")
            return
        
        self.mcx_live_data_running = True
        threading.Thread(target=self.fetch_mcx_live_data, args=(selected_contracts,), daemon=True).start()
        self.log_message(f"Started MCX live data for {len(selected_contracts)} contracts")
    
    def start_nse_live_data(self):
        """Start live data streaming for selected NSE contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        selected_contracts = [self.nse_contracts_listbox.get(i) for i in self.nse_contracts_listbox.curselection()]
        if not selected_contracts:
            messagebox.showerror("Error", "Please select at least one contract")
            return
        
        self.nse_live_data_running = True
        threading.Thread(target=self.fetch_nse_live_data, args=(selected_contracts,), daemon=True).start()
        self.log_message(f"Started NSE live data for {len(selected_contracts)} contracts")
    
    def fetch_mcx_live_data(self, contracts):
        """Fetch live data for selected MCX contracts"""
        try:
            while hasattr(self, 'mcx_live_data_running') and self.mcx_live_data_running and self.is_logged_in:
                try:
                    # Prepare instrument tokens
                    instruments = [f"MCX:{contract}" for contract in contracts]
                    
                    # Get LTP data
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
                    
                    # Update GUI
                    self.update_mcx_market_data_display(data)
                    time.sleep(2)  # Update every 2 seconds
                    
                except Exception as e:
                    self.log_message(f"Error in MCX live data fetch: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            self.log_message(f"MCX live data stream stopped: {e}")
    
    def fetch_nse_live_data(self, contracts):
        """Fetch live data for selected NSE contracts"""
        try:
            while hasattr(self, 'nse_live_data_running') and self.nse_live_data_running and self.is_logged_in:
                try:
                    # Prepare instrument tokens
                    instruments = [f"NSE:{contract}" for contract in contracts]
                    
                    # Get LTP data
                    ltp_data = self.kite.ltp(instruments)
                    
                    data = []
                    for key, values in ltp_data.items():
                        contract_name = key.replace("NSE:", "")
                        data.append({
                            'Contract': contract_name,
                            'LTP': values['last_price'],
                            'Volume': values.get('volume', 0),
                            'Change': values.get('net_change', 0),
                            'OI': values.get('oi', 0),
                            'Timestamp': datetime.now().strftime("%H:%M:%S")
                        })
                    
                    # Update GUI
                    self.update_nse_market_data_display(data)
                    time.sleep(2)  # Update every 2 seconds
                    
                except Exception as e:
                    self.log_message(f"Error in NSE live data fetch: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            self.log_message(f"NSE live data stream stopped: {e}")
    
    def update_mcx_market_data_display(self, data):
        """Update MCX market data display in GUI"""
        def update():
            self.mcx_market_data_text.delete(1.0, tk.END)
            self.mcx_market_data_text.insert(tk.END, f"{'Contract':<20} {'LTP':<15} {'Change':<15} {'Volume':<15} {'OI':<15} {'Time':<10}\n")
            self.mcx_market_data_text.insert(tk.END, "-" * 90 + "\n")
            
            for item in data:
                self.mcx_market_data_text.insert(tk.END, 
                    f"{item['Contract']:<20} {item['LTP']:<15.2f} {item['Change']:<15.2f} "
                    f"{item['Volume']:<15} {item['OI']:<15} {item['Timestamp']:<10}\n"
                )
        
        self.root.after(0, update)
    
    def update_nse_market_data_display(self, data):
        """Update NSE market data display in GUI"""
        def update():
            self.nse_market_data_text.delete(1.0, tk.END)
            self.nse_market_data_text.insert(tk.END, f"{'Contract':<20} {'LTP':<15} {'Change':<15} {'Volume':<15} {'OI':<15} {'Time':<10}\n")
            self.nse_market_data_text.insert(tk.END, "-" * 90 + "\n")
            
            for item in data:
                self.nse_market_data_text.insert(tk.END, 
                    f"{item['Contract']:<20} {item['LTP']:<15.2f} {item['Change']:<15.2f} "
                    f"{item['Volume']:<15} {item['OI']:<15} {item['Timestamp']:<10}\n"
                )
        
        self.root.after(0, update)
    
    def stop_mcx_live_data(self):
        """Stop MCX live data streaming"""
        self.mcx_live_data_running = False
        self.log_message("MCX live data stopped")
    
    def stop_nse_live_data(self):
        """Stop NSE live data streaming"""
        self.nse_live_data_running = False
        self.log_message("NSE live data stopped")

    def setup_mcx_futures_trading_tab(self, notebook):
        """Setup MCX futures trading tab"""
        futures_frame = ttk.Frame(notebook)
        notebook.add(futures_frame, text="MCX Futures")
        
        # Create paned window for better layout
        paned_window = ttk.PanedWindow(futures_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Left side - Futures selection table
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        
        # Right side - Order placement
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        # Futures Selection Table
        futures_table_frame = ttk.LabelFrame(left_frame, text="MCX Futures Contracts (Live Prices)")
        futures_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Buttons for futures table
        futures_buttons_frame = ttk.Frame(futures_table_frame)
        futures_buttons_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(futures_buttons_frame, text="Refresh Futures", 
                  command=self.refresh_mcx_futures_table).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Start Live Prices", 
                  command=self.start_mcx_futures_live_data).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Stop Live Prices", 
                  command=self.stop_mcx_futures_live_data).pack(side='left', padx=5)
        
        # Futures table
        table_frame = ttk.Frame(futures_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.mcx_futures_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        
        tree_scroll.config(command=self.mcx_futures_tree.yview)
        
        # Define headings
        self.mcx_futures_tree.heading('Symbol', text='Trading Symbol')
        self.mcx_futures_tree.heading('Name', text='Name')
        self.mcx_futures_tree.heading('Expiry', text='Expiry')
        self.mcx_futures_tree.heading('Lot Size', text='Lot Size')
        self.mcx_futures_tree.heading('LTP', text='LTP')
        self.mcx_futures_tree.heading('Change', text='Change %')
        self.mcx_futures_tree.heading('Volume', text='Volume')
        
        # Set column widths
        self.mcx_futures_tree.column('Symbol', width=150)
        self.mcx_futures_tree.column('Name', width=100)
        self.mcx_futures_tree.column('Expiry', width=100)
        self.mcx_futures_tree.column('Lot Size', width=80, anchor='center')
        self.mcx_futures_tree.column('LTP', width=100, anchor='center')
        self.mcx_futures_tree.column('Change', width=80, anchor='center')
        self.mcx_futures_tree.column('Volume', width=80, anchor='center')
        
        self.mcx_futures_tree.pack(fill='both', expand=True)
        
        # Order placement (Right side)
        order_frame = ttk.LabelFrame(right_frame, text="MCX Futures Order Placement")
        order_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create notebook for different order types
        order_notebook = ttk.Notebook(order_frame)
        order_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Single Transaction Tab
        single_tab = ttk.Frame(order_notebook)
        order_notebook.add(single_tab, text="Single Transaction")
        
        # Buy/Sell Together Tab
        pair_tab = ttk.Frame(order_notebook)
        order_notebook.add(pair_tab, text="Buy & Sell Together")
        
        # Setup single transaction tab
        self.setup_mcx_futures_single_transaction_tab(single_tab)
        
        # Setup buy/sell together tab
        self.setup_mcx_futures_buy_sell_together_tab(pair_tab)
        
        # Orders log
        orders_log_frame = ttk.LabelFrame(right_frame, text="MCX Futures Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.mcx_futures_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.mcx_futures_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
    
    def setup_mcx_futures_single_transaction_tab(self, parent):
        """Setup MCX futures single transaction tab"""
        # Selection frame
        selection_frame = ttk.LabelFrame(parent, text="MCX Futures Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(selection_frame, text="Select from Table", 
                  command=self.select_mcx_futures_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", 
                  command=self.clear_mcx_futures_single_selection).pack(side='left', padx=5, pady=5)
        
        self.selected_mcx_futures_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_mcx_futures_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_mcx_futures_single_text.insert(tk.END, "No MCX futures contracts selected")
        
        # Order parameters
        params_frame = ttk.LabelFrame(parent, text="MCX Futures Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        # Transaction type
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.mcx_futures_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_transaction_type.set("BUY")
        
        # Order type
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.mcx_futures_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_order_type.set("MARKET")
        
        # Quantity type
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.mcx_futures_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_quantity_type.set("Lot Size")
        
        # Quantity
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_quantity_entry = ttk.Entry(params_frame)
        self.mcx_futures_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_quantity_entry.insert(0, "1")
        
        # Price (for limit orders)
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_price_entry = ttk.Entry(params_frame)
        self.mcx_futures_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_price_entry.insert(0, "0")
        
        # Order buttons frame
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(order_buttons_frame, text="Place MCX Futures Orders with Real-time Prices", 
                  command=self.place_mcx_futures_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", 
                  command=self.validate_mcx_futures_single_selection).pack(side='left', padx=5)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)
    
    def setup_mcx_futures_buy_sell_together_tab(self, parent):
        """Setup MCX futures buy and sell together tab"""
        # Create paned window for separate BUY/SELL selection
        pair_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pair_paned.pack(fill='both', expand=True, padx=5, pady=5)
        
        # BUY Selection Frame
        buy_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(buy_selection_frame, weight=1)
        
        # SELL Selection Frame
        sell_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(sell_selection_frame, weight=1)
        
        # BUY Contracts Selection
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY MCX Futures Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", 
                  command=self.select_mcx_futures_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", 
                  command=self.clear_mcx_futures_buy_selection).pack(padx=5, pady=5)
        
        self.selected_mcx_futures_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_mcx_futures_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_mcx_futures_buy_text.insert(tk.END, "No BUY MCX futures contracts selected")
        
        # BUY Order Parameters
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.mcx_futures_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_buy_order_type.set("MARKET")
        
        ttk.Label(buy_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_buy_quantity_type = ttk.Combobox(buy_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.mcx_futures_buy_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_buy_quantity_type.set("Lot Size")
        
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.mcx_futures_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_buy_quantity_entry.insert(0, "1")
        
        ttk.Label(buy_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_buy_price_entry = ttk.Entry(buy_params_frame)
        self.mcx_futures_buy_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_buy_price_entry.insert(0, "0")
        
        # SELL Contracts Selection
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL MCX Futures Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", 
                  command=self.select_mcx_futures_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", 
                  command=self.clear_mcx_futures_sell_selection).pack(padx=5, pady=5)
        
        self.selected_mcx_futures_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_mcx_futures_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_mcx_futures_sell_text.insert(tk.END, "No SELL MCX futures contracts selected")
        
        # SELL Order Parameters
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.mcx_futures_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_sell_order_type.set("MARKET")
        
        ttk.Label(sell_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_sell_quantity_type = ttk.Combobox(sell_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.mcx_futures_sell_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_sell_quantity_type.set("Lot Size")
        
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.mcx_futures_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_sell_quantity_entry.insert(0, "1")
        
        ttk.Label(sell_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.mcx_futures_sell_price_entry = ttk.Entry(sell_params_frame)
        self.mcx_futures_sell_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_futures_sell_price_entry.insert(0, "0")
        
        # Combined order button
        combined_button_frame = ttk.Frame(parent)
        combined_button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(combined_button_frame, text="Place BUY & SELL MCX Futures Orders with Real-time Prices", 
                  command=self.place_mcx_futures_buy_sell_orders).pack(pady=5)
        
        # Configure grid weights
        buy_params_frame.columnconfigure(1, weight=1)
        sell_params_frame.columnconfigure(1, weight=1)

    def setup_mcx_options_trading_tab(self, notebook):
        """Setup MCX options trading tab"""
        options_frame = ttk.Frame(notebook)
        notebook.add(options_frame, text="MCX Options")
        
        # Create paned window for better layout
        paned_window = ttk.PanedWindow(options_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Left side - Options selection table
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        
        # Right side - Order placement
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        # Options Selection Table
        options_table_frame = ttk.LabelFrame(left_frame, text="MCX Options Contracts (Live Prices)")
        options_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Options selection controls
        options_controls_frame = ttk.Frame(options_table_frame)
        options_controls_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(options_controls_frame, text="Underlying:").pack(side='left', padx=5)
        self.mcx_options_underlying_var = tk.StringVar()
        self.mcx_options_underlying_combo = ttk.Combobox(options_controls_frame, textvariable=self.mcx_options_underlying_var,
                                                   values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS"])
        self.mcx_options_underlying_combo.pack(side='left', padx=5)
        self.mcx_options_underlying_combo.set("GOLD")
        
        ttk.Button(options_controls_frame, text="Refresh Options", 
                  command=self.refresh_mcx_options_table).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Start Live Prices", 
                  command=self.start_mcx_options_live_data).pack(side='left', padx=5)
        ttk.Button(options_controls_frame, text="Stop Live Prices", 
                  command=self.stop_mcx_options_live_data).pack(side='left', padx=5)
        
        # Options table
        table_frame = ttk.Frame(options_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.mcx_options_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        
        tree_scroll.config(command=self.mcx_options_tree.yview)
        
        # Define headings
        self.mcx_options_tree.heading('Symbol', text='Symbol')
        self.mcx_options_tree.heading('Name', text='Name')
        self.mcx_options_tree.heading('Expiry', text='Expiry')
        self.mcx_options_tree.heading('Strike', text='Strike')
        self.mcx_options_tree.heading('Type', text='Type')
        self.mcx_options_tree.heading('Lot Size', text='Lot Size')
        self.mcx_options_tree.heading('LTP', text='LTP')
        self.mcx_options_tree.heading('Change', text='Change %')
        self.mcx_options_tree.heading('Volume', text='Volume')
        
        # Set column widths
        self.mcx_options_tree.column('Symbol', width=150)
        self.mcx_options_tree.column('Name', width=100)
        self.mcx_options_tree.column('Expiry', width=100)
        self.mcx_options_tree.column('Strike', width=80, anchor='center')
        self.mcx_options_tree.column('Type', width=60, anchor='center')
        self.mcx_options_tree.column('Lot Size', width=80, anchor='center')
        self.mcx_options_tree.column('LTP', width=80, anchor='center')
        self.mcx_options_tree.column('Change', width=80, anchor='center')
        self.mcx_options_tree.column('Volume', width=80, anchor='center')
        
        self.mcx_options_tree.pack(fill='both', expand=True)
        
        # Order placement (Right side)
        order_frame = ttk.LabelFrame(right_frame, text="MCX Options Order Placement")
        order_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create notebook for different order types
        order_notebook = ttk.Notebook(order_frame)
        order_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Single Transaction Tab
        single_tab = ttk.Frame(order_notebook)
        order_notebook.add(single_tab, text="Single Transaction")
        
        # Buy/Sell Together Tab
        pair_tab = ttk.Frame(order_notebook)
        order_notebook.add(pair_tab, text="Buy & Sell Together")
        
        # Strategies Tab
        strategies_tab = ttk.Frame(order_notebook)
        order_notebook.add(strategies_tab, text="MCX Options Strategies")
        
        # Setup single transaction tab
        self.setup_mcx_options_single_transaction_tab(single_tab)
        
        # Setup buy/sell together tab
        self.setup_mcx_options_buy_sell_together_tab(pair_tab)
        
        # Setup strategies tab
        self.setup_mcx_options_strategies_tab(strategies_tab)
        
        # Orders log
        orders_log_frame = ttk.LabelFrame(right_frame, text="MCX Options Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.mcx_options_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.mcx_options_orders_text.pack(fill='both', expand=True, padx=5, pady=5)

    def setup_mcx_options_single_transaction_tab(self, parent):
        """Setup MCX options single transaction tab"""
        # Selection frame
        selection_frame = ttk.LabelFrame(parent, text="MCX Options Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(selection_frame, text="Select from Table", 
                  command=self.select_mcx_options_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", 
                  command=self.clear_mcx_options_single_selection).pack(side='left', padx=5, pady=5)
        
        self.selected_mcx_options_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_mcx_options_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_mcx_options_single_text.insert(tk.END, "No MCX options contracts selected")
        
        # Order parameters
        params_frame = ttk.LabelFrame(parent, text="MCX Options Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        # Transaction type
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.mcx_options_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_transaction_type.set("BUY")
        
        # Order type
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.mcx_options_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_order_type.set("MARKET")
        
        # Quantity type
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.mcx_options_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_quantity_type.set("Lot Size")
        
        # Quantity
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_quantity_entry = ttk.Entry(params_frame)
        self.mcx_options_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_quantity_entry.insert(0, "1")
        
        # Price (for limit orders)
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_price_entry = ttk.Entry(params_frame)
        self.mcx_options_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_price_entry.insert(0, "0")
        
        # Order buttons frame
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(order_buttons_frame, text="Place MCX Options Orders with Real-time Prices", 
                  command=self.place_mcx_options_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", 
                  command=self.validate_mcx_options_single_selection).pack(side='left', padx=5)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)

    def setup_mcx_options_buy_sell_together_tab(self, parent):
        """Setup MCX options buy and sell together tab"""
        # Create paned window for separate BUY/SELL selection
        pair_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pair_paned.pack(fill='both', expand=True, padx=5, pady=5)
        
        # BUY Selection Frame
        buy_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(buy_selection_frame, weight=1)
        
        # SELL Selection Frame
        sell_selection_frame = ttk.Frame(pair_paned)
        pair_paned.add(sell_selection_frame, weight=1)
        
        # BUY Contracts Selection
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY MCX Options Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", 
                  command=self.select_mcx_options_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", 
                  command=self.clear_mcx_options_buy_selection).pack(padx=5, pady=5)
        
        self.selected_mcx_options_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_mcx_options_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_mcx_options_buy_text.insert(tk.END, "No BUY MCX options contracts selected")
        
        # BUY Order Parameters
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.mcx_options_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_buy_order_type.set("MARKET")
        
        ttk.Label(buy_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_buy_quantity_type = ttk.Combobox(buy_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.mcx_options_buy_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_buy_quantity_type.set("Lot Size")
        
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.mcx_options_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_buy_quantity_entry.insert(0, "1")
        
        ttk.Label(buy_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_buy_price_entry = ttk.Entry(buy_params_frame)
        self.mcx_options_buy_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_buy_price_entry.insert(0, "0")
        
        # SELL Contracts Selection
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL MCX Options Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", 
                  command=self.select_mcx_options_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", 
                  command=self.clear_mcx_options_sell_selection).pack(padx=5, pady=5)
        
        self.selected_mcx_options_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_mcx_options_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_mcx_options_sell_text.insert(tk.END, "No SELL MCX options contracts selected")
        
        # SELL Order Parameters
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.mcx_options_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_sell_order_type.set("MARKET")
        
        ttk.Label(sell_params_frame, text="Quantity Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_sell_quantity_type = ttk.Combobox(sell_params_frame, values=["Fixed Quantity", "Lot Size"])
        self.mcx_options_sell_quantity_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_sell_quantity_type.set("Lot Size")
        
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.mcx_options_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_sell_quantity_entry.insert(0, "1")
        
        ttk.Label(sell_params_frame, text="Price (for LIMIT):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.mcx_options_sell_price_entry = ttk.Entry(sell_params_frame)
        self.mcx_options_sell_price_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_options_sell_price_entry.insert(0, "0")
        
        # Combined order button
        combined_button_frame = ttk.Frame(parent)
        combined_button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(combined_button_frame, text="Place BUY & SELL MCX Options Orders with Real-time Prices", 
                  command=self.place_mcx_options_buy_sell_orders).pack(pady=5)
        
        # Configure grid weights
        buy_params_frame.columnconfigure(1, weight=1)
        sell_params_frame.columnconfigure(1, weight=1)

    def setup_mcx_options_strategies_tab(self, parent):
        """Setup MCX options strategies tab"""
        strategies_frame = ttk.Frame(parent)
        strategies_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Strategy selection
        strategy_selection_frame = ttk.LabelFrame(strategies_frame, text="MCX Options Strategies")
        strategy_selection_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(strategy_selection_frame, text="Select Strategy:").pack(side='left', padx=5, pady=5)
        
        self.mcx_strategy_var = tk.StringVar()
        mcx_strategy_combo = ttk.Combobox(strategy_selection_frame, textvariable=self.mcx_strategy_var,
                                        values=["Long Call", "Long Put", "Short Call", "Short Put", 
                                               "Bull Call Spread", "Bear Put Spread", "Straddle", "Strangle"])
        mcx_strategy_combo.pack(side='left', padx=5, pady=5)
        mcx_strategy_combo.set("Long Call")
        
        ttk.Button(strategy_selection_frame, text="Explain Strategy", 
                  command=self.explain_mcx_strategy).pack(side='left', padx=5, pady=5)
        
        # Strategy parameters
        params_frame = ttk.LabelFrame(strategies_frame, text="Strategy Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(params_frame, text="Underlying:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.mcx_strategy_underlying_var = tk.StringVar()
        self.mcx_strategy_underlying_combo = ttk.Combobox(params_frame, textvariable=self.mcx_strategy_underlying_var,
                                                        values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS"])
        self.mcx_strategy_underlying_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_strategy_underlying_combo.set("GOLD")
        
        ttk.Label(params_frame, text="Strike Price:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.mcx_strike_price_entry = ttk.Entry(params_frame)
        self.mcx_strike_price_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_strike_price_entry.insert(0, "0")
        
        ttk.Label(params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.mcx_strategy_quantity_entry = ttk.Entry(params_frame)
        self.mcx_strategy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.mcx_strategy_quantity_entry.insert(0, "1")
        
        # Strategy description
        desc_frame = ttk.LabelFrame(strategies_frame, text="Strategy Description")
        desc_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.mcx_strategy_desc_text = scrolledtext.ScrolledText(desc_frame, height=8)
        self.mcx_strategy_desc_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Execute strategy button
        execute_frame = ttk.Frame(strategies_frame)
        execute_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(execute_frame, text="Execute MCX Strategy with Real-time Prices", 
                  command=self.execute_mcx_options_strategy).pack(pady=5)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)
        
        # Load initial strategy description
        self.explain_mcx_strategy()

    def explain_mcx_strategy(self):
        """Explain the selected MCX options strategy"""
        strategy = self.mcx_strategy_var.get()
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
        self.mcx_strategy_desc_text.delete(1.0, tk.END)
        self.mcx_strategy_desc_text.insert(tk.END, description)

    # Due to character limits, I'll continue with the Nifty trading tab implementation in the next message
    # Let me know if you want me to continue with the remaining Nifty tab implementation