import os
import requests
from datetime import datetime


FRANKFURTER_API_BASE_URL = os.getenv("FRANKFURTER_API_BASE_URL", "https://api.frankfurter.dev/v2")


def fetch_fx_time_series(base: str, quote: str, date_from: str, date_to: str):
    url = f"{FRANKFURTER_API_BASE_URL}/rates"
    params = {
        "base": base.upper(),
        "from": date_from,
        "to": date_to,
        "quotes": quote.upper(),
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json(), str(response.url)


def normalize_fx_time_series(base: str, quote: str, raw_payload):
    rows = []

    for item in raw_payload:
        rate_date = item.get("date")
        rate = item.get("rate")

        if rate_date is None or rate is None:
            continue

        symbol = f"{base.upper()}/{quote.upper()}"
        name = f"{base.upper()} to {quote.upper()}"

        rows.append({
            "asset": {
                "symbol": symbol,
                "name": name,
                "assetClass": "fx",
                "region": "global",
                "attributes": {
                    "base_currency": base.upper(),
                    "quote_currency": quote.upper()
                },
                "provider_mappings": {
                    "frankfurter_base": base.upper(),
                    "frankfurter_quote": quote.upper()
                }
            },
            "ts": datetime.fromisoformat(rate_date),
            "metrics": {
                "exchange_rate": rate
            }
        })

    return rows