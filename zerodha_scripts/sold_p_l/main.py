from kiteconnect import KiteConnect
import pandas as pd

# --------------------------
# CONFIGURATION
# --------------------------
api_key = "5urwq90z9w08qrkm"
access_token = "your_access_token"

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# --------------------------
# FETCH POSITIONS
# --------------------------
positions = kite.positions()

# Combine day and net positions if needed
net_positions = positions['net']

# Convert to DataFrame for easy filtering
df = pd.DataFrame(net_positions)

# --------------------------
# FILTER SOLD OPTIONS
# --------------------------
# 'tradingsymbol' contains 'CE' or 'PE' for options
sold_options = df[
    (df['tradingsymbol'].str.contains('CE|PE', case=False, na=False)) &
    (df['quantity'] < 0)
]

# --------------------------
# CALCULATE CURRENT PROFIT
# --------------------------
# P&L = (Last Price - Average Price) * Quantity
sold_options['current_pl'] = (sold_options['last_price'] - sold_options['average_price']) * sold_options['quantity']

# Reverse sign (since quantity is negative for sold)
sold_options['current_pl'] = -sold_options['current_pl']

# --------------------------
# DISPLAY RESULTS
# --------------------------
if not sold_options.empty:
    print("Current Profit/Loss for Sold Options:")
    print(sold_options[['tradingsymbol', 'quantity', 'average_price', 'last_price', 'current_pl']])
    print("\nTotal P&L:", sold_options['current_pl'].sum())
else:
    print("No sold options found in current positions.")
