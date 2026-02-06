# import requests
# import pandas as pd
# import time
# from datetime import datetime, timedelta
# import logging
# from typing import List, Optional, Dict, Tuple
# import warnings
# import hashlib
# import webbrowser
# import urllib.parse
# import json
# import os
# warnings.filterwarnings('ignore')

# # Setup logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# class ZerodhaNaturalGasDataFetcher:
#     """
#     Fetch 1-minute natural gas futures data from Zerodha API by stitching monthly contracts.
    
#     Important Notes:
#     1. You need valid Zerodha API credentials with historical data access
#     2. This stitches data from individual monthly contracts (no continuous 1-minute data available)
#     3. Natural gas futures expire around the 20th of each month on MCX
#     4. Historical data has a rate limit of 3 requests per second
#     """
    
#     def __init__(self, api_key: str, api_secret: str, redirect_url: str = "http://localhost:8080/"):
#         """
#         Initialize with Zerodha API credentials.
        
#         Args:
#             api_key: Your Zerodha API key
#             api_secret: Your Zerodha API secret
#             redirect_url: Redirect URL configured in Zerodha developer console
#         """
#         self.api_key = api_key
#         self.api_secret = api_secret
#         self.redirect_url = redirect_url
#         self.base_url = "https://api.kite.trade"
#         self.access_token = None
#         self.token_created_at = None
#         self.headers = None
        
#         # Natural gas futures details
#         self.symbol = "NATURALGAS"
#         self.exchange = "MCX"
        
#         # Rate limiting
#         self.last_request_time = 0
#         self.min_request_interval = 0.34  # ~3 requests per second
        
#     def _generate_checksum(self, api_key: str, request_token: str, api_secret: str) -> str:
#         """Generate SHA256 checksum for access token generation."""
#         data = api_key + request_token + api_secret
#         return hashlib.sha256(data.encode()).hexdigest()
    
#     def get_login_url(self) -> str:
#         """
#         Generate login URL for user authentication.
        
#         Returns:
#             URL to open in browser for login
#         """
#         login_url = f"https://kite.trade/connect/login?api_key={self.api_key}&v=3"
#         return login_url
    
#     def get_request_token_from_url(self, url: str) -> str:
#         """
#         Extract request token from the redirect URL after login.
        
#         Args:
#             url: The redirect URL after successful login
            
#         Returns:
#             Request token string
#         """
#         try:
#             # Parse the URL to get query parameters
#             parsed = urllib.parse.urlparse(url)
#             query_params = urllib.parse.parse_qs(parsed.query)
            
#             if 'request_token' in query_params:
#                 request_token = query_params['request_token'][0]
#                 logger.info(f"Extracted request token: {request_token}")
#                 return request_token
#             else:
#                 raise ValueError("No request_token found in URL")
                
#         except Exception as e:
#             logger.error(f"Error extracting request token: {e}")
#             raise
    
#     def generate_access_token(self, request_token: str) -> Tuple[str, str]:
#         """
#         Generate access token using request token.
        
#         Args:
#             request_token: Request token obtained after login
            
#         Returns:
#             Tuple of (access_token, public_token)
#         """
#         try:
#             # Generate checksum
#             checksum = self._generate_checksum(
#                 api_key=self.api_key,
#                 request_token=request_token,
#                 api_secret=self.api_secret
#             )
            
#             # Make request to get access token
#             url = f"{self.base_url}/session/token"
#             data = {
#                 'api_key': self.api_key,
#                 'request_token': request_token,
#                 'checksum': checksum
#             }
            
#             response = requests.post(url, data=data)
#             response.raise_for_status()
            
#             data = response.json()
            
#             if data['status'] == 'success':
#                 self.access_token = data['data']['access_token']
#                 public_token = data['data']['public_token']
#                 self.token_created_at = datetime.now()  # Track when token was created
                
#                 # Update headers
#                 self.headers = {
#                     "X-Kite-Version": "3",
#                     "Authorization": f"token {self.api_key}:{self.access_token}",
#                     "User-Agent": "KiteConnect Python/3.0"
#                 }
                
