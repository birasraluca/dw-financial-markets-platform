from datetime import datetime
from app.db.mongo import db

def seed_assets():
    assets = [
        {
            "symbol": "BTC",
            "assetClass": "crypto",
            "name": "Bitcoin",
            "region": "global",
            "attributes": {
                "category": "cryptocurrency"
            }
        },
        {
            "symbol": "ETH",
            "assetClass": "crypto",
            "name": "Ethereum",
            "region": "global",
            "attributes": {
                "category": "cryptocurrency"
            }
        },
        {
            "symbol": "AAPL",
            "assetClass": "stock",
            "name": "Apple Inc.",
            "region": "US",
            "attributes": {
                "sector": "Technology"
            }
        }
    ]

    result = db.assets.insert_many(assets)
    print("Assets inserted")
    return result.inserted_ids


def seed_sources():
    sources = [
        {
            "name": "CoinGecko",
            "type": "REST API",
            "baseUrl": "https://api.coingecko.com/api/v3",
            "notes": "Crypto market data"
        },
        {
            "name": "AlphaVantage",
            "type": "REST API",
            "baseUrl": "https://www.alphavantage.co",
            "notes": "Stock market data"
        }
    ]

    result = db.data_sources.insert_many(sources)
    print("Sources inserted")
    return result.inserted_ids


def seed_ingestion(source_id, rows_inserted, notes):
    ingestion = {
        "source_id": source_id,
        "started_at": datetime(2024, 1, 10, 9, 0, 0),
        "finished_at": datetime(2024, 1, 10, 9, 1, 0),
        "status": "success",
        "rows_inserted": rows_inserted,
        "notes": notes
    }

    result = db.ingestions.insert_one(ingestion)
    print("Ingestion inserted")
    return result.inserted_id


def seed_series_points(asset_ids, source_ids):
    btc_id = asset_ids[0]
    eth_id = asset_ids[1]
    aapl_id = asset_ids[2]

    coingecko_id = source_ids[0]
    alphavantage_id = source_ids[1]

    coingecko_rows = [
        {
            "asset_id": btc_id,
            "source_id": coingecko_id,
            "ts": datetime(2024, 1, 1),
            "metrics": {"close": 42000},
            "is_deleted": False
        },
        {
            "asset_id": btc_id,
            "source_id": coingecko_id,
            "ts": datetime(2024, 1, 2),
            "metrics": {"close": 43200},
            "is_deleted": False
        },
        {
            "asset_id": btc_id,
            "source_id": coingecko_id,
            "ts": datetime(2024, 1, 3),
            "metrics": {"close": 44150},
            "is_deleted": False
        },
        {
            "asset_id": eth_id,
            "source_id": coingecko_id,
            "ts": datetime(2024, 1, 1),
            "metrics": {"close": 2200},
            "is_deleted": False
        },
        {
            "asset_id": eth_id,
            "source_id": coingecko_id,
            "ts": datetime(2024, 1, 2),
            "metrics": {"close": 2255},
            "is_deleted": False
        },
        {
            "asset_id": eth_id,
            "source_id": coingecko_id,
            "ts": datetime(2024, 1, 3),
            "metrics": {"close": None},
            "is_deleted": True
        }
    ]

    alphavantage_rows = [
        {
            "asset_id": aapl_id,
            "source_id": alphavantage_id,
            "ts": datetime(2024, 1, 1),
            "metrics": {"close": 190.5},
            "is_deleted": False
        },
        {
            "asset_id": aapl_id,
            "source_id": alphavantage_id,
            "ts": datetime(2024, 1, 2),
            "metrics": {"close": 192.1},
            "is_deleted": False
        }
    ]

    coingecko_ingestion_id = seed_ingestion(
        coingecko_id,
        len(coingecko_rows),
        "Initial demo load from CoinGecko"
    )

    alphavantage_ingestion_id = seed_ingestion(
        alphavantage_id,
        len(alphavantage_rows),
        "Initial demo load from AlphaVantage"
    )

    for row in coingecko_rows:
        row["ingestion_id"] = coingecko_ingestion_id

    for row in alphavantage_rows:
        row["ingestion_id"] = alphavantage_ingestion_id

    db.series_points.insert_many(coingecko_rows + alphavantage_rows)
    print("Series points inserted")


if __name__ == "__main__":
    db.assets.delete_many({})
    db.data_sources.delete_many({})
    db.ingestions.delete_many({})
    db.series_points.delete_many({})

    asset_ids = seed_assets()
    source_ids = seed_sources()
    seed_series_points(asset_ids, source_ids)