"""
Zerodha NIFTY CE/PE Difference Trading Bot
File: zerodha_nifty_diff_bot.py

WHAT IT DOES
- Connects to Kite Connect using API key + access token saved in a file
- Monitors live LTP for a specified NIFTY CE and PE pair
- Enters a directional pair trade when CE-PE difference crosses configured thresholds
  (example: if CE - PE > ENTRY_DIFF then SELL CE + BUY PE)
- Monitors combined P&L and exits both legs on target profit or max loss
- Logs orders, fills, and P&L to a CSV log

NOTES / SAFETY
- You must generate a fresh access token each trading day (or automate it separately)
- Test this script thoroughly in paper/demo before running with real money
- Update SYMBOLS, LOT_SIZE, API_KEY, and thresholds to match your setup

DEPENDENCIES
- pip install kiteconnect pandas

USAGE
- Edit the CONFIG section below with your API_KEY, ACCESS_TOKEN or use the request_token flow
- Run: python zerodha_nifty_diff_bot.py

"""

import time
import csv
import logging
from datetime import datetime
from kiteconnect import KiteConnect

# ----------------------- CONFIG -----------------------
API_KEY = "5urwq90z9w08qrkm"
API_SECRET = "qfqy3blh4dldp3f59105afhmwlg1cj7o"
ACCESS_TOKEN_FILE = "access_token.txt"  # file with today's access token
LOG_CSV = "nifty_diff_trades.csv"

# Symbols: update to the exact tradingsymbols you want (expiry/strike/style)
CE_SYMBOL = "NIFTY24OCT24400CE"  # example
PE_SYMBOL = "NIFTY24OCT24400PE"
EXCHANGE = "NFO"  # NIFTY options are in NFO
LOT_SIZE = 50       # NIFTY lot size (usually 50) - set correctly

# Strategy parameters
ENTRY_DIFF_UPPER = 50    # if CE - PE > this => trigger SELL CE + BUY PE
ENTRY_DIFF_LOWER = -50   # if CE - PE < this => trigger BUY CE + SELL PE
QTY_LOTS = 1             # Number of lots to trade (qty = LOT_SIZE * QTY_LOTS)
TRADE_QTY = LOT_SIZE * QTY_LOTS

TARGET_PROFIT = 5000     # combined rupee profit to exit
MAX_LOSS = 7000          # combined rupee loss to exit
POLL_INTERVAL = 3        # seconds between LTP polls

# Order settings
ORDER_PRODUCT = "MIS"   # MIS for intraday, NRML for overnight
ORDER_TYPE = "MARKET"   # MARKET or LIMIT

# ----------------------- LOGGING -----------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# ----------------------- HELPERS -----------------------

def save_access_token(token: str):
    with open(ACCESS_TOKEN_FILE, 'w') as f:
        f.write(token)