#                 logger.info("Access token generated successfully")
#                 logger.info(f"Access Token: {self.access_token[:10]}...")
#                 logger.info(f"Public Token: {public_token[:10]}...")
#                 logger.info(f"Token created at: {self.token_created_at}")
                
#                 return self.access_token, public_token
#             else:
#                 raise Exception(f"Failed to generate access token: {data}")
                
#         except Exception as e:
#             logger.error(f"Error generating access token: {e}")
#             raise
    
#     def is_token_valid(self) -> bool:
#         """
#         Check if the current access token is still valid (less than 24 hours old).
        
#         Returns:
#             True if token is valid, False otherwise
#         """
#         if not self.access_token or not self.token_created_at:
#             return False
        
#         # Check if token is older than 23.5 hours (with 30 min buffer)
#         token_age = datetime.now() - self.token_created_at
#         token_age_hours = token_age.total_seconds() / 3600
        
#         # Token is valid for ~24 hours, but we'll consider it expired after 23.5 hours
#         if token_age_hours < 23.5:
#             logger.info(f"Token is {token_age_hours:.2f} hours old (still valid)")
#             return True
#         else:
#             logger.warning(f"Token is {token_age_hours:.2f} hours old (expired or about to expire)")
#             return False
    
#     def authenticate_manually(self) -> str:
#         """
#         Manual authentication flow - opens browser for login.
        
#         Returns:
#             Access token
#         """
#         try:
#             # Step 1: Generate login URL
#             login_url = self.get_login_url()
#             print("\n" + "="*60)
#             print("ZERODHA API AUTHENTICATION")
#             print("="*60)
#             print(f"\n1. Open this URL in your browser:")
#             print(f"\n{login_url}\n")
            
#             # Try to open browser automatically
#             try:
#                 webbrowser.open(login_url)
#                 print("Browser opened automatically. Please login to Zerodha.")
#             except:
#                 print("Please copy and paste the above URL in your browser.")
            
#             # Step 2: Get redirect URL from user
#             print("\n2. After login, you will be redirected to a URL.")
#             print("   Please paste the entire redirect URL here:")
#             redirect_url = input("\nRedirect URL: ").strip()
            
#             # Step 3: Extract request token
#             request_token = self.get_request_token_from_url(redirect_url)
            
#             # Step 4: Generate access token
#             access_token, public_token = self.generate_access_token(request_token)
            
#             print("\n" + "="*60)
#             print("AUTHENTICATION SUCCESSFUL!")
#             print("="*60)
#             print(f"\nAccess Token: {access_token[:20]}...")
#             print(f"Token created at: {self.token_created_at}")
#             print(f"Token valid until: {self.token_created_at + timedelta(hours=24)}")
#             print(f"Public Token: {public_token[:10]}...")
#             print("\nSave these tokens for future use.")
            
#             return access_token
            
#         except Exception as e:
#             logger.error(f"Authentication failed: {e}")
#             raise
    
#     def authenticate_with_tokens(self, access_token: str = None, token_created_at: datetime = None) -> bool:
#         """
#         Authenticate using existing access token with validation.
        
#         Args:
#             access_token: Existing access token (optional)
#             token_created_at: When the token was created (optional)
            
#         Returns:
#             True if authentication successful
#         """
#         try:
#             if access_token:
#                 self.access_token = access_token
#                 self.token_created_at = token_created_at or datetime.now()
            
#             if not self.access_token:
#                 logger.error("No access token provided")
#                 return False
            
#             # Check if token is still valid (less than 24 hours old)
#             if not self.is_token_valid():
#                 logger.warning("Token is expired or about to expire. Need to regenerate.")
#                 return False
            
#             # Update headers
#             self.headers = {
#                 "X-Kite-Version": "3",
#                 "Authorization": f"token {self.api_key}:{self.access_token}",
#                 "User-Agent": "KiteConnect Python/3.0"
#             }
            
#             # Test authentication with a simple API call
#             self._rate_limit()
#             response = requests.get(f"{self.base_url}/user/profile", headers=self.headers)
#             response.raise_for_status()
            
