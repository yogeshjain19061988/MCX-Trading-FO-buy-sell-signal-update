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
import calendar
from dateutil.relativedelta import relativedelta
import math

class ZerodhaTradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha MCX Trading Platform")
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
        self.live_data_running = False
        self.futures_data_running = False
        self.options_data_running = False
        self.ce_pe_data_running = False  # New: CE/PE data running flag
        
        # Selection dictionaries
        self.selected_buy_futures = {}
        self.selected_sell_futures = {}
        self.selected_single_futures = {}
        self.selected_buy_options = {}
        self.selected_sell_options = {}
        self.selected_single_options = {}
        
        # ===== NEW: CE/PE Selection Dictionaries =====
        self.selected_ce_options = {}
        self.selected_pe_options = {}
        self.selected_cepe_pair = {}  # For combined CE/PE orders
        # ============================================
        
        # Month selection variables
        self.current_month = datetime.now().month
        self.current_year = datetime.now().year
        self.selected_option_month = None
        self.selected_option_year = None
        
        # Real-time price tracking
        self.price_update_event = Event()
        self.current_prices = {}
        self.real_time_windows = []
        
        # Month & Protection Variables
        self.expiry_month_map = {}
        self.protection_settings = {
            'daily_loss_limit': -5000.0,
            'max_orders_per_symbol': 10,
            'max_qty_per_symbol': 100,
            'position_value_alert_percent': 80.0,
            'enable_loss_protection': True,
            'enable_margin_check': True,
            'enable_lot_validation': True
        }
        
        # ===== ENHANCED: AUTOMATIC LIMIT PRICE SETTINGS =====
        self.limit_price_settings = {
            'auto_limit_enabled': True,
            'futures_buy_tolerance': 0.5,  # % below market for BUY
            'futures_sell_tolerance': 0.5,  # % above market for SELL
            'options_buy_tolerance': 0.5,
            'options_sell_tolerance': 0.5,
            'ce_buy_tolerance': 0.5,
            'ce_sell_tolerance': 0.5,
            'pe_buy_tolerance': 0.5,
            'pe_sell_tolerance': 0.5,
            'exit_buy_tolerance': 0.5,  # For exiting SHORT positions (BUY to cover)
            'exit_sell_tolerance': 0.5,  # For exiting LONG positions (SELL)
            'min_price_tick': 0.05,
            'max_adjustment_percent': 2.0,
            'use_market_fallback': True,
            'round_to_tick': True
        }
        # =====================================================
        
        self.daily_pnl = 0.0
        self.order_count_per_symbol = {}
        self.positions_value = 0.0
        self.protection_alerts = []
        # =============================================
        
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
                #print(all_instruments)
                #all_instruments.append(["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"])  # Also load NFO for options
                self.instruments_df = pd.DataFrame(all_instruments)
                
                # Convert expiry to datetime if it's string
                if 'expiry' in self.instruments_df.columns and self.instruments_df['expiry'].dtype == 'object':
                    self.instruments_df['expiry'] = pd.to_datetime(self.instruments_df['expiry']).dt.date
                
                print(f"Loaded {len(self.instruments_df)} MCX instruments")
                self.log_message(f"Loaded {len(self.instruments_df)} MCX instruments")
                
                # Update symbol lists in GUI after loading
                self.update_symbol_lists()
                
        except Exception as e:
            self.log_message(f"Error loading instruments: {e}")
    

    def debug_month_data(self):
        """Debug method to check month data"""
        try:
            underlying = self.options_underlying_var.get()
            month_str = self.options_month_combo.get()
            
            print(f"\n=== DEBUG MONTH DATA ===")
            print(f"Underlying: {underlying}")
            print(f"Month string: {month_str}")
            
            if month_str:
                # Parse the month
                month_part = month_str.split()[0]
                year_part = month_str.split()[1] if len(month_str.split()) > 1 else "'24"
                
                month_dict = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                
                target_month = month_dict.get(month_part, datetime.now().month)
                
                # Parse year
                year_part = year_part.replace("'", "")
                if len(year_part) == 2:
                    target_year = 2000 + int(year_part)
                else:
                    target_year = int(year_part)
                
                print(f"Parsed month/year: {target_month}/{target_year}")
                
                # Get contracts for this month
                contracts = self.get_month_contracts(underlying, month_str)
                print(f"Found {len(contracts)} contracts")
                
                if contracts:
                    for i, contract in enumerate(contracts[:5]):
                        print(f"  {i+1}. {contract['tradingsymbol']} - {contract['instrument_type']} - Strike: {contract['strike']}")
                
            print("=== END DEBUG ===\n")
            
        except Exception as e:
            print(f"Debug error: {e}")



    def get_mcx_symbols(self):
        """Get available MCX symbols from instruments"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                # if self.instruments_df is None:
                #     return ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"]
            
            # Get unique base symbols from MCX instruments
            mcx_instruments = self.instruments_df[self.instruments_df['exchange'] == 'MCX']
            
            # Extract base symbols (first word before any numbers or special chars)
            def extract_base_symbol(tradingsymbol):
                # Remove numbers and special characters, take first word
                import re
                base = re.split(r'[0-9]+', tradingsymbol)[0]
                base = re.sub(r'[^a-zA-Z]', '', base)
                return base
            
            mcx_instruments['base_symbol'] = mcx_instruments['tradingsymbol'].apply(extract_base_symbol)
            
            # Get unique symbols, filter out empty and very short ones
            unique_symbols = mcx_instruments['base_symbol'].unique()
            valid_symbols = [symbol for symbol in unique_symbols if len(symbol) > 2]
            
            # Sort alphabetically
            valid_symbols.sort()

            #print(list(set(valid_symbols))[:15] )
            
            return list(set(valid_symbols))[:15]  # Return top 15 unique symbols
            
        except Exception as e:
            self.log_message(f"Error getting MCX symbols: {e}")
            return ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"]
    
    def update_symbol_lists(self):
        """Update all symbol dropdowns with actual MCX symbols"""
        try:
            if self.instruments_df is not None:
                # Get actual MCX symbols
                mcx_symbols = self.get_mcx_symbols()
                
                # Update Market Data tab
                if hasattr(self, 'instrument_combo'):
                    current_value = self.instrument_combo.get()
                    self.instrument_combo['values'] = mcx_symbols
                    if current_value in mcx_symbols:
                        self.instrument_combo.set(current_value)
                    elif mcx_symbols:
                        self.instrument_combo.set(mcx_symbols[0])
                
                # Update Options Trading tab
                if hasattr(self, 'options_underlying_combo'):
                    current_value = self.options_underlying_combo.get()
                    self.options_underlying_combo['values'] = mcx_symbols
                    if current_value in mcx_symbols:
                        self.options_underlying_combo.set(current_value)
                    elif mcx_symbols:
                        self.options_underlying_combo.set(mcx_symbols[0])
                
                # Update Strategy tab
                if hasattr(self, 'strategy_underlying_combo'):
                    current_value = self.strategy_underlying_combo.get()
                    self.strategy_underlying_combo['values'] = mcx_symbols
                    if current_value in mcx_symbols:
                        self.strategy_underlying_combo.set(current_value)
                    elif mcx_symbols:
                        self.strategy_underlying_combo.set(mcx_symbols[0])
                
                # ===== NEW: Update CE/PE tab underlying =====
                if hasattr(self, 'cepe_underlying_combo'):
                    current_value = self.cepe_underlying_combo.get()
                    self.cepe_underlying_combo['values'] = mcx_symbols
                    if current_value in mcx_symbols:
                        self.cepe_underlying_combo.set(current_value)
                    elif mcx_symbols:
                        self.cepe_underlying_combo.set(mcx_symbols[0])
                # ===========================================
                        
        except Exception as e:
            print(f"Error updating symbol lists: {e}")

    def get_all_futures(self):
        """Get all available futures contracts"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                # if self.instruments_df is None:
                #     return []
                if self.instruments_df is None:
                    return ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM", "NICKEL"]
            
            # Filter only futures contracts
            futures_df = self.instruments_df[
                (self.instruments_df['instrument_type'] == 'FUT') |
                (self.instruments_df['name'].str.contains('FUT', na=False))
            ].copy()
            
            # Sort by name and expiry
            futures_df = futures_df.sort_values(['name', 'expiry'])
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            futures_df = futures_df[futures_df['expiry'] >= current_date]
            
            return futures_df[['tradingsymbol', 'name', 'expiry', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting futures: {e}")
            return []
    
    def get_all_options(self, base_symbol=None):
        """Get all available options contracts"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            
            # Filter only options contracts
            options_df = self.instruments_df[
                (self.instruments_df['instrument_type'] == 'CE') |
                (self.instruments_df['instrument_type'] == 'PE') |
                (self.instruments_df['name'].str.contains('CE', na=False)) |
                (self.instruments_df['name'].str.contains('PE', na=False))
            ].copy()
            
            # Filter by base symbol if provided
            if base_symbol:
                # Extract base symbol from the name
                options_df = options_df[
                    options_df['name'].str.startswith(base_symbol)
                ]
            
            # Sort by expiry, strike, and type
            options_df = options_df.sort_values(['expiry', 'strike', 'instrument_type'])
            
            # Get current date for filtering
            current_date = datetime.now().date()
            
            # Filter out expired contracts
            options_df = options_df[options_df['expiry'] >= current_date]
            
            return options_df[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting options: {e}")
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
            return []
    
    # ===== NEW: ENHANCED MONTHLY EXPIRY METHODS =====
    def get_available_months(self, base_symbol):
        """Get all unique expiry months for a symbol from futures and options."""
        if self.instruments_df is None:
            self.load_instruments()
            if self.instruments_df is None:
                return []
        try:
            # Filter for the symbol (using name field for broader match)
            symbol_contracts = self.instruments_df[
                self.instruments_df['name'].str.contains(base_symbol, na=False)
            ].copy()
            
            if symbol_contracts.empty:
                return []
            
            # Ensure expiry is datetime and filter valid ones
            current_date = datetime.now().date()
            if 'expiry' in symbol_contracts.columns:
                if symbol_contracts['expiry'].dtype == 'object':
                    symbol_contracts['expiry'] = pd.to_datetime(symbol_contracts['expiry'])
                symbol_contracts['expiry_date'] = symbol_contracts['expiry'].dt.date
                valid_contracts = symbol_contracts[symbol_contracts['expiry_date'] >= current_date]
            
            # Extract unique month-year combinations
            unique_months = set()
            for expiry in valid_contracts['expiry_date'].unique():
                month_str = expiry.strftime("%b '%y")  # Format: "Feb '25"
                unique_months.add(month_str)
                # Store mapping for later use
                self.expiry_month_map[month_str] = (expiry.year, expiry.month)
            
            # Return sorted list
            available_months = sorted(list(unique_months), 
                                     key=lambda x: (self.expiry_month_map[x][0], 
                                                  self.expiry_month_map[x][1]))
            return available_months[:12]  # Limit to next 12 months
            
        except Exception as e:
            self.log_message(f"Error in get_available_months: {e}")
            return []

    def get_futures_for_month(self, base_symbol, month_str):
        """Get futures contracts for a specific month."""
        if month_str not in self.expiry_month_map:
            return []
        
        target_year, target_month = self.expiry_month_map[month_str]
        try:
            # Filter futures for the symbol and month
            futures_df = self.instruments_df[
                (self.instruments_df['name'].str.contains(base_symbol, na=False)) &
                ((self.instruments_df['instrument_type'] == 'FUT') |
                (self.instruments_df['tradingsymbol'].str.contains('FUT')))
            ].copy()
            
            if futures_df.empty:
                return []
            
            # Filter by month
            futures_df['expiry'] = pd.to_datetime(futures_df['expiry'])
            month_futures = futures_df[
                (futures_df['expiry'].dt.year == target_year) &
                (futures_df['expiry'].dt.month == target_month)
            ]
            
            return month_futures.to_dict('records')
            
        except Exception as e:
            self.log_message(f"Error getting futures for month: {e}")
            return []
    # ================================================
    
    # ===== NEW: MARKET PROTECTION METHODS =====
    def validate_order_safety(self, symbol, quantity, order_type="BUY"):
        """Check multiple safety conditions before order placement."""
        try:
            # 1. Daily Loss Limit Check
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                msg = f"BLOCKED: Daily loss limit {self.daily_pnl} reached. Limit: {self.protection_settings['daily_loss_limit']}"
                self.log_futures_message(msg)
                self.add_protection_alert("Loss Limit Triggered", msg)
                return False, msg
            
            # 2. Order Count Limit
            symbol_count = self.order_count_per_symbol.get(symbol, 0)
            if symbol_count >= self.protection_settings['max_orders_per_symbol']:
                msg = f"Max orders ({symbol_count}) for {symbol} reached. Limit: {self.protection_settings['max_orders_per_symbol']}"
                return False, msg
            
            # 3. Quantity Limit
            if quantity > self.protection_settings['max_qty_per_symbol']:
                msg = f"Quantity {quantity} exceeds max {self.protection_settings['max_qty_per_symbol']}."
                return False, msg
            
            # 4. Lot Size Validation (for futures/options)
            if self.protection_settings['enable_lot_validation']:
                # Check in selected futures
                if (hasattr(self, 'selected_single_futures') and 
                    symbol in self.selected_single_futures):
                    lot_size = int(self.selected_single_futures[symbol].get('lot_size', 1))
                    if quantity % lot_size != 0:
                        msg = f"Quantity {quantity} must be multiple of lot size {lot_size}."
                        return False, msg
                
                # Check in selected options
                if (hasattr(self, 'selected_single_options') and 
                    symbol in self.selected_single_options):
                    lot_size = int(self.selected_single_options[symbol].get('lot_size', 1))
                    if quantity % lot_size != 0:
                        msg = f"Quantity {quantity} must be multiple of lot size {lot_size}."
                        return False, msg
                
                # ===== NEW: Check for CE/PE selections =====
                if symbol in self.selected_ce_options:
                    lot_size = int(self.selected_ce_options[symbol].get('lot_size', 1))
                    if quantity % lot_size != 0:
                        msg = f"Quantity {quantity} must be multiple of lot size {lot_size}."
                        return False, msg
                
                if symbol in self.selected_pe_options:
                    lot_size = int(self.selected_pe_options[symbol].get('lot_size', 1))
                    if quantity % lot_size != 0:
                        msg = f"Quantity {quantity} must be multiple of lot size {lot_size}."
                        return False, msg
                # ===========================================
            
            # 5. Margin Safety Check (estimated)
            if self.protection_settings['enable_margin_check']:
                # Get current price for margin estimation
                current_price = self.current_prices.get(symbol)
                if current_price:
                    estimated_value = quantity * current_price
                    margin_safe = self.check_margin_safety(estimated_value)
                    if not margin_safe:
                        msg = f"Order estimated value {estimated_value:.2f} may exceed safe margin limits."
                        return False, msg
            
            return True, "Validation passed."
            
        except Exception as e:
            return False, f"Safety validation error: {str(e)}"

    def check_margin_safety(self, estimated_order_value):
        """Check if new order fits within available margins."""
        try:
            if not self.is_logged_in or not self.kite:
                return True  # Pass if not logged in
            
            margins = self.kite.margins()
            available_margin = float(margins['equity']['available']['cash'])
            
            # Calculate total positions value
            self.calculate_positions_value()
            
            # Check if adding this order would exceed safe limits
            total_exposure = self.positions_value + estimated_order_value
            margin_usage_percent = (total_exposure / available_margin) * 100 if available_margin > 0 else 0
            
            if margin_usage_percent > self.protection_settings['position_value_alert_percent']:
                msg = f"WARNING: Margin usage would be {margin_usage_percent:.1f}% (> {self.protection_settings['position_value_alert_percent']}%)"
                self.add_protection_alert("Margin Warning", msg)
                return False
            
            return True
            
        except Exception as e:
            self.log_message(f"Margin check error: {e}")
            return True  # Fail open if check fails

    def calculate_positions_value(self):
        """Calculate total value of all positions."""
        try:
            if not self.is_logged_in:
                self.positions_value = 0.0
                return
            
            positions = self.kite.positions()
            total_value = 0.0
            
            for position in positions['net']:
                if position['quantity'] != 0:
                    position_value = abs(position['quantity']) * position['last_price']
                    total_value += position_value
            
            self.positions_value = total_value
            
        except Exception as e:
            self.log_message(f"Error calculating positions value: {e}")

    def add_protection_alert(self, alert_type, message):
        """Add a protection alert to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        alert = f"[{timestamp}] {alert_type}: {message}"
        self.protection_alerts.append(alert)
        
        # Keep only last 50 alerts
        if len(self.protection_alerts) > 50:
            self.protection_alerts.pop(0)
        
        # Log to appropriate text area
        self.log_message(alert)

    def update_daily_pnl(self):
        """Track daily P&L for loss protection."""
        try:
            positions = self.kite.positions()
            day_pnl = 0
            for pos in positions['net']:
                day_pnl += pos.get('day_pnl', 0)
            
            self.daily_pnl = day_pnl
            
            # Check loss limit
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                alert_msg = f"ALERT: Daily P&L ({self.daily_pnl:.2f}) hit loss limit! Trading may be restricted."
                self.add_protection_alert("Loss Limit Alert", alert_msg)
                
                # Show warning message box
                def show_warning():
                    messagebox.showwarning("Loss Limit Alert", alert_msg)
                if self.root.winfo_exists():
                    self.root.after(0, show_warning)
                    
        except Exception as e:
            self.log_message(f"Error updating daily P&L: {e}")
    # =========================================

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
        
        # Options Trading Tab
        self.setup_options_trading_tab(notebook)
        
        # ===== NEW: CE/PE Options Tab =====
        self.setup_ce_pe_options_tab(notebook)
        # ==================================
        
        # Position Exit Tab
        self.setup_position_exit_tab(notebook)
        self.setup_positions_tab(notebook)
        
        # P&L Tab
        self.setup_pnl_tab(notebook)
        
        # ===== NEW: Protection Settings Tab =====
        self.setup_protection_tab(notebook)
        # ========================================

        # ===== NEW: Limit Price Settings Tab =====
        self.setup_limit_price_settings_tab(notebook)

    # ===== NEW: PROTECTION SETTINGS TAB =====
    def setup_protection_tab(self, notebook):
        """Setup market protection settings tab"""
        protection_frame = ttk.Frame(notebook)
        notebook.add(protection_frame, text="Protection Settings")
        
        # Main frame with scrollbar
        main_frame = ttk.Frame(protection_frame)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Protection Settings Frame
        settings_frame = ttk.LabelFrame(main_frame, text="Market Protection Settings")
        settings_frame.pack(fill='x', padx=5, pady=5)
        
        row = 0
        
        # Daily Loss Limit
        ttk.Label(settings_frame, text="Daily Loss Limit (₹):").grid(row=row, column=0, padx=5, pady=5, sticky='w')
        self.loss_limit_var = tk.StringVar(value=str(self.protection_settings['daily_loss_limit']))
        loss_limit_entry = ttk.Entry(settings_frame, textvariable=self.loss_limit_var, width=15)
        loss_limit_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(settings_frame, text="(Negative value, e.g., -5000)").grid(row=row, column=2, padx=5, pady=5, sticky='w')
        row += 1
        
        # Max Orders per Symbol
        ttk.Label(settings_frame, text="Max Orders per Symbol:").grid(row=row, column=0, padx=5, pady=5, sticky='w')
        self.max_orders_var = tk.StringVar(value=str(self.protection_settings['max_orders_per_symbol']))
        max_orders_entry = ttk.Entry(settings_frame, textvariable=self.max_orders_var, width=15)
        max_orders_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        row += 1
        
        # Max Quantity per Symbol
        ttk.Label(settings_frame, text="Max Quantity per Symbol:").grid(row=row, column=0, padx=5, pady=5, sticky='w')
        self.max_qty_var = tk.StringVar(value=str(self.protection_settings['max_qty_per_symbol']))
        max_qty_entry = ttk.Entry(settings_frame, textvariable=self.max_qty_var, width=15)
        max_qty_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        row += 1
        
        # Position Value Alert Percent
        ttk.Label(settings_frame, text="Margin Alert %:").grid(row=row, column=0, padx=5, pady=5, sticky='w')
        self.margin_alert_var = tk.StringVar(value=str(self.protection_settings['position_value_alert_percent']))
        margin_alert_entry = ttk.Entry(settings_frame, textvariable=self.margin_alert_var, width=15)
        margin_alert_entry.grid(row=row, column=1, padx=5, pady=5, sticky='w')
        ttk.Label(settings_frame, text="(Alert when margin usage exceeds this %)").grid(row=row, column=2, padx=5, pady=5, sticky='w')
        row += 1
        
        # Enable/Disable Features
        self.enable_loss_protection_var = tk.BooleanVar(value=self.protection_settings['enable_loss_protection'])
        loss_protection_check = ttk.Checkbutton(settings_frame, text="Enable Loss Protection", 
                                               variable=self.enable_loss_protection_var)
        loss_protection_check.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='w')
        row += 1
        
        self.enable_margin_check_var = tk.BooleanVar(value=self.protection_settings['enable_margin_check'])
        margin_check_check = ttk.Checkbutton(settings_frame, text="Enable Margin Check", 
                                            variable=self.enable_margin_check_var)
        margin_check_check.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='w')
        row += 1
        
        self.enable_lot_validation_var = tk.BooleanVar(value=self.protection_settings['enable_lot_validation'])
        lot_validation_check = ttk.Checkbutton(settings_frame, text="Enable Lot Size Validation", 
                                              variable=self.enable_lot_validation_var)
        lot_validation_check.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='w')
        row += 1
        
        # Save Settings Button
        save_button_frame = ttk.Frame(settings_frame)
        save_button_frame.grid(row=row, column=0, columnspan=3, pady=10)
        ttk.Button(save_button_frame, text="Save Protection Settings", 
                  command=self.save_protection_settings).pack(pady=5)
        
        # Protection Alerts Display
        alerts_frame = ttk.LabelFrame(main_frame, text="Recent Protection Alerts")
        alerts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.protection_alerts_text = scrolledtext.ScrolledText(alerts_frame, height=15)
        self.protection_alerts_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Current Status Frame
        status_frame = ttk.LabelFrame(main_frame, text="Current Protection Status")
        status_frame.pack(fill='x', padx=5, pady=5)
        
        self.daily_pnl_status_label = ttk.Label(status_frame, text="Daily P&L: Loading...")
        self.daily_pnl_status_label.pack(anchor='w', padx=5, pady=2)
        
        self.margin_status_label = ttk.Label(status_frame, text="Margin Usage: Loading...")
        self.margin_status_label.pack(anchor='w', padx=5, pady=2)
        
        self.positions_value_label = ttk.Label(status_frame, text="Total Positions Value: Loading...")
        self.positions_value_label.pack(anchor='w', padx=5, pady=2)
        
        # Refresh Status Button
        ttk.Button(status_frame, text="Refresh Status", 
                  command=self.update_protection_status).pack(pady=5)

    def save_protection_settings(self):
        """Save protection settings from GUI"""
        try:
            self.protection_settings['daily_loss_limit'] = float(self.loss_limit_var.get())
            self.protection_settings['max_orders_per_symbol'] = int(self.max_orders_var.get())
            self.protection_settings['max_qty_per_symbol'] = int(self.max_qty_var.get())
            self.protection_settings['position_value_alert_percent'] = float(self.margin_alert_var.get())
            self.protection_settings['enable_loss_protection'] = self.enable_loss_protection_var.get()
            self.protection_settings['enable_margin_check'] = self.enable_margin_check_var.get()
            self.protection_settings['enable_lot_validation'] = self.enable_lot_validation_var.get()
            
            # Reset order counts if max orders changed
            self.order_count_per_symbol = {}
            
            messagebox.showinfo("Success", "Protection settings saved successfully!")
            
            # Update protection alerts display
            self.update_protection_alerts_display()
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid numeric values")

    def update_protection_alerts_display(self):
        """Update the protection alerts display"""
        self.protection_alerts_text.delete(1.0, tk.END)
        for alert in self.protection_alerts[-20:]:  # Show last 20 alerts
            self.protection_alerts_text.insert(tk.END, alert + "\n")

    def update_protection_status(self):
        """Update protection status display"""
        try:
            self.update_daily_pnl()
            self.calculate_positions_value()
            
            # Update labels
            self.daily_pnl_status_label.config(
                text=f"Daily P&L: ₹{self.daily_pnl:.2f} (Limit: ₹{self.protection_settings['daily_loss_limit']})"
            )
            
            # Get margin info if available
            margin_text = "Margin Usage: Not available"
            try:
                if self.is_logged_in:
                    margins = self.kite.margins()
                    available_margin = float(margins['equity']['available']['cash'])
                    total_margin = float(margins['equity']['available']['cash']) + float(margins['equity']['used']['debits'])
                    if total_margin > 0:
                        margin_percent = (self.positions_value / total_margin) * 100
                        margin_text = f"Margin Usage: {margin_percent:.1f}% (Alert at {self.protection_settings['position_value_alert_percent']}%)"
            except:
                pass
            
            self.margin_status_label.config(text=margin_text)
            self.positions_value_label.config(text=f"Total Positions Value: ₹{self.positions_value:.2f}")
            
            # Update alerts display
            self.update_protection_alerts_display()
            
        except Exception as e:
            self.log_message(f"Error updating protection status: {e}")
    # ========================================
    
    # ===== MODIFIED: FUTURES TRADING TAB WITH MONTH SELECTION =====
    def setup_futures_trading_tab(self, notebook):
        """Setup futures trading tab with month selection"""
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
        
        # Futures Selection Table with Month Filter
        futures_table_frame = ttk.LabelFrame(left_frame, text="Available Futures Contracts (Live Prices)")
        futures_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Month selection controls
        month_controls_frame = ttk.Frame(futures_table_frame)
        month_controls_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(month_controls_frame, text="Underlying:").pack(side='left', padx=5)
        self.futures_underlying_var = tk.StringVar()
        self.futures_underlying_combo = ttk.Combobox(month_controls_frame, textvariable=self.futures_underlying_var,
                                                   values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM"])
        self.futures_underlying_combo.pack(side='left', padx=5)
        self.futures_underlying_combo.set("NATURALGAS")
        self.futures_underlying_combo.bind('<<ComboboxSelected>>', self.on_futures_underlying_changed)
        
        ttk.Label(month_controls_frame, text="Expiry Month:").pack(side='left', padx=5)
        self.futures_month_var = tk.StringVar()
        self.futures_month_combo = ttk.Combobox(month_controls_frame, textvariable=self.futures_month_var, width=12)
        self.futures_month_combo.pack(side='left', padx=5)
        
        # Buttons for futures table
        futures_buttons_frame = ttk.Frame(futures_table_frame)
        futures_buttons_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(futures_buttons_frame, text="Refresh Futures", 
                  command=self.refresh_futures_table).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Start Live Prices", 
                  command=self.start_futures_live_data).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="Stop Live Prices", 
                  command=self.stop_futures_live_data).pack(side='left', padx=5)
        ttk.Button(futures_buttons_frame, text="All Months", 
                  command=self.show_all_futures_months).pack(side='left', padx=5)
        
        # Futures table
        table_frame = ttk.Frame(futures_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.futures_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Lot Size', 'LTP', 'Change', 'Volume'
        ), show='headings', yscrollcommand=tree_scroll.set, height=15)
        
        tree_scroll.config(command=self.futures_tree.yview)
        
        # Define headings
        self.futures_tree.heading('Symbol', text='Trading Symbol')
        self.futures_tree.heading('Name', text='Name')
        self.futures_tree.heading('Expiry', text='Expiry')
        self.futures_tree.heading('Lot Size', text='Lot Size')
        self.futures_tree.heading('LTP', text='LTP')
        self.futures_tree.heading('Change', text='Change %')
        self.futures_tree.heading('Volume', text='Volume')
        
        # Set column widths
        self.futures_tree.column('Symbol', width=150)
        self.futures_tree.column('Name', width=100)
        self.futures_tree.column('Expiry', width=100)
        self.futures_tree.column('Lot Size', width=80, anchor='center')
        self.futures_tree.column('LTP', width=100, anchor='center')
        self.futures_tree.column('Change', width=80, anchor='center')
        self.futures_tree.column('Volume', width=80, anchor='center')
        
        self.futures_tree.pack(fill='both', expand=True)
        
        # Order placement (Right side) - This remains the same
        order_frame = ttk.LabelFrame(right_frame, text="Futures Order Placement")
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
        
        # Initialize month selection
        self.on_futures_underlying_changed()
    
    def on_futures_underlying_changed(self, event=None):
        """Update month selection when futures underlying changes"""
        try:
            if not self.is_logged_in:
                self.futures_month_combo['values'] = []
                self.futures_month_combo.set("")
                return
            
            underlying = self.futures_underlying_var.get()
            
            if not underlying:
                return
            
            available_months = self.get_available_months(underlying)
            
            if available_months:
                self.futures_month_combo['values'] = available_months
                self.futures_month_combo.set(available_months[0])
                
                self.log_futures_message(f"Loaded {len(available_months)} expiry months for {underlying}")
            else:
                self.futures_month_combo['values'] = []
                self.futures_month_combo.set("")
                self.log_futures_message(f"No expiry months found for {underlying}")
                
        except Exception as e:
            self.log_futures_message(f"Error updating futures month selection: {e}")
    
    def refresh_futures_table(self):
        """Refresh the futures contracts table with month filtering"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            # Clear existing data
            for item in self.futures_tree.get_children():
                self.futures_tree.delete(item)
            
            underlying = self.futures_underlying_var.get()
            month_str = self.futures_month_var.get()
            
            if month_str:
                # Get futures for specific month
                futures = self.get_futures_for_month(underlying, month_str)
                self.log_futures_message(f"Loaded {len(futures)} futures for {underlying} - {month_str}")
            else:
                # Get all futures (legacy behavior)
                futures = self.get_all_futures()
                self.log_futures_message(f"Loaded {len(futures)} futures for {underlying} (all months)")
            
            # Add futures to table
            for future in futures:
                expiry_str = future['expiry'].strftime('%d-%b-%Y') if hasattr(future['expiry'], 'strftime') else str(future['expiry'])
                self.futures_tree.insert('', 'end', values=(
                    future['tradingsymbol'],
                    future['name'],
                    expiry_str,
                    future['lot_size'],
                    'Loading...',  # LTP
                    'Loading...',  # Change %
                    'Loading...'   # Volume
                ))
            
            # Start live data for futures if not already running
            if not self.futures_data_running:
                self.start_futures_live_data()
            
        except Exception as e:
            self.log_futures_message(f"Error refreshing futures table: {e}")
    
    def show_all_futures_months(self):
        """Show futures for all months (legacy behavior)"""
        self.futures_month_var.set("")
        self.refresh_futures_table()
    # ===================================================
    
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
        self.instrument_combo.set("NATURALGAS")
        
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
                    f"{item['Contract']:<20} {item['LTP']:<15.2f} {item['Change']:<15.2f} "
                    f"{item['Volume']:<15} {item['OI']:<15} {item['Timestamp']:<10}\n"
                )
        
        self.root.after(0, update)
    
    def stop_live_data(self):
        """Stop live data streaming"""
        self.live_data_running = False
        self.log_message("Live data stopped")
    
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
        self.futures_order_type.set("MARKET")
        
        # Quantity type
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.futures_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.futures_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.futures_quantity_type.set("Lot Size")
        
        # Quantity
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.futures_quantity_entry = ttk.Entry(params_frame)
        self.futures_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.futures_quantity_entry.insert(0, "1")
        
        # Price (for limit orders)
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.futures_price_entry = ttk.Entry(params_frame)
        self.futures_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.futures_price_entry.insert(0, "0")
        
        # Order buttons frame
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(order_buttons_frame, text="Place Futures Orders with Real-time Prices", 
                  command=self.place_futures_single_orders).pack(side='left', padx=5)
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
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Futures Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", 
                  command=self.select_futures_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", 
                  command=self.clear_futures_buy_selection).pack(padx=5, pady=5)
        
        self.selected_futures_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_futures_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_futures_buy_text.insert(tk.END, "No BUY futures contracts selected")
        
        # BUY Order Parameters
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
        
        # SELL Contracts Selection
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Futures Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", 
                  command=self.select_futures_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", 
                  command=self.clear_futures_sell_selection).pack(padx=5, pady=5)
        
        self.selected_futures_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_futures_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_futures_sell_text.insert(tk.END, "No SELL futures contracts selected")
        
        # SELL Order Parameters
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
        
        # Combined order button
        combined_button_frame = ttk.Frame(parent)
        combined_button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(combined_button_frame, text="Place BUY & SELL Futures Orders with Real-time Prices", 
                  command=self.place_futures_buy_sell_orders).pack(pady=5)
        
        # Configure grid weights
        buy_params_frame.columnconfigure(1, weight=1)
        sell_params_frame.columnconfigure(1, weight=1)
    
    def setup_options_trading_tab(self, notebook):
        """Setup options trading tab with improved month selection"""
        options_frame = ttk.Frame(notebook)
        notebook.add(options_frame, text="Options Trading")
        
        # Create paned window for better layout
        paned_window = ttk.PanedWindow(options_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Left side - Options selection table
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=2)
        
        # Right side - Order placement
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=1)
        
        # Options Selection Table
        options_table_frame = ttk.LabelFrame(left_frame, text="Options Contracts Selection")
        options_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Month selection controls
        month_controls_frame = ttk.Frame(options_table_frame)
        month_controls_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(month_controls_frame, text="Underlying:").pack(side='left', padx=5)
        self.options_underlying_var = tk.StringVar()
        self.options_underlying_combo = ttk.Combobox(month_controls_frame, textvariable=self.options_underlying_var,
                                                   values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM"])
        self.options_underlying_combo.pack(side='left', padx=5)
        self.options_underlying_combo.set("NATURALGAS")
        self.options_underlying_combo.bind('<<ComboboxSelected>>', self.on_underlying_changed)
        
        ttk.Label(month_controls_frame, text="Expiry Month:").pack(side='left', padx=5)
        self.options_month_var = tk.StringVar()
        self.options_month_combo = ttk.Combobox(month_controls_frame, textvariable=self.options_month_var, width=12)
        self.options_month_combo.pack(side='left', padx=5)
        
        ttk.Label(month_controls_frame, text="Option Type:").pack(side='left', padx=5)
        self.options_type_var = tk.StringVar()
        self.options_type_combo = ttk.Combobox(month_controls_frame, textvariable=self.options_type_var,
                                             values=["ALL", "CE", "PE"])
        self.options_type_combo.pack(side='left', padx=5)
        self.options_type_combo.set("ALL")
        
        ttk.Button(month_controls_frame, text="Load Options", 
                  command=self.refresh_options_table_month).pack(side='left', padx=5)
        ttk.Button(month_controls_frame, text="Start Live Prices", 
                  command=self.start_options_live_data).pack(side='left', padx=5)
        ttk.Button(month_controls_frame, text="Stop Live Prices", 
                  command=self.stop_options_live_data).pack(side='left', padx=5)
        
        # Filter frame
        filter_frame = ttk.Frame(options_table_frame)
        filter_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(filter_frame, text="Strike Range:").pack(side='left', padx=5)
        
        ttk.Label(filter_frame, text="From:").pack(side='left', padx=2)
        self.min_strike_var = tk.StringVar(value="0")
        min_strike_entry = ttk.Entry(filter_frame, textvariable=self.min_strike_var, width=8)
        min_strike_entry.pack(side='left', padx=2)
        
        ttk.Label(filter_frame, text="To:").pack(side='left', padx=2)
        self.max_strike_var = tk.StringVar(value="100000")
        max_strike_entry = ttk.Entry(filter_frame, textvariable=self.max_strike_var, width=8)
        max_strike_entry.pack(side='left', padx=2)
        
        ttk.Button(filter_frame, text="Apply Filter", 
                  command=self.apply_strike_filter).pack(side='left', padx=10)
        

        ttk.Button(month_controls_frame, text="Debug Month", 
          command=self.debug_month_data).pack(side='left', padx=5)
        
        # Options table
        table_frame = ttk.Frame(options_table_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create treeview with scrollbar
        tree_scroll = ttk.Scrollbar(table_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.options_tree = ttk.Treeview(table_frame, columns=(
            'Symbol', 'Name', 'Expiry', 'Strike', 'Type', 'Lot Size', 'LTP', 'Change', 'Volume', 'OI'
        ), show='headings', yscrollcommand=tree_scroll.set, height=20)
        
        tree_scroll.config(command=self.options_tree.yview)
        
        # Define headings
        columns = {
            'Symbol': ('Symbol', 120),
            'Name': ('Name', 100),
            'Expiry': ('Expiry', 100),
            'Strike': ('Strike', 80),
            'Type': ('Type', 50),
            'Lot Size': ('Lot Size', 80),
            'LTP': ('LTP', 90),
            'Change': ('Change %', 80),
            'Volume': ('Volume', 80),
            'OI': ('OI', 80)
        }
        
        for col, (text, width) in columns.items():
            self.options_tree.heading(col, text=text)
            self.options_tree.column(col, width=width, anchor='center')
        
        self.options_tree.pack(fill='both', expand=True)
        
        # Order placement (Right side)
        order_frame = ttk.LabelFrame(right_frame, text="Options Order Placement")
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
        order_notebook.add(strategies_tab, text="Options Strategies")
        
        # Setup single transaction tab
        self.setup_options_single_transaction_tab(single_tab)
        
        # Setup buy/sell together tab
        self.setup_options_buy_sell_together_tab(pair_tab)
        
        # Setup strategies tab
        self.setup_options_strategies_tab(strategies_tab)
        
        # Orders log
        orders_log_frame = ttk.LabelFrame(right_frame, text="Options Orders Log")
        orders_log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.options_orders_text = scrolledtext.ScrolledText(orders_log_frame, height=15)
        self.options_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Initialize month selection
        self.on_underlying_changed()
    
    def setup_options_single_transaction_tab(self, parent):
        """Setup options single transaction tab"""
        # Selection frame
        selection_frame = ttk.LabelFrame(parent, text="Options Contract Selection")
        selection_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(selection_frame, text="Select from Table", 
                  command=self.select_options_from_table_single).pack(side='left', padx=5, pady=5)
        ttk.Button(selection_frame, text="Clear Selection", 
                  command=self.clear_options_single_selection).pack(side='left', padx=5, pady=5)
        
        self.selected_options_single_text = scrolledtext.ScrolledText(selection_frame, height=4)
        self.selected_options_single_text.pack(fill='x', padx=5, pady=5)
        self.selected_options_single_text.insert(tk.END, "No options contracts selected")
        
        # Order parameters
        params_frame = ttk.LabelFrame(parent, text="Options Order Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        # Transaction type
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.options_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"])
        self.options_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.options_transaction_type.set("BUY")
        
        # Order type
        ttk.Label(params_frame, text="Order Type:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.options_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"])
        self.options_order_type.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        self.options_order_type.set("MARKET")
        
        # Quantity type
        ttk.Label(params_frame, text="Quantity Type:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.options_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"])
        self.options_quantity_type.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.options_quantity_type.set("Lot Size")
        
        # Quantity
        ttk.Label(params_frame, text="Quantity:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.options_quantity_entry = ttk.Entry(params_frame)
        self.options_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.options_quantity_entry.insert(0, "1")
        
        # Price (for limit orders)
        ttk.Label(params_frame, text="Price (for LIMIT):").grid(row=4, column=0, padx=5, pady=5, sticky='w')
        self.options_price_entry = ttk.Entry(params_frame)
        self.options_price_entry.grid(row=4, column=1, padx=5, pady=5, sticky='ew')
        self.options_price_entry.insert(0, "0")
        
        # Order buttons frame
        order_buttons_frame = ttk.Frame(parent)
        order_buttons_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(order_buttons_frame, text="Place Options Orders with Real-time Prices", 
                  command=self.place_options_single_orders).pack(side='left', padx=5)
        ttk.Button(order_buttons_frame, text="Validate Selection", 
                  command=self.validate_options_single_selection).pack(side='left', padx=5)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)
    
    def setup_options_buy_sell_together_tab(self, parent):
        """Setup options buy and sell together tab"""
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
        buy_contracts_frame = ttk.LabelFrame(buy_selection_frame, text="BUY Options Contracts")
        buy_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(buy_contracts_frame, text="Select BUY Contracts", 
                  command=self.select_options_buy_contracts).pack(padx=5, pady=5)
        ttk.Button(buy_contracts_frame, text="Clear BUY Selection", 
                  command=self.clear_options_buy_selection).pack(padx=5, pady=5)
        
        self.selected_options_buy_text = scrolledtext.ScrolledText(buy_contracts_frame, height=8)
        self.selected_options_buy_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_options_buy_text.insert(tk.END, "No BUY options contracts selected")
        
        # BUY Order Parameters
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
        
        # SELL Contracts Selection
        sell_contracts_frame = ttk.LabelFrame(sell_selection_frame, text="SELL Options Contracts")
        sell_contracts_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ttk.Button(sell_contracts_frame, text="Select SELL Contracts", 
                  command=self.select_options_sell_contracts).pack(padx=5, pady=5)
        ttk.Button(sell_contracts_frame, text="Clear SELL Selection", 
                  command=self.clear_options_sell_selection).pack(padx=5, pady=5)
        
        self.selected_options_sell_text = scrolledtext.ScrolledText(sell_contracts_frame, height=8)
        self.selected_options_sell_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.selected_options_sell_text.insert(tk.END, "No SELL options contracts selected")
        
        # SELL Order Parameters
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
        
        # Combined order button
        combined_button_frame = ttk.Frame(parent)
        combined_button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(combined_button_frame, text="Place BUY & SELL Options Orders with Real-time Prices", 
                  command=self.place_options_buy_sell_orders).pack(pady=5)
        
        # Configure grid weights
        buy_params_frame.columnconfigure(1, weight=1)
        sell_params_frame.columnconfigure(1, weight=1)
    
    def setup_options_strategies_tab(self, parent):
        """Setup options strategies tab"""
        strategies_frame = ttk.Frame(parent)
        strategies_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Strategy selection
        strategy_selection_frame = ttk.LabelFrame(strategies_frame, text="Options Strategies")
        strategy_selection_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(strategy_selection_frame, text="Select Strategy:").pack(side='left', padx=5, pady=5)
        
        self.strategy_var = tk.StringVar()
        strategy_combo = ttk.Combobox(strategy_selection_frame, textvariable=self.strategy_var,
                                    values=["Long Call", "Long Put", "Short Call", "Short Put", 
                                           "Bull Call Spread", "Bear Put Spread", "Straddle", "Strangle",
                                           "Iron Condor", "Butterfly"])
        strategy_combo.pack(side='left', padx=5, pady=5)
        strategy_combo.set("Long Call")
        
        ttk.Button(strategy_selection_frame, text="Explain Strategy", 
                  command=self.explain_strategy).pack(side='left', padx=5, pady=5)
        
        # Strategy parameters
        params_frame = ttk.LabelFrame(strategies_frame, text="Strategy Parameters")
        params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(params_frame, text="Underlying:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.strategy_underlying_var = tk.StringVar()
        self.strategy_underlying_combo = ttk.Combobox(params_frame, textvariable=self.strategy_underlying_var,
                                                    values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS"])
        self.strategy_underlying_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.strategy_underlying_combo.set("NATURALGAS")
        self.strategy_underlying_combo.bind('<<ComboboxSelected>>', self.on_strategy_underlying_changed)
        
        # Month selection for strategy
        ttk.Label(params_frame, text="Expiry Month:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.strategy_month_var = tk.StringVar()
        self.strategy_month_combo = ttk.Combobox(params_frame, textvariable=self.strategy_month_var, width=12)
        self.strategy_month_combo.grid(row=1, column=1, padx=5, pady=5, sticky='ew')
        
        # Strike price
        ttk.Label(params_frame, text="Strike Price:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.strike_price_entry = ttk.Entry(params_frame)
        self.strike_price_entry.grid(row=2, column=1, padx=5, pady=5, sticky='ew')
        self.strike_price_entry.insert(0, "0")
        
        # Quantity
        ttk.Label(params_frame, text="Quantity (Lots):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.strategy_quantity_entry = ttk.Entry(params_frame)
        self.strategy_quantity_entry.grid(row=3, column=1, padx=5, pady=5, sticky='ew')
        self.strategy_quantity_entry.insert(0, "1")
        
        # Initialize strategy month selection
        self.on_strategy_underlying_changed()
        
        # Strategy description
        desc_frame = ttk.LabelFrame(strategies_frame, text="Strategy Description")
        desc_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.strategy_desc_text = scrolledtext.ScrolledText(desc_frame, height=8)
        self.strategy_desc_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Execute strategy button
        execute_frame = ttk.Frame(strategies_frame)
        execute_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(execute_frame, text="Execute Strategy with Real-time Prices", 
                  command=self.execute_options_strategy).pack(pady=5)
        
        # Configure grid weights
        params_frame.columnconfigure(1, weight=1)
        
        # Load initial strategy description
        self.explain_strategy()
    
    def explain_strategy(self):
        """Explain the selected options strategy"""
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
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
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
    
    # Options selection methods (similar to futures but for options)
    def select_options_from_table_single(self):
        self.open_options_selection_window('single')
    
    def select_options_buy_contracts(self):
        self.open_options_selection_window('buy')
    
    def select_options_sell_contracts(self):
        self.open_options_selection_window('sell')
    
    def open_options_selection_window(self, order_type):
        selection_window = tk.Toplevel(self.root)
        selection_window.title(f"Select Options Contracts for {order_type.upper()} Orders")
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
        
        # Populate with options data
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
            message = f"{len(self.selected_single_options)} options contracts selected for trading"
        elif order_type == 'buy':
            self.update_options_buy_selection_display()
            message = f"{len(self.selected_buy_options)} options contracts selected for BUY orders"
        else:
            self.update_options_sell_selection_display()
            message = f"{len(self.selected_sell_options)} options contracts selected for SELL orders"
        
        window.destroy()
        messagebox.showinfo("Selection Complete", message)
    
    def update_options_single_selection_display(self):
        self.selected_options_single_text.delete(1.0, tk.END)
        
        if not self.selected_single_options:
            self.selected_options_single_text.insert(tk.END, "No options contracts selected")
            return
        
        for symbol, details in self.selected_single_options.items():
            self.selected_options_single_text.insert(tk.END, 
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Strike: {details['strike']}\n"
                f"Type: {details['type']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
                f"{'-'*40}\n"
            )
    
    def update_options_buy_selection_display(self):
        self.selected_options_buy_text.delete(1.0, tk.END)
        
        if not self.selected_buy_options:
            self.selected_options_buy_text.insert(tk.END, "No BUY options contracts selected")
            return
        
        for symbol, details in self.selected_buy_options.items():
            self.selected_options_buy_text.insert(tk.END, 
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Strike: {details['strike']}\n"
                f"Type: {details['type']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
                f"{'-'*40}\n"
            )
    
    def update_options_sell_selection_display(self):
        self.selected_options_sell_text.delete(1.0, tk.END)
        
        if not self.selected_sell_options:
            self.selected_options_sell_text.insert(tk.END, "No SELL options contracts selected")
            return
        
        for symbol, details in self.selected_sell_options.items():
            self.selected_options_sell_text.insert(tk.END, 
                f"Symbol: {symbol}\n"
                f"Name: {details['name']}\n"
                f"Expiry: {details['expiry']}\n"
                f"Strike: {details['strike']}\n"
                f"Type: {details['type']}\n"
                f"Lot Size: {details['lot_size']}\n"
                f"LTP: {details.get('ltp', 'N/A')}\n"
                f"{'-'*40}\n"
            )
    
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
            messagebox.showwarning("Warning", "No options contracts selected")
            return
        
        messagebox.showinfo("Selection Valid", 
                          f"{len(self.selected_single_options)} options contracts selected and ready for trading")
    
    # Real-time Price Methods
    def get_current_price(self, symbol):
        """Get current LTP for a symbol with retry mechanism"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ltp_data = self.kite.ltp(f"MCX:{symbol}")
                price = list(ltp_data.values())[0]['last_price']
                self.current_prices[symbol] = price
                return price
            except Exception as e:
                self.log_message(f"Price fetch attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        return None
    
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
                # Fetch prices in batches
                batch_size = 10
                for i in range(0, len(symbols), batch_size):
                    batch_symbols = symbols[i:i + batch_size]
                    instruments = [f"MCX:{symbol}" for symbol in batch_symbols]
                    
                    ltp_data = self.kite.ltp(instruments)
                    
                    for instrument_key, data in ltp_data.items():
                        symbol = instrument_key.replace("MCX:", "")
                        self.current_prices[symbol] = data['last_price']
                    
                    # Small delay between batches
                    time.sleep(0.2)
                
                # Wait before next update cycle
                time.sleep(1)
                
            except Exception as e:
                self.log_message(f"Error in continuous price update: {e}")
                time.sleep(2)
    
    # ===== MODIFIED: FUTURES ORDER PLACEMENT WITH PROTECTION =====
    def place_futures_single_orders(self):
        """Place futures single transaction orders with real-time price updates and protection"""
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
            
            # Check protection before proceeding
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit ({self.protection_settings['daily_loss_limit']}). Order blocked.")
                return
            
            # Get symbols for price updates
            symbols = list(self.selected_single_futures.keys())
            
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(symbols)
            
            # Show real-time price window
            self.show_futures_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting futures order placement: {e}")
    
        # ===== UPDATED: ORDER EXECUTION METHODS WITH AUTOMATIC LIMIT =====
    def execute_futures_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        """Execute futures single transaction orders using latest prices with protection"""
        orders_placed = 0
        total_orders = len(self.selected_single_futures)
        
        self.log_futures_message(f"Starting to place {total_orders} {transaction} futures orders with real-time prices...")
        
        for symbol, details in self.selected_single_futures.items():
            try:
                # Calculate quantity for validation
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                
                # Run safety validation
                is_safe, safety_msg = self.validate_order_safety(symbol, quantity, transaction)
                if not is_safe:
                    self.log_futures_message(f"❌ Order blocked for {symbol}: {safety_msg}")
                    self.add_protection_alert("Order Blocked", safety_msg)
                    continue
                
                # Get the latest price from our continuous updates
                current_price = self.current_prices.get(symbol)
                
                if not current_price:
                    # Fallback: fetch price directly
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_futures_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_futures_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                
                # ===== UPDATED: AUTOMATIC LIMIT PRICE CALCULATION =====
                final_price = price
                if order_type == "LIMIT":
                    if price == 0 or not price:  # No price specified, use automatic calculation
                        final_price = self.calculate_limit_price(current_price, transaction, "FUTURES")
                        self.log_futures_message(f"Auto Limit: {symbol} {transaction} at {final_price:.2f} "
                                               f"(Current: {current_price:.2f}, Tol: {self.limit_price_settings['futures_' + transaction.lower() + '_tolerance']}%)")
                    else:
                        final_price = price  # Use user-specified price
                # ======================================================
                
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
                self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                
                self.log_futures_message(f"✅ {transaction} Futures Order {orders_placed}/{total_orders}: "
                                       f"{symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                
                # Small delay between orders
                time.sleep(1)
                
            except Exception as e:
                self.log_futures_message(f"❌ Failed to place {transaction} futures order for {symbol}: {e}")
                # Try market order fallback if enabled
                if self.limit_price_settings['use_market_fallback'] and order_type == "LIMIT":
                    try:
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange="MCX",
                            tradingsymbol=symbol,
                            transaction_type=transaction,
                            quantity=quantity,
                            order_type="MARKET",
                            product=self.kite.PRODUCT_NRML
                        )
                        self.log_futures_message(f"⚠️ Market Fallback: {symbol} {transaction} {quantity} - ID: {order_id}")
                        orders_placed += 1
                    except:
                        pass
        
        self.log_futures_message(f"{transaction} futures order placement completed: {orders_placed}/{total_orders} successful")
        self.update_protection_status()
        
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} futures orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", 
                                     f"{orders_placed} out of {total_orders} {transaction} futures orders placed successfully")
        
        self.root.after(0, show_summary)
    # ==============================================================
    
    def place_futures_buy_sell_orders(self):
        """Place both BUY and SELL futures orders with real-time price updates"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_buy_futures and not self.selected_sell_futures:
            messagebox.showwarning("Warning", "No futures contracts selected for BUY or SELL")
            return
        
        try:
            # Buy order parameters
            buy_order_type = self.futures_buy_order_type.get()
            buy_quantity_type = self.futures_buy_quantity_type.get()
            buy_quantity = int(self.futures_buy_quantity_entry.get())
            buy_price = float(self.futures_buy_price_entry.get()) if self.futures_buy_price_entry.get() and float(self.futures_buy_price_entry.get()) > 0 else 0
            
            # Sell order parameters
            sell_order_type = self.futures_sell_order_type.get()
            sell_quantity_type = self.futures_sell_quantity_type.get()
            sell_quantity = int(self.futures_sell_quantity_entry.get())
            sell_price = float(self.futures_sell_price_entry.get()) if self.futures_sell_price_entry.get() and float(self.futures_sell_price_entry.get()) > 0 else 0
            
            # Check protection
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Order blocked.")
                return
            
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
            self.show_futures_buy_sell_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                sell_order_type, sell_quantity_type, sell_quantity, sell_price
            )
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting futures buy/sell order placement: {e}")
    
    # Options Order Placement Methods (similarly modified with protection)
    def place_options_single_orders(self):
        """Place options single transaction orders with real-time price updates and protection"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_single_options:
            messagebox.showwarning("Warning", "No options contracts selected")
            return
        
        try:
            transaction = self.options_transaction_type.get()
            order_type = self.options_order_type.get()
            quantity_type = self.options_quantity_type.get()
            base_quantity = int(self.options_quantity_entry.get())
            price = float(self.options_price_entry.get()) if self.options_price_entry.get() and float(self.options_price_entry.get()) > 0 else 0
            
            # Check protection
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Order blocked.")
                return
            
            # Get symbols for price updates
            symbols = list(self.selected_single_options.keys())
            
            if not symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(symbols)
            
            # Show real-time price window
            self.show_options_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting options order placement: {e}")
    
    def execute_options_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        """Execute options single transaction orders using latest prices with protection"""
        orders_placed = 0
        total_orders = len(self.selected_single_options)
        
        self.log_options_message(f"Starting to place {total_orders} {transaction} options orders with real-time prices...")
        
        for symbol, details in self.selected_single_options.items():
            try:
                # Calculate quantity for validation
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                
                # Safety check
                is_safe, safety_msg = self.validate_order_safety(symbol, quantity, transaction)
                if not is_safe:
                    self.log_options_message(f"❌ Order blocked for {symbol}: {safety_msg}")
                    self.add_protection_alert("Order Blocked", safety_msg)
                    continue
                
                # Get the latest price
                current_price = self.current_prices.get(symbol)
                
                if not current_price:
                    # Fallback: fetch price directly
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_options_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_options_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                
                # ===== UPDATED: AUTOMATIC LIMIT PRICE CALCULATION =====
                final_price = price
                if order_type == "LIMIT":
                    if price == 0 or not price:
                        final_price = self.calculate_limit_price(current_price, transaction, "OPTIONS")
                        self.log_options_message(f"Auto Limit: {symbol} {transaction} at {final_price:.2f} "
                                               f"(Current: {current_price:.2f}, Tol: {self.limit_price_settings['options_' + transaction.lower() + '_tolerance']}%)")
                    else:
                        final_price = price
                # ======================================================
                
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
                self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                
                self.log_options_message(f"✅ {transaction} Options Order {orders_placed}/{total_orders}: "
                                       f"{symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                
                time.sleep(1)
                
            except Exception as e:
                self.log_options_message(f"❌ Failed to place {transaction} options order for {symbol}: {e}")
                # Market fallback
                if self.limit_price_settings['use_market_fallback'] and order_type == "LIMIT":
                    try:
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange="MCX",
                            tradingsymbol=symbol,
                            transaction_type=transaction,
                            quantity=quantity,
                            order_type="MARKET",
                            product=self.kite.PRODUCT_NRML
                        )
                        self.log_options_message(f"⚠️ Market Fallback: {symbol} {transaction} {quantity} - ID: {order_id}")
                        orders_placed += 1
                    except:
                        pass
        
        self.log_options_message(f"{transaction} options order placement completed: {orders_placed}/{total_orders} successful")
        self.update_protection_status()
        
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} options orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", 
                                     f"{orders_placed} out of {total_orders} {transaction} options orders placed successfully")
        
        self.root.after(0, show_summary)
    
    def place_options_buy_sell_orders(self):
        """Place both BUY and SELL options orders with real-time price updates"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_buy_options and not self.selected_sell_options:
            messagebox.showwarning("Warning", "No options contracts selected for BUY or SELL")
            return
        
        try:
            # Buy order parameters
            buy_order_type = self.options_buy_order_type.get()
            buy_quantity_type = self.options_buy_quantity_type.get()
            buy_quantity = int(self.options_buy_quantity_entry.get())
            buy_price = float(self.options_buy_price_entry.get()) if self.options_buy_price_entry.get() and float(self.options_buy_price_entry.get()) > 0 else 0
            
            # Sell order parameters
            sell_order_type = self.options_sell_order_type.get()
            sell_quantity_type = self.options_sell_quantity_type.get()
            sell_quantity = int(self.options_sell_quantity_entry.get())
            sell_price = float(self.options_sell_price_entry.get()) if self.options_sell_price_entry.get() and float(self.options_sell_price_entry.get()) > 0 else 0
            
            # Check protection
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Order blocked.")
                return
            
            # Get all symbols for price updates
            buy_symbols = list(self.selected_buy_options.keys())
            sell_symbols = list(self.selected_sell_options.keys())
            all_symbols = buy_symbols + sell_symbols
            
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(all_symbols)
            
            # Show real-time price window for buy/sell
            self.show_options_buy_sell_real_time_window(
                buy_symbols, sell_symbols,
                buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                sell_order_type, sell_quantity_type, sell_quantity, sell_price
            )
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_message(f"Error starting options buy/sell order placement: {e}")
    
    def execute_options_buy_sell_orders_with_current_prices(self, buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                                                          sell_order_type, sell_quantity_type, sell_quantity, sell_price):
        """Execute both BUY and SELL options orders using latest prices with protection"""
        total_buy_orders = len(self.selected_buy_options)
        total_sell_orders = len(self.selected_sell_options)
        buy_orders_placed = 0
        sell_orders_placed = 0
        
        self.log_options_message(f"Starting to place {total_buy_orders} BUY and {total_sell_orders} SELL options orders with real-time prices...")
        
        # Place BUY orders
        if total_buy_orders > 0:
            self.log_options_message("=== PLACING BUY OPTIONS ORDERS ===")
            for symbol, details in self.selected_buy_options.items():
                try:
                    # Calculate quantity for validation
                    if buy_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = buy_quantity * lot_size
                    else:
                        quantity = buy_quantity
                    
                    # Safety check
                    is_safe, safety_msg = self.validate_order_safety(symbol, quantity, "BUY")
                    if not is_safe:
                        self.log_options_message(f"❌ BUY order blocked for {symbol}: {safety_msg}")
                        self.add_protection_alert("Order Blocked", safety_msg)
                        continue
                    
                    # Get latest price
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_options_message(f"❌ Could not fetch LTP for BUY {symbol}, skipping...")
                            continue
                    
                    # Determine final price for BUY
                    final_price = buy_price
                    if buy_order_type == "LIMIT":
                        if buy_price == 0:
                            final_price = current_price * 0.995  # 0.5% below LTP
                        self.log_options_message(f"BUY Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    
                    # Place BUY order
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
                    self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                    self.log_options_message(f"✅ BUY Options Order {buy_orders_placed}/{total_buy_orders}: {symbol} {quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_options_message(f"❌ Failed to place BUY options order for {symbol}: {e}")
        
        # Place SELL orders
        if total_sell_orders > 0:
            self.log_options_message("=== PLACING SELL OPTIONS ORDERS ===")
            for symbol, details in self.selected_sell_options.items():
                try:
                    # Calculate quantity for validation
                    if sell_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = sell_quantity * lot_size
                    else:
                        quantity = sell_quantity
                    
                    # Safety check
                    is_safe, safety_msg = self.validate_order_safety(symbol, quantity, "SELL")
                    if not is_safe:
                        self.log_options_message(f"❌ SELL order blocked for {symbol}: {safety_msg}")
                        self.add_protection_alert("Order Blocked", safety_msg)
                        continue
                    
                    # Get latest price
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_options_message(f"❌ Could not fetch LTP for SELL {symbol}, skipping...")
                            continue
                    
                    # Determine final price for SELL
                    final_price = sell_price
                    if sell_order_type == "LIMIT":
                        if sell_price == 0:
                            final_price = current_price * 1.005  # 0.5% above LTP
                        self.log_options_message(f"SELL Options Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    
                    # Place SELL order
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
                    self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                    self.log_options_message(f"✅ SELL Options Order {sell_orders_placed}/{total_sell_orders}: {symbol} {quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_options_message(f"❌ Failed to place SELL options order for {symbol}: {e}")
        
        # Final summary
        self.log_options_message("=== OPTIONS ORDER PLACEMENT SUMMARY ===")
        self.log_options_message(f"BUY Options Orders: {buy_orders_placed}/{total_buy_orders} successful")
        self.log_options_message(f"SELL Options Orders: {sell_orders_placed}/{total_sell_orders} successful")
        
        # Update protection status
        self.update_protection_status()
        
        def show_final_summary():
            messagebox.showinfo(
                "Buy & Sell Options Orders Completed",
                f"BUY Options Orders: {buy_orders_placed}/{total_buy_orders} successful\n"
                f"SELL Options Orders: {sell_orders_placed}/{total_sell_orders} successful"
            )
        
        self.root.after(0, show_final_summary)
    
    def execute_futures_buy_sell_orders_with_current_prices(self, buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                                                          sell_order_type, sell_quantity_type, sell_quantity, sell_price):
        """Execute both BUY and SELL futures orders using latest prices with protection"""
        total_buy_orders = len(self.selected_buy_futures)
        total_sell_orders = len(self.selected_sell_futures)
        buy_orders_placed = 0
        sell_orders_placed = 0
        
        self.log_futures_message(f"Starting to place {total_buy_orders} BUY and {total_sell_orders} SELL futures orders with real-time prices...")
        
        # Place BUY orders
        if total_buy_orders > 0:
            self.log_futures_message("=== PLACING BUY FUTURES ORDERS ===")
            for symbol, details in self.selected_buy_futures.items():
                try:
                    # Calculate quantity for validation
                    if buy_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = buy_quantity * lot_size
                    else:
                        quantity = buy_quantity
                    
                    # Safety check
                    is_safe, safety_msg = self.validate_order_safety(symbol, quantity, "BUY")
                    if not is_safe:
                        self.log_futures_message(f"❌ BUY order blocked for {symbol}: {safety_msg}")
                        self.add_protection_alert("Order Blocked", safety_msg)
                        continue
                    
                    # Get latest price
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_futures_message(f"❌ Could not fetch LTP for BUY {symbol}, skipping...")
                            continue
                    
                    # Determine final price for BUY
                    final_price = buy_price
                    if buy_order_type == "LIMIT":
                        if buy_price == 0:
                            final_price = current_price * 0.995  # 0.5% below LTP
                        self.log_futures_message(f"BUY Futures Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    
                    # Place BUY order
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
                    self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                    self.log_futures_message(f"✅ BUY Futures Order {buy_orders_placed}/{total_buy_orders}: {symbol} {quantity} @ {final_price if buy_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_futures_message(f"❌ Failed to place BUY futures order for {symbol}: {e}")
        
        # Place SELL orders
        if total_sell_orders > 0:
            self.log_futures_message("=== PLACING SELL FUTURES ORDERS ===")
            for symbol, details in self.selected_sell_futures.items():
                try:
                    # Calculate quantity for validation
                    if sell_quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = sell_quantity * lot_size
                    else:
                        quantity = sell_quantity
                    
                    # Safety check
                    is_safe, safety_msg = self.validate_order_safety(symbol, quantity, "SELL")
                    if not is_safe:
                        self.log_futures_message(f"❌ SELL order blocked for {symbol}: {safety_msg}")
                        self.add_protection_alert("Order Blocked", safety_msg)
                        continue
                    
                    # Get latest price
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_futures_message(f"❌ Could not fetch LTP for SELL {symbol}, skipping...")
                            continue
                    
                    # Determine final price for SELL
                    final_price = sell_price
                    if sell_order_type == "LIMIT":
                        if sell_price == 0:
                            final_price = current_price * 1.005  # 0.5% above LTP
                        self.log_futures_message(f"SELL Futures Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    
                    # Place SELL order
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
                    self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                    self.log_futures_message(f"✅ SELL Futures Order {sell_orders_placed}/{total_sell_orders}: {symbol} {quantity} @ {final_price if sell_order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_futures_message(f"❌ Failed to place SELL futures order for {symbol}: {e}")
        
        # Final summary
        self.log_futures_message("=== FUTURES ORDER PLACEMENT SUMMARY ===")
        self.log_futures_message(f"BUY Futures Orders: {buy_orders_placed}/{total_buy_orders} successful")
        self.log_futures_message(f"SELL Futures Orders: {sell_orders_placed}/{total_sell_orders} successful")
        
        # Update protection status
        self.update_protection_status()
        
        def show_final_summary():
            messagebox.showinfo(
                "Buy & Sell Futures Orders Completed",
                f"BUY Futures Orders: {buy_orders_placed}/{total_buy_orders} successful\n"
                f"SELL Futures Orders: {sell_orders_placed}/{total_sell_orders} successful"
            )
        
        self.root.after(0, show_final_summary)
    
    def execute_options_strategy(self):
        """Execute selected options strategy with month selection and protection"""
        strategy = self.strategy_var.get()
        underlying = self.strategy_underlying_var.get()
        month_str = self.strategy_month_var.get()
        
        if not month_str:
            messagebox.showerror("Error", "Please select an expiry month for the strategy")
            return
        
        try:
            strike_price = float(self.strike_price_entry.get())
            quantity = int(self.strategy_quantity_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid strike price and quantity")
            return
        
        # Check protection before strategy execution
        self.update_daily_pnl()
        if (self.protection_settings['enable_loss_protection'] and 
            self.daily_pnl <= self.protection_settings['daily_loss_limit']):
            messagebox.showwarning("Loss Limit", 
                f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Strategy execution blocked.")
            return
        
        # Get available options for the selected month
        month_options = self.get_month_contracts(underlying, month_str)
        
        if not month_options:
            messagebox.showinfo("Info", f"No options found for {underlying} - {month_str}")
            return
        
        # For now, just show a message about the strategy
        messagebox.showinfo("Strategy Execution", 
                          f"Preparing to execute {strategy} strategy for {underlying}\n"
                          f"Expiry: {month_str}, Strike: {strike_price}, Quantity: {quantity}\n\n"
                          f"Safety checks passed. Ready to execute with real-time prices.")
        
        # Note: In a full implementation, you would:
        # 1. Find the appropriate options contracts for the strategy
        # 2. Apply protection checks to each leg of the strategy
        # 3. Place the orders using the existing order placement methods
    
    # Real-time Price Windows (these remain the same as your original code)
    def show_futures_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        """Show real-time price window for futures orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time Futures Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        
        # Store reference to prevent garbage collection
        self.real_time_windows.append(price_window)
        
        # Main frame
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, text="Real-time Futures Prices (Updating every 1 second)", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Price display frame
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        # Create price labels for each symbol
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='blue', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        # Current order info
        info_frame = ttk.LabelFrame(main_frame, text="Futures Order Information")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='green').pack(pady=5)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            """Place orders with current prices"""
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            # Execute orders in background thread
            Thread(
                target=self.execute_futures_single_orders_with_current_prices,
                args=(transaction, order_type, quantity_type, base_quantity, price),
                daemon=True
            ).start()
        
        def cancel_orders():
            """Cancel order placement"""
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_futures_message("Futures order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place Futures Orders Now", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        # Start price updates in this window
        self.update_futures_price_display(price_labels, price_window)
    
    def update_futures_price_display(self, price_labels, window):
        """Update price labels with current prices"""
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
        
        # Schedule next update
        if window.winfo_exists():
            window.after(1000, lambda: self.update_futures_price_display(price_labels, window))
    
    def show_futures_buy_sell_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity_type, 
                                             buy_quantity, buy_price, sell_order_type, sell_quantity_type, 
                                             sell_quantity, sell_price):
        """Show real-time price window for futures buy/sell orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time Futures Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        
        # Store reference
        self.real_time_windows.append(price_window)
        
        # Main frame
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, text="Real-time Futures Prices for BUY & SELL Orders", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Create paned window for BUY/SELL
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        # BUY Frame
        buy_frame = ttk.LabelFrame(paned_window, text="BUY Futures Contracts")
        paned_window.add(buy_frame, weight=1)
        
        # SELL Frame
        sell_frame = ttk.LabelFrame(paned_window, text="SELL Futures Contracts")
        paned_window.add(sell_frame, weight=1)
        
        # BUY prices
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            buy_price_labels[symbol] = price_label
        
        # SELL prices
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            sell_price_labels[symbol] = price_label
        
        # Order info
        info_frame = ttk.LabelFrame(main_frame, text="Futures Order Summary")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='blue').pack(pady=2)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_futures_buy_sell_orders_with_current_prices,
                args=(
                    buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                    sell_order_type, sell_quantity_type, sell_quantity, sell_price
                ),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_futures_message("Futures BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY & SELL Futures Orders", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        # Start price updates
        self.update_futures_buy_sell_price_display(buy_price_labels, sell_price_labels, price_window)
    
    def update_futures_buy_sell_price_display(self, buy_labels, sell_labels, window):
        """Update BUY and SELL price labels for futures"""
        if not window.winfo_exists():
            return
        
        try:
            # Update BUY prices
            for symbol, label in buy_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            
            # Update SELL prices
            for symbol, label in sell_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
                    
        except Exception as e:
            print(f"Error updating futures buy/sell price display: {e}")
        
        # Schedule next update
        if window.winfo_exists():
            window.after(1000, lambda: self.update_futures_buy_sell_price_display(buy_labels, sell_labels, window))
    
    def show_options_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        """Show real-time price window for options orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time Options Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        
        # Store reference to prevent garbage collection
        self.real_time_windows.append(price_window)
        
        # Main frame
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, text="Real-time Options Prices (Updating every 1 second)", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Price display frame
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        # Create price labels for each symbol
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='blue', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        # Current order info
        info_frame = ttk.LabelFrame(main_frame, text="Options Order Information")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='green').pack(pady=5)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            """Place orders with current prices"""
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            # Execute orders in background thread
            Thread(
                target=self.execute_options_single_orders_with_current_prices,
                args=(transaction, order_type, quantity_type, base_quantity, price),
                daemon=True
            ).start()
        
        def cancel_orders():
            """Cancel order placement"""
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_options_message("Options order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place Options Orders Now", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        # Start price updates in this window
        self.update_options_price_display(price_labels, price_window)
    
    def update_options_price_display(self, price_labels, window):
        """Update price labels with current prices for options"""
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
        
        # Schedule next update
        if window.winfo_exists():
            window.after(1000, lambda: self.update_options_price_display(price_labels, window))
    
    def show_options_buy_sell_real_time_window(self, buy_symbols, sell_symbols, buy_order_type, buy_quantity_type, 
                                             buy_quantity, buy_price, sell_order_type, sell_quantity_type, 
                                             sell_quantity, sell_price):
        """Show real-time price window for options buy/sell orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time Options Prices - Confirm BUY & SELL Orders")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        
        # Store reference
        self.real_time_windows.append(price_window)
        
        # Main frame
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, text="Real-time Options Prices for BUY & SELL Orders", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        # Create paned window for BUY/SELL
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        # BUY Frame
        buy_frame = ttk.LabelFrame(paned_window, text="BUY Options Contracts")
        paned_window.add(buy_frame, weight=1)
        
        # SELL Frame
        sell_frame = ttk.LabelFrame(paned_window, text="SELL Options Contracts")
        paned_window.add(sell_frame, weight=1)
        
        # BUY prices
        buy_price_labels = {}
        for symbol in buy_symbols:
            symbol_frame = ttk.Frame(buy_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            buy_price_labels[symbol] = price_label
        
        # SELL prices
        sell_price_labels = {}
        for symbol in sell_symbols:
            symbol_frame = ttk.Frame(sell_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            sell_price_labels[symbol] = price_label
        
        # Order info
        info_frame = ttk.LabelFrame(main_frame, text="Options Order Summary")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"BUY: {len(buy_symbols)} contracts | SELL: {len(sell_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='blue').pack(pady=2)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_options_buy_sell_orders_with_current_prices,
                args=(
                    buy_order_type, buy_quantity_type, buy_quantity, buy_price,
                    sell_order_type, sell_quantity_type, sell_quantity, sell_price
                ),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_options_message("Options BUY/SELL order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place BUY & SELL Options Orders", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        # Start price updates
        self.update_options_buy_sell_price_display(buy_price_labels, sell_price_labels, price_window)
    
    def update_options_buy_sell_price_display(self, buy_labels, sell_labels, window):
        """Update BUY and SELL price labels for options"""
        if not window.winfo_exists():
            return
        
        try:
            # Update BUY prices
            for symbol, label in buy_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            
            # Update SELL prices
            for symbol, label in sell_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
                    
        except Exception as e:
            print(f"Error updating options buy/sell price display: {e}")
        
        # Schedule next update
        if window.winfo_exists():
            window.after(1000, lambda: self.update_options_buy_sell_price_display(buy_labels, sell_labels, window))
    
    # Data Refresh Methods
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
    
    def start_options_live_data(self):
        """Start live data updates for options table"""
        if not self.is_logged_in:
            return
        
        self.options_data_running = True
        threading.Thread(target=self.update_options_live_data, daemon=True).start()
        self.log_options_message("Started live prices for options table")
    
    def stop_options_live_data(self):
        """Stop live data updates for options table"""
        self.options_data_running = False
        self.log_options_message("Stopped live prices for options table")
    
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
                
                # Get LTP data in batches to avoid API limits
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        
                        # Update table with live data using thread-safe method
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("MCX:", "")
                            
                            # Create a function to update the specific item
                            def update_item(symbol=symbol, data=data):
                                try:
                                    # Find the item in the tree
                                    for item in self.futures_tree.get_children():
                                        item_values = self.futures_tree.item(item, 'values')
                                        if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                            # Calculate change percentage
                                            ltp = data['last_price']
                                            change = data.get('net_change', 0)
                                            change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                            volume = data.get('volume', 0)
                                            
                                            # Update the row
                                            new_values = (
                                                item_values[0],  # Keep symbol
                                                item_values[1],  # Keep name
                                                item_values[2],  # Keep expiry
                                                item_values[3],  # Keep lot size
                                                f"{ltp:.2f}",
                                                f"{change_percent:+.2f}%",
                                                f"{volume:,}"
                                            )
                                            self.futures_tree.item(item, values=new_values)
                                            break
                                except Exception as e:
                                    # Silently fail for individual items to not break the whole update
                                    pass
                            
                            # Schedule the update in the main thread
                            if self.root.winfo_exists():
                                self.root.after(0, update_item)
                    
                    except Exception as e:
                        self.log_futures_message(f"Error updating futures batch {i//batch_size + 1}: {e}")
                
                time.sleep(3)  # Update every 3 seconds
                
            except Exception as e:
                self.log_futures_message(f"Error in futures live data update: {e}")
                time.sleep(10)
    
    def update_options_live_data(self):
        """Update live data for options table"""
        while self.options_data_running and self.is_logged_in:
            try:
                # Get all symbols from the table
                symbols = []
                for item in self.options_tree.get_children():
                    values = self.options_tree.item(item, 'values')
                    if values and len(values) > 0:
                        symbols.append(values[0])  # Symbol is at index 0
                
                if not symbols:
                    time.sleep(5)
                    continue
                
                # Prepare instrument list
                instruments = [f"MCX:{symbol}" for symbol in symbols]
                
                # Get LTP data in batches to avoid API limits
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        
                        # Update table with live data
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("MCX:", "")
                            
                            # Find the item in the tree
                            for item in self.options_tree.get_children():
                                item_values = self.options_tree.item(item, 'values')
                                if item_values and len(item_values) > 0 and item_values[0] == symbol:
                                    # Calculate change percentage
                                    ltp = data['last_price']
                                    change = data.get('net_change', 0)
                                    change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                    volume = data.get('volume', 0)
                                    
                                    # Update the row (keep existing values for other columns)
                                    new_values = (
                                        item_values[0],  # Symbol
                                        item_values[1],  # Name
                                        item_values[2],  # Expiry
                                        item_values[3],  # Strike
                                        item_values[4],  # Type
                                        item_values[5],  # Lot Size
                                        f"{ltp:.2f}",
                                        f"{change_percent:+.2f}%",
                                        f"{volume:,}"
                                    )
                                    # Schedule the update in the main thread
                                    def update_item(item=item, new_values=new_values):
                                        try:
                                            self.options_tree.item(item, values=new_values)
                                        except:
                                            pass
                                    
                                    if self.root.winfo_exists():
                                        self.root.after(0, update_item)
                                    break
                    
                    except Exception as e:
                        self.log_options_message(f"Error updating options batch: {e}")
                
                time.sleep(3)
                
            except Exception as e:
                self.log_options_message(f"Error in options live data update: {e}")
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
        
        # Start protection status updates
        threading.Thread(target=self.update_protection_status_loop, daemon=True).start()
        

        # Start exit positions updates
        threading.Thread(target=self.update_exit_positions_loop, daemon=True).start()
        # Auto-refresh tables after login
        if self.is_logged_in:
            self.root.after(2000, self.refresh_futures_table)  # Refresh futures after 2 seconds
            self.root.after(3000, self.refresh_options_table_month)  # Refresh options after 3 seconds
            self.root.after(4000, self.refresh_exit_positions)  # Refresh exit positions after 4 seconds
    
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
            self.daily_pnl = day_pnl  # Update for protection checks
            
            def update_gui():
                self.total_pnl_label.config(text=f"Total P&L: ₹{total_pnl:.2f}")
                self.day_pnl_label.config(text=f"Day P&L: ₹{day_pnl:.2f}")
                self.realized_pnl_label.config(text=f"Realized P&L: ₹{realized_pnl:.2f}")
                
                # Update color based on P&L
                color = 'green' if total_pnl >= 0 else 'red'
                self.total_pnl_label.config(foreground=color)
            
            self.root.after(1000, update_gui)
            
        except Exception as e:
            self.log_message(f"Error updating P&L: {e}")
    
    def update_protection_status_loop(self):
        """Continuously update protection status"""
        while self.is_logged_in:
            try:
                self.update_protection_status()
                time.sleep(15)  # Update every 15 seconds
            except Exception as e:
                self.log_message(f"Error updating protection status: {e}")
                time.sleep(30)
    
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
        """Thread-safe logging method"""
        def update_log():
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.market_data_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.market_data_text.see(tk.END)
            except Exception as e:
                print(f"Log error: {e}")
        
        # Schedule the update in the main thread
        try:
            if self.root.winfo_exists():
                self.root.after(0, update_log)
        except:
            pass

    def log_futures_message(self, message):
        """Thread-safe futures logging method"""
        def update_log():
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.futures_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.futures_orders_text.see(tk.END)
            except Exception as e:
                print(f"Futures log error: {e}")
        
        try:
            if self.root.winfo_exists():
                self.root.after(0, update_log)
        except:
            pass

    def log_options_message(self, message):
        """Thread-safe options logging method"""
        def update_log():
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.options_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.options_orders_text.see(tk.END)
            except Exception as e:
                print(f"Options log error: {e}")
        
        try:
            if self.root.winfo_exists():
                self.root.after(0, update_log)
        except:
            pass

    def get_options_by_month(self, base_symbol, target_month=None, target_year=None):
        """Get options contracts for a specific month"""
        try:
            if self.instruments_df is None:
                self.load_instruments()
                if self.instruments_df is None:
                    return []
            
            # Use current month/year if not specified
            if target_month is None:
                target_month = datetime.now().month
            if target_year is None:
                target_year = datetime.now().year
            
            # Filter options for the base symbol
            options_df = self.instruments_df[
                (self.instruments_df['tradingsymbol'].str.startswith(base_symbol)) &
                ((self.instruments_df['instrument_type'] == 'CE') | 
                (self.instruments_df['instrument_type'] == 'PE'))
            ].copy()
            
            if options_df.empty:
                # Try alternative naming
                options_df = self.instruments_df[
                    (self.instruments_df['name'].str.contains(base_symbol, na=False)) &
                    ((self.instruments_df['instrument_type'] == 'CE') | 
                    (self.instruments_df['instrument_type'] == 'PE'))
                ].copy()
            
            self.log_message(f"Found {len(options_df)} raw options for {base_symbol}")
            
            if options_df.empty:
                self.log_message(f"No options found for {base_symbol}")
                return []
            
            # Ensure expiry is datetime
            if 'expiry' in options_df.columns:
                if options_df['expiry'].dtype == 'object':
                    options_df['expiry'] = pd.to_datetime(options_df['expiry'])
                
                # Extract month and year from expiry
                options_df['expiry_month'] = options_df['expiry'].dt.month
                options_df['expiry_year'] = options_df['expiry'].dt.year
                
                # Filter for target month and year
                month_options = options_df[
                    (options_df['expiry_month'] == target_month) &
                    (options_df['expiry_year'] == target_year)
                ]
                
                self.log_message(f"Found {len(month_options)} options for {base_symbol} in {target_month}/{target_year}")
                
                if month_options.empty:
                    return []
                
                # Sort by strike price and option type
                month_options = month_options.sort_values(['strike', 'instrument_type'])
                
                return month_options[['tradingsymbol', 'name', 'expiry', 'strike', 'instrument_type', 'lot_size']].to_dict('records')
            else:
                return []
            
        except Exception as e:
            self.log_message(f"Error getting options by month for {base_symbol}: {str(e)}")
            return []

    def get_month_contracts(self, base_symbol, month_str):
        """Get contracts for a specific month string (e.g., "Jan '25")"""
        try:
            if not month_str:
                return []
            
            # Parse month string
            parts = month_str.split()
            if len(parts) < 2:
                self.log_message(f"Invalid month format: {month_str}")
                return []
            
            month_part = parts[0]
            year_part = parts[1]
            
            # Convert to month number
            month_dict = {
                'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
            }
            
            if month_part not in month_dict:
                self.log_message(f"Invalid month: {month_part}")
                return []
            
            target_month = month_dict[month_part]
            
            # Parse year (handle '25 format)
            year_part = year_part.replace("'", "")
            if len(year_part) == 2:
                target_year = 2000 + int(year_part)
            else:
                target_year = int(year_part)
            
            # Get options for this month
            options = self.get_options_by_month(base_symbol, target_month, target_year)
            
            return options
            
        except Exception as e:
            self.log_message(f"Error getting month contracts: {e}")
            return []
        

    def on_underlying_changed(self, event=None):
        """Update month selection when underlying changes"""
        try:
            if not self.is_logged_in:
                # If not logged in, clear the month dropdown
                self.options_month_combo['values'] = []
                self.options_month_combo.set("")
                return
            
            underlying = self.options_underlying_var.get()
            
            if not underlying:
                return
            
            # Get available expiry months for this underlying
            available_months = self.get_available_months(underlying)
            
            if available_months:
                self.options_month_combo['values'] = available_months
                self.options_month_combo.set(available_months[0])
                
                self.log_options_message(f"Loaded {len(available_months)} expiry months for {underlying}")
            else:
                self.options_month_combo['values'] = []
                self.options_month_combo.set("")
                self.log_options_message(f"No expiry months found for {underlying}. The contract might be expired or not available.")
                
        except Exception as e:
            self.log_options_message(f"Error updating month selection: {e}")
    
    def refresh_options_table_month(self):
        """Refresh options table with month-based filtering"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            underlying = self.options_underlying_var.get()
            month_str = self.options_month_var.get()
            option_type = self.options_type_var.get()
            
            if not month_str:
                messagebox.showwarning("Warning", "Please select an expiry month")
                return
            
            # Debug: Print what we're looking for
            self.log_options_message(f"Loading options for {underlying} - {month_str} ({option_type})")
            
            # Get options for selected month
            options_data = self.get_month_contracts(underlying, month_str)
            
            if not options_data:
                # Try to find the nearest available month
                available_months = self.get_available_months(underlying)
                if available_months:
                    messagebox.showinfo("Info", 
                                    f"No options found for {underlying} - {month_str}\n\n"
                                    f"Available months for {underlying}:\n" + 
                                    "\n".join(available_months))
                else:
                    messagebox.showinfo("Info", 
                                    f"No options found for {underlying} - {month_str}\n"
                                    f"No expiry months available for {underlying}")
                return
            
            # Clear existing data
            for item in self.options_tree.get_children():
                self.options_tree.delete(item)
            
            # Apply type filter
            if option_type != "ALL":
                options_data = [opt for opt in options_data if opt['instrument_type'] == option_type]
            
            # Apply strike filter
            try:
                min_strike = float(self.min_strike_var.get())
                max_strike = float(self.max_strike_var.get())
                options_data = [opt for opt in options_data if min_strike <= opt['strike'] <= max_strike]
            except:
                pass  # Ignore filter if values are invalid
            
            if not options_data:
                messagebox.showinfo("Info", f"No options match the filter criteria for {underlying} - {month_str}")
                return
            
            # Add options to table
            for option in options_data:
                expiry_str = option['expiry'].strftime('%d-%b-%Y') if hasattr(option['expiry'], 'strftime') else str(option['expiry'])
                self.options_tree.insert('', 'end', values=(
                    option['tradingsymbol'],
                    option['name'],
                    expiry_str,
                    option['strike'],
                    option['instrument_type'],
                    option['lot_size'],
                    'Loading...',  # LTP
                    'Loading...',  # Change %
                    'Loading...',  # Volume
                    'Loading...'   # OI
                ))
            
            self.log_options_message(f"Loaded {len(options_data)} {option_type} options for {underlying} - {month_str}")
            
            # Color code by option type
            for item in self.options_tree.get_children():
                values = self.options_tree.item(item, 'values')
                if len(values) > 4:
                    if values[4] == 'CE':
                        self.options_tree.tag_configure('CE', foreground='green')
                        self.options_tree.item(item, tags=('CE',))
                    elif values[4] == 'PE':
                        self.options_tree.tag_configure('PE', foreground='red')
                        self.options_tree.item(item, tags=('PE',))
            
            # Start live data if not already running
            if not self.options_data_running:
                self.start_options_live_data()
            
        except Exception as e:
            self.log_options_message(f"Error refreshing options table: {e}")
            messagebox.showerror("Error", f"Failed to load options: {e}")
    
    def apply_strike_filter(self):
        """Apply strike price filter to options table"""
        self.refresh_options_table_month()


    def on_strategy_underlying_changed(self, event=None):
        """Update month selection when strategy underlying changes"""
        try:
            if not self.is_logged_in:
                self.strategy_month_combo['values'] = []
                self.strategy_month_combo.set("")
                return
            
            underlying = self.strategy_underlying_var.get()
            
            if not underlying:
                return
            
            available_months = self.get_available_months(underlying)
            
            if available_months:
                self.strategy_month_combo['values'] = available_months
                self.strategy_month_combo.set(available_months[0])
            else:
                self.strategy_month_combo['values'] = []
                self.strategy_month_combo.set("")
                
        except Exception as e:
            self.log_options_message(f"Error updating strategy month selection: {e}")

    def debug_month_dropdown(self):
        """Debug method to check month dropdown"""
        print(f"Logged in: {self.is_logged_in}")
        print(f"Instruments loaded: {self.instruments_df is not None}")
        print(f"Underlying: {self.options_underlying_var.get()}")
        print(f"Month values: {self.options_month_combo['values']}")
        print(f"Current month selection: {self.options_month_combo.get()}")


    # ===== NEW: CE/PE OPTIONS TAB =====
    def setup_ce_pe_options_tab(self, notebook):
        """Setup CE/PE Options tab with side-by-side display"""
        cepe_frame = ttk.Frame(notebook)
        notebook.add(cepe_frame, text="CE/PE Options")
        
        # Main container
        main_container = ttk.Frame(cepe_frame)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Top control frame
        control_frame = ttk.LabelFrame(main_container, text="Options Selection Controls")
        control_frame.pack(fill='x', padx=5, pady=5)
        
        # Underlying selection
        ttk.Label(control_frame, text="Underlying:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.cepe_underlying_var = tk.StringVar()
        self.cepe_underlying_combo = ttk.Combobox(control_frame, textvariable=self.cepe_underlying_var,
                                                values=["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "LEAD", "ZINC", "ALUMINIUM"])
        self.cepe_underlying_combo.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.cepe_underlying_combo.set("NATURALGAS")
        self.cepe_underlying_combo.bind('<<ComboboxSelected>>', self.on_cepe_underlying_changed)
        
        # Month selection
        ttk.Label(control_frame, text="Expiry Month:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.cepe_month_var = tk.StringVar()
        self.cepe_month_combo = ttk.Combobox(control_frame, textvariable=self.cepe_month_var, width=12)
        self.cepe_month_combo.grid(row=0, column=3, padx=5, pady=5, sticky='ew')
        
        # Strike range filter
        ttk.Label(control_frame, text="Strike Range:").grid(row=0, column=4, padx=5, pady=5, sticky='w')
        
        ttk.Label(control_frame, text="From:").grid(row=0, column=5, padx=2, pady=5, sticky='w')
        self.cepe_min_strike_var = tk.StringVar(value="0")
        ttk.Entry(control_frame, textvariable=self.cepe_min_strike_var, width=8).grid(row=0, column=6, padx=2, pady=5, sticky='ew')
        
        ttk.Label(control_frame, text="To:").grid(row=0, column=7, padx=2, pady=5, sticky='w')
        self.cepe_max_strike_var = tk.StringVar(value="100000")
        ttk.Entry(control_frame, textvariable=self.cepe_max_strike_var, width=8).grid(row=0, column=8, padx=2, pady=5, sticky='ew')
        
        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=0, column=9, padx=10, pady=5, sticky='ew')
        
        ttk.Button(button_frame, text="Load Options", 
                  command=self.refresh_ce_pe_tables).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Start Live", 
                  command=self.start_ce_pe_live_data).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Stop Live", 
                  command=self.stop_ce_pe_live_data).pack(side='left', padx=2)
        ttk.Button(button_frame, text="Clear All", 
                  command=self.clear_ce_pe_selections).pack(side='left', padx=2)
        
        # CE/PE tables frame (side by side)
        tables_frame = ttk.Frame(main_container)
        tables_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create paned window for CE/PE tables
        paned_window = ttk.PanedWindow(tables_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True)
        
        # CE Options Frame (Left side)
        ce_frame = ttk.LabelFrame(paned_window, text="CALL OPTIONS (CE)")
        paned_window.add(ce_frame, weight=1)
        
        # CE table controls
        ce_control_frame = ttk.Frame(ce_frame)
        ce_control_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(ce_control_frame, text="Select All CE", 
                  command=lambda: self.select_all_in_tree('ce')).pack(side='left', padx=2)
        ttk.Button(ce_control_frame, text="Clear CE Selection", 
                  command=lambda: self.clear_selection('ce')).pack(side='left', padx=2)
        ttk.Button(ce_control_frame, text="Place CE Order", 
                  command=self.place_ce_single_order).pack(side='left', padx=2)
        
        # CE table
        ce_table_frame = ttk.Frame(ce_frame)
        ce_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        ce_tree_scroll = ttk.Scrollbar(ce_table_frame)
        ce_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.ce_tree = ttk.Treeview(ce_table_frame, columns=(
            'Select', 'Symbol', 'Strike', 'LTP', 'Change', 'Volume', 'OI', 'Lot'
        ), show='headings', yscrollcommand=ce_tree_scroll.set, height=15)
        
        ce_tree_scroll.config(command=self.ce_tree.yview)
        
        columns_ce = {
            'Select': ('✓', 40),
            'Symbol': ('Symbol', 120),
            'Strike': ('Strike', 80),
            'LTP': ('LTP', 90),
            'Change': ('Change %', 80),
            'Volume': ('Volume', 80),
            'OI': ('OI', 80),
            'Lot': ('Lot Size', 70)
        }
        
        for col, (text, width) in columns_ce.items():
            self.ce_tree.heading(col, text=text)
            self.ce_tree.column(col, width=width, anchor='center')
        
        self.ce_tree.pack(fill='both', expand=True)
        
        # Bind click event for CE tree
        self.ce_tree.bind('<Button-1>', lambda e: self.on_cepe_tree_click(e, 'ce'))
        
        # PE Options Frame (Right side)
        pe_frame = ttk.LabelFrame(paned_window, text="PUT OPTIONS (PE)")
        paned_window.add(pe_frame, weight=1)
        
        # PE table controls
        pe_control_frame = ttk.Frame(pe_frame)
        pe_control_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(pe_control_frame, text="Select All PE", 
                  command=lambda: self.select_all_in_tree('pe')).pack(side='left', padx=2)
        ttk.Button(pe_control_frame, text="Clear PE Selection", 
                  command=lambda: self.clear_selection('pe')).pack(side='left', padx=2)
        ttk.Button(pe_control_frame, text="Place PE Order", 
                  command=self.place_pe_single_order).pack(side='left', padx=2)
        
        # PE table
        pe_table_frame = ttk.Frame(pe_frame)
        pe_table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        pe_tree_scroll = ttk.Scrollbar(pe_table_frame)
        pe_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.pe_tree = ttk.Treeview(pe_table_frame, columns=(
            'Select', 'Symbol', 'Strike', 'LTP', 'Change', 'Volume', 'OI', 'Lot'
        ), show='headings', yscrollcommand=pe_tree_scroll.set, height=15)
        
        pe_tree_scroll.config(command=self.pe_tree.yview)
        
        columns_pe = {
            'Select': ('✓', 40),
            'Symbol': ('Symbol', 120),
            'Strike': ('Strike', 80),
            'LTP': ('LTP', 90),
            'Change': ('Change %', 80),
            'Volume': ('Volume', 80),
            'OI': ('OI', 80),
            'Lot': ('Lot Size', 70)
        }
        
        for col, (text, width) in columns_pe.items():
            self.pe_tree.heading(col, text=text)
            self.pe_tree.column(col, width=width, anchor='center')
        
        self.pe_tree.pack(fill='both', expand=True)
        
        # Bind click event for PE tree
        self.pe_tree.bind('<Button-1>', lambda e: self.on_cepe_tree_click(e, 'pe'))
        
        # Order placement frame (bottom)
        order_frame = ttk.LabelFrame(main_container, text="CE/PE Order Placement")
        order_frame.pack(fill='x', padx=5, pady=5)
        
        # Order parameters
        params_frame = ttk.Frame(order_frame)
        params_frame.pack(fill='x', padx=5, pady=5)
        
        # Transaction type
        ttk.Label(params_frame, text="Transaction Type:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.cepe_transaction_type = ttk.Combobox(params_frame, values=["BUY", "SELL"], width=8)
        self.cepe_transaction_type.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.cepe_transaction_type.set("BUY")
        
        # Order type
        ttk.Label(params_frame, text="Order Type:").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.cepe_order_type = ttk.Combobox(params_frame, values=["MARKET", "LIMIT"], width=8)
        self.cepe_order_type.grid(row=0, column=3, padx=5, pady=5, sticky='ew')
        self.cepe_order_type.set("MARKET")
        
        # Quantity type
        ttk.Label(params_frame, text="Quantity Type:").grid(row=0, column=4, padx=5, pady=5, sticky='w')
        self.cepe_quantity_type = ttk.Combobox(params_frame, values=["Fixed Quantity", "Lot Size"], width=12)
        self.cepe_quantity_type.grid(row=0, column=5, padx=5, pady=5, sticky='ew')
        self.cepe_quantity_type.set("Lot Size")
        
        # Quantity
        ttk.Label(params_frame, text="Quantity:").grid(row=0, column=6, padx=5, pady=5, sticky='w')
        self.cepe_quantity_entry = ttk.Entry(params_frame, width=8)
        self.cepe_quantity_entry.grid(row=0, column=7, padx=5, pady=5, sticky='ew')
        self.cepe_quantity_entry.insert(0, "1")
        
        # Price (for limit orders)
        ttk.Label(params_frame, text="Price (LIMIT):").grid(row=0, column=8, padx=5, pady=5, sticky='w')
        self.cepe_price_entry = ttk.Entry(params_frame, width=8)
        self.cepe_price_entry.grid(row=0, column=9, padx=5, pady=5, sticky='ew')
        self.cepe_price_entry.insert(0, "0")
        
        # Order buttons
        button_frame2 = ttk.Frame(order_frame)
        button_frame2.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(button_frame2, text="Place CE Order with Real-time Prices", 
                  command=self.place_ce_single_order).pack(side='left', padx=2)
        ttk.Button(button_frame2, text="Place PE Order with Real-time Prices", 
                  command=self.place_pe_single_order).pack(side='left', padx=2)
        ttk.Button(button_frame2, text="Place CE & PE Together", 
                  command=self.place_ce_pe_together).pack(side='left', padx=2)
        ttk.Button(button_frame2, text="Validate Selection", 
                  command=self.validate_ce_pe_selection).pack(side='left', padx=2)
        
        # Selection display
        selection_frame = ttk.LabelFrame(main_container, text="Selected Contracts")
        selection_frame.pack(fill='x', padx=5, pady=5)
        
        # Create paned window for CE/PE selection display
        selection_paned = ttk.PanedWindow(selection_frame, orient=tk.HORIZONTAL)
        selection_paned.pack(fill='both', expand=True, padx=5, pady=5)
        
        # CE selection display
        ce_selection_frame = ttk.Frame(selection_paned)
        selection_paned.add(ce_selection_frame, weight=1)
        
        ttk.Label(ce_selection_frame, text="Selected CE Contracts:").pack(anchor='w', padx=5, pady=2)
        self.ce_selection_text = scrolledtext.ScrolledText(ce_selection_frame, height=6)
        self.ce_selection_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.ce_selection_text.insert(tk.END, "No CE contracts selected")
        
        # PE selection display
        pe_selection_frame = ttk.Frame(selection_paned)
        selection_paned.add(pe_selection_frame, weight=1)
        
        ttk.Label(pe_selection_frame, text="Selected PE Contracts:").pack(anchor='w', padx=5, pady=2)
        self.pe_selection_text = scrolledtext.ScrolledText(pe_selection_frame, height=6)
        self.pe_selection_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.pe_selection_text.insert(tk.END, "No PE contracts selected")
        
        # Orders log
        log_frame = ttk.LabelFrame(main_container, text="CE/PE Orders Log")
        log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.cepe_orders_text = scrolledtext.ScrolledText(log_frame, height=10)
        self.cepe_orders_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Initialize month selection
        self.on_cepe_underlying_changed()

    def on_cepe_underlying_changed(self, event=None):
        """Update month selection when CE/PE underlying changes"""
        try:
            if not self.is_logged_in:
                self.cepe_month_combo['values'] = []
                self.cepe_month_combo.set("")
                return
            
            underlying = self.cepe_underlying_var.get()
            
            if not underlying:
                return
            
            available_months = self.get_available_months(underlying)
            
            if available_months:
                self.cepe_month_combo['values'] = available_months
                self.cepe_month_combo.set(available_months[0])
                self.log_cepe_message(f"Loaded {len(available_months)} expiry months for {underlying}")
            else:
                self.cepe_month_combo['values'] = []
                self.cepe_month_combo.set("")
                self.log_cepe_message(f"No expiry months found for {underlying}")
                
        except Exception as e:
            self.log_cepe_message(f"Error updating CE/PE month selection: {e}")
    
    def refresh_ce_pe_tables(self):
        """Refresh CE and PE tables with month-based filtering"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            underlying = self.cepe_underlying_var.get()
            month_str = self.cepe_month_var.get()
            
            if not month_str:
                messagebox.showwarning("Warning", "Please select an expiry month")
                return
            
            self.log_cepe_message(f"Loading options for {underlying} - {month_str}")
            
            # Get options for selected month
            options_data = self.get_month_contracts(underlying, month_str)
            
            if not options_data:
                messagebox.showinfo("Info", f"No options found for {underlying} - {month_str}")
                return
            
            # Clear existing data
            for item in self.ce_tree.get_children():
                self.ce_tree.delete(item)
            for item in self.pe_tree.get_children():
                self.pe_tree.delete(item)
            
            # Apply strike filter
            try:
                min_strike = float(self.cepe_min_strike_var.get())
                max_strike = float(self.cepe_max_strike_var.get())
                filtered_data = [opt for opt in options_data if min_strike <= opt['strike'] <= max_strike]
            except:
                filtered_data = options_data
            
            # Separate CE and PE options
            ce_options = [opt for opt in filtered_data if opt['instrument_type'] == 'CE']
            pe_options = [opt for opt in filtered_data if opt['instrument_type'] == 'PE']
            
            # Add CE options to table
            for option in ce_options:
                expiry_str = option['expiry'].strftime('%d-%b-%Y') if hasattr(option['expiry'], 'strftime') else str(option['expiry'])
                self.ce_tree.insert('', 'end', values=(
                    '□',  # Select checkbox
                    option['tradingsymbol'],
                    option['strike'],
                    'Loading...',  # LTP
                    'Loading...',  # Change %
                    'Loading...',  # Volume
                    'Loading...',  # OI
                    option['lot_size']
                ))
            
            # Add PE options to table
            for option in pe_options:
                expiry_str = option['expiry'].strftime('%d-%b-%Y') if hasattr(option['expiry'], 'strftime') else str(option['expiry'])
                self.pe_tree.insert('', 'end', values=(
                    '□',  # Select checkbox
                    option['tradingsymbol'],
                    option['strike'],
                    'Loading...',  # LTP
                    'Loading...',  # Change %
                    'Loading...',  # Volume
                    'Loading...',  # OI
                    option['lot_size']
                ))
            
            self.log_cepe_message(f"Loaded {len(ce_options)} CE and {len(pe_options)} PE options for {underlying} - {month_str}")
            
            # Start live data if not already running
            if not self.ce_pe_data_running:
                self.start_ce_pe_live_data()
            
        except Exception as e:
            self.log_cepe_message(f"Error refreshing CE/PE tables: {e}")
            messagebox.showerror("Error", f"Failed to load options: {e}")

    def on_cepe_tree_click(self, event, tree_type):
        """Handle click events on CE/PE treeviews"""
        if tree_type == 'ce':
            tree = self.ce_tree
            selection_dict = self.selected_ce_options
            selection_text = self.ce_selection_text
        else:
            tree = self.pe_tree
            selection_dict = self.selected_pe_options
            selection_text = self.pe_selection_text
        
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        
        if item and column == '#1':  # Clicked on select column
            values = tree.item(item, 'values')
            symbol = values[1]
            
            if symbol in selection_dict:
                # Deselect
                tree.set(item, 'Select', '□')
                del selection_dict[symbol]
                self.log_cepe_message(f"Deselected {symbol}")
            else:
                # Select
                tree.set(item, 'Select', '✓')
                selection_dict[symbol] = {
                    'symbol': symbol,
                    'strike': values[2],
                    'lot_size': values[7],
                    'ltp': values[3] if values[3] != 'Loading...' else 'N/A'
                }
                self.log_cepe_message(f"Selected {symbol}")
            
            # Update selection display
            self.update_cepe_selection_display()

    def select_all_in_tree(self, tree_type):
        """Select all contracts in CE or PE tree"""
        if tree_type == 'ce':
            tree = self.ce_tree
            selection_dict = self.selected_ce_options
        else:
            tree = self.pe_tree
            selection_dict = self.selected_pe_options
        
        for item in tree.get_children():
            values = tree.item(item, 'values')
            symbol = values[1]
            
            tree.set(item, 'Select', '✓')
            selection_dict[symbol] = {
                'symbol': symbol,
                'strike': values[2],
                'lot_size': values[7],
                'ltp': values[3] if values[3] != 'Loading...' else 'N/A'
            }
        
        self.update_cepe_selection_display()
        self.log_cepe_message(f"Selected all {tree_type.upper()} contracts")

    def clear_selection(self, tree_type):
        """Clear selection for CE or PE"""
        if tree_type == 'ce':
            tree = self.ce_tree
            selection_dict = self.selected_ce_options
        else:
            tree = self.pe_tree
            selection_dict = self.selected_pe_options
        
        for item in tree.get_children():
            tree.set(item, 'Select', '□')
        
        selection_dict.clear()
        self.update_cepe_selection_display()
        self.log_cepe_message(f"Cleared {tree_type.upper()} selection")


    def clear_ce_pe_selections(self):
        """Clear all CE and PE selections"""
        self.clear_selection('ce')
        self.clear_selection('pe')
        self.selected_cepe_pair.clear()
        self.log_cepe_message("Cleared all CE/PE selections")

    
    def update_cepe_selection_display(self):
        """Update CE and PE selection display text areas"""
        # Update CE selection display
        self.ce_selection_text.delete(1.0, tk.END)
        if not self.selected_ce_options:
            self.ce_selection_text.insert(tk.END, "No CE contracts selected")
        else:
            for symbol, details in self.selected_ce_options.items():
                self.ce_selection_text.insert(tk.END, 
                    f"Symbol: {symbol}\n"
                    f"Strike: {details['strike']}\n"
                    f"Lot Size: {details['lot_size']}\n"
                    f"LTP: {details.get('ltp', 'N/A')}\n"
                    f"{'-'*30}\n"
                )
        
        # Update PE selection display
        self.pe_selection_text.delete(1.0, tk.END)
        if not self.selected_pe_options:
            self.pe_selection_text.insert(tk.END, "No PE contracts selected")
        else:
            for symbol, details in self.selected_pe_options.items():
                self.pe_selection_text.insert(tk.END, 
                    f"Symbol: {symbol}\n"
                    f"Strike: {details['strike']}\n"
                    f"Lot Size: {details['lot_size']}\n"
                    f"LTP: {details.get('ltp', 'N/A')}\n"
                    f"{'-'*30}\n"
                )

    def validate_ce_pe_selection(self):
        """Validate CE/PE selection"""
        ce_count = len(self.selected_ce_options)
        pe_count = len(self.selected_pe_options)
        
        if ce_count == 0 and pe_count == 0:
            messagebox.showwarning("Warning", "No CE or PE contracts selected")
            return
        
        message = f"Selection Valid:\n"
        if ce_count > 0:
            message += f"- {ce_count} CE contract(s) selected\n"
        if pe_count > 0:
            message += f"- {pe_count} PE contract(s) selected\n"
        
        messagebox.showinfo("Selection Valid", message)

    def start_ce_pe_live_data(self):
        """Start live data updates for CE/PE tables"""
        if not self.is_logged_in:
            return
        
        self.ce_pe_data_running = True
        threading.Thread(target=self.update_ce_pe_live_data, daemon=True).start()
        self.log_cepe_message("Started live prices for CE/PE tables")

    def stop_ce_pe_live_data(self):
        """Stop live data updates for CE/PE tables"""
        self.ce_pe_data_running = False
        self.log_cepe_message("Stopped live prices for CE/PE tables")


    def update_ce_pe_live_data(self):
        """Update live data for CE/PE tables"""
        while self.ce_pe_data_running and self.is_logged_in:
            try:
                # Get all symbols from both tables
                symbols = []
                
                # Get CE symbols
                for item in self.ce_tree.get_children():
                    values = self.ce_tree.item(item, 'values')
                    if values and len(values) > 1:
                        symbols.append(values[1])
                
                # Get PE symbols
                for item in self.pe_tree.get_children():
                    values = self.pe_tree.item(item, 'values')
                    if values and len(values) > 1:
                        symbols.append(values[1])
                
                if not symbols:
                    time.sleep(5)
                    continue
                
                # Prepare instrument list
                instruments = [f"MCX:{symbol}" for symbol in symbols]
                
                # Get LTP data in batches
                batch_size = 50
                for i in range(0, len(instruments), batch_size):
                    batch = instruments[i:i + batch_size]
                    try:
                        ltp_data = self.kite.ltp(batch)
                        
                        # Update tables with live data
                        for instrument_key, data in ltp_data.items():
                            symbol = instrument_key.replace("MCX:", "")
                            
                            # Try CE table first
                            found = False
                            for item in self.ce_tree.get_children():
                                item_values = self.ce_tree.item(item, 'values')
                                if item_values and item_values[1] == symbol:
                                    # Calculate change percentage
                                    ltp = data['last_price']
                                    change = data.get('net_change', 0)
                                    change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                    volume = data.get('volume', 0)
                                    oi = data.get('oi', 0)
                                    
                                    # Update the row
                                    new_values = (
                                        item_values[0],  # Keep select status
                                        symbol,
                                        item_values[2],  # Keep strike
                                        f"{ltp:.2f}",
                                        f"{change_percent:+.2f}%",
                                        f"{volume:,}",
                                        f"{oi:,}",
                                        item_values[7]  # Keep lot size
                                    )
                                    self.ce_tree.item(item, values=new_values)
                                    
                                    # Update selection dictionary if selected
                                    if symbol in self.selected_ce_options:
                                        self.selected_ce_options[symbol]['ltp'] = f"{ltp:.2f}"
                                    
                                    found = True
                                    break
                            
                            # If not found in CE table, try PE table
                            if not found:
                                for item in self.pe_tree.get_children():
                                    item_values = self.pe_tree.item(item, 'values')
                                    if item_values and item_values[1] == symbol:
                                        # Calculate change percentage
                                        ltp = data['last_price']
                                        change = data.get('net_change', 0)
                                        change_percent = (change / (ltp - change)) * 100 if (ltp - change) != 0 else 0
                                        volume = data.get('volume', 0)
                                        oi = data.get('oi', 0)
                                        
                                        # Update the row
                                        new_values = (
                                            item_values[0],  # Keep select status
                                            symbol,
                                            item_values[2],  # Keep strike
                                            f"{ltp:.2f}",
                                            f"{change_percent:+.2f}%",
                                            f"{volume:,}",
                                            f"{oi:,}",
                                            item_values[7]  # Keep lot size
                                        )
                                        self.pe_tree.item(item, values=new_values)
                                        
                                        # Update selection dictionary if selected
                                        if symbol in self.selected_pe_options:
                                            self.selected_pe_options[symbol]['ltp'] = f"{ltp:.2f}"
                                        
                                        break
                    
                    except Exception as e:
                        self.log_cepe_message(f"Error updating CE/PE batch: {e}")
                
                # Update selection display with new prices
                self.update_cepe_selection_display()
                
                time.sleep(3)
                
            except Exception as e:
                self.log_cepe_message(f"Error in CE/PE live data update: {e}")
                time.sleep(10)

    def place_ce_single_order(self):
        """Place order for selected CE contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_ce_options:
            messagebox.showwarning("Warning", "No CE contracts selected")
            return
        
        try:
            transaction = self.cepe_transaction_type.get()
            order_type = self.cepe_order_type.get()
            quantity_type = self.cepe_quantity_type.get()
            base_quantity = int(self.cepe_quantity_entry.get())
            price = float(self.cepe_price_entry.get()) if self.cepe_price_entry.get() and float(self.cepe_price_entry.get()) > 0 else 0
            
            # Check protection
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Order blocked.")
                return
            
            # Get symbols for price updates
            symbols = list(self.selected_ce_options.keys())
            
            if not symbols:
                messagebox.showerror("Error", "No CE symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(symbols)
            
            # Show real-time price window
            self.show_ce_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_cepe_message(f"Error starting CE order placement: {e}")
    
    def place_pe_single_order(self):
        """Place order for selected PE contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_pe_options:
            messagebox.showwarning("Warning", "No PE contracts selected")
            return
        
        try:
            transaction = self.cepe_transaction_type.get()
            order_type = self.cepe_order_type.get()
            quantity_type = self.cepe_quantity_type.get()
            base_quantity = int(self.cepe_quantity_entry.get())
            price = float(self.cepe_price_entry.get()) if self.cepe_price_entry.get() and float(self.cepe_price_entry.get()) > 0 else 0
            
            # Check protection
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Order blocked.")
                return
            
            # Get symbols for price updates
            symbols = list(self.selected_pe_options.keys())
            
            if not symbols:
                messagebox.showerror("Error", "No PE symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(symbols)
            
            # Show real-time price window
            self.show_pe_real_time_price_window(symbols, transaction, order_type, quantity_type, base_quantity, price)
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_cepe_message(f"Error starting PE order placement: {e}")
    
    def place_ce_pe_together(self):
        """Place combined order for selected CE and PE contracts"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_ce_options and not self.selected_pe_options:
            messagebox.showwarning("Warning", "No CE or PE contracts selected")
            return
        
        try:
            transaction = self.cepe_transaction_type.get()
            order_type = self.cepe_order_type.get()
            quantity_type = self.cepe_quantity_type.get()
            base_quantity = int(self.cepe_quantity_entry.get())
            price = float(self.cepe_price_entry.get()) if self.cepe_price_entry.get() and float(self.cepe_price_entry.get()) > 0 else 0
            
            # Check protection
            self.update_daily_pnl()
            if (self.protection_settings['enable_loss_protection'] and 
                self.daily_pnl <= self.protection_settings['daily_loss_limit']):
                messagebox.showwarning("Loss Limit", 
                    f"Daily P&L ({self.daily_pnl:.2f}) is at or below loss limit. Order blocked.")
                return
            
            # Get symbols for price updates
            ce_symbols = list(self.selected_ce_options.keys())
            pe_symbols = list(self.selected_pe_options.keys())
            all_symbols = ce_symbols + pe_symbols
            
            if not all_symbols:
                messagebox.showerror("Error", "No symbols selected")
                return
            
            # Start real-time price updates
            self.start_price_updates_for_order(all_symbols)
            
            # Show real-time price window
            self.show_ce_pe_together_real_time_window(
                ce_symbols, pe_symbols, transaction, order_type, quantity_type, base_quantity, price
            )
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid quantity and price values")
        except Exception as e:
            self.log_cepe_message(f"Error starting CE/PE together order placement: {e}")
    
    def show_ce_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        """Show real-time price window for CE orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time CE Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time CE Prices (Updating every 1 second)", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="CE Order Information")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='green').pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_ce_single_orders_with_current_prices,
                args=(transaction, order_type, quantity_type, base_quantity, price),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_cepe_message("CE order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place CE Orders Now", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        self.update_ce_price_display(price_labels, price_window)
    
    def update_ce_price_display(self, price_labels, window):
        """Update price labels with current prices for CE"""
        if not window.winfo_exists():
            return
        
        try:
            for symbol, label in price_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating CE price display: {e}")
        
        if window.winfo_exists():
            window.after(1000, lambda: self.update_ce_price_display(price_labels, window))
    
    def show_pe_real_time_price_window(self, symbols, transaction, order_type, quantity_type, base_quantity, price):
        """Show real-time price window for PE orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time PE Prices - Confirm Order")
        price_window.geometry("600x400")
        price_window.transient(self.root)
        price_window.grab_set()
        
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time PE Prices (Updating every 1 second)", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        price_frame = ttk.Frame(main_frame)
        price_frame.pack(fill='both', expand=True, pady=10)
        
        price_labels = {}
        for i, symbol in enumerate(symbols):
            symbol_frame = ttk.Frame(price_frame)
            symbol_frame.pack(fill='x', pady=2)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=20, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 10, 'bold'))
            price_label.pack(side='left')
            price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="PE Order Information")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=5)
        ttk.Label(info_frame, text=f"Quantity: {base_quantity} ({quantity_type})").pack(pady=5)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='green').pack(pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_pe_single_orders_with_current_prices,
                args=(transaction, order_type, quantity_type, base_quantity, price),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_cepe_message("PE order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place PE Orders Now", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        self.update_pe_price_display(price_labels, price_window)
    
    def update_pe_price_display(self, price_labels, window):
        """Update price labels with current prices for PE"""
        if not window.winfo_exists():
            return
        
        try:
            for symbol, label in price_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
        except Exception as e:
            print(f"Error updating PE price display: {e}")
        
        if window.winfo_exists():
            window.after(1000, lambda: self.update_pe_price_display(price_labels, window))
    
    def show_ce_pe_together_real_time_window(self, ce_symbols, pe_symbols, transaction, order_type, quantity_type, base_quantity, price):
        """Show real-time price window for CE/PE together orders"""
        price_window = tk.Toplevel(self.root)
        price_window.title("Real-time CE & PE Prices - Confirm Combined Order")
        price_window.geometry("700x500")
        price_window.transient(self.root)
        price_window.grab_set()
        
        self.real_time_windows.append(price_window)
        
        main_frame = ttk.Frame(price_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        title_label = ttk.Label(main_frame, text="Real-time CE & PE Prices for Combined Order", 
                               font=('Arial', 12, 'bold'))
        title_label.pack(pady=10)
        
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill='both', expand=True, pady=10)
        
        ce_frame = ttk.LabelFrame(paned_window, text="CE Contracts")
        paned_window.add(ce_frame, weight=1)
        
        pe_frame = ttk.LabelFrame(paned_window, text="PE Contracts")
        paned_window.add(pe_frame, weight=1)
        
        ce_price_labels = {}
        for symbol in ce_symbols:
            symbol_frame = ttk.Frame(ce_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='green', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            ce_price_labels[symbol] = price_label
        
        pe_price_labels = {}
        for symbol in pe_symbols:
            symbol_frame = ttk.Frame(pe_frame)
            symbol_frame.pack(fill='x', pady=2, padx=5)
            
            ttk.Label(symbol_frame, text=f"{symbol}:", width=25, anchor='w').pack(side='left')
            price_label = ttk.Label(symbol_frame, text="Fetching...", foreground='red', font=('Arial', 9, 'bold'))
            price_label.pack(side='left')
            pe_price_labels[symbol] = price_label
        
        info_frame = ttk.LabelFrame(main_frame, text="CE/PE Order Summary")
        info_frame.pack(fill='x', pady=10)
        
        ttk.Label(info_frame, text=f"CE: {len(ce_symbols)} contracts | PE: {len(pe_symbols)} contracts").pack(pady=2)
        ttk.Label(info_frame, text=f"Transaction: {transaction} | Order Type: {order_type}").pack(pady=2)
        ttk.Label(info_frame, text="Prices update every 1 second. Place orders when ready.", 
                 foreground='blue').pack(pady=2)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=10)
        
        def place_orders_now():
            price_window.destroy()
            self.stop_price_updates()
            self.real_time_windows.remove(price_window)
            
            Thread(
                target=self.execute_ce_pe_together_orders_with_current_prices,
                args=(transaction, order_type, quantity_type, base_quantity, price),
                daemon=True
            ).start()
        
        def cancel_orders():
            price_window.destroy()
            self.stop_price_updates()
            if price_window in self.real_time_windows:
                self.real_time_windows.remove(price_window)
            self.log_cepe_message("CE/PE together order placement cancelled by user")
        
        ttk.Button(button_frame, text="Place CE & PE Orders Together", 
                  command=place_orders_now).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", 
                  command=cancel_orders).pack(side='left', padx=5)
        
        self.update_ce_pe_together_price_display(ce_price_labels, pe_price_labels, price_window)
    
    def update_ce_pe_together_price_display(self, ce_labels, pe_labels, window):
        """Update price labels for CE/PE together"""
        if not window.winfo_exists():
            return
        
        try:
            for symbol, label in ce_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='green')
                else:
                    label.config(text="Price unavailable", foreground='red')
            
            for symbol, label in pe_labels.items():
                current_price = self.current_prices.get(symbol)
                if current_price:
                    label.config(text=f"₹{current_price:.2f}", foreground='red')
                else:
                    label.config(text="Price unavailable", foreground='red')
                    
        except Exception as e:
            print(f"Error updating CE/PE together price display: {e}")
        
        if window.winfo_exists():
            window.after(1000, lambda: self.update_ce_pe_together_price_display(ce_labels, pe_labels, window))
    
    def execute_ce_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        """Execute CE single transaction orders using latest prices with protection"""
        orders_placed = 0
        total_orders = len(self.selected_ce_options)
        
        self.log_cepe_message(f"Starting to place {total_orders} {transaction} CE orders with real-time prices...")
        
        for symbol, details in self.selected_ce_options.items():
            try:
                # Calculate quantity for validation
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                
                # Safety check
                is_safe, safety_msg = self.validate_order_safety(symbol, quantity, transaction)
                if not is_safe:
                    self.log_cepe_message(f"❌ CE order blocked for {symbol}: {safety_msg}")
                    self.add_protection_alert("Order Blocked", safety_msg)
                    continue
                
                # Get the latest price
                current_price = self.current_prices.get(symbol)
                
                if not current_price:
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_cepe_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_cepe_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                
                # ===== UPDATED: AUTOMATIC LIMIT PRICE CALCULATION =====
                final_price = price
                if order_type == "LIMIT":
                    if price == 0 or not price:
                        final_price = self.calculate_limit_price(current_price, transaction, "CE")
                        self.log_cepe_message(f"Auto Limit CE: {symbol} {transaction} at {final_price:.2f} "
                                            f"(Current: {current_price:.2f}, Tol: {self.limit_price_settings['ce_' + transaction.lower() + '_tolerance']}%)")
                    else:
                        final_price = price
                # ======================================================
                
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
                self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                
                self.log_cepe_message(f"✅ {transaction} CE Order {orders_placed}/{total_orders}: "
                                    f"{symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                
                time.sleep(1)
                
            except Exception as e:
                self.log_cepe_message(f"❌ Failed to place {transaction} CE order for {symbol}: {e}")
                # Market fallback
                if self.limit_price_settings['use_market_fallback'] and order_type == "LIMIT":
                    try:
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange="MCX",
                            tradingsymbol=symbol,
                            transaction_type=transaction,
                            quantity=quantity,
                            order_type="MARKET",
                            product=self.kite.PRODUCT_NRML
                        )
                        self.log_cepe_message(f"⚠️ Market Fallback CE: {symbol} {transaction} {quantity} - ID: {order_id}")
                        orders_placed += 1
                    except:
                        pass
        
        self.log_cepe_message(f"{transaction} CE order placement completed: {orders_placed}/{total_orders} successful")
        self.update_protection_status()
        self.selected_ce_options.clear()
        self.update_cepe_selection_display()
        
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} CE orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", 
                                     f"{orders_placed} out of {total_orders} {transaction} CE orders placed successfully")
        
        self.root.after(0, show_summary)
    
    def execute_pe_single_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        """Execute PE single transaction orders using latest prices with protection"""
        orders_placed = 0
        total_orders = len(self.selected_pe_options)
        
        self.log_cepe_message(f"Starting to place {total_orders} {transaction} PE orders with real-time prices...")
        
        for symbol, details in self.selected_pe_options.items():
            try:
                # Calculate quantity for validation
                if quantity_type == "Lot Size":
                    lot_size = int(details['lot_size'])
                    quantity = base_quantity * lot_size
                else:
                    quantity = base_quantity
                
                # Safety check
                is_safe, safety_msg = self.validate_order_safety(symbol, quantity, transaction)
                if not is_safe:
                    self.log_cepe_message(f"❌ PE order blocked for {symbol}: {safety_msg}")
                    self.add_protection_alert("Order Blocked", safety_msg)
                    continue
                
                # Get the latest price
                current_price = self.current_prices.get(symbol)
                
                if not current_price:
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                        self.log_cepe_message(f"Fetched current LTP for {symbol}: {current_price}")
                    except:
                        self.log_cepe_message(f"❌ Could not fetch LTP for {symbol}, skipping...")
                        continue
                
                # ===== UPDATED: AUTOMATIC LIMIT PRICE CALCULATION =====
                final_price = price
                if order_type == "LIMIT":
                    if price == 0 or not price:
                        final_price = self.calculate_limit_price(current_price, transaction, "PE")
                        self.log_cepe_message(f"Auto Limit PE: {symbol} {transaction} at {final_price:.2f} "
                                            f"(Current: {current_price:.2f}, Tol: {self.limit_price_settings['pe_' + transaction.lower() + '_tolerance']}%)")
                    else:
                        final_price = price
                # ======================================================
                
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
                self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                
                self.log_cepe_message(f"✅ {transaction} PE Order {orders_placed}/{total_orders}: "
                                    f"{symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                
                time.sleep(1)
                
            except Exception as e:
                self.log_cepe_message(f"❌ Failed to place {transaction} PE order for {symbol}: {e}")
                # Market fallback
                if self.limit_price_settings['use_market_fallback'] and order_type == "LIMIT":
                    try:
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange="MCX",
                            tradingsymbol=symbol,
                            transaction_type=transaction,
                            quantity=quantity,
                            order_type="MARKET",
                            product=self.kite.PRODUCT_NRML
                        )
                        self.log_cepe_message(f"⚠️ Market Fallback PE: {symbol} {transaction} {quantity} - ID: {order_id}")
                        orders_placed += 1
                    except:
                        pass
        
        self.log_cepe_message(f"{transaction} PE order placement completed: {orders_placed}/{total_orders} successful")
        self.update_protection_status()
        self.selected_pe_options.clear()
        self.update_cepe_selection_display()
        
        def show_summary():
            if orders_placed == total_orders:
                messagebox.showinfo("Success", f"All {orders_placed} {transaction} PE orders placed successfully!")
            else:
                messagebox.showwarning("Partial Success", 
                                     f"{orders_placed} out of {total_orders} {transaction} PE orders placed successfully")
        
        self.root.after(0, show_summary)
    
    def execute_ce_pe_together_orders_with_current_prices(self, transaction, order_type, quantity_type, base_quantity, price):
        """Execute both CE and PE orders together using latest prices with protection"""
        total_ce_orders = len(self.selected_ce_options)
        total_pe_orders = len(self.selected_pe_options)
        ce_orders_placed = 0
        pe_orders_placed = 0
        
        self.log_cepe_message(f"Starting to place {total_ce_orders} CE and {total_pe_orders} PE orders together...")
        
        # Place CE orders
        if total_ce_orders > 0:
            self.log_cepe_message("=== PLACING CE ORDERS ===")
            for symbol, details in self.selected_ce_options.items():
                try:
                    # Calculate quantity for validation
                    if quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = base_quantity * lot_size
                    else:
                        quantity = base_quantity
                    
                    # Safety check
                    is_safe, safety_msg = self.validate_order_safety(symbol, quantity, transaction)
                    if not is_safe:
                        self.log_cepe_message(f"❌ CE order blocked for {symbol}: {safety_msg}")
                        self.add_protection_alert("Order Blocked", safety_msg)
                        continue
                    
                    # Get latest price
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_cepe_message(f"❌ Could not fetch LTP for CE {symbol}, skipping...")
                            continue
                    
                    
                    # Determine final price for CE
                    final_price = price
                    if order_type == "LIMIT":
                        if price == 0:
                            if transaction == "BUY":
                            
                                final_price = math.ceil(current_price / 0.5) * 0.5
                            else:
                                final_price =  math.floor(current_price / 0.5) * 0.5
                        self.log_cepe_message(f"CE Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    
                    # Place CE order
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
                    
                    ce_orders_placed += 1
                    self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                    self.log_cepe_message(f"✅ CE Order {ce_orders_placed}/{total_ce_orders}: {symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_cepe_message(f"❌ Failed to place CE order for {symbol}: {e}")
        
        # Place PE orders
        if total_pe_orders > 0:
            self.log_cepe_message("=== PLACING PE ORDERS ===")
            for symbol, details in self.selected_pe_options.items():
                try:
                    # Calculate quantity for validation
                    if quantity_type == "Lot Size":
                        lot_size = int(details['lot_size'])
                        quantity = base_quantity * lot_size
                    else:
                        quantity = base_quantity
                    
                    # Safety check
                    is_safe, safety_msg = self.validate_order_safety(symbol, quantity, transaction)
                    if not is_safe:
                        self.log_cepe_message(f"❌ PE order blocked for {symbol}: {safety_msg}")
                        self.add_protection_alert("Order Blocked", safety_msg)
                        continue
                    
                    # Get latest price
                    current_price = self.current_prices.get(symbol)
                    if not current_price:
                        try:
                            ltp_data = self.kite.ltp(f"MCX:{symbol}")
                            current_price = list(ltp_data.values())[0]['last_price']
                        except:
                            self.log_cepe_message(f"❌ Could not fetch LTP for PE {symbol}, skipping...")
                            continue
                    
                    # Determine final price for PE
                    final_price = price
                    if order_type == "LIMIT":
                        if price == 0:
                            if transaction == "BUY":
                                final_price = math.ceil(current_price / 0.5) * 0.5
                            else:
                                final_price = math.floor(current_price / 0.5) * 0.5
                            #final_price = current_price * 0.995
                        self.log_cepe_message(f"PE Limit order for {symbol}: Using price {final_price:.2f} (Current LTP: {current_price:.2f})")
                    
                    # Place PE order
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
                    
                    pe_orders_placed += 1
                    self.order_count_per_symbol[symbol] = self.order_count_per_symbol.get(symbol, 0) + 1
                    self.log_cepe_message(f"✅ PE Order {pe_orders_placed}/{total_pe_orders}: {symbol} {quantity} @ {final_price if order_type == 'LIMIT' else 'MARKET'} - ID: {order_id}")
                    
                    time.sleep(1)
                    
                except Exception as e:
                    self.log_cepe_message(f"❌ Failed to place PE order for {symbol}: {e}")
        
        # Final summary
        self.log_cepe_message("=== CE/PE ORDER PLACEMENT SUMMARY ===")
        self.log_cepe_message(f"CE Orders: {ce_orders_placed}/{total_ce_orders} successful")
        self.log_cepe_message(f"PE Orders: {pe_orders_placed}/{total_pe_orders} successful")
        
        # Update protection status
        self.update_protection_status()
        
        # Clear all selections after order
        self.selected_ce_options.clear()
        self.selected_pe_options.clear()
        self.update_cepe_selection_display()
        
        def show_final_summary():
            messagebox.showinfo(
                "CE & PE Orders Completed",
                f"CE Orders: {ce_orders_placed}/{total_ce_orders} successful\n"
                f"PE Orders: {pe_orders_placed}/{total_pe_orders} successful"
            )
        
        self.root.after(0, show_final_summary)
    
    def log_cepe_message(self, message):
        """Thread-safe CE/PE logging method"""
        def update_log():
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.cepe_orders_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.cepe_orders_text.see(tk.END)
            except Exception as e:
                print(f"CE/PE log error: {e}")
        
        try:
            if self.root.winfo_exists():
                self.root.after(0, update_log)
        except:
            pass


    def setup_position_exit_tab(self, notebook):
        """Setup position exit tab with automatic limit prices"""
        exit_frame = ttk.Frame(notebook)
        notebook.add(exit_frame, text="Position Exit")
        
        # Main container
        main_container = ttk.Frame(exit_frame)
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Control Frame
        control_frame = ttk.LabelFrame(main_container, text="Position Exit Controls")
        control_frame.pack(fill='x', padx=5, pady=5)
        
        # Auto Exit Settings Frame
        settings_frame = ttk.Frame(control_frame)
        settings_frame.pack(fill='x', padx=5, pady=5)
        
        # Tolerance Settings
        ttk.Label(settings_frame, text="Buy Exit Tolerance (%):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.buy_exit_tolerance_var = tk.StringVar(value="0.5")
        ttk.Entry(settings_frame, textvariable=self.buy_exit_tolerance_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky='w')
        
        ttk.Label(settings_frame, text="Sell Exit Tolerance (%):").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.sell_exit_tolerance_var = tk.StringVar(value="0.5")
        ttk.Entry(settings_frame, textvariable=self.sell_exit_tolerance_var, width=10).grid(row=0, column=3, padx=5, pady=5, sticky='w')
        
        # Price Tick Settings
        ttk.Label(settings_frame, text="Price Tick:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.exit_price_tick_var = tk.StringVar(value="0.05")
        ttk.Entry(settings_frame, textvariable=self.exit_price_tick_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        # Max Adjustment
        ttk.Label(settings_frame, text="Max Adjustment (%):").grid(row=1, column=2, padx=5, pady=5, sticky='w')
        self.max_exit_adjustment_var = tk.StringVar(value="2.0")
        ttk.Entry(settings_frame, textvariable=self.max_exit_adjustment_var, width=10).grid(row=1, column=3, padx=5, pady=5, sticky='w')
        
        # Auto Exit Options
        options_frame = ttk.Frame(control_frame)
        options_frame.pack(fill='x', padx=5, pady=5)
        
        self.auto_limit_exit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Enable Auto Limit Prices", 
                        variable=self.auto_limit_exit_var).pack(side='left', padx=5)
        
        self.use_market_fallback_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Market Order Fallback", 
                        variable=self.use_market_fallback_var).pack(side='left', padx=5)
        
        # Buttons Frame
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill='x', padx=5, pady=10)
        
        ttk.Button(button_frame, text="Refresh Positions", 
                command=self.refresh_exit_positions).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Exit Selected Positions", 
                command=self.exit_selected_positions).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Exit All Positions", 
                command=self.exit_all_positions).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Calculate Exit Prices", 
                command=self.calculate_exit_prices).pack(side='left', padx=5)
        
        # Positions Table Frame
        table_frame = ttk.LabelFrame(main_container, text="Current Positions for Exit")
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Create treeview with scrollbars
        tree_frame = ttk.Frame(table_frame)
        tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Horizontal scrollbar
        h_scroll = ttk.Scrollbar(tree_frame, orient='horizontal')
        h_scroll.pack(side='bottom', fill='x')
        
        # Vertical scrollbar
        v_scroll = ttk.Scrollbar(tree_frame)
        v_scroll.pack(side='right', fill='y')
        
        # Treeview
        self.exit_positions_tree = ttk.Treeview(tree_frame, columns=(
            'Select', 'Symbol', 'Quantity', 'Avg Price', 'LTP', 'P&L', 'Type',
            'Exit Price', 'Exit Type', 'Status'
        ), show='headings', xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set, height=15)
        
        h_scroll.config(command=self.exit_positions_tree.xview)
        v_scroll.config(command=self.exit_positions_tree.yview)
        
        # Define headings
        columns = {
            'Select': ('✓', 40),
            'Symbol': ('Symbol', 120),
            'Quantity': ('Qty', 80),
            'Avg Price': ('Avg Price', 90),
            'LTP': ('LTP', 90),
            'P&L': ('P&L', 90),
            'Type': ('Type', 60),
            'Exit Price': ('Exit Price', 90),
            'Exit Type': ('Exit Type', 90),
            'Status': ('Status', 100)
        }
        
        for col, (text, width) in columns.items():
            self.exit_positions_tree.heading(col, text=text)
            self.exit_positions_tree.column(col, width=width, anchor='center')
        
        self.exit_positions_tree.pack(fill='both', expand=True)
        
        # Bind click event for selection
        self.exit_positions_tree.bind('<Button-1>', self.on_exit_position_select)
        
        # Status Frame
        status_frame = ttk.LabelFrame(main_container, text="Exit Status")
        status_frame.pack(fill='x', padx=5, pady=5)
        
        self.exit_status_text = scrolledtext.ScrolledText(status_frame, height=8)
        self.exit_status_text.pack(fill='both', expand=True, padx=5, pady=5)
        self.exit_status_text.insert(tk.END, "Ready for position exit...\n")
        
        # Store selected positions for exit
        self.selected_exit_positions = {}

    def on_exit_position_select(self, event):
        """Handle selection of positions for exit"""
        item = self.exit_positions_tree.identify_row(event.y)
        column = self.exit_positions_tree.identify_column(event.x)
        
        if item and column == '#1':  # Clicked on select column
            values = self.exit_positions_tree.item(item, 'values')
            symbol = values[1]
            
            if symbol in self.selected_exit_positions:
                # Deselect
                self.exit_positions_tree.set(item, 'Select', '□')
                del self.selected_exit_positions[symbol]
                self.log_exit_message(f"Deselected {symbol} for exit")
            else:
                # Select
                self.exit_positions_tree.set(item, 'Select', '✓')
                self.selected_exit_positions[symbol] = {
                    'symbol': symbol,
                    'quantity': int(values[2]),
                    'avg_price': float(values[3]),
                    'ltp': float(values[4]) if values[4] != 'N/A' else 0,
                    'type': values[6],
                    'exit_price': values[7] if values[7] != 'Calc...' else 0,
                    'exit_type': values[8]
                }
                self.log_exit_message(f"Selected {symbol} for exit")

    def refresh_exit_positions(self):
        """Refresh positions for exit tab"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            positions = self.kite.positions()
            
            # Clear existing data
            for item in self.exit_positions_tree.get_children():
                self.exit_positions_tree.delete(item)
            
            # Clear selection
            self.selected_exit_positions.clear()
            
            # Add net positions
            total_positions = 0
            for position in positions['net']:
                if position['quantity'] != 0:
                    total_positions += 1
                    symbol = position['tradingsymbol']
                    quantity = position['quantity']
                    avg_price = position['average_price']
                    ltp = position['last_price']
                    pnl = position['pnl']
                    
                    # Determine position type
                    pos_type = "LONG" if quantity > 0 else "SHORT"
                    
                    # Calculate initial exit price
                    exit_price = 'Calc...'
                    exit_type = 'LIMIT'
                    
                    # Color code based on P&L
                    tags = ()
                    if pnl > 0:
                        tags = ('profit',)
                    elif pnl < 0:
                        tags = ('loss',)
                    
                    self.exit_positions_tree.insert('', 'end', values=(
                        '□',  # Select checkbox
                        symbol,
                        abs(quantity),
                        f"{avg_price:.2f}",
                        f"{ltp:.2f}",
                        f"{pnl:.2f}",
                        pos_type,
                        exit_price,
                        exit_type,
                        'Ready'
                    ), tags=tags)
            
            # Configure tag colors
            self.exit_positions_tree.tag_configure('profit', foreground='green')
            self.exit_positions_tree.tag_configure('loss', foreground='red')
            
            self.log_exit_message(f"Refreshed {total_positions} positions for exit")
            
            # Auto-calculate exit prices if positions exist
            if total_positions > 0:
                self.calculate_exit_prices()
                
        except Exception as e:
            self.log_exit_message(f"Error refreshing exit positions: {e}")

    def calculate_exit_prices(self):
        """Calculate automatic exit prices for all positions"""
        if not self.is_logged_in:
            return
        
        try:
            # Get current LTP for all positions
            symbols = []
            for item in self.exit_positions_tree.get_children():
                values = self.exit_positions_tree.item(item, 'values')
                if values and len(values) > 1:
                    symbols.append(values[1])
            
            if not symbols:
                self.log_exit_message("No positions to calculate exit prices")
                return
            
            # Get latest prices
            try:
                instruments = [f"MCX:{symbol}" for symbol in symbols]
                ltp_data = self.kite.ltp(instruments)
            except:
                ltp_data = {}
            
            # Calculate exit prices for each position
            for item in self.exit_positions_tree.get_children():
                values = self.exit_positions_tree.item(item, 'values')
                if not values or len(values) < 7:
                    continue
                
                symbol = values[1]
                quantity = int(values[2])
                pos_type = values[6]
                
                # Get current LTP
                current_price = 0
                try:
                    current_price = ltp_data.get(f"MCX:{symbol}", {}).get('last_price', 0)
                except:
                    # Try to get from previous value
                    try:
                        current_price = float(values[4]) if values[4] != 'N/A' else 0
                    except:
                        current_price = 0
                
                if current_price <= 0:
                    self.exit_positions_tree.set(item, 'Exit Price', 'N/A')
                    self.exit_positions_tree.set(item, 'Status', 'No Price')
                    continue
                
                # ===== UPDATED: USE AUTOMATIC LIMIT PRICE CALCULATION =====
                exit_price = 0
                exit_type = "LIMIT" if self.limit_price_settings['auto_limit_enabled'] else "MARKET"
                
                if exit_type == "LIMIT":
                    exit_price = self.calculate_exit_limit_price(current_price, pos_type)
                    
                    # Update tree
                    self.exit_positions_tree.set(item, 'Exit Price', f"{exit_price:.2f}")
                    self.exit_positions_tree.set(item, 'Exit Type', exit_type)
                    self.exit_positions_tree.set(item, 'Status', f'Calculated ({self.limit_price_settings["exit_" + ("sell" if pos_type == "LONG" else "buy") + "_tolerance"]}%)')
                    
                    # Log calculation details
                    self.log_exit_message(f"Exit price for {symbol} ({pos_type}): "
                                        f"LTP={current_price:.2f}, Exit={exit_price:.2f}, "
                                        f"Tol={self.limit_price_settings['exit_' + ('sell' if pos_type == 'LONG' else 'buy') + '_tolerance']}%")
                else:
                    self.exit_positions_tree.set(item, 'Exit Price', 'MARKET')
                    self.exit_positions_tree.set(item, 'Exit Type', 'MARKET')
                    self.exit_positions_tree.set(item, 'Status', 'Market Order')
                
                # Update selection if exists
                if symbol in self.selected_exit_positions:
                    self.selected_exit_positions[symbol]['exit_price'] = exit_price
                    self.selected_exit_positions[symbol]['exit_type'] = exit_type
            
            self.log_exit_message(f"Calculated exit prices for {len(symbols)} positions")
            
        except Exception as e:
            self.log_exit_message(f"Error calculating exit prices: {e}")

    def exit_selected_positions(self):
        """Exit selected positions with automatic limit prices"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        if not self.selected_exit_positions:
            messagebox.showwarning("Warning", "No positions selected for exit")
            return
        
        try:
            # Confirm with user
            confirm = messagebox.askyesno(
                "Confirm Exit",
                f"Exit {len(self.selected_exit_positions)} selected positions?\n"
                f"Using automatic limit prices with tolerance settings."
            )
            
            if not confirm:
                return
            
            # Execute exits
            successful = 0
            failed = 0
            
            for symbol, position in self.selected_exit_positions.items():
                try:
                    quantity = position['quantity']
                    exit_type = position['exit_type']
                    exit_price = position['exit_price']
                    pos_type = position['type']
                    
                    # Determine transaction type
                    if pos_type == "LONG":
                        transaction = "SELL"
                        tol_type = "sell"
                    else:  # SHORT
                        transaction = "BUY"
                        tol_type = "buy"
                    
                    # Get current price for logging
                    current_price = 0
                    try:
                        ltp_data = self.kite.ltp(f"MCX:{symbol}")
                        current_price = list(ltp_data.values())[0]['last_price']
                    except:
                        pass
                    
                    # Place order
                    if exit_type == "MARKET" or exit_price <= 0:
                        # Use market order
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange="MCX",
                            tradingsymbol=symbol,
                            transaction_type=transaction,
                            quantity=abs(quantity),
                            order_type=self.kite.ORDER_TYPE_MARKET,
                            product=self.kite.PRODUCT_NRML
                        )
                        self.log_exit_message(f"✅ Market Exit: {symbol} {transaction} {abs(quantity)} - ID: {order_id}")
                    else:
                        # Use limit order with calculated price
                        order_id = self.kite.place_order(
                            variety=self.kite.VARIETY_REGULAR,
                            exchange="MCX",
                            tradingsymbol=symbol,
                            transaction_type=transaction,
                            quantity=abs(quantity),
                            order_type=self.kite.ORDER_TYPE_LIMIT,
                            product=self.kite.PRODUCT_NRML,
                            price=exit_price
                        )
                        self.log_exit_message(f"✅ Limit Exit: {symbol} {transaction} {abs(quantity)} @ {exit_price:.2f} "
                                           f"(LTP: {current_price:.2f}, Tol: {self.limit_price_settings['exit_' + tol_type + '_tolerance']}%) - ID: {order_id}")
                    
                    successful += 1
                    
                    # Update status in tree
                    for item in self.exit_positions_tree.get_children():
                        values = self.exit_positions_tree.item(item, 'values')
                        if values and len(values) > 1 and values[1] == symbol:
                            self.exit_positions_tree.set(item, 'Status', 'Exit Placed')
                            break
                    
                    time.sleep(1)  # Delay between orders
                    
                except Exception as e:
                    failed += 1
                    self.log_exit_message(f"❌ Failed to exit {symbol}: {e}")
                    
                    # Try market order fallback if enabled
                    if self.limit_price_settings['use_market_fallback'] and exit_type == "LIMIT":
                        try:
                            order_id = self.kite.place_order(
                                variety=self.kite.VARIETY_REGULAR,
                                exchange="MCX",
                                tradingsymbol=symbol,
                                transaction_type=transaction,
                                quantity=abs(quantity),
                                order_type=self.kite.ORDER_TYPE_MARKET,
                                product=self.kite.PRODUCT_NRML
                            )
                            self.log_exit_message(f"⚠️ Market Fallback Exit: {symbol} {transaction} {abs(quantity)} - ID: {order_id}")
                            successful += 1
                            failed -= 1
                        except:
                            pass
            
            # Show summary
            messagebox.showinfo(
                "Exit Summary",
                f"Exit orders placed:\n"
                f"Successful: {successful}\n"
                f"Failed: {failed}\n\n"
                f"Tolerance Settings:\n"
                f"Buy: {self.limit_price_settings['exit_buy_tolerance']}%\n"
                f"Sell: {self.limit_price_settings['exit_sell_tolerance']}%"
            )
            
            # Clear selection
            self.selected_exit_positions.clear()
            
            # Refresh positions after some delay
            self.root.after(5000, self.refresh_exit_positions)
            
        except Exception as e:
            self.log_exit_message(f"Error in exit_selected_positions: {e}")

    def exit_all_positions(self):
        """Exit all open positions with automatic limit prices"""
        if not self.is_logged_in:
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            # Select all positions
            self.selected_exit_positions.clear()
            for item in self.exit_positions_tree.get_children():
                values = self.exit_positions_tree.item(item, 'values')
                if values and len(values) > 1:
                    symbol = values[1]
                    self.exit_positions_tree.set(item, 'Select', '✓')
                    self.selected_exit_positions[symbol] = {
                        'symbol': symbol,
                        'quantity': int(values[2]),
                        'avg_price': float(values[3]),
                        'ltp': float(values[4]) if values[4] != 'N/A' else 0,
                        'type': values[6],
                        'exit_price': float(values[7]) if values[7] not in ['Calc...', 'N/A'] else 0,
                        'exit_type': values[8]
                    }
            
            if not self.selected_exit_positions:
                messagebox.showinfo("Info", "No positions to exit")
                return
            
            # Exit selected positions
            self.exit_selected_positions()
            
        except Exception as e:
            self.log_exit_message(f"Error in exit_all_positions: {e}")

    def log_exit_message(self, message):
        """Thread-safe logging for exit operations"""
        def update_log():
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.exit_status_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.exit_status_text.see(tk.END)
            except Exception as e:
                print(f"Exit log error: {e}")
        
        try:
            if self.root.winfo_exists():
                self.root.after(0, update_log)
        except:
            pass

    # Add this method to update positions for exit tab periodically
    def update_exit_positions_loop(self):
        """Periodically update exit positions"""
        while self.is_logged_in:
            try:
                # Only refresh if the tab is active (simplified - refresh every 30 seconds)
                time.sleep(30)
                if hasattr(self, 'exit_positions_tree'):
                    self.root.after(0, self.refresh_exit_positions)
            except Exception as e:
                self.log_exit_message(f"Error in exit positions loop: {e}")
                time.sleep(60)

    # ===== NEW: AUTOMATIC LIMIT PRICE CALCULATION METHODS =====
    def calculate_limit_price(self, current_price, transaction_type, instrument_type="FUTURES"):
        """Calculate automatic limit price based on tolerance settings"""
        if not self.limit_price_settings['auto_limit_enabled']:
            return current_price
        
        try:
            # Determine tolerance based on instrument type and transaction
            tolerance_key = f"{instrument_type.lower()}_{transaction_type.lower()}_tolerance"
            tolerance = self.limit_price_settings.get(tolerance_key, 0.5)
            
            # Convert percentage to decimal
            tolerance_decimal = tolerance / 100.0
            
            # Apply max adjustment limit
            max_adjustment = self.limit_price_settings['max_adjustment_percent'] / 100.0
            tolerance_decimal = min(tolerance_decimal, max_adjustment)
            
            # Calculate limit price
            if transaction_type.upper() == "BUY":
                limit_price = current_price * (1 - tolerance_decimal)
            else:  # SELL
                limit_price = current_price * (1 + tolerance_decimal)
            
            # Round to price tick if enabled
            if self.limit_price_settings['round_to_tick']:
                tick_size = self.limit_price_settings['min_price_tick']
                limit_price = round(limit_price / tick_size) * tick_size
            
            # Ensure limit price is valid
            if limit_price <= 0:
                return current_price
            
            return limit_price
            
        except Exception as e:
            self.log_message(f"Error calculating limit price: {e}")
            return current_price
    
    def calculate_exit_limit_price(self, current_price, position_type):
        """Calculate exit limit price based on position type"""
        if position_type.upper() == "LONG":
            # For LONG position, we SELL to exit - use sell tolerance
            return self.calculate_limit_price(current_price, "SELL", "EXIT")
        else:  # SHORT position
            # For SHORT position, we BUY to exit - use buy tolerance
            return self.calculate_limit_price(current_price, "BUY", "EXIT")
    
    def apply_price_tick(self, price):
        """Round price to nearest tick size"""
        tick_size = self.limit_price_settings['min_price_tick']
        if tick_size > 0:
            return round(price / tick_size) * tick_size
        return price
    # =========================================================
    def setup_limit_price_settings_tab(self, notebook):
            """Setup automatic limit price settings tab"""
            settings_frame = ttk.Frame(notebook)
            notebook.add(settings_frame, text="Limit Price Settings")
            
            # Main frame with scrollbar
            main_frame = ttk.Frame(settings_frame)
            main_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            # General Settings Frame
            general_frame = ttk.LabelFrame(main_frame, text="General Limit Price Settings")
            general_frame.pack(fill='x', padx=5, pady=5)
            
            row = 0
            
            # Enable Auto Limit
            self.auto_limit_var = tk.BooleanVar(value=self.limit_price_settings['auto_limit_enabled'])
            ttk.Checkbutton(general_frame, text="Enable Automatic Limit Prices", 
                        variable=self.auto_limit_var).grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='w')
            row += 1
            
            # Minimum Price Tick
            ttk.Label(general_frame, text="Minimum Price Tick:").grid(row=row, column=0, padx=5, pady=5, sticky='w')
            self.price_tick_var = tk.StringVar(value=str(self.limit_price_settings['min_price_tick']))
            ttk.Entry(general_frame, textvariable=self.price_tick_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
            row += 1
            
            # Max Adjustment Percent
            ttk.Label(general_frame, text="Max Adjustment %:").grid(row=row, column=0, padx=5, pady=5, sticky='w')
            self.max_adj_var = tk.StringVar(value=str(self.limit_price_settings['max_adjustment_percent']))
            ttk.Entry(general_frame, textvariable=self.max_adj_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
            row += 1
            
            # Round to Tick
            self.round_tick_var = tk.BooleanVar(value=self.limit_price_settings['round_to_tick'])
            ttk.Checkbutton(general_frame, text="Round to Nearest Tick", 
                        variable=self.round_tick_var).grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='w')
            row += 1
            
            # Market Fallback
            self.market_fallback_var = tk.BooleanVar(value=self.limit_price_settings['use_market_fallback'])
            ttk.Checkbutton(general_frame, text="Use Market Order Fallback", 
                        variable=self.market_fallback_var).grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='w')
            row += 1
            
            # Tolerance Settings Frame (Futures)
            futures_frame = ttk.LabelFrame(main_frame, text="Futures Tolerance Settings (%)")
            futures_frame.pack(fill='x', padx=5, pady=5)
            
            ttk.Label(futures_frame, text="BUY Tolerance (% below market):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
            self.futures_buy_tol_var = tk.StringVar(value=str(self.limit_price_settings['futures_buy_tolerance']))
            ttk.Entry(futures_frame, textvariable=self.futures_buy_tol_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky='w')
            
            ttk.Label(futures_frame, text="SELL Tolerance (% above market):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
            self.futures_sell_tol_var = tk.StringVar(value=str(self.limit_price_settings['futures_sell_tolerance']))
            ttk.Entry(futures_frame, textvariable=self.futures_sell_tol_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky='w')
            
            # Tolerance Settings Frame (Options)
            options_frame = ttk.LabelFrame(main_frame, text="Options Tolerance Settings (%)")
            options_frame.pack(fill='x', padx=5, pady=5)
            
            ttk.Label(options_frame, text="BUY Tolerance (% below market):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
            self.options_buy_tol_var = tk.StringVar(value=str(self.limit_price_settings['options_buy_tolerance']))
            ttk.Entry(options_frame, textvariable=self.options_buy_tol_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky='w')
            
            ttk.Label(options_frame, text="SELL Tolerance (% above market):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
            self.options_sell_tol_var = tk.StringVar(value=str(self.limit_price_settings['options_sell_tolerance']))
            ttk.Entry(options_frame, textvariable=self.options_sell_tol_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky='w')
            
            # Tolerance Settings Frame (CE/PE)
            cepe_frame = ttk.LabelFrame(main_frame, text="CE/PE Tolerance Settings (%)")
            cepe_frame.pack(fill='x', padx=5, pady=5)
            
            ttk.Label(cepe_frame, text="CE BUY Tolerance (% below market):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
            self.ce_buy_tol_var = tk.StringVar(value=str(self.limit_price_settings['ce_buy_tolerance']))
            ttk.Entry(cepe_frame, textvariable=self.ce_buy_tol_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky='w')
            
            ttk.Label(cepe_frame, text="CE SELL Tolerance (% above market):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
            self.ce_sell_tol_var = tk.StringVar(value=str(self.limit_price_settings['ce_sell_tolerance']))
            ttk.Entry(cepe_frame, textvariable=self.ce_sell_tol_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky='w')
            
            ttk.Label(cepe_frame, text="PE BUY Tolerance (% below market):").grid(row=2, column=0, padx=5, pady=5, sticky='w')
            self.pe_buy_tol_var = tk.StringVar(value=str(self.limit_price_settings['pe_buy_tolerance']))
            ttk.Entry(cepe_frame, textvariable=self.pe_buy_tol_var, width=10).grid(row=2, column=1, padx=5, pady=5, sticky='w')
            
            ttk.Label(cepe_frame, text="PE SELL Tolerance (% above market):").grid(row=3, column=0, padx=5, pady=5, sticky='w')
            self.pe_sell_tol_var = tk.StringVar(value=str(self.limit_price_settings['pe_sell_tolerance']))
            ttk.Entry(cepe_frame, textvariable=self.pe_sell_tol_var, width=10).grid(row=3, column=1, padx=5, pady=5, sticky='w')
            
            # Exit Tolerance Settings
            exit_frame = ttk.LabelFrame(main_frame, text="Exit Position Tolerance Settings (%)")
            exit_frame.pack(fill='x', padx=5, pady=5)
            
            ttk.Label(exit_frame, text="Exit BUY Tolerance (% below market):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
            self.exit_buy_tol_var = tk.StringVar(value=str(self.limit_price_settings['exit_buy_tolerance']))
            ttk.Entry(exit_frame, textvariable=self.exit_buy_tol_var, width=10).grid(row=0, column=1, padx=5, pady=5, sticky='w')
            
            ttk.Label(exit_frame, text="Exit SELL Tolerance (% above market):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
            self.exit_sell_tol_var = tk.StringVar(value=str(self.limit_price_settings['exit_sell_tolerance']))
            ttk.Entry(exit_frame, textvariable=self.exit_sell_tol_var, width=10).grid(row=1, column=1, padx=5, pady=5, sticky='w')
            
            # Save Button
            save_frame = ttk.Frame(main_frame)
            save_frame.pack(fill='x', padx=5, pady=10)
            
            ttk.Button(save_frame, text="Save Limit Price Settings", 
                    command=self.save_limit_price_settings).pack(pady=5)
            
            # Status Label
            self.limit_settings_status = ttk.Label(main_frame, text="Settings ready", foreground='green')
            self.limit_settings_status.pack(pady=5)

    def save_limit_price_settings(self):
        """Save limit price settings from GUI"""
        try:
            # Update settings from GUI variables
            self.limit_price_settings['auto_limit_enabled'] = self.auto_limit_var.get()
            self.limit_price_settings['min_price_tick'] = float(self.price_tick_var.get())
            self.limit_price_settings['max_adjustment_percent'] = float(self.max_adj_var.get())
            self.limit_price_settings['round_to_tick'] = self.round_tick_var.get()
            self.limit_price_settings['use_market_fallback'] = self.market_fallback_var.get()
            
            # Update tolerance settings
            self.limit_price_settings['futures_buy_tolerance'] = float(self.futures_buy_tol_var.get())
            self.limit_price_settings['futures_sell_tolerance'] = float(self.futures_sell_tol_var.get())
            self.limit_price_settings['options_buy_tolerance'] = float(self.options_buy_tol_var.get())
            self.limit_price_settings['options_sell_tolerance'] = float(self.options_sell_tol_var.get())
            self.limit_price_settings['ce_buy_tolerance'] = float(self.ce_buy_tol_var.get())
            self.limit_price_settings['ce_sell_tolerance'] = float(self.ce_sell_tol_var.get())
            self.limit_price_settings['pe_buy_tolerance'] = float(self.pe_buy_tol_var.get())
            self.limit_price_settings['pe_sell_tolerance'] = float(self.pe_sell_tol_var.get())
            self.limit_price_settings['exit_buy_tolerance'] = float(self.exit_buy_tol_var.get())
            self.limit_price_settings['exit_sell_tolerance'] = float(self.exit_sell_tol_var.get())
            
            # Update status
            self.limit_settings_status.config(text="Settings saved successfully!", foreground='green')
            messagebox.showinfo("Success", "Limit price settings saved successfully!")
            
        except ValueError as e:
            self.limit_settings_status.config(text="Error: Please enter valid numeric values", foreground='red')
            messagebox.showerror("Error", "Please enter valid numeric values for all tolerance settings")
        except Exception as e:
            self.limit_settings_status.config(text=f"Error: {str(e)}", foreground='red')
            messagebox.showerror("Error", f"Failed to save settings: {e}")

def main():
    """Main entry point for the application"""
    try:
        root = tk.Tk()
        app = ZerodhaTradingApp(root)
        
        # Handle window closing
        def on_closing():
            # Stop all background threads
            app.is_logged_in = False
            app.live_data_running = False
            app.futures_data_running = False
            app.options_data_running = False
            if hasattr(app, 'price_update_event'):
                app.price_update_event.set()
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
