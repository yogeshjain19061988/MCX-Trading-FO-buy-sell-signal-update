import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import threading
import time
from datetime import datetime, timedelta
import webbrowser
from threading import Thread, Event
import pandas as pd

try:
    from kiteconnect import KiteConnect
except ImportError:
    print("Please install kiteconnect: pip install kiteconnect")
    exit()

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha MCX Trading Platform - Bid/Ask Based Orders")
        self.root.geometry("1400x900")
        
        # Initialize variables
        self.kite = None
        self.is_logged_in = False
        self.api_key = ""
        self.access_token = ""
        self.live_data = {}
        self.positions = {}
        self.orders = {}
        self.profit_target = 0
        self.total_pnl = 0
        self.instruments_df = None
        
        # Live data flags
        self.live_data_running = False
        self.futures_data_running = False
        self.options_data_running = False
        
        # Selection dictionaries
        self.selected_buy_futures = {}
        self.selected_sell_futures = {}
        self.selected_single_futures = {}
        self.selected_buy_options = {}
        self.selected_sell_options = {}
        self.selected_single_options = {}
        
        # Real-time price tracking
        self.price_update_event = Event()
        self.current_prices = {}
        self.current_bid_prices = {}
        self.current_ask_prices = {}
        self.real_time_windows = []
        
        # Load credentials
        self.load_credentials()
        
        # Setup GUI
        self.setup_gui()
        
        # Auto login if credentials exist
        if hasattr(self, 'api_key') and hasattr(self, 'access_token') and self.api_key and self.access_token:
            self.root.after(1000, self.auto_login)

    def load_credentials(self):
        """Load API credentials from file"""
        try:
            if os.path.exists('zerodha_credentials.json'):
                with open('zerodha_credentials.json', 'r') as f:
                    creds = json.load(f)
                    self.api_key = creds.get('api_key', '')
                    self.access_token = creds.get('access_token', '')
                    print("Credentials loaded successfully")
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
                json.dump(creds, f, indent=4)
            print("Credentials saved successfully")
        except Exception as e:
            print(f"Error saving credentials: {e}")

    def load_instruments(self):
        """Load MCX instruments"""
        try:
            if self.kite and self.is_logged_in:
                # Get all instruments
                all_instruments = self.kite.instruments("MCX")
                self.instruments_df = pd.DataFrame(all_instruments)
                
                # Convert expiry to datetime if it's string
                if 'expiry' in self.instruments_df.columns and self.instruments_df['expiry'].dtype == 'object':
                    self.instruments_df['expiry'] = pd.to_datetime(self.instruments_df['expiry']).dt.date
                
                print(f"Loaded {len(self.instruments_df)} MCX instruments")
                self.log_message(f"Loaded {len(self.instruments_df)} MCX instruments")
                
        except Exception as e:
            self.log_message(f"Error loading instruments: {e}")

    def get_all_futures(self):
        """Get all available futures contracts"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            
            # Filter only futures contracts
            futures_df = self.instruments_df[
                (self.instruments_df['instrument_type'] == 'FUT')
            ].copy()
            
            # Sort by name and expiry
            futures_df = futures_df.sort_values(['tradingsymbol'])
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            futures_df = futures_df[futures_df['expiry'] >= current_date]
            
            return futures_df[['tradingsymbol', 'name', 'expiry', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting futures: {e}")
            return []

    def get_monthly_contracts(self, base_symbol):
        """Get previous, current, and next month contracts"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            
            # Filter instruments for the base symbol (futures)
            relevant_instruments = self.instruments_df[
                (self.instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                (self.instruments_df['instrument_type'] == 'FUT')
            ].copy()
            
            if relevant_instruments.empty:
                self.log_message(f"No FUT contracts found for {base_symbol}")
                return []
            
            # Sort by expiry
            relevant_instruments = relevant_instruments.sort_values('expiry')
            
            # Get current date
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            relevant_instruments = relevant_instruments[relevant_instruments['expiry'] >= current_date]
            
            # Get nearest 3 contracts
            selected_contracts = relevant_instruments.head(3)['tradingsymbol'].tolist()
            
            self.log_message(f"Found {len(selected_contracts)} contracts for {base_symbol}")
            return selected_contracts
            
        except Exception as e:
            self.log_message(f"Error getting monthly contracts: {str(e)}")
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
        
        # Futures Trading Tab
        self.setup_futures_trading_tab(notebook)
        
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
        
        # Instructions
        instructions = """
        Instructions:
        1. Enter your API Key and Secret (get from Zerodha developer console)
        2. Click 'Generate Login URL' and login to Zerodha
        3. After login, copy the request token from URL and paste above
        4. Click 'Login' to authenticate
        5. Use 'Auto Login' for future sessions
        """
        ttk.Label(login_frame, text=instructions, justify='left').grid(row=5, column=0, columnspan=3, padx=10, pady=10)

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
            if not hasattr(self, 'api_key') or not self.api_key or not hasattr(self, 'access_token') or not self.access_token:
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

    def setup_market_data_tab(self, notebook):
        """Setup market data tab"""
        market_frame = ttk.Frame(notebook)
        notebook.add(market_frame, text="Market Data")
        
        # Instrument selection
        selection_frame = ttk.Frame(market_frame)
        selection_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(selection_frame, text="Select Instrument:").pack(side='left', padx=5)
        
        self.instrument_var = tk.StringVar()
        self.instrument_combo = ttk.Combobox(selection_frame, textvariable=self.instrument_var, 
                                       values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"])
        self.instrument_combo.pack(side='left', padx=5)
        self.instrument_combo.set("GOLD")
        
        ttk.Button(selection_frame, text="Load Contracts", 
                  command=self.load_contracts).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Start Live Data", 
                  command=self.start_live_data).pack(side='left', padx=10)
        ttk.Button(selection_frame, text="Stop Live Data", 
                  command=self.stop_live_data).pack(side='left', padx=10)
        
        # Contracts selection
        contracts_frame = ttk.Frame(market_frame)
        contracts_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Label(contracts_frame, text="Select Contracts:").pack(side='left', padx=5)
        
        self.contracts_listbox = tk.Listbox(contracts_frame, selectmode='multiple', height=4, width=50)
        self.contracts_listbox.pack(side='left', padx=5, fill='x', expand=True)
        
        # Market data display
        self.market_data_text = scrolledtext.ScrolledText(market_frame, height=20, width=150)
        self.market_data_text.pack(fill='both', expand=True, padx=10, pady=10)

    def load_contracts(self):
        """Load available contracts for selected instrument"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            base_instrument = self.instrument_var.get()
            contracts = self.get_monthly_contracts(base_instrument)
            
            self.contracts_listbox.delete(0, tk.END)
            for contract in contracts:
                self.contracts_listbox.insert(tk.END, contract)
            
            # Select all contracts by default
            for i in range(len(contracts)):
                self.contracts_listbox.select_set(i)
            
            if contracts:
                self.log_message(f"Loaded {len(contracts)} contracts for {base_instrument}")
            else:
                self.log_message(f"No contracts found for {base_instrument}")
            
        except Exception as e:
            self.log_message(f"Error loading contracts: {e}")

    def start_live_data(self):
        """Start live data streaming for selected contracts"""
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
        """Fetch live data for selected contracts"""
        try:
            while self.live_data_running and self.is_logged_in:
                try:
                    # Prepare instrument tokens
                    instruments = [f"MCX:{contract}" for contract in contracts]
                    
                    # Get quote data for bid/ask
                    quote_data = self.kite.quote(instruments)
                    
                    data = []
                    for key, values in quote_data.items():
                        contract_name = key.replace("MCX:", "")
                        depth = values.get('depth', {})
                        buy_quotes = depth.get('buy', [])
                        sell_quotes = depth.get('sell', [])
                        
                        best_bid = buy_quotes[0]['price'] if buy_quotes else 0
                        best_ask = sell_quotes[0]['price'] if sell_quotes else 0
                        
                        data.append({
                            'Contract': contract_name,
                            'LTP': values['last_price'],
                            'Best Bid': best_bid,
                            'Best Ask': best_ask,
                            'Volume': values.get('volume', 0),
                            'Change': values.get('net_change', 0),
                            'Timestamp': datetime.now().strftime("%H:%M:%S")
                        })
                    
                    # Update GUI
                    self.update_market_data_display(data)
                    time.sleep(2)  # Update every 2 seconds
                    
                except Exception as e:
                    self.log_message(f"Error in live data fetch: {e}")
                    time.sleep(5)
                    
        except Exception as e:
            self.log_message(f"Live data stream stopped: {e}")

    def update_market_data_display(self, data):
        """Update market data display in GUI"""
        def update():
            self.market_data_text.delete(1.0, tk.END)
            self.market_data_text.insert(tk.END, f"{'Contract':<20} {'LTP':<12} {'Best Bid':<12} {'Best Ask':<12} {'Change':<12} {'Volume':<12} {'Time':<10}\n")
            self.market_data_text.insert(tk.END, "-" * 100 + "\n")
            
            for item in data:
                self.market_data_text.insert(tk.END, 
                    f"{item['Contract']:<20} {item['LTP']:<12.2f} {item['Best Bid']:<12.2f} {item['Best Ask']:<12.2f} "
                    f"{item['Change']:<12.2f} {item['Volume']:<12} {item['Timestamp']:<10}\n"
                )
        
        self.root.after(0, update)

    def stop_live_data(self):
        """Stop live data streaming"""
        self.live_data_running = False
        self.log_message("Live data stopped")

    def setup_futures_trading_tab(self, notebook):
        """Setup futures trading tab"""
        futures_frame = ttk.Frame(notebook)
        notebook.add(futures_frame, text="Futures Trading")
        
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
        futures_table_frame = ttk.LabelFrame(left_frame, text="Available Futures Contracts (Live Prices)")
        futures_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Buttons for futures table
        futures_buttons_frame = ttk.Frame(futures_table_frame)
        futures_buttons_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(futures_buttons_frame, text="Refresh Futures", 
                  command=self.refresh_futures_table).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Start Live Prices", 
                  command=self.start_futures_live_data).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Stop Live Prices", 
                  command=self.stop_futures_live_data).pack(side='left', padx=5)
        
        # Futures table
        table_frame = ttk.Frame(futures_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.futures_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Lot Size', 'LTP', 'Best Bid', 'Best Ask', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        
        tree_scroll.config(command=self.futures_tree.yview)
        
        # Define headings
        columns = {
            'Symbol': 150, 'Name': 100, 'Expiry': 100, 'Lot Size': 80, 
            'LTP': 80, 'Best Bid': 80, 'Best Ask': 80, 'Volume': 80
        }
        
        for col, width in columns.items():
            self.futures_tree.heading(col, text=col)
            self.futures_tree.column(col, width=width, anchor='center')
        
        self.futures_tree.pack(fill='both', expand=True)
        
        # Order placement (Right side)
        order_frame = ttk.LabelFrame(right_frame, text="Bid/Ask Based Order Placement")
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
        self.setup_futures_single_transaction_tab(single_tab)
        
        # Setup buy/sell together tab
        self.setup_futures_buy_sell_together_tab(pair_tab)
        
        # Orders log
        orders_log_frame = ttk.LabelFrame(right_frame, text="Futures Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.futures_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.futures_orders_text.pack(fill='both', expand=True, padx=5, pady=5)

    def setup_futures_single_transaction_tab(self, parent):
        """Setup futures single transaction tab"""
        # Selection frame
        selection_frame = ttk.LabelFrame(parent, text="Futures Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(selection_frame, text="Select from Table", 
                  command=self.select_futures_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", 
                  command=self.clear_futures_single_selection).pack(side='left', padx=5, pady=5)
        
        self.selected_futures_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_futures_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_futures_single_text.insert(tk.END, "No futures contracts selected")
        
        # Order parameters
        params_frame = ttk.LabelFrame(parent, text="Futures Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        # Transaction type
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.futures_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.futures_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.futures_transaction_type.set("BUY")
        
        # Order type
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.futures_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.futures_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.futures_order_type.set("LIMIT")
        
        # Price offset (for limit orders)
        ttk.Label(params_frame, text="Price Offset:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_price_offset_entry = ttk.Entry(params_frame)
        self.futures_price_offset_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_price_offset_entry.insert(0, "0.5")
        ttk.Label(params_frame, text="(Positive for BUY, Negative for SELL)").grid(row=2, column=2, padx=5, pady=5, sticky='w')
        
        # Quantity
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.futures_quantity_entry = ttk.Entry(params_frame)
        self.futures_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.futures_quantity_entry.insert(0, "1")
        
        # Order buttons frame
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(order_buttons_frame, text="Place Futures Orders with Real-time Bid/Ask", 
                  command=self.place_futures_single_orders_bid_ask).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", 
                  command=self.validate_futures_single_selection).pack(side='left', padx=5)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)

    def setup_futures_buy_sell_together_tab(self, parent):
        """Setup futures buy and sell together tab"""
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
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Futures Contracts (BID Prices)")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", 
                  command=self.select_futures_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", 
                  command=self.clear_futures_buy_selection).pack(padx=5, pady=5)
        
        self.selected_futures_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_futures_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_futures_buy_text.insert(tk.END, "No BUY futures contracts selected")
        
        # BUY Order Parameters
        buy_params_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Order Parameters (Based on BID)")
        buy_params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(buy_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_order_type = ttk.Combobox(buy_params_frame, values=["MARKET", "LIMIT"])
        self.futures_buy_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_order_type.set("LIMIT")
        
        ttk.Label(buy_params_frame, text="BID Price Offset:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_offset_entry = ttk.Entry(buy_params_frame)
        self.futures_buy_offset_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_offset_entry.insert(0, "0.5")
        
        ttk.Label(buy_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_buy_quantity_entry = ttk.Entry(buy_params_frame)
        self.futures_buy_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_buy_quantity_entry.insert(0, "1")
        
        # SELL Contracts Selection
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Futures Contracts (ASK Prices)")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", 
                  command=self.select_futures_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", 
                  command=self.clear_futures_sell_selection).pack(padx=5, pady=5)
        
        self.selected_futures_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_futures_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_futures_sell_text.insert(tk.END, "No SELL futures contracts selected")
        
        # SELL Order Parameters
        sell_params_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Order Parameters (Based on ASK)")
        sell_params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(sell_params_frame, text="Order Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_order_type = ttk.Combobox(sell_params_frame, values=["MARKET", "LIMIT"])
        self.futures_sell_order_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_order_type.set("LIMIT")
        
        ttk.Label(sell_params_frame, text="ASK Price Offset:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_offset_entry = ttk.Entry(sell_params_frame)
        self.futures_sell_offset_entry.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_offset_entry.insert(0, "0.5")
        
        ttk.Label(sell_params_frame, text="Quantity:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_sell_quantity_entry = ttk.Entry(sell_params_frame)
        self.futures_sell_quantity_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_sell_quantity_entry.insert(0, "1")
        
        # Combined order button
        combined_button_frame = ttk.Frame(parent)
        combined_button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(combined_button_frame, text="Place BUY (BID) & SELL (ASK) Orders with Real-time Prices", 
                  command=self.place_futures_buy_sell_orders_bid_ask).pack(pady=5)
        
        # Configure grid weights
        buy_params_frame.columnconfigure(1, weight=1)
        sell_params_frame.columnconfigure(1, weight=1)

    # Market Depth Methods
    def get_current_market_depth(self, symbol):
        """Get current market depth (bid/ask prices) for a symbol"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use quote API to get market depth
                quote_data = self.kite.quote(f"MCX:{symbol}")
                return quote_data[f"MCX:{symbol}"]
            except Exception as e:
                self.log_message(f"Market depth fetch attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        return None

    def get_best_bid_price(self, symbol):
        """Get best bid price from market depth"""
        market_depth = self.get_current_market_depth(symbol)
        if market_depth and 'depth' in market_depth and 'buy' in market_depth['depth']:
            bids = market_depth['depth']['buy']
            if bids and len(bids) > 0:
                return bids[0]['price']  # Best bid (highest buy price)
        return None

    def get_best_ask_price(self, symbol):
        """Get best ask price from market depth"""
        market_depth = self.get_current_market_depth(symbol)
        if market_depth and 'depth' in market_depth and 'sell' in market_depth['depth']:
            asks = market_depth['depth']['sell']
            if asks and len(asks) > 0:
                return asks[0]['price']  # Best ask (lowest sell price)
        return None

    # Real-time Price Methods
    def start_price_updates_for_order(self, symbols):
        """Start continuous price updates for order symbols"""
        self.price_update_event.clear()
        Thread(target=self._update_prices_continuously, args=(symbols,), daemon=True).start()

    def stop_price_updates(self):
        """Stop continuous price updates"""
        self.price_update_event.set()

    def _update_prices_continuously(self, symbols):
        """Continuously update prices for selected symbols"""
        while not self.price_update_event.is_set() and self.is_logged_in:
            try:
                # Fetch market depth in batches
                batch_size = 10
                for i in range(0, len(symbols), batch_size):
                    batch_symbols = symbols[i:i + batch_size]
                    
                    for symbol in batch_symbols:
                        market_depth = self.get_current_market_depth(symbol)
                        if market_depth:
                            self.current_prices[symbol] = market_depth['last_price']
                            
                            # Update bid/ask prices
                            bids = market_depth.get('depth', {}).get('buy', [])
                            asks = market_depth.get('depth', {}).get('sell', [])
                            
                            if bids:
                                self.current_bid_prices[symbol] = bids[0]['price']
                            if asks:
                                self.current_ask_prices[symbol] = asks[0]['price']
                    
                    # Small delay between batches
                    time.sleep(0.2)
                
                # Wait before next update cycle
                time.sleep(1)
                
            except Exception as e:
                self.log_message(f"Error in continuous price update: {e}")
                time.sleep(2)

    # Futures selection methods
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
            'Select', 'Symbol', 'Name', 'Expiry', 'Lot Size', 'LTP', 'Best Bid', 'Best Ask'
        ), show='headings', yscrollcommand=tree_scroll.set, height=20)
        
        tree_scroll.config(command=select_tree.yview)
        
        select_tree.heading('Select', text='✓')
        select_tree.heading('Symbol', text='Symbol')
        select_tree.heading('Name', text='Name')
        select_tree.heading('Expiry', text='Expiry')
        select_tree.heading('Lot Size', text='Lot Size')
        select_tree.heading('LTP', text='LTP')
        select_tree.heading('Best Bid', text='Best Bid')
        select_tree.heading('Best Ask', text='Best Ask')
        
        select_tree.column('Select', width=50, anchor='center')
        select_tree.column('Symbol', width=150)
        select_tree.column('Name', width=100)
        select_tree.column('Expiry', width=100)
        select_tree.column('Lot Size', width=80, anchor='center')
        select_tree.column('LTP', width=80, anchor='center')
        select_tree.column('Best Bid', width=80, anchor='center')
        select_tree.column('Best Ask', width=80, anchor='center')
        
        select_tree.pack(fill='both', expand=True)
        
        # Populate with futures data
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
                    'ltp': values[5] if len(values) > 5 else 'N/A',
                    'best_bid': values[6] if len(values) > 6 else 'N/A',
                    'best_ask': values[7] if len(values) > 7 else 'N/A'
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
                    'ltp': values[5] if len(values) > 5 else 'N/A',
                    'best_bid': values[6] if len(values) > 6 else 'N/A',
                    'best_ask': values[7] if len(values) > 7 else 'N/A'
                }
            elif order_type == 'buy':
                self.selected_buy_futures[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'lot_size': values[4],
                    'ltp': values[5] if len(values) > 5 else 'N/A',
                    'best_bid': values[6] if len(values) > 6 else 'N/A',
                    'best_ask': values[7] if len(values) > 7 else 'N/A'
                }
            else:
                self.selected_sell_futures[symbol] = {
                    'symbol': symbol,
                    'name': values[2],
                    'expiry': values[3],
                    'lot_size': values[4],
                    'ltp': values[5] if len(values) > 5 else 'N/A',
                    'best_bid': values[6] if len(values) > 6 else 'N/A',
                    'best_ask': values[7] if len(values) > 7 else 'N/A'
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
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
                f"Best Bid: {details.get('best_bid', 'N/A')}\n"
                f"Best Ask: {details.get('best_ask', 'N/A')}\n"
                f"{'-'*40}\n"
            )

    def update_futures_buy_selection_display(self):
        self.selected_futures_buy_text.delete(1.0, tk.END)
        
        if not self.selected_buy_futures:
            self.selected_futures_buy_text.insert(tk.END, "No BUY futures contracts selected")
            return
        
        for symbol, details in self.selected_buy_futures.items():
            self.selected_futures_buy_text.insert(tk.END, 
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
                f"Best Bid: {details.get('best_bid', 'N/A')}\n"
                f"Best Ask: {details.get('best_ask', 'N/A')}\n"
                f"{'-'*40}\n"
            )

    def update_futures_sell_selection_display(self):
        self.selected_futures_sell_text.delete(1.0, tk.END)
        
        if not self.selected_sell_futures:
            self.selected_futures_sell_text.insert(tk.END, "No SELL futures contracts selected")
            return
        
        for symbol, details in self.selected_sell_futures.items():
            self.selected_futures_sell_text.insert(tk.END, 
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
                f"Best Bid: {details.get('best_bid', 'N/A')}\n"
                f"Best Ask: {details.get('best_ask', 'N/A')}\n"
                f"{'-'*40}\n"
            )

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
        
        messagebox.showinfo("Selection Valid", 
                          f"{len(self.selected_single_futures)} futures contracts selected and ready for trading")

    # Order Placement Methods with Bid/Ask Prices
    def place_futures_single_orders_bid_ask(self):
        """Place futures single transaction orders with real-time bid/ask prices"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_single_futures:
            messagebox.showwarning("Warning", "No futures contracts selected")
            return
        
        try:
            transaction = self.futures_transaction_type.get()
            order_type = self.futures_order_type.get()
            price_offset = float(self.futures_price_offset_entry.get())
            quantity = int(self.futures_quantity_entry.get())
            
            # Get symbols for price updates
            symbols = list(self.selected_single_futures.keys())
            
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(symbols)
            
            # Show real-time bid/ask price window
            self.show_futures_bid_ask_real_time_window(symbols, transaction, order_type, quantity, price_offset)
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid offset and quantity values")
        except Exception as e:
            self.log_message(f"Error starting futures order placement: {e}")

    def place_futures_buy_sell_orders_bid_ask(self):
        """Place both BUY and SELL futures orders with real-time bid/ask prices"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_buy_futures and not self.selected_sell_futures:
            messagebox.showwarning("Warning", "No futures contracts selected for BUY or SELL")
            return
        
        try:
            # Buy order parameters
            buy_order_type = self.futures_buy_order_type.get()
            buy_price_offset = float(self.futures_buy_offset_entry.get())
            buy_quantity = int(self.futures_buy_quantity_entry.get())
            
            # Sell order parameters
            sell_order_type = self.futures_sell_order_type.get()
            sell_price_offset = float(self.futures_sell_offset_entry.get())
            sell_quantity = int(self.futures_sell_quantity_entry.get())
            
            # Get all symbols for price updates
            buy_symbols = list(self.selected_buy_futures.keys())
            sell_symbols = list(self.selected_sell_futures.keys())
            all_symbols = buy_symbols + sell_symbols
            
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(all_symbols)
            
            # Show real-time price window for buy/sell
            self.show_futures_buy_sell_bid_ask_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity, buy_price_offset,
                sell_order_type, sell_quantity, sell_price_offset
            )
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid offset and quantity values")
        except Exception as e:
            self.log_message(f"Error starting futures buy/sell order placement: {e}")

    # Real-time Price Windows for Bid/Ask
    def show_futures_bid_ask_real_time_window(self, symbols, transaction, order_type, quantity, price_offset):
        """Show real-time bid/ask price window for futures orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title(f"Real-time {'BID' if transaction == 'BUY' else 'ASK'} Prices - Confirm {transaction} Order")
        price_window.geometry("600x500")
        price_window.transient(self.root)
        price_window.grab_set()
        
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text=f"Real-time {'BID' if transaction == 'BUY' else 'ASK'} Prices for {transaction} Orders", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Price display frame
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        # Create price labels for each symbol
        price_labels = {}
        for symbol in symbols:
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            
            # Show appropriate price based on transaction type
            if transaction == "BUY":
                bid_label = ttk.Label(symbol_frame, text="Fetching BID...", foreground='green', font=('Arial', 10, 'bold'))
                bid_label.pack(side='left')
                price_labels[symbol] = bid_label
                
                if order_type == "LIMIT":
                    limit_frame = ttk.Frame(price_frame)
                    limit_frame.pack(fill='x', pady=1)
                    ttk.Label(limit_frame, text="  Limit Price:", width=20, anchor='w').pack(side='left')
                    limit_label = ttk.Label(limit_frame, text="Calculating...", foreground='blue')
                    limit_label.pack(side='left')
                    price_labels[f"{symbol}_limit"] = limit_label
            else:
                ask_label = ttk.Label(symbol_frame, text="Fetching ASK...", foreground='red', font=('Arial', 10, 'bold'))
                ask_label.pack(side='left')
                price_labels[symbol] = ask_label
                
                if order_type == "LIMIT":
                    limit_frame = ttk.Frame(price_frame)
                    limit_frame.pack(fill='x', pady=1)
                    ttk.Label(limit_frame, text="  Limit Price:", width=20, anchor='w').pack(side='left')
                    limit_label = ttk.Label(limit_frame, text="Calculating...", foreground='blue')
                    limit_label.pack(side='left')
                    price_labels[f"{symbol}_limit"] = limit_label
        
        # Order info
        info_frame = ttk.LabelFrame(main_frame, text=f"{transaction} Order Information")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"Order Type: {order_type} | Quantity: {quantity}").pack(pady=5)
        if order_type == "LIMIT":
            offset_text = f"Price Offset: {price_offset} ({'below BID' if transaction == 'BUY' else 'above ASK'})"
            ttk.Label(info_frame, text=offset_text).pack(pady=5)
        ttk.Label(info_frame, text=f"{'BID' if transaction == 'BUY' else 'ASK'} prices update every 1 second. Place orders when ready.", 
                 foreground='green').pack(pady=5)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_futures_single_orders_with_bid_ask_prices,
                args=(transaction, order_type, quantity, price_offset),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_futures_message(f"{transaction} order placement cancelled by user")
        
        ttk.Button(button_frame, text=f"Place {transaction} Orders at {'BID' if transaction == 'BUY' else 'ASK'} Prices", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        # Start price updates
        self.update_futures_bid_ask_price_display(price_labels, transaction, order_type, price_offset, price_window)

    def update_futures_bid_ask_price_display(self, price_labels, transaction, order_type, price_offset, window):
        """Update bid/ask price labels with current market depth"""
        if not window.winfo_exists():
            return
        
        try:
            for symbol, label in price_labels.items():
                if not symbol.endswith('_limit'):
                    if transaction == "BUY":
                        best_bid = self.current_bid_prices.get(symbol)
                        if best_bid:
                            label.config(text=f"BID: ₹{best_bid:.2f}", foreground='green')
                            
                            # Update limit price for LIMIT orders
                            if order_type == "LIMIT":
                                limit_price = best_bid - price_offset
                                limit_label = price_labels.get(f"{symbol}_limit")
                                if limit_label:
                                    limit_label.config(text=f"₹{limit_price:.2f}", foreground='blue')
                        else:
                            label.config(text="BID: Unavailable", foreground='red')
                    else:
                        best_ask = self.current_ask_prices.get(symbol)
                        if best_ask:
                            label.config(text=f"ASK: ₹{best_ask:.2f}", foreground='red')
                            
                            # Update limit price for LIMIT orders
                            if order_type == "LIMIT":
                                limit_price = best_ask + price_offset
                                limit_label = price_labels.get(f"{symbol}_limit")
                                if limit_label:
                                    limit_label.config(text=f"₹{limit_price:.2f}", foreground='blue')
                        else:
                            label.config(text="ASK: Unavailable", foreground='red')
                            
        except Exception as e:
            print(f"Error updating bid/ask price display: {e}")
        
        # Schedule next update
        if window.winfo_exists():
            window.after(1000, lambda: self.update_futures_bid_ask_price_display(price_labels, transaction, order_type, price_offset, window))

    def show_futures_buy_sell_bid_ask_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity, buy_price_offset,
                                                     sell_order_type, sell_quantity, sell_price_offset):
        """Show real-time price window for futures buy/sell orders with bid/ask"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time BID/ASK Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x600")
        price_window.transient(self.root)
        price_window.grab_set()
        
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time BID/ASK Prices for BUY & SELL Orders", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Create paned window for BUY/SELL
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        # BUY Frame
        buy_frame = ttk.LabelFrame(paned_window, text="BUY Futures Contracts (BID Prices)")
        paned_window.add(buy_frame, weight=1)
        
        # SELL Frame
        sell_frame = ttk.LabelFrame(paned_window, text="SELL Futures Contracts (ASK Prices)")
        paned_window.add(sell_frame, weight=1)
        
        # BUY prices
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            bid_label = ttk.Label(symbol_frame, text="Fetching BID...", foreground='green', font=('Arial', 9, 'bold'))
            bid_label.pack(side='left')
            buy_price_labels[symbol] = bid_label
            
            if buy_order_type == "LIMIT":
                limit_frame = ttk.Frame(buy_frame)
                limit_frame.pack(fill='x', pady=1, padx=5)
                ttk.Label(limit_frame, text="  Limit Price:", width=25, anchor='w').pack(side='left')
                limit_label = ttk.Label(limit_frame, text="Calculating...", foreground='blue')
                limit_label.pack(side='left')
                buy_price_labels[f"{symbol}_limit"] = limit_label
        
        # SELL prices
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            ask_label = ttk.Label(symbol_frame, text="Fetching ASK...", foreground='red', font=('Arial', 9, 'bold'))
            ask_label.pack(side='left')
            sell_price_labels[symbol] = ask_label
            
            if sell_order_type == "LIMIT":
                limit_frame = ttk.Frame(sell_frame)
                limit_frame.pack(fill='x', pady=1, padx=5)
                ttk.Label(limit_frame, text="  Limit Price:", width=25, anchor='w').pack(side='left')
                limit_label = ttk.Label(limit_frame, text="Calculating...", foreground='blue')
                limit_label.pack(side='left')
                sell_price_labels[f"{symbol}_limit"] = limit_label
        
        # Order info
        info_frame = ttk.LabelFrame(main_frame, text="Order Summary")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="BID/ASK prices update every 1 second. Place orders when ready.", 
                 foreground='blue').pack(pady=2)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_futures_buy_sell_orders_with_bid_ask_prices,
                args=(
                    buy_order_type, buy_quantity, buy_price_offset,
                    sell_order_type, sell_quantity, sell_price_offset
                ),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_futures_message("BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY (BID) & SELL (ASK) Orders", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        # Start price updates
        self.update_futures_buy_sell_bid_ask_price_display(
            buy_price_labels, sell_price_labels, 
            buy_order_type, buy_price_offset,
            sell_order_type, sell_price_offset, 
            price_window
        )

    def update_futures_buy_sell_bid_ask_price_display(self, buy_labels, sell_labels, buy_order_type, buy_price_offset,
                                                    sell_order_type, sell_price_offset, window):
        """Update BUY and SELL price labels with bid/ask prices"""
        if not window.winfo_exists():
            return
        
        try:
            # Update BUY prices (BID)
            for symbol, label in buy_labels.items():
                if not symbol.endswith('_limit'):
                    best_bid = self.current_bid_prices.get(symbol)
                    if best_bid:
                        label.config(text=f"BID: ₹{best_bid:.2f}", foreground='green')
                        
                        # Update limit price for LIMIT orders
                        if buy_order_type == "LIMIT":
                            limit_price = best_bid - buy_price_offset
                            limit_label = buy_labels.get(f"{symbol}_limit")
                            if limit_label:
                                limit_label.config(text=f"₹{limit_price:.2f}", foreground='blue')
                    else:
                        label.config(text="BID: Unavailable", foreground='red')
            
            # Update SELL prices (ASK)
            for symbol, label in sell_labels.items():
                if not symbol.endswith('_limit'):
                    best_ask = self.current_ask_prices.get(symbol)
                    if best_ask:
                        label.config(text=f"ASK: ₹{best_ask:.2f}", foreground='red')
                        
                        # Update limit price for LIMIT orders
                        if sell_order_type == "LIMIT":
                            limit_price = best_ask + sell_price_offset
                            limit_label = sell_labels.get(f"{symbol}_limit")
                            if limit_label:
                                limit_label.config(text=f"₹{limit_price:.2f}", foreground='blue')
                    else:
                        label.config(text="ASK: Unavailable", foreground='red')
                        
        except Exception as e:
            print(f"Error updating buy/sell bid/ask price display: {e}")
        
        # Schedule next update
        if window.winfo_exists():
            window.after(1000, lambda: self.update_futures_buy_sell_bid_ask_price_display(
                buy_labels, sell_labels, buy_order_type, buy_price_offset,
                sell_order_type, sell_price_offset, window
            ))

    # Order Execution Methods with Bid/Ask Prices
    def execute_futures_single_orders_with_bid_ask_prices(self, transaction, order_type, quantity, price_offset):
        """Execute futures single transaction orders using bid/ask prices"""
        orders_placed = 0
        total_orders = len(self.selected_single_futures)
        
        self.log_futures_message(f"Starting to place {total_orders} {transaction} futures orders using {'BID' if transaction == 'BUY' else 'ASK'} prices...")
        
        for symbol, details in self.selected_single_futures.items():
            try:
                # Determine price based on transaction type
                if transaction == "BUY":
                    # For BUY orders, use best bid price
                    best_bid = self.current_bid_prices.get(symbol)
                    if not best_bid:
                        # Fallback: fetch current bid price
                        best_bid = self.get_best_bid_price(symbol)
                    
                    if not best_bid:
                        self.log_futures_message(f"❌ No bid price available for {symbol}, skipping...")
                        continue
                    
                    if order_type == "LIMIT":
                        # For limit buy orders, use bid price with offset
                        final_price = best_bid - price_offset
                        self.log_futures_message(f"BUY Limit order for {symbol}: Using bid price {best_bid:.2f} - offset = {final_price:.2f}")
                    else:
                        # For market buy orders
                        final_price = 0
                        self.log_futures_message(f"BUY Market order for {symbol}: Best bid price is {best_bid:.2f}")
                    
                else:  # SELL order
                    # For SELL orders, use best ask price
                    best_ask = self.current_ask_prices.get(symbol)
                    if not best_ask:
                        # Fallback: fetch current ask price
                        best_ask = self.get_best_ask_price(symbol)
                    
                    if not best_ask:
                        self.log_futures_message(f"❌ No ask price available for {symbol}, skipping...")
                        continue
                    
                    if order_type == "LIMIT":
                        # For limit sell orders, use ask price with offset
                        final_price = best_ask + price_offset
                        self.log_futures_message(f"SELL Limit order for {symbol}: Using ask price {best_ask:.2f} + offset = {final_price:.2f}")
                    else:
                        # For market sell orders
                        final_price = 0
                        self.log_futures_message(f"SELL Market order for {symbol}: Best ask price is {best_ask:.2f}")
                
                # Place order
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
                
                # Log order details with bid/ask information
                if transaction == "BUY":
                    log_msg = f"✅ BUY Futures Order {orders_placed}/{total_orders}: {symbol} {quantity} "
                    if order_type == "LIMIT":
                        log_msg += f"@ LIMIT {final_price:.2f} (BID: {best_bid:.2f})"
                    else:
                        log_msg += f"@ MARKET (BID: {best_bid:.2f})"
                else:
                    log_msg = f"✅ SELL Futures Order {orders_placed}/{total_orders}: {symbol} {quantity} "
                    if order_type == "LIMIT":
                        log_msg += f"@ LIMIT {final_price:.2f} (ASK: {best_ask:.2f})"
                    else:
                        log_msg += f"@ MARKET (ASK: {best_ask:.2f})"
                
                log_msg += f" - ID: {order_id}"
                self.log_futures_message(log_msg)
                
                # Small delay between orders
                time.sleep(1)
                
            except Exception as e:
                self.log_futures_message(f"❌ Failed to place {transaction} futures order for {symbol}: {e}")
        
        self.log_futures_message(f"{transaction} futures order placement completed: {orders_placed}/{total_orders} successful")
        
        # Show summary
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} futures orders placed successfully using {'bid' if transaction == 'BUY' else 'ask'} prices!")
            else:
                messagebox.showwarning("Partial Success", 
                                     f"{orders_placed} out of {total_orders} {transaction} futures orders placed successfully")
        
        self.root.after(0, show_summary)

    def execute_futures_buy_sell_orders_with_bid_ask_prices(self, buy_order_type, buy_quantity, buy_price_offset,
                                                          sell_order_type, sell_quantity, sell_price_offset):
        """Execute both BUY and SELL futures orders using bid/ask prices"""
        total_buy_orders = len(self.selected_buy_futures)
        total_sell_orders = len(self.selected_sell_futures)
        buy_orders_placed = 0
        sell_orders_placed = 0
        
        self.log_futures_message(f"Starting to place {total_buy_orders} BUY (using BID) and {total_sell_orders} SELL (using ASK) futures orders...")
        
        # Place BUY orders using BID prices
        if total_buy_orders > 0:
            self.log_futures_message("=== PLACING BUY FUTURES ORDERS (USING BID PRICES) ===")
            for symbol, details in self.selected_buy_futures.items():
                try:
                    # Get best bid price for BUY orders
                    best_bid = self.current_bid_prices.get(symbol)
                    if not best_bid:
                        best_bid = self.get_best_bid_price(symbol)
                    
                    if not best_bid:
                        self.log_futures_message(f"❌ No bid price available for BUY {symbol}, skipping...")
                        continue
                    
                    # Determine final price for BUY
                    final_price = 0
                    if buy_order_type == "LIMIT":
                        final_price = best_bid - buy_price_offset
                        self.log_futures_message(f"BUY Limit order for {symbol}: Using bid price {best_bid:.2f} - offset = {final_price:.2f}")
                    else:
                        self.log_futures_message(f"BUY Market order for {symbol}: Best bid price is {best_bid:.2f}")
                    
                    # Place BUY order
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="MCX",
                        tradingsymbol=symbol,
                        transaction_type="BUY",
                        quantity=buy_quantity,
                        order_type=buy_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if buy_order_type == "LIMIT" else None
                    )
                    
                    buy_orders_placed += 1
                    self.log_futures_message(f"✅ BUY Futures Order {buy_orders_placed}/{total_buy_orders}: {symbol} {buy_quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} (BID: {best_bid:.2f}) - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_futures_message(f"❌ Failed to place BUY futures order for {symbol}: {e}")
        
        # Place SELL orders using ASK prices
        if total_sell_orders > 0:
            self.log_futures_message("=== PLACING SELL FUTURES ORDERS (USING ASK PRICES) ===")
            for symbol, details in self.selected_sell_futures.items():
                try:
                    # Get best ask price for SELL orders
                    best_ask = self.current_ask_prices.get(symbol)
                    if not best_ask:
                        best_ask = self.get_best_ask_price(symbol)
                    
                    if not best_ask:
                        self.log_futures_message(f"❌ No ask price available for SELL {symbol}, skipping...")
                        continue
                    
                    # Determine final price for SELL
                    final_price = 0
                    if sell_order_type == "LIMIT":
                        final_price = best_ask + sell_price_offset
                        self.log_futures_message(f"SELL Limit order for {symbol}: Using ask price {best_ask:.2f} + offset = {final_price:.2f}")
                    else:
                        self.log_futures_message(f"SELL Market order for {symbol}: Best ask price is {best_ask:.2f}")
                    
                    # Place SELL order
                    order_id = self.kite.place_order(
                        variety=self.kite.VARIETY_REGULAR,
                        exchange="MCX",
                        tradingsymbol=symbol,
                        transaction_type="SELL",
                        quantity=sell_quantity,
                        order_type=sell_order_type,
                        product=self.kite.PRODUCT_NRML,
                        price=final_price if sell_order_type == "LIMIT" else None
                    )
                    
                    sell_orders_placed += 1
                    self.log_futures_message(f"✅ SELL Futures Order {sell_orders_placed}/{total_sell_orders}: {symbol} {sell_quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} (ASK: {best_ask:.2f}) - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_futures_message(f"❌ Failed to place SELL futures order for {symbol}: {e}")
        
        # Final summary
        self.log_futures_message("=== FUTURES ORDER PLACEMENT SUMMARY ===")
        self.log_futures_message(f"BUY Futures Orders (BID prices): {buy_orders_placed}/{total_buy_orders} successful")
        self.log_futures_message(f"SELL Futures Orders (ASK prices): {sell_orders_placed}/{total_sell_orders} successful")
        
        def show_final_summary():
            messagebox.showinfo(
                "Buy & Sell Futures Orders Completed",
                f"BUY Orders (using BID prices): {buy_orders_placed}/{total_buy_orders} successful\n"
                f"SELL Orders (using ASK prices): {sell_orders_placed}/{total_sell_orders} successful"
            )
        
        self.root.after(0, show_final_summary)

    # Data Refresh Methods
    def refresh_futures_table(self):
        """Refresh the futures contracts table"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            futures = self.get_all_futures()
            
            # Clear existing data
            for item in self.futures_tree.get_children():
                self.futures_tree.delete(item)
            
            # Add futures to table
            for future in futures:
                self.futures_tree.insert('', 'end', values=(
                    future['tradingsymbol'],
                    future['name'],
                    future['expiry'],
                    future['lot_size'],
                    'Loading...',  # LTP
                    'Loading...',  # Best Bid
                    'Loading...',  # Best Ask
                    'Loading...'   # Volume
                ))
            
            self.log_futures_message(f"Loaded {len(futures)} futures contracts")
            
            # Start live data for futures if not already running
            if not self.futures_data_running:
                self.start_futures_live_data()
            
        except Exception as e:
            self.log_futures_message(f"Error refreshing futures table: {e}")

    def start_futures_live_data(self):
        """Start live data updates for futures table"""
        if not self.is_logged_in:
            return
        
        self.futures_data_running = True
        threading.Thread(target=self.update_futures_live_data, daemon=True).start()
        self.log_futures_message("Started live prices for futures table")

    def stop_futures_live_data(self):
        """Stop live data updates for futures table"""
        self.futures_data_running = False
        self.log_futures_message("Stopped live prices for futures table")

    def update_futures_live_data(self):
        """Update live data for futures table"""
        while self.futures_data_running and self.is_logged_in:
            try:
                # Get all symbols from the table
                symbols = []
                for item in self.futures_tree.get_children():
                    values = self.futures_tree.item(item, 'values')
                    if values and len(values) > 0:
                        symbols.append(values[0])  # Symbol is at index 0
                
                if not symbols:
                    time.sleep(5)
                    continue
                
                # Prepare instrument list
                instruments = [f"MCX:{symbol}" for symbol in symbols]
                
                # Get quote data in batches to avoid API limits
                batch_size = 20
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        quote_data = self.kite.quote(batch)
                        
                        # Update table with live data
                        for instrument_key, data in quote_data.items():
                            symbol = instrument_key.replace("MCX:", "")
                            
                            # Find the item in the tree
                            for item in self.futures_tree.get_children():
                                item_values = self.futures_tree.item(item, 'values')
                                if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                    # Get bid/ask prices from market depth
                                    depth = data.get('depth', {})
                                    buy_quotes = depth.get('buy', [])
                                    sell_quotes = depth.get('sell', [])
                                    
                                    best_bid = buy_quotes[0]['price'] if buy_quotes else 0
                                    best_ask = sell_quotes[0]['price'] if sell_quotes else 0
                                    volume = data.get('volume', 0)
                                    
                                    # Update the row
                                    new_values = (
                                        item_values[0],  # Keep symbol
                                        item_values[1],  # Keep name
                                        item_values[2],  # Keep expiry
                                        item_values[3],  # Keep lot size
                                        f"{data['last_price']:.2f}",
                                        f"{best_bid:.2f}",
                                        f"{best_ask:.2f}",
                                        f"{volume:,}"
                                    )
                                    self.futures_tree.item(item, values=new_values)
                                    break
                    
                    except Exception as e:
                        self.log_futures_message(f"Error updating futures batch {i//batch_size + 1}: {e}")
                
                time.sleep(3)  # Update every 3 seconds
                
            except Exception as e:
                self.log_futures_message(f"Error in futures live data update: {e}")
                time.sleep(10)

    def setup_positions_tab(self, notebook):
        """Setup positions tab"""
        positions_frame = ttk.Frame(notebook)
        notebook.add(positions_frame, text="Positions")
        
        self.positions_tree = ttk.Treeview(positions_frame, columns=(
            'Instrument', 'Quantity', 'Avg Price', 'LTP', 'P&L', 'Day P&L'
        ), show='headings')
        
        # Define headings
        for col in self.positions_tree['columns']:
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=120)
        
        self.positions_tree.pack(fill='both', expand=True, padx=10, pady=10)
        
        ttk.Button(positions_frame, text="Refresh Positions", 
                  command=self.refresh_positions).pack(pady=10)

    def setup_pnl_tab(self, notebook):
        """Setup P&L tab"""
        pnl_frame = ttk.Frame(notebook)
        notebook.add(pnl_frame, text="P&L")
        
        # P&L Summary
        summary_frame = ttk.LabelFrame(pnl_frame, text="P&L Summary")
        summary_frame.pack(fill='x', padx=10, pady=10)
        
        self.total_pnl_label = ttk.Label(summary_frame, text="Total P&L: ₹0.00", font=('Arial', 14, 'bold'))
        self.total_pnl_label.pack(pady=10)
        
        self.day_pnl_label = ttk.Label(summary_frame, text="Day P&L: ₹0.00", font=('Arial', 12))
        self.day_pnl_label.pack(pady=5)
        
        self.realized_pnl_label = ttk.Label(summary_frame, text="Realized P&L: ₹0.00", font=('Arial', 12))
        self.realized_pnl_label.pack(pady=5)
        
        # Profit target frame
        profit_target_frame = ttk.Frame(summary_frame)
        profit_target_frame.pack(fill='x', pady=5)
        
        ttk.Label(profit_target_frame, text="Auto Exit Profit Target: ₹").pack(side='left', padx=5)
        self.profit_target_entry = ttk.Entry(profit_target_frame, width=10)
        self.profit_target_entry.pack(side='left', padx=5)
        self.profit_target_entry.insert(0, "1000")
        
        ttk.Button(profit_target_frame, text="Set Target", 
                  command=self.set_profit_target).pack(side='left', padx=5)
        ttk.Button(profit_target_frame, text="Auto Exit All", 
                  command=self.auto_exit_positions).pack(side='left', padx=5)
        
        # P&L History
        history_frame = ttk.LabelFrame(pnl_frame, text="P&L History")
        history_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.pnl_tree = ttk.Treeview(history_frame, columns=(
            'Date', 'Instrument', 'Quantity', 'Buy Price', 'Sell Price', 'P&L'
        ), show='headings')
        
        for col in self.pnl_tree['columns']:
            self.pnl_tree.heading(col, text=col)
            self.pnl_tree.column(col, width=100)
        
        self.pnl_tree.pack(fill='both', expand=True, padx=10, pady=10)

    def start_background_tasks(self):
        """Start background data fetching tasks"""
        # Start position updates
        threading.Thread(target=self.update_positions_loop, daemon=True).start()
        
        # Start P&L updates
        threading.Thread(target=self.update_pnl_loop, daemon=True).start()
        
        # Start profit target monitoring
        threading.Thread(target=self.monitor_profit_target, daemon=True).start()
        
        # Auto-refresh tables after login
        if self.is_logged_in:
            self.root.after(2000, self.refresh_futures_table)

    def update_positions_loop(self):
        """Continuously update positions"""
        while self.is_logged_in:
            try:
                self.refresh_positions()
                time.sleep(5)  # Update every 5 seconds
            except Exception as e:
                self.log_message(f"Error updating positions: {e}")
                time.sleep(30)

    def refresh_positions(self):
        """Refresh positions display"""
        if not self.is_logged_in:
            return
        
        try:
            positions = self.kite.positions()
            
            def update_gui():
                # Clear existing data
                for item in self.positions_tree.get_children():
                    self.positions_tree.delete(item)
                
                # Add net positions
                for position in positions['net']:
                    if position['quantity'] != 0:
                        self.positions_tree.insert('', 'end', values=(
                            position['tradingsymbol'],
                            position['quantity'],
                            position['average_price'],
                            position['last_price'],
                            position['pnl'],
                            position.get('day_pnl', 0)
                        ))
            
            self.root.after(0, update_gui)
            
        except Exception as e:
            self.log_message(f"Error refreshing positions: {e}")

    def update_pnl_loop(self):
        """Continuously update P&L"""
        while self.is_logged_in:
            try:
                self.update_pnl()
                time.sleep(10)  # Update every 10 seconds
            except Exception as e:
                self.log_message(f"Error updating P&L: {e}")
                time.sleep(30)

    def update_pnl(self):
        """Update P&L display"""
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
            
            # Get realized P&L from day positions
            for position in positions['day']:
                realized_pnl += position.get('realised', 0)
            
            # Update total P&L
            self.total_pnl = total_pnl
            
            def update_gui():
                self.total_pnl_label.config(text=f"Total P&L: ₹{total_pnl:.2f}")
                self.day_pnl_label.config(text=f"Day P&L: ₹{day_pnl:.2f}")
                self.realized_pnl_label.config(text=f"Realized P&L: ₹{realized_pnl:.2f}")
                
                # Update color based on P&L
                color = 'green' if total_pnl >= 0 else 'red'
                self.total_pnl_label.config(foreground=color)
            
            self.root.after(0, update_gui)
            
        except Exception as e:
            self.log_message(f"Error updating P&L: {e}")

    def set_profit_target(self):
        """Set profit target for auto exit"""
        try:
            self.profit_target = float(self.profit_target_entry.get())
            self.log_message(f"Profit target set to: ₹{self.profit_target}")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid profit target")

    def monitor_profit_target(self):
        """Monitor and auto exit positions when profit target is reached"""
        while self.is_logged_in:
            try:
                if self.profit_target > 0 and self.total_pnl >= self.profit_target:
                    self.log_message(f"Profit target reached! Total P&L: ₹{self.total_pnl}")
                    self.auto_exit_positions()
                    self.profit_target = 0  # Reset target
                
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                self.log_message(f"Error monitoring profit target: {e}")
                time.sleep(30)

    def auto_exit_positions(self):
        """Auto exit all positions"""
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
            
            if orders_placed > 0:
                self.log_message(f"Auto exit completed for {orders_placed} positions")
            else:
                self.log_message("No positions to exit")
            
        except Exception as e:
            self.log_message(f"Error in auto exit: {e}")

    # Logging methods
    def log_message(self, message):
        """Add message to market data log"""
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.market_data_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.market_data_text.see(tk.END)
        
        self.root.after(0, update_log)

    def log_futures_message(self, message):
        """Add message to futures orders log"""
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.futures_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.futures_orders_text.see(tk.END)
        
        self.root.after(0, update_log)

def main():
    root = tk.Tk()
    app = ZerodhaTradingApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()