#             data = response.json()
#             if data['status'] == 'success':
#                 user_data = data['data']
#                 logger.info(f"Authenticated as: {user_data.get('user_name', 'Unknown')}")
#                 logger.info(f"User ID: {user_data.get('user_id', 'Unknown')}")
#                 logger.info(f"Token age: {(datetime.now() - self.token_created_at).total_seconds() / 3600:.2f} hours")
#                 return True
#             else:
#                 logger.error("Authentication test failed")
#                 return False
                
#         except requests.exceptions.HTTPError as e:
#             logger.error(f"HTTP error during authentication: {e}")
#             return False
#         except Exception as e:
#             logger.error(f"Authentication failed: {e}")
#             return False
    
#     def ensure_valid_token(self) -> bool:
#         """
#         Ensure we have a valid token, renewing if necessary.
        
#         Returns:
#             True if we have a valid token, False otherwise
#         """
#         # Check if we have a token and it's valid
#         if self.access_token and self.is_token_valid():
#             # Test if the token actually works
#             if self.authenticate_with_tokens():
#                 return True
#             else:
#                 logger.warning("Token exists but doesn't work. Need to regenerate.")
#                 self.access_token = None
#                 self.token_created_at = None
        
#         # If we get here, we need a new token
#         print("\n" + "="*60)
#         print("TOKEN VALIDATION FAILED")
#         print("="*60)
#         print("\nPossible reasons:")
#         print("1. Token is expired (older than 24 hours)")
#         print("2. Token was revoked (logged in elsewhere)")
#         print("3. No valid token available")
        
#         choice = input("\nDo you want to generate a new access token? (y/n): ").strip().lower()
        
#         if choice == 'y':
#             try:
#                 new_token = self.authenticate_manually()
#                 return self.authenticate_with_tokens(new_token)
#             except Exception as e:
#                 logger.error(f"Failed to generate new token: {e}")
#                 return False
#         else:
#             logger.error("User chose not to generate new token")
#             return False
    
#     def _rate_limit(self):
#         """Enforce rate limiting of 3 requests per second."""
#         current_time = time.time()
#         time_since_last = current_time - self.last_request_time
#         if time_since_last < self.min_request_interval:
#             time.sleep(self.min_request_interval - time_since_last)
#         self.last_request_time = time.time()
    
#     def _get_instruments(self) -> pd.DataFrame:
#         """
#         Fetch all available instruments from Zerodha.
#         This helps identify the correct instrument tokens for natural gas futures.
#         """
#         try:
#             # Ensure we have a valid token before making API calls
#             if not self.ensure_valid_token():
#                 raise Exception("Not authenticated. Need valid access token.")
            
#             logger.info("Fetching instrument list...")
#             self._rate_limit()
#             response = requests.get(f"{self.base_url}/instruments", headers=self.headers)
#             response.raise_for_status()
            
#             # Parse the CSV response
#             import io
#             df = pd.read_csv(io.StringIO(response.text))
#             return df
            
#         except Exception as e:
#             logger.error(f"Error fetching instruments: {e}")
#             raise
    
#     def _identify_monthly_contracts(self, months_back: int = 4) -> List[Dict]:
#         """
#         Identify natural gas futures contracts for the last few months.
#         """
#         try:
#             # Ensure we have a valid token
#             if not self.ensure_valid_token():
#                 raise Exception("Not authenticated. Need valid access token.")
            
#             instruments_df = self._get_instruments()
            
#             # Filter for natural gas futures on MCX
#             natural_gas_futures = instruments_df[
#                 (instruments_df['tradingsymbol'].str.contains(self.symbol, na=False)) &
#                 (instruments_df['instrument_type'] == 'FUT') &
#                 (instruments_df['exchange'] == self.exchange)
#             ].copy()
            
#             if natural_gas_futures.empty:
#                 logger.warning("No natural gas futures contracts found!")
#                 return []
            