def load_access_token() -> str:
    try:
        with open(ACCESS_TOKEN_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def generate_login_url():
    import requests
    import webbrowser
    url = 'https://kite.trade/connect/login?api_key=5urwq90z9w08qrkm'
    resp = requests.post(url)
    webbrowser.open(url)
    #print(resp.text)
    # kite = KiteConnect(api_key=API_KEY)
    # url = kite.login_url()
    # print("Open this URL in your browser, login and paste the request_token to generate access token:")
    # print(url)
    # import webbrowser

    #url = "https://www.example.com"
    #r = webbrowser.open(url)  # Opens in a new tab or window
    #print(r)
    #return url


def generate_access_token_from_request_token(request_token: str) -> str:
    kite = KiteConnect(api_key=API_KEY)
    data = kite.generate_session(request_token, api_secret=API_SECRET)
    print(data)
    access_token = data.get('access_token')
    save_access_token(access_token)
    logger.info('Generated and saved access token')
    return access_token


def init_kite():
    #generate_access_token_from_request_token()
    intputAcc = input("Enter the request token")
    access_token = intputAcc
    if not access_token:
        logger.error('No access token found. Run generate_login_url() and generate_access_token_from_request_token(request_token)')
        raise RuntimeError('Access token required')
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(access_token)
    return kite


def get_ltp(kite, symbol: str) -> float:
    key = f"{EXCHANGE}:{symbol}"
    data = kite.ltp(key)
    # data example: {'NFO:NIFTY24OCT24400CE': {'last_price': 123.45, ...}}
    return float(data[key]['last_price'])


def place_order(kite, symbol: str, transaction_type: str, quantity: int, product: str = ORDER_PRODUCT, order_type: str = ORDER_TYPE):
    resp = kite.place_order(
        variety=kite.VARIETY_REGULAR,
        exchange=EXCHANGE,
        tradingsymbol=symbol,
        transaction_type=transaction_type,
        quantity=quantity,
        order_type=getattr(kite, f"ORDER_TYPE_{order_type}"),
        product=getattr(kite, f"PRODUCT_{product}"),
    )
    return resp


def fetch_order_trades(kite, order_id: str):
    # returns list of trades for the order (may be empty until executed)
    return kite.trades(order_id=order_id)


def log_trade(row: dict):
    header = [
        'timestamp', 'action', 'symbol', 'qty', 'order_id', 'executed_price', 'combined_pnl'
    ]
    file_exists = False
    try:
        with open(LOG_CSV, 'r') as f:
            file_exists = True
    except FileNotFoundError:
        file_exists = False

    with open(LOG_CSV, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ----------------------- STRATEGY -----------------------

def calculate_combined_pnl(kite, entry_prices: dict, qty: int) -> (float, dict):
    # PnL = (entry_price - current_price) for short; (current - entry) for long
    ce_ltp = get_ltp(kite, CE_SYMBOL)
    pe_ltp = get_ltp(kite, PE_SYMBOL)

    # entry_prices: {'CE': price, 'PE': price, 'CE_side': 'SELL'/'BUY', 'PE_side': 'SELL'/'BUY'}
    ce_pnl = 0.0
    pe_pnl = 0.0

    # CE leg
    if entry_prices['CE_side'] == 'SELL':
        ce_pnl = (entry_prices['CE'] - ce_ltp) * qty
    else:
        ce_pnl = (ce_ltp - entry_prices['CE']) * qty

    # PE leg
    if entry_prices['PE_side'] == 'SELL':
        pe_pnl = (entry_prices['PE'] - pe_ltp) * qty
    else:
        pe_pnl = (pe_ltp - entry_prices['PE']) * qty

    total = ce_pnl + pe_pnl
    details = {'ce_ltp': ce_ltp, 'pe_ltp': pe_ltp, 'ce_pnl': ce_pnl, 'pe_pnl': pe_pnl}
    return total, details


def enter_pair_trade(kite, direction: str, qty: int):
    """direction: 'CE_MINUS_PE_HIGH' means CE much higher => SELL CE + BUY PE
       'PE_MINUS_CE_HIGH' means PE much higher => BUY CE + SELL PE
    Returns entry_prices dict and order ids
    """
    # Place two market orders sequentially and attempt to fetch executed prices
    if direction == 'CE_MINUS_PE_HIGH':
        # SELL CE, BUY PE
        resp_ce = place_order(kite, CE_SYMBOL, kite.TRANSACTION_TYPE_SELL, qty)
        time.sleep(0.2)
        resp_pe = place_order(kite, PE_SYMBOL, kite.TRANSACTION_TYPE_BUY, qty)
        ce_side = 'SELL'
        pe_side = 'BUY'
    else:
        # BUY CE, SELL PE
        resp_ce = place_order(kite, CE_SYMBOL, kite.TRANSACTION_TYPE_BUY, qty)
        time.sleep(0.2)
        resp_pe = place_order(kite, PE_SYMBOL, kite.TRANSACTION_TYPE_SELL, qty)
        ce_side = 'BUY'
        pe_side = 'SELL'

    # Try to read executed prices from order trades (may require a short wait)
    time.sleep(0.5)
    ce_trades = kite.trades(order_id=resp_ce)
    pe_trades = kite.trades(order_id=resp_pe)

    def avg_trade_price(trades):
        if not trades:
            return None
        total_qty = 0
        weighted = 0.0
        for t in trades:
            total_qty += t['quantity']
            weighted += t['quantity'] * float(t['price'])
        return weighted / total_qty if total_qty else None

    ce_ex = avg_trade_price(ce_trades) or get_ltp(kite, CE_SYMBOL)
    pe_ex = avg_trade_price(pe_trades) or get_ltp(kite, PE_SYMBOL)

    entry = {'CE': ce_ex, 'PE': pe_ex, 'CE_side': ce_side, 'PE_side': pe_side, 'CE_order_id': resp_ce, 'PE_order_id': resp_pe}
    logger.info('Entered pair trade: %s', entry)

    # Log initial fills
    row_ce = {'timestamp': datetime.now().isoformat(), 'action': f'ENTER_{ce_side}', 'symbol': CE_SYMBOL, 'qty': qty, 'order_id': resp_ce, 'executed_price': ce_ex, 'combined_pnl': ''}
    row_pe = {'timestamp': datetime.now().isoformat(), 'action': f'ENTER_{pe_side}', 'symbol': PE_SYMBOL, 'qty': qty, 'order_id': resp_pe, 'executed_price': pe_ex, 'combined_pnl': ''}
    log_trade(row_ce)
    log_trade(row_pe)

    return entry


def exit_pair_trade(kite, entry: dict, qty: int):
    # To exit, place opposite-side orders for both legs
    # If entry had SELL on CE, we BUY to exit
    if entry['CE_side'] == 'SELL':
        resp_ce = place_order(kite, CE_SYMBOL, kite.TRANSACTION_TYPE_BUY, qty)
    else:
        resp_ce = place_order(kite, CE_SYMBOL, kite.TRANSACTION_TYPE_SELL, qty)

    time.sleep(0.2)

    if entry['PE_side'] == 'SELL':
        resp_pe = place_order(kite, PE_SYMBOL, kite.TRANSACTION_TYPE_BUY, qty)
    else:
        resp_pe = place_order(kite, PE_SYMBOL, kite.TRANSACTION_TYPE_SELL, qty)

    # fetch executed prices
    time.sleep(0.5)
    ce_trades = kite.trades(order_id=resp_ce)
    pe_trades = kite.trades(order_id=resp_pe)

    def avg_trade_price(trades):
        if not trades:
            return None
        total_qty = 0
        weighted = 0.0
        for t in trades:
            total_qty += t['quantity']
            weighted += t['quantity'] * float(t['price'])
        return weighted / total_qty if total_qty else None

    ce_ex = avg_trade_price(ce_trades) or get_ltp(kite, CE_SYMBOL)
    pe_ex = avg_trade_price(pe_trades) or get_ltp(kite, PE_SYMBOL)

    # Log exits and combined pnl
    total_pnl, details = calculate_combined_pnl(kite, entry, qty)
    row_ce = {'timestamp': datetime.now().isoformat(), 'action': 'EXIT', 'symbol': CE_SYMBOL, 'qty': qty, 'order_id': resp_ce, 'executed_price': ce_ex, 'combined_pnl': total_pnl}
    row_pe = {'timestamp': datetime.now().isoformat(), 'action': 'EXIT', 'symbol': PE_SYMBOL, 'qty': qty, 'order_id': resp_pe, 'executed_price': pe_ex, 'combined_pnl': total_pnl}
    log_trade(row_ce)
    log_trade(row_pe)

    logger.info('Exited pair trade. Combined PnL: %.2f | details: %s', total_pnl, details)
    return total_pnl, details


# ----------------------- MAIN LOOP -----------------------

def main():
    kite = init_kite()
    logger.info('Connected to Kite')

    in_position = False
    entry = None

    try:
        while True:
            try:
                ce = get_ltp(kite, CE_SYMBOL)
                pe = get_ltp(kite, PE_SYMBOL)
                diff = ce - pe
                logger.info('LTPs -> CE: %.2f | PE: %.2f | Diff (CE-PE): %.2f', ce, pe, diff)

                if not in_position:
                    if diff > ENTRY_DIFF_UPPER:
                        logger.info('Entry condition met: CE-PE > %s -> SELL CE + BUY PE', ENTRY_DIFF_UPPER)
                        entry = enter_pair_trade(kite, 'CE_MINUS_PE_HIGH', TRADE_QTY)
                        in_position = True
                    elif diff < ENTRY_DIFF_LOWER:
                        logger.info('Entry condition met: CE-PE < %s -> BUY CE + SELL PE', ENTRY_DIFF_LOWER)
                        entry = enter_pair_trade(kite, 'PE_MINUS_CE_HIGH', TRADE_QTY)
                        in_position = True

                else:
                    total_pnl, details = calculate_combined_pnl(kite, entry, TRADE_QTY)
                    logger.info('In-position PnL: %.2f | details: %s', total_pnl, details)

                    if total_pnl >= TARGET_PROFIT:
                        logger.info('Target profit reached -> exiting')
                        exit_pair_trade(kite, entry, TRADE_QTY)
                        in_position = False
                        entry = None
                    elif total_pnl <= -abs(MAX_LOSS):
                        logger.warning('Max loss hit -> exiting')
                        exit_pair_trade(kite, entry, TRADE_QTY)
                        in_position = False
                        entry = None

                time.sleep(POLL_INTERVAL)

            except Exception as e:
                logger.exception('Error in main loop: %s', e)
                time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info('User interrupted. Exiting...')


if __name__ == '__main__':
    print('Zerodha NIFTY CE/PE difference trading bot')
    print('Edit config and run. Use generate_login_url() to get request_token if needed.')
    #generate_login_url()
    main()
