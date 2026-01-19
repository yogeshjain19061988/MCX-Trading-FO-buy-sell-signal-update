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

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha MCX Trading Platform")
        self.root.geometry("1400x800")
        
        # Initialize variables
        self.kite = None
        self.is_logged_in = False
        self.live_data = {}
        self.positions = {}
        self.orders = {}
        self.profit_target = 0
        self.total_pnl = 0
        self.instruments_df = None
        self.live_data_running = False
        
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
    
    def get_instrument_token(self, tradingsymbol):
        """Get instrument token for trading symbol"""
        if self.instruments_df is not None:
            instrument = self.instruments_df[
                self.instruments_df['tradingsymbol'] == tradingsymbol
            ]
            if not instrument.empty:
                return instrument.iloc[0]['instrument_token']
        return None
    
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
                (self.instruments_df['tradingsymbol'].str.contains('FUT')) &
                (self.instruments_df['expiry'].notnull())
            ].copy()
            
            if relevant_instruments.empty:
                self.log_message(f"No FUT contracts found for {base_symbol}")
                # Try without FUT filter
                relevant_instruments = self.instruments_df[
                    (self.instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                    (self.instruments_df['expiry'].notnull())
                ].copy()
            
            if relevant_instruments.empty:
                self.log_message(f"No contracts found for {base_symbol}")
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
            
            self.log_message(f"Found {len(selected_contracts)} contracts for {base_symbol}")
            return selected_contracts[:3]  # Return max 3 contracts
            
        except Exception as e:
            self.log_message(f"Error getting monthly contracts: {str(e)}")
            import traceback
            self.log_message(f"Traceback: {traceback.format_exc()}")
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
        
        # Trading Tab
        self.setup_trading_tab(notebook)
        
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
        
        # Instrument selection
        selection_frame = ttk.Frame(market_frame)
        selection_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(selection_frame, text="Select Instrument:").pack(side='left', padx=5)
        
        self.instrument_var = tk.StringVar()
        self.instrument_combo = ttk.Combobox(selection_frame, textvariable=self.instrument_var, 
                                       values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC"])
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
        
        self.contracts_var = tk.StringVar()
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
    
    def setup_trading_tab(self, notebook):
        """Setup trading tab"""
        trade_frame = ttk.Frame(notebook)
        notebook.add(trade_frame, text="Trading")
        
        # Order placement
        order_frame = ttk.LabelFrame(trade_frame, text="Place Order")
        order_frame.pack(fill='x', padx=10, pady=10)
        
        # Instrument
        ttk.Label(order_frame, text="Instrument:").grid(row=0, column=0, padx=5, pady=5)
        self.trade_instrument = ttk.Combobox(order_frame, values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC"])
        self.trade_instrument.grid(row=0, column=1, padx=5, pady=5)
        self.trade_instrument.set("GOLD")
        
        # Transaction type
        ttk.Label(order_frame, text="Transaction:").grid(row=0, column=2, padx=5, pady=5)
        self.transaction_type = ttk.Combobox(order_frame, values=["BUY", "SELL"])
        self.transaction_type.grid(row=0, column=3, padx=5, pady=5)
        self.transaction_type.set("BUY")
        
        # Quantity
        ttk.Label(order_frame, text="Quantity:").grid(row=1, column=0, padx=5, pady=5)
        self.quantity_entry = ttk.Entry(order_frame)
        self.quantity_entry.grid(row=1, column=1, padx=5, pady=5)
        self.quantity_entry.insert(0, "1")
        
        # Order type
        ttk.Label(order_frame, text="Order Type:").grid(row=1, column=2, padx=5, pady=5)
        self.order_type = ttk.Combobox(order_frame, values=["MARKET", "LIMIT"])
        self.order_type.grid(row=1, column=3, padx=5, pady=5)
        self.order_type.set("MARKET")
        
        # Price (for limit orders)
        ttk.Label(order_frame, text="Price:").grid(row=2, column=0, padx=5, pady=5)
        self.price_entry = ttk.Entry(order_frame)
        self.price_entry.grid(row=2, column=1, padx=5, pady=5)
        self.price_entry.insert(0, "0")
        
        # Multiple orders
        ttk.Label(order_frame, text="Multiple Orders:").grid(row=2, column=2, padx=5, pady=5)
        self.multiple_orders = ttk.Entry(order_frame, width=10)
        self.multiple_orders.grid(row=2, column=3, padx=5, pady=5)
        self.multiple_orders.insert(0, "1")
        
        # Buttons
        ttk.Button(order_frame, text="Place Single Order", 
                  command=self.place_single_order).grid(row=3, column=0, padx=5, pady=10)
        ttk.Button(order_frame, text="Place Multiple Orders", 
                  command=self.place_multiple_orders).grid(row=3, column=1, padx=5, pady=10)
        
        # Profit target
        ttk.Label(order_frame, text="Auto Exit Profit Target:").grid(row=4, column=0, padx=5, pady=5)
        self.profit_target_entry = ttk.Entry(order_frame)
        self.profit_target_entry.grid(row=4, column=1, padx=5, pady=5)
        self.profit_target_entry.insert(0, "1000")
        
        ttk.Button(order_frame, text="Set Profit Target", 
                  command=self.set_profit_target).grid(row=4, column=2, padx=5, pady=10)
        ttk.Button(order_frame, text="Auto Exit All Positions", 
                  command=self.auto_exit_positions).grid(row=4, column=3, padx=5, pady=10)
        
        # Orders log
        orders_log_frame = ttk.LabelFrame(trade_frame, text="Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.orders_text.pack(fill='both', expand=True, padx=10, pady=10)
    
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
    
    def start_background_tasks(self):
        """Start background data fetching tasks"""
        # Start position updates
        threading.Thread(target=self.update_positions_loop, daemon=True).start()
        
        # Start P&L updates
        threading.Thread(target=self.update_pnl_loop, daemon=True).start()
        
        # Start profit target monitoring
        threading.Thread(target=self.monitor_profit_target, daemon=True).start()
    
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
            self.market_data_text.insert(tk.END, f"{'Contract':<20} {'LTP':<15} {'Change':<15} {'Volume':<15} {'OI':<15} {'Time':<10}\n")
            self.market_data_text.insert(tk.END, "-" * 90 + "\n")
            
            for item in data:
                self.market_data_text.insert(tk.END, 
                    f"{item['Contract']:<20} {item['LTP']:<15} {item['Change']:<15} "
                    f"{item['Volume']:<15} {item['OI']:<15} {item['Timestamp']:<10}\n"
                )
        
        self.root.after(0, update)
    
    def stop_live_data(self):
        """Stop live data streaming"""
        self.live_data_running = False
        self.log_message("Live data stopped")
    
    def place_single_order(self):
        """Place a single order"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            instrument = self.trade_instrument.get()
            transaction = self.transaction_type.get()
            quantity = int(self.quantity_entry.get())
            order_type = self.order_type.get()
            price = float(self.price_entry.get()) if self.price_entry.get() and float(self.price_entry.get()) > 0 else 0
            
            # Get current month contract for trading
            contracts = self.get_monthly_contracts(instrument)
            if not contracts:
                messagebox.showerror("Error", f"No contracts found for {instrument}")
                return
            
            trading_symbol = contracts[1] if len(contracts) > 1 else contracts[0]  # Use current month
            
            # Get current LTP for reference
            try:
                ltp_data = self.kite.ltp(f"MCX:{trading_symbol}")
                current_ltp = list(ltp_data.values())[0]['last_price']
                self.log_message(f"Current LTP for {trading_symbol}: {current_ltp}")
            except:
                current_ltp = 0
            
            # For market orders, price should be 0
            if order_type == "MARKET":
                price = 0
            
            # Place order
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange="MCX",
                tradingsymbol=trading_symbol,
                transaction_type=transaction,
                quantity=quantity,
                order_type=order_type,
                product=self.kite.PRODUCT_NRML,
                price=price if order_type == "LIMIT" else None
            )
            
            self.log_message(f"Order placed successfully: {trading_symbol} {transaction} {quantity} - Order ID: {order_id}")
            
        except Exception as e:
            self.log_message(f"Error placing order: {e}")
    
    def place_multiple_orders(self):
        """Place multiple orders automatically"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            num_orders = int(self.multiple_orders.get())
            instrument = self.trade_instrument.get()
            transaction = self.transaction_type.get()
            quantity = int(self.quantity_entry.get())
            order_type = self.order_type.get()
            
            threading.Thread(target=self.execute_multiple_orders, 
                           args=(num_orders, instrument, transaction, quantity, order_type),
                           daemon=True).start()
            
        except Exception as e:
            self.log_message(f"Error starting multiple orders: {e}")
    
    def execute_multiple_orders(self, num_orders, instrument, transaction, quantity, order_type):
        """Execute multiple orders in sequence"""
        orders_placed = 0
        
        for i in range(num_orders):
            try:
                # Get current month contract
                contracts = self.get_monthly_contracts(instrument)
                if not contracts:
                    self.log_message(f"No contracts found for {instrument}")
                    break
                
                trading_symbol = contracts[1] if len(contracts) > 1 else contracts[0]
                
                # Get current LTP
                ltp_data = self.kite.ltp(f"MCX:{trading_symbol}")
                current_ltp = list(ltp_data.values())[0]['last_price']
                
                # Calculate price for limit orders
                price = 0
                if order_type == "LIMIT":
                    # Set limit price slightly better than LTP
                    if transaction == "BUY":
                        price = current_ltp * 0.995  # 0.5% below LTP
                    else:
                        price = current_ltp * 1.005  # 0.5% above LTP
                
                # Place order
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange="MCX",
                    tradingsymbol=trading_symbol,
                    transaction_type=transaction,
                    quantity=quantity,
                    order_type=order_type,
                    product=self.kite.PRODUCT_NRML,
                    price=price if order_type == "LIMIT" else None
                )
                
                orders_placed += 1
                self.log_message(f"Order {i+1}/{num_orders} placed - {trading_symbol} {transaction} {quantity} - ID: {order_id} at LTP: {current_ltp}")
                
                # Wait before next order
                time.sleep(2)
                
            except Exception as e:
                self.log_message(f"Error placing order {i+1}: {e}")
                # Wait and retry
                time.sleep(5)
        
        self.log_message(f"Multiple orders completed: {orders_placed}/{num_orders} placed successfully")
    
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
    
    def log_message(self, message):
        """Add message to orders log"""
        def update_log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.orders_text.see(tk.END)
        
        self.root.after(0, update_log)

def main():
    root = tk.Tk()
    app = ZerodhaTradingApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()