#             # Convert expiry to datetime
#             natural_gas_futures['expiry'] = pd.to_datetime(natural_gas_futures['expiry'])
#             # Sort by expiry (newest first)
#             natural_gas_futures = natural_gas_futures.sort_values('expiry', ascending=False)
            
#             # Set current date and start date for filtering
#             current_date = pd.Timestamp(datetime.now())
#             start_date = current_date - pd.Timedelta(days=30 * months_back)
            
#             # Filter contracts active in last 'months_back' months
#             active_contracts = natural_gas_futures[
#                 (natural_gas_futures['expiry'] >= start_date)
#             ]
            
#             if active_contracts.empty:
#                 logger.warning(f"No active contracts found for the last {months_back} months")
#                 return []
            
#             # Get most recent contracts (up to months_back)
#             contracts = []
#             for _, row in active_contracts.head(months_back).iterrows():
#                 contract_info = {
#                     'instrument_token': int(row['instrument_token']),
#                     'tradingsymbol': row['tradingsymbol'],
#                     'expiry': row['expiry'],
#                     'lot_size': int(row['lot_size'])
#                 }
#                 contracts.append(contract_info)
#                 logger.info(f"Found contract: {contract_info}")
            
#             return contracts
            
#         except Exception as e:
#             logger.error(f"Error identifying contracts: {e}")
#             return []
    
#     def _fetch_contract_data(self, instrument_token: int, from_date: datetime, to_date: datetime) -> Optional[pd.DataFrame]:
#         try:
#             # Ensure we have a valid token before making API calls
#             if not self.ensure_valid_token():
#                 raise Exception("Not authenticated. Need valid access token.")
            
#             from_str = from_date.strftime('%Y-%m-%d')
#             to_str = to_date.strftime('%Y-%m-%d')

#             url = f"{self.base_url}/instruments/historical/{instrument_token}/minute"
#             params = {
#                 'from': from_str,
#                 'to': to_str,
#                 'continuous': 0,
#                 'oi': 1
#             }
#             logger.info(f"Fetching data for token {instrument_token} from {from_str} to {to_str}")
#             self._rate_limit()

#             response = requests.get(url, headers=self.headers, params=params)
#             response.raise_for_status()

#             data = response.json()

#             if data.get('status') != 'success' or 'candles' not in data.get('data', {}):
#                 logger.warning(f"No data returned for token {instrument_token}")
#                 return None

#             candles = data['data']['candles']
#             if not candles:
#                 logger.info(f"No candles data for token {instrument_token}")
#                 return None

#             df = pd.DataFrame(candles, columns=[
#                 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'
#             ])

#             df['timestamp'] = pd.to_datetime(df['timestamp'])
#             df.set_index('timestamp', inplace=True)
#             numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'oi']
#             df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')

#             logger.info(f"Fetched {len(df)} records for token {instrument_token}")
#             return df

#         except requests.exceptions.HTTPError as e:
#             logger.error(f"HTTP error for token {instrument_token}: {e}")
#             return None
#         except Exception as e:
#             logger.error(f"Error processing data for token {instrument_token}: {e}")
#             return None
    
#     def get_three_months_minute_data(self, save_to_csv: bool = True) -> pd.DataFrame:
#         """
#         Main method to get 3 months of 1-minute data by stitching monthly contracts.
        
#         Args:
#             save_to_csv: Whether to save the result to a CSV file
            
#         Returns:
#             DataFrame with 3 months of 1-minute data
#         """
#         try:
#             # Ensure we have a valid token before starting
#             if not self.ensure_valid_token():
#                 raise Exception("Not authenticated. Need valid access token.")
            
#             # Calculate date range (3 months back)
#             end_date = datetime.now()
#             start_date = end_date - timedelta(days=90)  # Approx 3 months
            
#             logger.info(f"Fetching data from {start_date.date()} to {end_date.date()}")
            
#             # Step 1: Identify monthly contracts
#             contracts = self._identify_monthly_contracts(months_back=4)
            
#             if not contracts:
#                 logger.error("Could not identify any contracts!")
#                 return pd.DataFrame()
            
