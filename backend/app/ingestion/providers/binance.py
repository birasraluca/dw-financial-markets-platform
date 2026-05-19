import os
import requests
from datetime import datetime, timezone


BINANCE_API_BASE_URL = os.getenv(
    "BINANCE_API_BASE_URL",
    "https://api.binance.com/api/v3"
)


def to_milliseconds(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_klines(symbol: str, interval: str, start_time_ms: int, end_time_ms: int, limit: int = 1000):
    url = f"{BINANCE_API_BASE_URL}/klines"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": limit,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json(), str(response.url)


def normalize_klines(symbol: str, asset_name: str, raw_payload):
    rows = []

    for item in raw_payload:
        # Binance kline format:
        # [
        #   0 open time,
        #   1 open,
        #   2 high,
        #   3 low,
        #   4 close,
        #   5 volume,
        #   6 close time,
        #   ...
        # ]
        open_time_ms = item[0]

        rows.append({
            "asset": {
                "symbol": symbol.upper(),
                "name": asset_name,
                "assetClass": "crypto",
                "region": "global",
                "attributes": {
                    "exchange": "Binance",
                    "market_type": "spot"
                },
                "provider_mappings": {
                    "binance_symbol": symbol.upper()
                }
            },
            "ts": datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
            "metrics": {
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        })

    return rows