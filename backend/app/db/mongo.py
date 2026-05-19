import os
import certifi
from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000,
    connectTimeoutMS=10000,
    socketTimeoutMS=10000
)

db = client[DB_NAME]


def ensure_indexes():
    # assets
    db.assets.create_index([("symbol", ASCENDING)], name="idx_assets_symbol")
    db.assets.create_index([("assetClass", ASCENDING)], name="idx_assets_assetClass")

    # data sources
    db.data_sources.create_index([("name", ASCENDING)], name="idx_data_sources_name")
    db.data_sources.create_index([("type", ASCENDING)], name="idx_data_sources_type")

    # ingestions
    db.ingestions.create_index(
        [("source_id", ASCENDING), ("started_at", DESCENDING)],
        name="idx_ingestions_source_started_at"
    )
    db.ingestions.create_index([("status", ASCENDING)], name="idx_ingestions_status")

    # series points
    db.series_points.create_index(
        [("asset_id", ASCENDING), ("source_id", ASCENDING), ("ts", ASCENDING)],
        name="idx_series_asset_source_ts"
    )
    db.series_points.create_index(
        [("source_id", ASCENDING), ("ts", ASCENDING)],
        name="idx_series_source_ts"
    )
    db.series_points.create_index(
        [("ingestion_id", ASCENDING)],
        name="idx_series_ingestion_id"
    )
    db.series_points.create_index(
        [("is_deleted", ASCENDING)],
        name="idx_series_is_deleted"
    )
    db.assets.create_index(
        [("provider_mappings.binance_symbol", ASCENDING)],
        name="idx_assets_binance_symbol"
    )
    db.assets.create_index(
        [("provider_mappings.frankfurter_base", ASCENDING), ("provider_mappings.frankfurter_quote", ASCENDING)],
        name="idx_assets_frankfurter_pair"
    )
    db.assets.create_index(
        [("asset_key", ASCENDING), ("is_current", ASCENDING), ("is_deleted", ASCENDING)],
        name="idx_assets_key_current_deleted"
    )
    db.assets.create_index(
        [("valid_from", ASCENDING), ("valid_to", ASCENDING)],
        name="idx_assets_validity"
    )

    db.data_sources.create_index(
        [("source_key", ASCENDING), ("is_current", ASCENDING), ("is_deleted", ASCENDING)],
        name="idx_sources_key_current_deleted"
    )
    db.data_sources.create_index(
        [("valid_from", ASCENDING), ("valid_to", ASCENDING)],
        name="idx_sources_validity"
    )

    db.series_points.create_index(
        [("asset_id", ASCENDING), ("source_id", ASCENDING), ("ts", ASCENDING), ("is_deleted", ASCENDING)],
        name="idx_series_asset_source_ts_deleted"
    )
    db.assets.create_index(
        [("asset_key", ASCENDING), ("version", DESCENDING)],
        name="idx_assets_key_version"
    )
    db.data_sources.create_index(
        [("source_key", ASCENDING), ("version", DESCENDING)],
        name="idx_sources_key_version"
    )
    db.assets.create_index(
        [("asset_key", ASCENDING), ("valid_from", ASCENDING), ("valid_to", ASCENDING)],
        name="idx_assets_key_validity"
    )
    db.data_sources.create_index(
        [("source_key", ASCENDING), ("valid_from", ASCENDING), ("valid_to", ASCENDING)],
        name="idx_sources_key_validity"
    )
    db.ingestions.create_index(
        [("duration_ms", DESCENDING)],
        name="idx_ingestions_duration_ms"
    )
    db.assets.create_index(
        [("asset_key", ASCENDING)],
        name="uniq_assets_current_per_key",
        unique=True,
        partialFilterExpression={
            "is_current": True
        }
    )
    db.data_sources.create_index(
        [("source_key", ASCENDING)],
        name="uniq_sources_current_per_key",
        unique=True,
        partialFilterExpression={
            "is_current": True
        }
    )
    db.series_points.create_index(
        [("asset_id", ASCENDING), ("source_id", ASCENDING), ("ts", ASCENDING)],
        name="uniq_series_active_point",
        unique=True,
        partialFilterExpression={
            "is_deleted": False
        }
    )
    db.series_points.create_index(
        [("asset_id", ASCENDING), ("source_id", ASCENDING), ("ts", ASCENDING), ("marker_type", ASCENDING)],
        name="uniq_series_delete_marker",
        unique=True,
        partialFilterExpression={
            "is_deleted": True,
            "marker_type": "deletion"
        }
    )