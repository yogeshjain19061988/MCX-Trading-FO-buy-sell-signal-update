import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import logging
from typing import List, Optional, Dict
import warnings
warnings.filterwarnings('ignore')

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ZerodhaNaturalGasDataFetcher:
    """
    Fetch 1-minute natural gas futures data from Zerodha API by stitching monthly contracts.
    
    Important Notes:
    1. You need valid Zerodha API credentials with historical data access
    2. This stitches data from individual monthly contracts (no continuous 1-minute data available)
    3. Natural gas futures expire around the 20th of each month on MCX
    4. Historical data has a rate limit of 3 requests per second
    """
    
    def __init__(self, api_key: str, access_token: str):
        """
        Initialize with Zerodha API credentials.
        
        Args:
            api_key: Your Zerodha API key
            access_token: Your Zerodha access token
        """
        self.api_key = api_key
        self.access_token = access_token
        self.base_url = "https://api.kite.trade"
        self.headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{access_token}",
            "User-Agent": "KiteConnect Python/3.0"
        }
        
        # Natural gas futures details
        self.symbol = "NATGAS"
        self.exchange = "MCX"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.34  # ~3 requests per second
        
    def _rate_limit(self):
        """Enforce rate limiting of 3 requests per second."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _get_instruments(self) -> pd.DataFrame:
        """
        Fetch all available instruments from Zerodha.
        This helps identify the correct instrument tokens for natural gas futures.
        """
        try:
            logger.info("Fetching instrument list...")
            self._rate_limit()
            response = requests.get(f"{self.base_url}/instruments", headers=self.headers)
            response.raise_for_status()
            
            # Parse the CSV response
            import io
            df = pd.read_csv(io.StringIO(response.text))
            return df
            
        except Exception as e:
            logger.error(f"Error fetching instruments: {e}")
            raise
    
    def _identify_monthly_contracts(self, months_back: int = 4) -> List[Dict]:
        """
        Identify natural gas futures contracts for the last few months.
        
        Args:
            months_back: How many months to look back (including current month)
            
        Returns:
            List of contract information dictionaries
        """
        try:
            instruments_df = self._get_instruments()
            
            # Filter for natural gas futures on MCX
            natural_gas_futures = instruments_df[
                (instruments_df['tradingsymbol'].str.contains(self.symbol, na=False)) &
                (instruments_df['instrument_type'] == 'FUT') &
                (instruments_df['exchange'] == self.exchange)
            ].copy()
            
            if natural_gas_futures.empty:
                logger.warning("No natural gas futures contracts found!")
                return []
            
            # Sort by expiry (newest first)
            natural_gas_futures['expiry'] = pd.to_datetime(natural_gas_futures['expiry'])
            natural_gas_futures = natural_gas_futures.sort_values('expiry', ascending=False)
            
            # Get current date and calculate date range
            current_date = datetime.now()
            start_date = current_date - timedelta(days=30*months_back)
            
            # Filter contracts that were active in our time period
            active_contracts = natural_gas_futures[
                (natural_gas_futures['expiry'] >= start_date)
            ]
            
            if active_contracts.empty:
                logger.warning(f"No active contracts found for the last {months_back} months")
                return []
            
            # Get the most recent contracts (typically need 3-4 contracts for 3 months)
            contracts = []
            for _, row in active_contracts.head(months_back).iterrows():
                contract_info = {
                    'instrument_token': int(row['instrument_token']),
                    'tradingsymbol': row['tradingsymbol'],
                    'expiry': row['expiry'].date(),
                    'lot_size': int(row['lot_size'])
                }
                contracts.append(contract_info)
                logger.info(f"Found contract: {contract_info}")
            
            return contracts
            
        except Exception as e:
            logger.error(f"Error identifying contracts: {e}")
            return []
    
    def _fetch_contract_data(self, instrument_token: int, 
                           from_date: datetime, to_date: datetime) -> Optional[pd.DataFrame]:
        """
        Fetch 1-minute historical data for a specific contract.
        
        Args:
            instrument_token: Zerodha instrument token
            from_date: Start date for data
            to_date: End date for data
            
        Returns:
            DataFrame with OHLCV data or None if error
        """
        try:
            # Format dates for API
            from_str = from_date.strftime('%Y-%m-%d')
            to_str = to_date.strftime('%Y-%m-%d')
            
            # API endpoint for historical data
            url = f"{self.base_url}/instruments/historical/{instrument_token}/minute"
            params = {
                'from': from_str,
                'to': to_str,
                'continuous': 0,  # 0 for individual contracts
                'oi': 1           # Include open interest
            }
            
            logger.info(f"Fetching data for token {instrument_token} from {from_str} to {to_str}")
            self._rate_limit()
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'success' or 'candles' not in data.get('data', {}):
                logger.warning(f"No data returned for token {instrument_token}")
                return None
            
            candles = data['data']['candles']
            
            if not candles:
                logger.info(f"No candles data for token {instrument_token}")
                return None
            
            # Parse candles into DataFrame
            df = pd.DataFrame(candles, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'
            ])
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Convert numeric columns
            numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'oi']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            
            logger.info(f"Fetched {len(df)} records for token {instrument_token}")
            return df
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API error for token {instrument_token}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing data for token {instrument_token}: {e}")
            return None
    
    def get_three_months_minute_data(self, save_to_csv: bool = True) -> pd.DataFrame:
        """
        Main method to get 3 months of 1-minute data by stitching monthly contracts.
        
        Args:
            save_to_csv: Whether to save the result to a CSV file
            
        Returns:
            DataFrame with 3 months of 1-minute data
        """
        try:
            # Calculate date range (3 months back)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)  # Approx 3 months
            
            logger.info(f"Fetching data from {start_date.date()} to {end_date.date()}")
            
            # Step 1: Identify monthly contracts
            contracts = self._identify_monthly_contracts(months_back=4)
            
            if not contracts:
                logger.error("Could not identify any contracts!")
                return pd.DataFrame()
            
            # Step 2: Fetch data for each contract
            all_data = []
            
            for contract in contracts:
                contract_start = start_date
                contract_end = min(end_date, contract['expiry'])
                
                # Only fetch if contract was active during our period
                if contract_end > contract_start:
                    contract_data = self._fetch_contract_data(
                        contract['instrument_token'],
                        contract_start,
                        contract_end
                    )
                    
                    if contract_data is not None and not contract_data.empty:
                        # Add contract info as columns
                        contract_data['contract_symbol'] = contract['tradingsymbol']
                        contract_data['expiry'] = contract['expiry']
                        all_data.append(contract_data)
                    
                    # Add small delay between contracts
                    time.sleep(0.5)
            
            if not all_data:
                logger.error("No data fetched from any contract!")
                return pd.DataFrame()
            
            # Step 3: Combine all contract data
            combined_df = pd.concat(all_data, axis=0)
            
            # Sort by timestamp
            combined_df.sort_index(inplace=True)
            
            # Remove duplicate timestamps (keep last occurrence - typically from newer contract)
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            
            # Filter to our exact date range
            mask = (combined_df.index >= start_date) & (combined_df.index <= end_date)
            final_df = combined_df.loc[mask]
            
            # Add some useful derived columns
            final_df['returns'] = final_df['close'].pct_change()
            final_df['price_change'] = final_df['close'].diff()
            
            # Report statistics
            logger.info(f"Total records fetched: {len(final_df)}")
            logger.info(f"Date range: {final_df.index.min()} to {final_df.index.max()}")
            logger.info(f"Unique contracts: {final_df['contract_symbol'].nunique()}")
            
            if not final_df.empty:
                logger.info(f"Data shape: {final_df.shape}")
                logger.info(f"Columns: {', '.join(final_df.columns)}")
                
                # Save to CSV if requested
                if save_to_csv:
                    filename = f"natural_gas_1min_{start_date.date()}_to_{end_date.date()}.csv"
                    final_df.to_csv(filename)
                    logger.info(f"Data saved to {filename}")
            
            return final_df
            
        except Exception as e:
            logger.error(f"Error in main process: {e}")
            raise

    def analyze_data(self, df: pd.DataFrame):
        """Perform basic analysis on the fetched data."""
        if df.empty:
            logger.warning("No data to analyze!")
            return
        
        print("\n" + "="*50)
        print("DATA ANALYSIS SUMMARY")
        print("="*50)
        
        print(f"\n1. Basic Statistics:")
        print(f"   Total records: {len(df):,}")
        print(f"   Date range: {df.index.min()} to {df.index.max()}")
        print(f"   Trading days: {df.index.normalize().nunique()}")
        
        print(f"\n2. Price Statistics:")
        print(f"   Average price: ₹{df['close'].mean():.2f}")
        print(f"   Highest price: ₹{df['high'].max():.2f}")
        print(f"   Lowest price: ₹{df['low'].min():.2f}")
        print(f"   Daily volatility: {df['returns'].std()*100:.2f}%")
        
        print(f"\n3. Volume Statistics:")
        print(f"   Average volume: {df['volume'].mean():.0f}")
        print(f"   Total volume: {df['volume'].sum():,}")
        
        print(f"\n4. Contracts Used:")
        contracts = df['contract_symbol'].unique()
        for contract in contracts:
            contract_data = df[df['contract_symbol'] == contract]
            print(f"   • {contract}: {len(contract_data):,} records "
                  f"({contract_data.index.min().date()} to {contract_data.index.max().date()})")
        
        print("\n" + "="*50)

# Example usage script
def main():
    """
    Example script to fetch 3 months of natural gas 1-minute data.
    
    Before running:
    1. Install required packages: pip install pandas requests
    2. Get your Zerodha API credentials from kite.trade
    3. Ensure you have historical data permissions
    """
    
    # ============================================
    # CONFIGURATION - REPLACE WITH YOUR CREDENTIALS
    # ============================================
    API_KEY = "YOUR_API_KEY_HERE"  # Replace with your API key
    ACCESS_TOKEN = "YOUR_ACCESS_TOKEN_HERE"  # Replace with your access token
    
    if API_KEY == "YOUR_API_KEY_HERE" or ACCESS_TOKEN == "YOUR_ACCESS_TOKEN_HERE":
        print("ERROR: Please replace the API_KEY and ACCESS_TOKEN with your actual credentials!")
        print("Get them from: https://kite.trade/")
        return
    
    # Initialize the data fetcher
    fetcher = ZerodhaNaturalGasDataFetcher(api_key=API_KEY, access_token=ACCESS_TOKEN)
    
    try:
        # Fetch 3 months of 1-minute data
        print("Starting data fetch process...")
        data = fetcher.get_three_months_minute_data(save_to_csv=True)
        
        if not data.empty:
            # Display sample data
            print("\nFirst few records:")
            print(data.head())
            
            print("\nLast few records:")
            print(data.tail())
            
            # Perform analysis
            fetcher.analyze_data(data)
            
            # Display data quality info
            print("\n" + "="*50)
            print("DATA QUALITY CHECK")
            print("="*50)
            print(f"Missing values: {data.isnull().sum().sum()}")
            print(f"Duplicate timestamps removed: {len(data[data.index.duplicated()]) if data.index.duplicated().any() else 0}")
            
            # Check for gaps in data
            time_diff = data.index.to_series().diff()
            gaps = time_diff[time_diff > pd.Timedelta(minutes=5)]
            if not gaps.empty:
                print(f"\nWarning: Found {len(gaps)} data gaps > 5 minutes")
                print("Largest gap:", gaps.max())
        else:
            print("No data was fetched. Please check:")
            print("1. Your API credentials")
            print("2. Whether you have historical data permissions")
            print("3. If natural gas futures contracts exist for the period")
            
    except Exception as e:
        print(f"Error occurred: {e}")
        print("\nTroubleshooting tips:")
        print("1. Verify your API credentials are correct")
        print("2. Check if your access token is still valid")
        print("3. Ensure you're within API rate limits")
        print("4. Try with a shorter time period first")

if __name__ == "__main__":
    main()