#             # Step 2: Fetch data for each contract
#             all_data = []
            
#             for contract in contracts:
#                 contract_start = start_date
#                 contract_end = min(end_date, contract['expiry'])
                
#                 # Only fetch if contract was active during our period
#                 if contract_end > contract_start:
#                     contract_data = self._fetch_contract_data(
#                         contract['instrument_token'],
#                         contract_start,
#                         contract_end
#                     )
                    
#                     if contract_data is not None and not contract_data.empty:
#                         # Add contract info as columns
#                         contract_data['contract_symbol'] = contract['tradingsymbol']
#                         contract_data['expiry'] = contract['expiry']
#                         all_data.append(contract_data)
                    
#                     # Add small delay between contracts
#                     time.sleep(0.5)
            
#             if not all_data:
#                 logger.error("No data fetched from any contract!")
#                 return pd.DataFrame()
            
#             # Step 3: Combine all contract data
#             combined_df = pd.concat(all_data, axis=0)
            
#             # Sort by timestamp
#             combined_df.sort_index(inplace=True)
            
#             # Remove duplicate timestamps (keep last occurrence - typically from newer contract)
#             combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            
#             # Filter to our exact date range
#             mask = (combined_df.index >= start_date) & (combined_df.index <= end_date)
#             final_df = combined_df.loc[mask]
            
#             # Add some useful derived columns
#             final_df['returns'] = final_df['close'].pct_change()
#             final_df['price_change'] = final_df['close'].diff()
            
#             # Report statistics
#             logger.info(f"Total records fetched: {len(final_df)}")
#             logger.info(f"Date range: {final_df.index.min()} to {final_df.index.max()}")
#             logger.info(f"Unique contracts: {final_df['contract_symbol'].nunique()}")
            
#             if not final_df.empty:
#                 logger.info(f"Data shape: {final_df.shape}")
#                 logger.info(f"Columns: {', '.join(final_df.columns)}")
                
#                 # Save to CSV if requested
#                 if save_to_csv:
#                     filename = f"natural_gas_1min_{start_date.date()}_to_{end_date.date()}.csv"
#                     final_df.to_csv(filename)
#                     logger.info(f"Data saved to {filename}")
            
#             return final_df
            
#         except Exception as e:
#             logger.error(f"Error in main process: {e}")
#             raise

#     def analyze_data(self, df: pd.DataFrame):
#         """Perform basic analysis on the fetched data."""
#         if df.empty:
#             logger.warning("No data to analyze!")
#             return
        
#         print("\n" + "="*50)
#         print("DATA ANALYSIS SUMMARY")
#         print("="*50)
        
#         print(f"\n1. Basic Statistics:")
#         print(f"   Total records: {len(df):,}")
#         print(f"   Date range: {df.index.min()} to {df.index.max()}")
#         print(f"   Trading days: {df.index.normalize().nunique()}")
        
#         print(f"\n2. Price Statistics:")
#         print(f"   Average price: ₹{df['close'].mean():.2f}")
#         print(f"   Highest price: ₹{df['high'].max():.2f}")
#         print(f"   Lowest price: ₹{df['low'].min():.2f}")
#         print(f"   Daily volatility: {df['returns'].std()*100:.2f}%")
        
#         print(f"\n3. Volume Statistics:")
#         print(f"   Average volume: {df['volume'].mean():.0f}")
#         print(f"   Total volume: {df['volume'].sum():,}")
        
#         print(f"\n4. Contracts Used:")
#         contracts = df['contract_symbol'].unique()
#         for contract in contracts:
#             contract_data = df[df['contract_symbol'] == contract]
#             print(f"   • {contract}: {len(contract_data):,} records "
#                   f"({contract_data.index.min().date()} to {contract_data.index.max().date()})")
        
#         print("\n" + "="*50)


# # Enhanced Token management with expiration tracking
# class TokenManager:
#     """Helper class to manage tokens with expiration tracking."""
    
