import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import json
import os
import webbrowser
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from kiteconnect import KiteTicker
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import logging

# Disable websocket logging
logging.getLogger('kiteconnect').setLevel(logging.ERROR)

class TokenHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if 'request_token' in query_params:
            request_token = query_params['request_token'][0]
            self.server.request_token = request_token
            self.server.received_token = True
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            response_html = """
            <html>
                <body>
                    <h2>Login Successful!</h2>
                    <p>You can close this window and return to the application.</p>
                    <script>window.close();</script>
                </body>
            </html>
            """
            self.wfile.write(response_html.encode())
        else:
            self.send_response(400)
            self.end_headers()
    
    def log_message(self, format, *args):
        return

class ZerodhaFuturesTracker:
    def __init__(self, root):
        self.root = root
        self.root.title("Zerodha Live P&L Tracker")
        self.root.geometry("1200x900")
        
        # Initialize attributes
        self.api_key = ""
        self.api_secret = ""
        self.access_token = ""
        self.kite = None
        self.kws = None
        self.token_server = None
        self.server_thread = None
        self.current_month_data = {}
        self.next_month_data = {}
        self.is_running = False
        self.is_pnl_tracking = False
        self.last_current_ltp = 0
        self.last_next_ltp = 0
        
        # WebSocket tracking
        self.subscribed_tokens = set()
        self.live_prices = {}  # Store live prices for all instruments
        self.position_tokens = {}  # Map tokens to position data
        self.ws_reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # P&L tracking
        self.position_data = {
            'current_qty': 0,
            'current_avg_price': 0,
            'next_qty': 0,
            'next_avg_price': 0,
            'current_pnl': 0,
            'next_pnl': 0,
            'total_pnl': 0
        }
        
        # Existing positions from Zerodha
        self.existing_positions = {}
        self.net_positions = {}
        
        # Default settings
        self.selected_exchange = "NFO"
        self.selected_instrument_type = "FUT"
        self.selected_symbol = "NIFTY"
        
        # Token management
        self.token_expiry_time = None
        
        # P&L tracking thread
        self.pnl_thread = None
        
        # Initialize GUI elements
        self.api_key_entry = None
        self.api_secret_entry = None
        self.status_label = None
        self.connection_info = None
        self.log_text = None
        
        # Load saved credentials
        self.load_credentials()
        
        self.setup_gui()
    
    def setup_gui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # API Configuration Frame
        config_frame = ttk.LabelFrame(main_frame, text="API Configuration", padding="10")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(config_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W)
        self.api_key_entry = ttk.Entry(config_frame, width=40)
        self.api_key_entry.grid(row=0, column=1, padx=5)
        if self.api_key:
            self.api_key_entry.insert(0, self.api_key)
        
        ttk.Label(config_frame, text="API Secret:").grid(row=1, column=0, sticky=tk.W)
        self.api_secret_entry = ttk.Entry(config_frame, width=40, show="*")
        self.api_secret_entry.grid(row=1, column=1, padx=5, pady=5)
        if self.api_secret:
            self.api_secret_entry.insert(0, self.api_secret)
        
        # Exchange and Instrument Selection Frame
        selection_frame = ttk.LabelFrame(main_frame, text="Market Selection", padding="10")
        selection_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Exchange selection
        ttk.Label(selection_frame, text="Exchange:").grid(row=0, column=0, sticky=tk.W)
        self.exchange_var = tk.StringVar(value=self.selected_exchange)
        exchange_combo = ttk.Combobox(selection_frame, textvariable=self.exchange_var, 
                                    values=["NFO", "MCX"], state="readonly", width=10)
        exchange_combo.grid(row=0, column=1, padx=5, sticky=tk.W)
        exchange_combo.bind('<<ComboboxSelected>>', self.on_exchange_change)
        
        # Instrument type selection
        ttk.Label(selection_frame, text="Instrument Type:").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.instrument_var = tk.StringVar(value=self.selected_instrument_type)
        instrument_combo = ttk.Combobox(selection_frame, textvariable=self.instrument_var, 
                                      values=["FUT", "OPT"], state="readonly", width=10)
        instrument_combo.grid(row=0, column=3, padx=5, sticky=tk.W)
        instrument_combo.bind('<<ComboboxSelected>>', self.on_instrument_change)
        
        # Symbol selection
        ttk.Label(selection_frame, text="Symbol:").grid(row=0, column=4, sticky=tk.W, padx=(20,0))
        self.symbol_var = tk.StringVar(value=self.selected_symbol)
        self.symbol_combo = ttk.Combobox(selection_frame, textvariable=self.symbol_var, 
                                       width=15)
        self.symbol_combo.grid(row=0, column=5, padx=5, sticky=tk.W)
        
        # Update symbols based on default exchange
        self.update_symbol_list()
        
        # Buttons frame
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Auto Login", command=self.auto_login).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Manual Login", command=self.manual_login).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Start Live P&L", command=self.start_live_pnl).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Stop Live P&L", command=self.stop_live_pnl).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save Credentials", command=self.save_credentials).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Token", command=self.clear_token).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Refresh Positions", command=self.fetch_existing_positions).pack(side=tk.LEFT, padx=5)
        
        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Not connected")
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        self.connection_info = ttk.Label(status_frame, text="", foreground="blue")
        self.connection_info.grid(row=0, column=1, sticky=tk.E)
        
        # WebSocket status
        self.ws_status_label = ttk.Label(status_frame, text="WebSocket: Disconnected", foreground="red")
        self.ws_status_label.grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        
        # Token info frame
        token_frame = ttk.LabelFrame(main_frame, text="Token Information", padding="10")
        token_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(token_frame, text="Token Status:").grid(row=0, column=0, sticky=tk.W)
        self.token_status_label = ttk.Label(token_frame, text="No valid token", foreground="red")
        self.token_status_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(token_frame, text="Token Expiry:").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.token_expiry_label = ttk.Label(token_frame, text="N/A")
        self.token_expiry_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # Live P&L Status Frame
        pnl_status_frame = ttk.LabelFrame(main_frame, text="Live P&L Status", padding="10")
        pnl_status_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(pnl_status_frame, text="P&L Update Speed:").grid(row=0, column=0, sticky=tk.W)
        self.pnl_speed_label = ttk.Label(pnl_status_frame, text="Real-time (WebSocket)", font=('Arial', 10, 'bold'), foreground="green")
        self.pnl_speed_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(pnl_status_frame, text="Subscribed Tokens:").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.subscribed_tokens_label = ttk.Label(pnl_status_frame, text="0")
        self.subscribed_tokens_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        ttk.Label(pnl_status_frame, text="Last Tick:").grid(row=0, column=4, sticky=tk.W, padx=(20,0))
        self.last_tick_label = ttk.Label(pnl_status_frame, text="Never", font=('Arial', 8))
        self.last_tick_label.grid(row=0, column=5, sticky=tk.W, padx=10)
        
        # Existing Positions Frame
        positions_frame = ttk.LabelFrame(main_frame, text="Existing Positions from Zerodha", padding="10")
        positions_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Create treeview for positions
        columns = ('tradingsymbol', 'quantity', 'average_price', 'last_price', 'pnl', 'pnl_percent')
        self.positions_tree = ttk.Treeview(positions_frame, columns=columns, show='headings', height=6)
        
        # Define headings
        self.positions_tree.heading('tradingsymbol', text='Trading Symbol')
        self.positions_tree.heading('quantity', text='Quantity')
        self.positions_tree.heading('average_price', text='Avg Price')
        self.positions_tree.heading('last_price', text='LTP')
        self.positions_tree.heading('pnl', text='P&L')
        self.positions_tree.heading('pnl_percent', text='P&L %')
        
        # Define columns
        self.positions_tree.column('tradingsymbol', width=150)
        self.positions_tree.column('quantity', width=80)
        self.positions_tree.column('average_price', width=100)
        self.positions_tree.column('last_price', width=100)
        self.positions_tree.column('pnl', width=100)
        self.positions_tree.column('pnl_percent', width=80)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(positions_frame, orient=tk.VERTICAL, command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=scrollbar.set)
        
        self.positions_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Positions summary
        summary_frame = ttk.Frame(positions_frame)
        summary_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10,0))
        
        ttk.Label(summary_frame, text="Total P&L:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        self.total_positions_pnl_label = ttk.Label(summary_frame, text="₹0.00", font=('Arial', 10, 'bold'))
        self.total_positions_pnl_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(summary_frame, text="Open Positions:").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.open_positions_label = ttk.Label(summary_frame, text="0")
        self.open_positions_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # Data display frame
        data_frame = ttk.LabelFrame(main_frame, text="Price Differences", padding="10")
        data_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Current month instrument
        ttk.Label(data_frame, text="Current Month", font=('Arial', 11, 'bold')).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0,10))
        
        ttk.Label(data_frame, text="Instrument:").grid(row=1, column=0, sticky=tk.W)
        self.current_instrument_label = ttk.Label(data_frame, text="N/A", font=('Arial', 9))
        self.current_instrument_label.grid(row=1, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Open Price:").grid(row=2, column=0, sticky=tk.W)
        self.current_open_label = ttk.Label(data_frame, text="N/A", font=('Arial', 10, 'bold'))
        self.current_open_label.grid(row=2, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Live Price:").grid(row=3, column=0, sticky=tk.W)
        self.current_price_label = ttk.Label(data_frame, text="N/A", font=('Arial', 10, 'bold'))
        self.current_price_label.grid(row=3, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Difference from Open:").grid(row=4, column=0, sticky=tk.W)
        self.current_diff_label = ttk.Label(data_frame, text="N/A", font=('Arial', 10, 'bold'))
        self.current_diff_label.grid(row=4, column=1, sticky=tk.W, padx=10)
        
        # Next month instrument
        ttk.Label(data_frame, text="Next Month", font=('Arial', 11, 'bold')).grid(row=0, column=2, columnspan=2, sticky=tk.W, padx=(50,0), pady=(0,10))
        
        ttk.Label(data_frame, text="Instrument:").grid(row=1, column=2, sticky=tk.W, padx=(50,0))
        self.next_instrument_label = ttk.Label(data_frame, text="N/A", font=('Arial', 9))
        self.next_instrument_label.grid(row=1, column=3, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Open Price:").grid(row=2, column=2, sticky=tk.W, padx=(50,0))
        self.next_open_label = ttk.Label(data_frame, text="N/A", font=('Arial', 10, 'bold'))
        self.next_open_label.grid(row=2, column=3, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Live Price:").grid(row=3, column=2, sticky=tk.W, padx=(50,0))
        self.next_price_label = ttk.Label(data_frame, text="N/A", font=('Arial', 10, 'bold'))
        self.next_price_label.grid(row=3, column=3, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Difference from Open:").grid(row=4, column=2, sticky=tk.W, padx=(50,0))
        self.next_diff_label = ttk.Label(data_frame, text="N/A", font=('Arial', 10, 'bold'))
        self.next_diff_label.grid(row=4, column=3, sticky=tk.W, padx=10)
        
        # For Options, show additional information
        ttk.Label(data_frame, text="Options Data", font=('Arial', 11, 'bold')).grid(row=5, column=0, columnspan=4, sticky=tk.W, pady=(20,10))
        
        ttk.Label(data_frame, text="Strike Price:").grid(row=6, column=0, sticky=tk.W)
        self.strike_price_label = ttk.Label(data_frame, text="N/A")
        self.strike_price_label.grid(row=6, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Option Type:").grid(row=6, column=2, sticky=tk.W, padx=(50,0))
        self.option_type_label = ttk.Label(data_frame, text="N/A")
        self.option_type_label.grid(row=6, column=3, sticky=tk.W, padx=10)
        
        # Spread analysis
        ttk.Label(data_frame, text="Spread Analysis", font=('Arial', 12, 'bold')).grid(row=7, column=0, columnspan=4, sticky=tk.W, pady=(20,10))
        
        ttk.Label(data_frame, text="Spread (Next - Current):").grid(row=8, column=0, sticky=tk.W)
        self.spread_label = ttk.Label(data_frame, text="N/A", font=('Arial', 12, 'bold'))
        self.spread_label.grid(row=8, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(data_frame, text="Spread %:").grid(row=8, column=2, sticky=tk.W, padx=(50,0))
        self.spread_percent_label = ttk.Label(data_frame, text="N/A", font=('Arial', 12, 'bold'))
        self.spread_percent_label.grid(row=8, column=3, sticky=tk.W, padx=10)
        
        # Last update time
        self.update_time_label = ttk.Label(data_frame, text="Last update: Never", font=('Arial', 8))
        self.update_time_label.grid(row=9, column=0, columnspan=4, sticky=tk.W, pady=(10,0))
        
        # Manual P&L Tracking Frame
        pnl_frame = ttk.LabelFrame(main_frame, text="Manual P&L Tracking", padding="10")
        pnl_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Position input frame
        position_input_frame = ttk.Frame(pnl_frame)
        position_input_frame.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(position_input_frame, text="Current Month Position:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(position_input_frame, text="Qty:").grid(row=0, column=1, sticky=tk.W, padx=(10,0))
        self.current_qty_entry = ttk.Entry(position_input_frame, width=8)
        self.current_qty_entry.grid(row=0, column=2, padx=5)
        self.current_qty_entry.insert(0, "0")
        
        ttk.Label(position_input_frame, text="Avg Price:").grid(row=0, column=3, sticky=tk.W, padx=(10,0))
        self.current_avg_entry = ttk.Entry(position_input_frame, width=10)
        self.current_avg_entry.grid(row=0, column=4, padx=5)
        self.current_avg_entry.insert(0, "0")
        
        ttk.Label(position_input_frame, text="Next Month Position:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Label(position_input_frame, text="Qty:").grid(row=1, column=1, sticky=tk.W, padx=(10,0), pady=(5,0))
        self.next_qty_entry = ttk.Entry(position_input_frame, width=8)
        self.next_qty_entry.grid(row=1, column=2, padx=5, pady=(5,0))
        self.next_qty_entry.insert(0, "0")
        
        ttk.Label(position_input_frame, text="Avg Price:").grid(row=1, column=3, sticky=tk.W, padx=(10,0), pady=(5,0))
        self.next_avg_entry = ttk.Entry(position_input_frame, width=10)
        self.next_avg_entry.grid(row=1, column=4, padx=5, pady=(5,0))
        self.next_avg_entry.insert(0, "0")
        
        ttk.Button(position_input_frame, text="Update Positions", 
                  command=self.update_positions).grid(row=0, column=5, rowspan=2, padx=(20,0))
        
        # Manual P&L display frame
        pnl_display_frame = ttk.Frame(pnl_frame)
        pnl_display_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        
        # Current month P&L
        ttk.Label(pnl_display_frame, text="Current Month P&L:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)
        self.current_pnl_label = ttk.Label(pnl_display_frame, text="₹0.00", font=('Arial', 12, 'bold'))
        self.current_pnl_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        # Next month P&L
        ttk.Label(pnl_display_frame, text="Next Month P&L:", font=('Arial', 10, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=(30,0))
        self.next_pnl_label = ttk.Label(pnl_display_frame, text="₹0.00", font=('Arial', 12, 'bold'))
        self.next_pnl_label.grid(row=0, column=3, sticky=tk.W, padx=10)
        
        # Total P&L
        ttk.Label(pnl_display_frame, text="Total P&L:", font=('Arial', 11, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=(10,0))
        self.total_pnl_label = ttk.Label(pnl_display_frame, text="₹0.00", font=('Arial', 14, 'bold'))
        self.total_pnl_label.grid(row=1, column=1, sticky=tk.W, padx=10, pady=(10,0))
        
        # P&L breakdown
        ttk.Label(pnl_display_frame, text="P&L Breakdown:", font=('Arial', 9)).grid(row=2, column=0, sticky=tk.W, pady=(10,0))
        self.pnl_breakdown_label = ttk.Label(pnl_display_frame, text="No positions", font=('Arial', 8))
        self.pnl_breakdown_label.grid(row=2, column=1, columnspan=3, sticky=tk.W, padx=10, pady=(10,0))
        
        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, width=80)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(8, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        positions_frame.columnconfigure(0, weight=1)
        positions_frame.rowconfigure(0, weight=1)
        
        # Initial log message
        self.log_message("Application started successfully")
        if self.access_token:
            self.initialize_with_saved_token()
    
    def start_live_pnl(self):
        """Start live P&L tracking with WebSocket"""
        if not self.kite or not self.check_token_validity():
            messagebox.showerror("Error", "Please login first")
            return
        
        if self.kws and hasattr(self.kws, 'is_connected') and self.kws.is_connected():
            self.log_message("Live P&L is already running")
            return
        
        try:
            # Check if we have Kite Connect (paid) app credentials
            if not self.has_kite_connect_app():
                self.show_kite_connect_warning()
                return
            
            # Initialize WebSocket
            self.kws = KiteTicker(self.api_key, self.access_token)
            
            # Set WebSocket callbacks
            self.kws.on_ticks = self.on_ticks
            self.kws.on_connect = self.on_connect
            self.kws.on_close = self.on_close
            self.kws.on_error = self.on_error
            
            # Reset reconnect attempts
            self.ws_reconnect_attempts = 0
            
            # Connect to WebSocket
            self.kws.connect(threaded=True)
            self.is_pnl_tracking = True
            self.log_message("Starting Live P&L WebSocket...")
            
        except Exception as e:
            self.log_message(f"Error starting WebSocket: {e}")
            self.handle_websocket_error(e)
    
    def has_kite_connect_app(self):
        """Check if we're using Kite Connect (paid) app credentials"""
        # This is a basic check - you might want to implement more sophisticated validation
        if not self.api_key or len(self.api_key) < 10:
            return False
        return True
    
    def show_kite_connect_warning(self):
        """Show warning about Kite Connect app requirement"""
        warning_msg = """
WebSocket access requires a Kite Connect (PAID) app.

Your current API key appears to be from a Kite Personal (FREE) app, which doesn't have WebSocket access.

To fix this:
1. Go to https://kite.trade/
2. Create a Kite Connect (PAID) app
3. Use the new API key and secret
4. Generate a new access token

Would you like to open the Kite developer console now?
        """
        if messagebox.askyesno("Kite Connect App Required", warning_msg):
            webbrowser.open("https://kite.trade/")
    
    def handle_websocket_error(self, error):
        """Handle WebSocket errors appropriately"""
        error_str = str(error)
        if "403" in error_str or "Forbidden" in error_str:
            self.log_message("WebSocket 403 Error: Please use Kite Connect (paid) app credentials")
            self.show_kite_connect_warning()
        else:
            self.log_message(f"WebSocket Error: {error}")
    
    def stop_live_pnl(self):
        """Stop live P&L tracking"""
        if self.kws:
            try:
                self.kws.close()
            except:
                pass
        self.is_pnl_tracking = False
        self.ws_status_label.config(text="WebSocket: Disconnected", foreground="red")
        self.log_message("Stopped Live P&L tracking")
    
    def on_connect(self, ws, response):
        """WebSocket connect callback"""
        self.root.after(0, lambda: self.ws_status_label.config(text="WebSocket: Connected", foreground="green"))
        self.log_message("WebSocket connected successfully")
        self.ws_reconnect_attempts = 0  # Reset on successful connection
        
        # Subscribe to instruments
        self.subscribe_to_instruments()
    
    def on_close(self, ws, code, reason):
        """WebSocket close callback"""
        self.root.after(0, lambda: self.ws_status_label.config(text="WebSocket: Disconnected", foreground="red"))
        
        if "403" in str(reason) or "Forbidden" in str(reason):
            self.log_message("WebSocket closed: 403 Forbidden - Please use Kite Connect (paid) app")
            self.show_kite_connect_warning()
        else:
            self.log_message(f"WebSocket disconnected: {reason}")
        
        # Attempt reconnection for non-403 errors
        if "403" not in str(reason) and self.is_pnl_tracking:
            self.attempt_reconnect()
    
    def on_error(self, ws, code, reason):
        """WebSocket error callback"""
        self.root.after(0, lambda: self.ws_status_label.config(text="WebSocket: Error", foreground="red"))
        
        if "403" in str(reason) or "Forbidden" in str(reason):
            self.log_message(f"WebSocket 403 Error: {reason} - Please use Kite Connect (paid) app")
            self.show_kite_connect_warning()
        else:
            self.log_message(f"WebSocket error: {reason}")
            
        # Attempt reconnection for non-403 errors
        if "403" not in str(reason) and self.is_pnl_tracking:
            self.attempt_reconnect()
    
    def attempt_reconnect(self):
        """Attempt to reconnect WebSocket with exponential backoff"""
        if self.ws_reconnect_attempts >= self.max_reconnect_attempts:
            self.log_message("Max reconnection attempts reached. Please restart Live P&L manually.")
            return
        
        self.ws_reconnect_attempts += 1
        delay = min(30, 5 * self.ws_reconnect_attempts)  # Exponential backoff max 30 seconds
        
        self.log_message(f"Attempting reconnection {self.ws_reconnect_attempts}/{self.max_reconnect_attempts} in {delay} seconds...")
        
        # Schedule reconnection
        threading.Timer(delay, self.start_live_pnl).start()
    
    def on_ticks(self, ws, ticks):
        """WebSocket ticks callback - called on every price update"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.root.after(0, lambda: self.last_tick_label.config(text=timestamp))
            
            for tick in ticks:
                instrument_token = tick['instrument_token']
                last_price = tick['last_price']
                
                # Store live price
                self.live_prices[instrument_token] = last_price
                
                # Update manual P&L if this is one of our tracked instruments
                if (hasattr(self, 'current_month_data') and 
                    self.current_month_data.get('instrument') and 
                    instrument_token == self.current_month_data['instrument'].get('instrument_token')):
                    self.last_current_ltp = last_price
                    self.update_manual_pnl()
                
                if (hasattr(self, 'next_month_data') and 
                    self.next_month_data.get('instrument') and 
                    instrument_token == self.next_month_data['instrument'].get('instrument_token')):
                    self.last_next_ltp = last_price
                    self.update_manual_pnl()
                
                # Update existing positions P&L
                self.update_existing_position_pnl(instrument_token, last_price)
            
            # Update GUI
            self.update_live_display()
            
        except Exception as e:
            self.log_message(f"Error processing ticks: {e}")
    
    def subscribe_to_instruments(self):
        """Subscribe to instruments for live data"""
        try:
            tokens_to_subscribe = []
            
            # Add current and next month instruments
            current_instrument, next_instrument = self.get_instruments()
            if current_instrument:
                tokens_to_subscribe.append(current_instrument['instrument_token'])
                self.current_month_data['instrument'] = current_instrument
            if next_instrument:
                tokens_to_subscribe.append(next_instrument['instrument_token'])
                self.next_month_data['instrument'] = next_instrument
            
            # Add existing positions
            for position in self.existing_positions.values():
                if position['instrument_token'] not in tokens_to_subscribe:
                    tokens_to_subscribe.append(position['instrument_token'])
            
            if tokens_to_subscribe:
                self.kws.subscribe(tokens_to_subscribe)
                self.kws.set_mode(self.kws.MODE_LTP, tokens_to_subscribe)
                
                self.subscribed_tokens = set(tokens_to_subscribe)
                self.root.after(0, lambda: self.subscribed_tokens_label.config(text=str(len(tokens_to_subscribe))))
                self.log_message(f"Subscribed to {len(tokens_to_subscribe)} instruments for live data")
            
        except Exception as e:
            self.log_message(f"Error subscribing to instruments: {e}")
    
    def update_manual_pnl(self):
        """Update manual P&L with live prices"""
        if self.last_current_ltp > 0 and self.last_next_ltp > 0:
            self.calculate_pnl(self.last_current_ltp, self.last_next_ltp)
    
    def update_existing_position_pnl(self, instrument_token, last_price):
        """Update P&L for existing positions"""
        for tradingsymbol, position in self.existing_positions.items():
            if position['instrument_token'] == instrument_token:
                # Update position with current price
                position['last_price'] = last_price
                position['pnl'] = (last_price - position['average_price']) * position['quantity']
                
                # Update GUI
                self.refresh_positions_display()
                break
    
    def refresh_positions_display(self):
        """Refresh the positions treeview with updated data"""
        try:
            # Clear existing items
            for item in self.positions_tree.get_children():
                self.positions_tree.delete(item)
            
            total_pnl = 0
            # Add updated positions
            for symbol, position in self.existing_positions.items():
                self.add_position_to_treeview(position)
                total_pnl += position['pnl']
            
            # Update summary
            self.root.after(0, lambda: self.total_positions_pnl_label.config(text=f"₹{total_pnl:+.2f}"))
            self.root.after(0, lambda: self.update_pnl_color(self.total_positions_pnl_label, total_pnl))
                
        except Exception as e:
            pass  # Silent fail to avoid GUI update conflicts
    
    def update_live_display(self):
        """Update the main display with live data"""
        try:
            # Update current month data if available
            if self.last_current_ltp > 0:
                self.current_price_label.config(text=f"{self.last_current_ltp:.2f}")
                if self.current_month_data.get('open'):
                    current_diff = self.last_current_ltp - self.current_month_data['open']
                    current_diff_percent = (current_diff / self.current_month_data['open']) * 100
                    self.current_diff_label.config(text=f"{current_diff:+.2f} ({current_diff_percent:+.2f}%)")
                    self.update_label_color(self.current_diff_label, current_diff)
            
            # Update next month data if available
            if self.last_next_ltp > 0:
                self.next_price_label.config(text=f"{self.last_next_ltp:.2f}")
                if self.next_month_data.get('open'):
                    next_diff = self.last_next_ltp - self.next_month_data['open']
                    next_diff_percent = (next_diff / self.next_month_data['open']) * 100
                    self.next_diff_label.config(text=f"{next_diff:+.2f} ({next_diff_percent:+.2f}%)")
                    self.update_label_color(self.next_diff_label, next_diff)
            
            # Update spread
            if self.last_current_ltp > 0 and self.last_next_ltp > 0:
                spread = self.last_next_ltp - self.last_current_ltp
                spread_percent = (spread / self.last_current_ltp) * 100 if self.last_current_ltp else 0
                self.spread_label.config(text=f"{spread:+.2f}")
                self.spread_percent_label.config(text=f"{spread_percent:+.2f}%")
                self.update_label_color(self.spread_label, spread)
            
            # Update timestamp
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.update_time_label.config(text=f"Last update: {timestamp}")
            
        except Exception as e:
            pass  # Silent fail for GUI updates
    
    def fetch_existing_positions(self):
        """Fetch existing positions from Zerodha"""
        if not self.kite or not self.check_token_validity():
            messagebox.showerror("Error", "Please login first")
            return
        
        try:
            self.log_message("Fetching existing positions from Zerodha...")
            
            # Get positions from Zerodha
            positions_data = self.kite.positions()
            
            # Clear existing data
            self.existing_positions.clear()
            for item in self.positions_tree.get_children():
                self.positions_tree.delete(item)
            
            # Use only NET positions to avoid duplicates
            net_positions = positions_data.get('net', [])
            
            total_pnl = 0
            open_positions_count = 0
            
            # Process only net positions to avoid duplicates
            for position in net_positions:
                if position['quantity'] != 0:
                    self.add_position_to_treeview(position)
                    total_pnl += position['pnl']
                    open_positions_count += 1
                    # Store for tracking
                    self.existing_positions[position['tradingsymbol']] = position
            
            # Update summary
            self.total_positions_pnl_label.config(text=f"₹{total_pnl:+.2f}")
            self.update_pnl_color(self.total_positions_pnl_label, total_pnl)
            self.open_positions_label.config(text=str(open_positions_count))
            
            self.log_message(f"Fetched {open_positions_count} open positions. Total P&L: ₹{total_pnl:+.2f}")
            
            # Auto-populate manual tracking if matching symbols found
            self.auto_populate_manual_tracking()
            
            # Subscribe to these positions if WebSocket is running
            if self.kws and hasattr(self.kws, 'is_connected') and self.kws.is_connected():
                self.subscribe_to_instruments()
            
        except Exception as e:
            self.log_message(f"Error fetching positions: {e}")
            messagebox.showerror("Error", f"Failed to fetch positions: {e}")
    
    def add_position_to_treeview(self, position):
        """Add a position to the treeview with proper formatting"""
        pnl = position['pnl']
        pnl_percent = (pnl / abs(position['quantity'] * position['average_price'])) * 100 if position['quantity'] != 0 and position['average_price'] != 0 else 0
        
        item_id = self.positions_tree.insert('', tk.END, values=(
            position['tradingsymbol'],
            position['quantity'],
            f"{position['average_price']:.2f}",
            f"{position['last_price']:.2f}",
            f"₹{pnl:+.2f}",
            f"{pnl_percent:+.2f}%"
        ))
        
        # Color code based on P&L
        if pnl > 0:
            self.positions_tree.set(item_id, 'pnl', f"₹{pnl:+.2f}")
            self.positions_tree.set(item_id, 'pnl_percent', f"{pnl_percent:+.2f}%")
        elif pnl < 0:
            self.positions_tree.set(item_id, 'pnl', f"₹{pnl:+.2f}")
            self.positions_tree.set(item_id, 'pnl_percent', f"{pnl_percent:+.2f}%")
    
    def auto_populate_manual_tracking(self):
        """Auto-populate manual tracking fields based on existing positions"""
        try:
            current_symbol = self.selected_symbol
            current_month = datetime.now().strftime("%Y-%m")
            next_month = (datetime.now().replace(day=28) + timedelta(days=4)).strftime("%Y-%m")
            
            current_qty = 0
            current_avg = 0
            next_qty = 0
            next_avg = 0
            
            for symbol, position in self.existing_positions.items():
                if current_symbol in symbol:
                    # Check if it's current month or next month
                    if current_month in symbol:
                        current_qty = position['quantity']
                        current_avg = position['average_price']
                    elif next_month in symbol:
                        next_qty = position['quantity']
                        next_avg = position['average_price']
            
            # Update manual tracking fields
            if current_qty != 0:
                self.current_qty_entry.delete(0, tk.END)
                self.current_qty_entry.insert(0, str(current_qty))
                self.current_avg_entry.delete(0, tk.END)
                self.current_avg_entry.insert(0, f"{current_avg:.2f}")
            
            if next_qty != 0:
                self.next_qty_entry.delete(0, tk.END)
                self.next_qty_entry.insert(0, str(next_qty))
                self.next_avg_entry.delete(0, tk.END)
                self.next_avg_entry.insert(0, f"{next_avg:.2f}")
            
            # Update manual positions data
            if current_qty != 0 or next_qty != 0:
                self.update_positions()
                
        except Exception as e:
            self.log_message(f"Error auto-populating manual tracking: {e}")
    
    def initialize_with_saved_token(self):
        """Initialize with saved token and check validity"""
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            self.kite.set_access_token(self.access_token)
            
            # Test connection
            profile = self.kite.profile()
            self.status_label.config(text=f"Connected: {profile['user_name']}")
            self.connection_info.config(text=f"User: {profile['user_name']} | User ID: {profile['user_id']}")
            
            # Set token expiry (typically valid until market close)
            market_close = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
            if datetime.now().hour >= 15 and datetime.now().minute >= 30:
                # If market is closed, token is valid until next market open
                market_close = market_close + timedelta(days=1)
            
            self.token_expiry_time = market_close
            self.update_token_display()
            self.log_message(f"Reused saved token for: {profile['user_name']}")
            self.log_message(f"Token valid until: {market_close.strftime('%H:%M:%S')}")
            
            # Auto-fetch positions on startup if connected
            self.fetch_existing_positions()
            
        except Exception as e:
            self.log_message(f"Saved token invalid: {e}")
            self.access_token = ""
            self.save_credentials()
    
    def update_token_display(self):
        """Update token status display"""
        if self.token_expiry_time:
            time_remaining = self.token_expiry_time - datetime.now()
            if time_remaining.total_seconds() > 0:
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                self.token_status_label.config(text=f"Valid ({hours}h {minutes}m remaining)", foreground="green")
                self.token_expiry_label.config(text=f"{self.token_expiry_time.strftime('%H:%M:%S')}")
            else:
                self.token_status_label.config(text="Expired", foreground="red")
                self.token_expiry_label.config(text="N/A")
        else:
            self.token_status_label.config(text="No valid token", foreground="red")
            self.token_expiry_label.config(text="N/A")
    
    def check_token_validity(self):
        """Check if token is still valid and reconnect if needed"""
        if not self.access_token or not self.kite:
            return False
        
        try:
            # Simple API call to check token validity
            self.kite.profile()
            return True
        except Exception as e:
            self.log_message(f"Token validation failed: {e}")
            return False
    
    def on_exchange_change(self, event=None):
        self.selected_exchange = self.exchange_var.get()
        self.update_symbol_list()
        self.log_message(f"Exchange changed to: {self.selected_exchange}")
    
    def on_instrument_change(self, event=None):
        self.selected_instrument_type = self.instrument_var.get()
        self.log_message(f"Instrument type changed to: {self.selected_instrument_type}")
    
    def update_symbol_list(self):
        """Update symbol list based on selected exchange"""
        if self.selected_exchange == "NFO":
            symbols = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "RELIANCE", "TCS", "INFY", "HDFC", "ICICI", "SBIN"]
        else:  # MCX
            symbols = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER", "ZINC", "LEAD", "ALUMINIUM", "NICKEL"]
        
        self.symbol_combo['values'] = symbols
        if symbols:
            self.symbol_var.set(symbols[0])
            self.selected_symbol = symbols[0]
    
    def update_positions(self):
        """Update position quantities and average prices"""
        try:
            self.position_data['current_qty'] = int(self.current_qty_entry.get() or "0")
            self.position_data['current_avg_price'] = float(self.current_avg_entry.get() or "0")
            self.position_data['next_qty'] = int(self.next_qty_entry.get() or "0")
            self.position_data['next_avg_price'] = float(self.next_avg_entry.get() or "0")
            
            self.log_message(f"Manual positions updated - Current: {self.position_data['current_qty']} @ {self.position_data['current_avg_price']}, "
                           f"Next: {self.position_data['next_qty']} @ {self.position_data['next_avg_price']}")
            
        except ValueError as e:
            self.log_message(f"Invalid position data: {e}")
            messagebox.showerror("Error", "Please enter valid numeric values for quantity and average price")
    
    def calculate_pnl(self, current_ltp, next_ltp):
        """Calculate P&L based on positions and current prices"""
        try:
            # Calculate P&L for current month
            if self.position_data['current_qty'] != 0 and self.position_data['current_avg_price'] != 0:
                current_pnl = (current_ltp - self.position_data['current_avg_price']) * self.position_data['current_qty']
                self.position_data['current_pnl'] = current_pnl
            else:
                self.position_data['current_pnl'] = 0
            
            # Calculate P&L for next month
            if self.position_data['next_qty'] != 0 and self.position_data['next_avg_price'] != 0:
                next_pnl = (next_ltp - self.position_data['next_avg_price']) * self.position_data['next_qty']
                self.position_data['next_pnl'] = next_pnl
            else:
                self.position_data['next_pnl'] = 0
            
            # Calculate total P&L
            self.position_data['total_pnl'] = self.position_data['current_pnl'] + self.position_data['next_pnl']
            
            # Update P&L display
            self.update_pnl_display()
            
        except Exception as e:
            self.log_message(f"Error calculating P&L: {e}")
    
    def update_pnl_display(self):
        """Update P&L labels with colors"""
        # Current month P&L
        current_pnl_text = f"₹{self.position_data['current_pnl']:+.2f}"
        self.current_pnl_label.config(text=current_pnl_text)
        self.update_pnl_color(self.current_pnl_label, self.position_data['current_pnl'])
        
        # Next month P&L
        next_pnl_text = f"₹{self.position_data['next_pnl']:+.2f}"
        self.next_pnl_label.config(text=next_pnl_text)
        self.update_pnl_color(self.next_pnl_label, self.position_data['next_pnl'])
        
        # Total P&L
        total_pnl_text = f"₹{self.position_data['total_pnl']:+.2f}"
        self.total_pnl_label.config(text=total_pnl_text)
        self.update_pnl_color(self.total_pnl_label, self.position_data['total_pnl'])
        
        # P&L breakdown
        breakdown = f"Current: ₹{self.position_data['current_pnl']:+.2f} | Next: ₹{self.position_data['next_pnl']:+.2f}"
        self.pnl_breakdown_label.config(text=breakdown)
    
    def update_pnl_color(self, label, pnl_value):
        """Update P&L label color based on value"""
        if pnl_value > 0:
            label.config(foreground="green")
        elif pnl_value < 0:
            label.config(foreground="red")
        else:
            label.config(foreground="black")
    
    def update_label_color(self, label, value):
        """Update label color based on value"""
        if value > 0:
            label.config(foreground="green")
        elif value < 0:
            label.config(foreground="red")
        else:
            label.config(foreground="black")
    
    def log_message(self, message):
        """Safely log message to GUI and console"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}\n"
            
            print(log_entry.strip())
            
            if hasattr(self, 'log_text') and self.log_text:
                self.log_text.insert(tk.END, log_entry)
                self.log_text.see(tk.END)
            else:
                print("GUI log not available yet, message:", message)
                
        except Exception as e:
            print(f"Error in log_message: {e} - Original message: {message}")
    
    def load_credentials(self):
        try:
            if os.path.exists("zerodha_credentials.json"):
                with open("zerodha_credentials.json", "r") as f:
                    creds = json.load(f)
                    self.api_key = creds.get("api_key", "")
                    self.api_secret = creds.get("api_secret", "")
                    self.access_token = creds.get("access_token", "")
                    
        except Exception as e:
            print(f"Error loading credentials: {e}")
    
    def save_credentials(self):
        try:
            self.api_key = self.api_key_entry.get().strip()
            self.api_secret = self.api_secret_entry.get().strip()
            
            if not self.api_key or not self.api_secret:
                messagebox.showerror("Error", "Please enter both API Key and Secret")
                return
            
            creds = {
                "api_key": self.api_key,
                "api_secret": self.api_secret,
                "access_token": self.access_token
            }
            
            with open("zerodha_credentials.json", "w") as f:
                json.dump(creds, f)
            
            self.log_message("Credentials saved successfully")
        except Exception as e:
            self.log_message(f"Error saving credentials: {e}")
    
    def clear_token(self):
        self.access_token = ""
        self.kite = None
        if self.kws:
            try:
                self.kws.close()
            except:
                pass
            self.kws = None
        self.token_expiry_time = None
        self.is_pnl_tracking = False
        self.save_credentials()
        self.status_label.config(text="Token cleared - Not connected")
        self.connection_info.config(text="")
        self.token_status_label.config(text="No valid token", foreground="red")
        self.token_expiry_label.config(text="N/A")
        self.ws_status_label.config(text="WebSocket: Disconnected", foreground="red")
        
        # Clear positions treeview
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        
        self.log_message("Access token cleared")
    
    def start_token_server(self):
        """Start a local server to capture the redirect with request token"""
        try:
            class TokenServer(HTTPServer):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self.request_token = None
                    self.received_token = False
            
            # Find an available port
            for port in range(8000, 8020):
                try:
                    self.token_server = TokenServer(('localhost', port), TokenHandler)
                    self.token_server_port = port
                    break
                except OSError:
                    continue
            
            if not self.token_server:
                raise Exception("No available ports for token server")
            
            self.log_message(f"Token server started on port {self.token_server_port}")
            
            def serve_forever(server):
                with server:
                    server.serve_forever()
            
            self.server_thread = threading.Thread(target=serve_forever, args=(self.token_server,), daemon=True)
            self.server_thread.start()
            
            return True
            
        except Exception as e:
            self.log_message(f"Error starting token server: {e}")
            return False
    
    def auto_login(self):
        """Automated login with browser automation"""
        try:
            self.api_key = self.api_key_entry.get().strip()
            self.api_secret = self.api_secret_entry.get().strip()
            
            if not self.api_key or not self.api_secret:
                messagebox.showerror("Error", "Please enter API Key and Secret")
                return
            
            # Initialize KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)
            
            # Start token server
            if not self.start_token_server():
                raise Exception("Failed to start token server")
            
            # Generate login URL
            login_url = self.kite.login_url()
            redirect_url = f"http://localhost:{self.token_server_port}"
            full_login_url = f"{login_url}&redirect={redirect_url}"
            
            self.log_message("Opening browser for login...")
            self.log_message(f"If browser doesn't open, visit: {full_login_url}")
            
            # Open browser
            webbrowser.open(full_login_url)
            
            # Wait for token
            self.log_message("Waiting for login completion...")
            self.status_label.config(text="Waiting for login...")
            
            def wait_for_token():
                start_time = time.time()
                while time.time() - start_time < 120:  # 2 minute timeout
                    if hasattr(self.token_server, 'received_token') and self.token_server.received_token:
                        request_token = self.token_server.request_token
                        self.root.after(0, lambda: self.process_request_token(request_token))
                        return
                    time.sleep(1)
                
                self.root.after(0, lambda: self.log_message("Login timeout: No token received"))
                self.root.after(0, lambda: self.status_label.config(text="Login timeout"))
            
            threading.Thread(target=wait_for_token, daemon=True).start()
            
        except Exception as e:
            self.log_message(f"Auto login error: {e}")
            messagebox.showerror("Error", f"Auto login failed: {e}")
    
    def manual_login(self):
        """Manual login method for users who prefer to copy-paste token"""
        try:
            self.api_key = self.api_key_entry.get().strip()
            self.api_secret = self.api_secret_entry.get().strip()
            
            if not self.api_key or not self.api_secret:
                messagebox.showerror("Error", "Please enter API Key and Secret")
                return
            
            # Initialize KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)
            
            # Generate login URL
            login_url = self.kite.login_url()
            self.log_message(f"Please visit this URL to login: {login_url}")
            self.log_message("After login, copy the request_token from the redirect URL")
            
            # Ask for request token
            request_token = simpledialog.askstring("Request Token", 
                                                    "Enter request token from login redirect URL:")
            if request_token:
                self.process_request_token(request_token)
            
        except Exception as e:
            self.log_message(f"Manual login error: {e}")
            messagebox.showerror("Error", f"Manual login failed: {e}")
    
    def process_request_token(self, request_token):
        """Process the received request token and generate session"""
        try:
            self.log_message("Received request token, generating session...")
            
            # Generate session
            data = self.kite.generate_session(request_token, self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            
            # Get user profile to verify connection
            profile = self.kite.profile()
            
            # Set token expiry (typically valid until market close)
            market_close = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
            if datetime.now().hour >= 15 and datetime.now().minute >= 30:
                # If market is closed, token is valid until next market open
                market_close = market_close + timedelta(days=1)
            
            self.token_expiry_time = market_close
            
            self.save_credentials()
            self.status_label.config(text=f"Connected: {profile['user_name']}")
            self.connection_info.config(text=f"User: {profile['user_name']} | User ID: {profile['user_id']}")
            self.update_token_display()
            self.log_message(f"Login successful! Welcome {profile['user_name']}")
            self.log_message(f"Access token valid until: {market_close.strftime('%H:%M:%S')}")
            
            # Auto-fetch positions after login
            self.fetch_existing_positions()
            
        except Exception as e:
            self.log_message(f"Error processing request token: {e}")
            messagebox.showerror("Error", f"Session generation failed: {e}")
    
    def get_instruments(self):
        """Get current and next month instruments based on selection"""
        try:
            if not self.check_token_validity():
                self.log_message("Token expired, please login again")
                self.clear_token()
                return None, None
            
            self.selected_symbol = self.symbol_var.get()
            
            # Get all instruments for the selected exchange
            instruments = self.kite.instruments(self.selected_exchange)
            
            current_month = datetime.now().strftime("%Y-%m")
            next_month = (datetime.now().replace(day=28) + timedelta(days=4)).strftime("%Y-%m")
            
            # Filter instruments based on selection
            current_instruments = [inst for inst in instruments 
                                if inst["name"] == self.selected_symbol 
                                and inst["expiry"].strftime("%Y-%m") == current_month
                                and inst["instrument_type"] == self.selected_instrument_type]
            
            next_instruments = [inst for inst in instruments 
                            if inst["name"] == self.selected_symbol 
                            and inst["expiry"].strftime("%Y-%m") == next_month
                            and inst["instrument_type"] == self.selected_instrument_type]
            
            # Sort by expiry and get the nearest
            current_instruments.sort(key=lambda x: x["expiry"])
            next_instruments.sort(key=lambda x: x["expiry"])
            
            current_instrument = current_instruments[0] if current_instruments else None
            next_instrument = next_instruments[0] if next_instruments else None
            
            if current_instrument and next_instrument:
                self.log_message(f"Found instruments: {current_instrument['tradingsymbol']}, {next_instrument['tradingsymbol']}")
            else:
                self.log_message("Warning: Could not find both current and next month instruments")
            
            return current_instrument, next_instrument
            
        except Exception as e:
            self.log_message(f"Error getting instruments: {e}")
            return None, None
    
    def get_ohlc_data(self, instrument_token):
        """Get OHLC data for instrument"""
        try:
            if not self.check_token_validity():
                return None
                
            # Get today's OHLC data
            today = datetime.now().date()
            ohlc = self.kite.historical_data(instrument_token, today, today, "day")
            
            if ohlc and len(ohlc) > 0:
                return ohlc[0]
            return None
        except Exception as e:
            self.log_message(f"Error getting OHLC data: {e}")
            return None

def main():
    try:
        root = tk.Tk()
        app = ZerodhaFuturesTracker(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()