#     @staticmethod
#     def save_tokens(api_key: str, access_token: str, token_created_at: datetime, filename: str = "zerodha_tokens.json"):
#         """Save tokens to a JSON file with creation timestamp."""
#         try:
#             token_data = {
#                 'api_key': api_key,
#                 'access_token': access_token,
#                 'token_created_at': token_created_at.isoformat(),
#                 'saved_at': datetime.now().isoformat()
#             }
            
#             with open(filename, 'w') as f:
#                 json.dump(token_data, f, indent=2)
            
#             logger.info(f"Tokens saved to {filename}")
#             # Set secure file permissions
#             os.chmod(filename, 0o600)
            
#         except Exception as e:
#             logger.error(f"Error saving tokens: {e}")
    
#     @staticmethod
#     def load_tokens(filename: str = "zerodha_tokens.json") -> Dict:
#         """Load tokens from a JSON file."""
#         try:
#             if not os.path.exists(filename):
#                 logger.warning(f"Token file {filename} not found")
#                 return {}
            
#             with open(filename, 'r') as f:
#                 token_data = json.load(f)
            
#             # Convert string back to datetime
#             if 'token_created_at' in token_data:
#                 token_data['token_created_at'] = datetime.fromisoformat(token_data['token_created_at'])
            
#             if 'saved_at' in token_data:
#                 token_data['saved_at'] = datetime.fromisoformat(token_data['saved_at'])
            
#             logger.info(f"Tokens loaded from {filename}")
#             logger.info(f"Token age: {(datetime.now() - token_data['token_created_at']).total_seconds() / 3600:.2f} hours")
            
#             return token_data
            
#         except FileNotFoundError:
#             logger.warning(f"Token file {filename} not found")
#             return {}
#         except json.JSONDecodeError:
#             logger.error(f"Token file {filename} is corrupted")
#             return {}
#         except Exception as e:
#             logger.error(f"Error loading tokens: {e}")
#             return {}
    
#     @staticmethod
#     def is_token_expired(token_created_at: datetime, max_age_hours: float = 23.5) -> bool:
#         """
#         Check if token is expired.
        
#         Args:
#             token_created_at: When the token was created
#             max_age_hours: Maximum age in hours before considering expired
            
#         Returns:
#             True if expired, False otherwise
#         """
#         if not token_created_at:
#             return True
        
#         token_age = datetime.now() - token_created_at
#         token_age_hours = token_age.total_seconds() / 3600
        
#         return token_age_hours >= max_age_hours


# # Example usage script with automatic token validation
# def main():
#     """
#     Example script to fetch 3 months of natural gas 1-minute data.
    
#     Before running:
#     1. Install required packages: pip install pandas requests
#     2. Get your Zerodha API credentials from kite.trade
#     3. Ensure you have historical data permissions
#     """
    
#     # ============================================
#     # CONFIGURATION - REPLACE WITH YOUR CREDENTIALS
#     # ============================================
#     API_KEY = "wahkpp6wk6bpou2c"  # Replace with your API key
#     API_SECRET = "x3uniopsi4kau5tlgjc5d52i6nhg4wxq"  # Replace with your API secret
#     REDIRECT_URL = "http://localhost:8080/"  # Must match your Zerodha console setting
    
#     if API_KEY == "" or API_SECRET == "":
#         print("ERROR: Please replace the API_KEY and API_SECRET with your actual credentials!")
#         print("Get them from: https://kite.trade/")
#         return
    
#     # Initialize the data fetcher
#     fetcher = ZerodhaNaturalGasDataFetcher(
#         api_key=API_KEY,
#         api_secret=API_SECRET,
#         redirect_url=REDIRECT_URL
#     )
    
#     # Try to load existing tokens first
#     token_manager = TokenManager()
#     saved_tokens = token_manager.load_tokens()
    
#     access_token = None
#     token_created_at = None
    
#     if saved_tokens.get('api_key') == API_KEY and saved_tokens.get('access_token'):
#         # Check if saved token is expired
#         token_created_at = saved_tokens.get('token_created_at')
        
#         if TokenManager.is_token_expired(token_created_at):
#             print("Saved token is expired. Need to generate new one...")
#         else:
#             print(f"Found saved access token (age: {(datetime.now() - token_created_at).total_seconds() / 3600:.2f} hours)")
#             print("Testing authentication...")
            
#             if fetcher.authenticate_with_tokens(saved_tokens['access_token'], token_created_at):
#                 print("✓ Authentication successful with saved token!")
#                 access_token = saved_tokens['access_token']
#             else:
#                 print("✗ Saved token invalid. Starting new authentication...")
    
#     # If no valid token, start authentication
#     if not access_token:
#         access_token = fetcher.authenticate_manually()
#         token_created_at = fetcher.token_created_at
        
#         # Save new token
#         token_manager.save_tokens(API_KEY, access_token, token_created_at)
    
#     try:
#         # Fetch 3 months of 1-minute data
#         print("\n" + "="*60)
#         print("STARTING DATA FETCH")
#         print("="*60)
#         print(f"Token valid until: {token_created_at + timedelta(hours=24)}")
        
#         data = fetcher.get_three_months_minute_data(save_to_csv=True)
        
#         if not data.empty:
#             # Display sample data
#             print("\nFirst few records:")
#             print(data.head())
            
#             print("\nLast few records:")
#             print(data.tail())
            
#             # Perform analysis
#             fetcher.analyze_data(data)
            
#             # Display data quality info
#             print("\n" + "="*50)
#             print("DATA QUALITY CHECK")
#             print("="*50)
#             print(f"Missing values: {data.isnull().sum().sum()}")
#             print(f"Duplicate timestamps removed: {len(data[data.index.duplicated()]) if data.index.duplicated().any() else 0}")
            
#             # Check for gaps in data
#             time_diff = data.index.to_series().diff()
#             gaps = time_diff[time_diff > pd.Timedelta(minutes=5)]
#             if not gaps.empty:
#                 print(f"\nWarning: Found {len(gaps)} data gaps > 5 minutes")
#                 print("Largest gap:", gaps.max())
#         else:
#             print("No data was fetched. Please check:")
#             print("1. Your API credentials")
#             print("2. Whether you have historical data permissions")
#             print("3. If natural gas futures contracts exist for the period")
            
#     except Exception as e:
#         print(f"Error occurred: {e}")
#         print("\nTroubleshooting tips:")
#         print("1. Verify your API credentials are correct")
#         print("2. Check if your access token is still valid (expires in 24 hours)")
#         print("3. Ensure you're within API rate limits")
#         print("4. Try with a shorter time period first")
#         print("5. Check if market was open during the requested period")


# # Run the main function
# if __name__ == "__main__":
#     main()
# from kiteconnect import KiteConnect
# import pandas as pd
# from datetime import datetime

# kite = KiteConnect(api_key="wahkpp6wk6bpou2c")
# kite.set_access_token("YOUR_ACCESS_TOKEN")

# instrument_token = 123456  # MCX Natural Gas token
# from_date = datetime(2024, 1, 1)
# to_date   = datetime(2024, 12, 31)

# data = kite.historical_data(
#     instrument_token,
#     from_date,
#     to_date,
#     interval="5minute"   # 1minute, 15minute, day
# )

# df = pd.DataFrame(data)
# df.to_csv("NG_historical.csv", index=False)


# import yfinance as yf

# ng = yf.download("NG=F", start="2015-01-01", interval="1d")
# ng.to_csv("ng_daily.csv")

# import yfinance as yf

# ng = yf.download(
#     tickers="NG=F",
#     period="3mo",       # ~90 days
#     interval="5m",
#     progress=False
# )

# ng.to_csv("ng_2min_last_3_months.csv")

import yfinance as yf
#from tvDatafeed import TvDatafeed, Interval

#tv = TvDatafeed()

df = yf.download(
    tickers="NG=F",
    period="59d",       # ~90 days
    interval="5m",
    progress=False
)

if df is None or df.empty:
    print("❌ No data returned from Yahoo Finance")
else:
    df.to_csv("ng_1min_last_7_days.csv")
    print("✅ Data saved:", df.shape)
