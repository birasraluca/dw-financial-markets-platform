from bson import ObjectId
from bson.errors import InvalidId
from mcp.server.fastmcp import FastMCP
import requests
import os
from urllib.parse import quote

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")

from app.db.mongo import db
from app.routes.analytics import (
    build_summary_data,
    build_trend_data,
    build_forecast_data,
    build_risk_data,
    get_asset_or_404,
    get_source_or_404,
    get_metric_label,
)
from app.utils.serializers import serialize_doc, serialize_docs, serialize_value


mcp = FastMCP(
    "DW Financial Markets",
    stateless_http=True,
    json_response=True,
)


def to_object_id(value: str, field_name: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise ValueError(f"Invalid {field_name}") from exc


def get_asset_and_source(asset_id: str, source_id: str):
    asset_object_id = to_object_id(asset_id, "assetId")
    source_object_id = to_object_id(source_id, "sourceId")

    asset = get_asset_or_404(asset_object_id)
    if not asset:
        raise ValueError("Asset not found")

    source = get_source_or_404(source_object_id)
    if not source:
        raise ValueError("Source not found")

    return asset_object_id, source_object_id, asset, source


@mcp.tool()
def list_assets() -> list[dict]:
    """Return compact information about all financial assets."""
    assets = list(
        db.assets.find(
            {},
            {
                "symbol": 1,
                "name": 1,
                "assetClass": 1,
                "region": 1,
            },
        ).sort("symbol", 1)
    )
    return serialize_docs(assets)


@mcp.tool()
def list_sources() -> list[dict]:
    """Return compact information about all data sources/providers."""
    sources = list(
        db.data_sources.find(
            {},
            {
                "name": 1,
                "type": 1,
                "baseUrl": 1,
                "notes": 1,
            },
        ).sort("name", 1)
    )
    return serialize_docs(sources)


@mcp.tool()
def get_asset(asset_id: str) -> dict:
    """Return full details for one asset by its id."""
    asset_object_id = to_object_id(asset_id, "assetId")
    asset = db.assets.find_one({"_id": asset_object_id})
    if not asset:
        raise ValueError("Asset not found")
    return serialize_doc(asset)


@mcp.tool()
def get_source(source_id: str) -> dict:
    """Return full details for one source by its id."""
    source_object_id = to_object_id(source_id, "sourceId")
    source = db.data_sources.find_one({"_id": source_object_id})
    if not source:
        raise ValueError("Source not found")
    return serialize_doc(source)


@mcp.tool()
def get_time_series(
    asset_id: str,
    source_id: str,
    include_deleted: bool = False,
    limit: int = 100,
) -> list[dict]:
    """Return time-series points for an asset and source."""
    asset_object_id, source_object_id, _, _ = get_asset_and_source(asset_id, source_id)

    query = {
        "asset_id": asset_object_id,
        "source_id": source_object_id,
    }

    if not include_deleted:
        query["is_deleted"] = False

    cursor = db.series_points.find(query).sort("ts", 1)

    if limit and limit > 0:
        cursor = cursor.limit(limit)

    return serialize_docs(list(cursor))


@mcp.tool()
def get_summary(asset_id: str, source_id: str) -> dict:
    """Return summary analytics for an asset/source pair."""
    asset_object_id, source_object_id, asset, source = get_asset_and_source(asset_id, source_id)
    metric_label = get_metric_label(asset)

    summary = build_summary_data(asset_object_id, source_object_id, metric_label)
    if not summary:
        raise ValueError("No series data found for the given assetId and sourceId")

    return serialize_value(
        {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **summary,
        }
    )


@mcp.tool()
def get_trend(asset_id: str, source_id: str) -> dict:
    """Return trend analytics for an asset/source pair."""
    asset_object_id, source_object_id, asset, source = get_asset_and_source(asset_id, source_id)
    metric_label = get_metric_label(asset)

    trend = build_trend_data(asset_object_id, source_object_id, metric_label)
    if not trend:
        raise ValueError("No series data found for the given assetId and sourceId")

    return serialize_value(
        {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **trend,
        }
    )


@mcp.tool()
def get_forecast(asset_id: str, source_id: str) -> dict:
    """Return naive forecast analytics for an asset/source pair."""
    asset_object_id, source_object_id, asset, source = get_asset_and_source(asset_id, source_id)
    metric_label = get_metric_label(asset)

    forecast = build_forecast_data(asset_object_id, source_object_id, metric_label)
    if "error" in forecast:
        raise ValueError(forecast["error"])

    return serialize_value(
        {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **forecast,
        }
    )


@mcp.tool()
def get_risk(asset_id: str, source_id: str) -> dict:
    """Return simple risk analytics for an asset/source pair."""
    asset_object_id, source_object_id, asset, source = get_asset_and_source(asset_id, source_id)
    metric_label = get_metric_label(asset)

    risk = build_risk_data(asset_object_id, source_object_id, metric_label)
    if not risk:
        raise ValueError("No series data found for the given assetId and sourceId")

    return serialize_value(
        {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **risk,
        }
    )


@mcp.tool()
def get_dashboard(asset_id: str, source_id: str) -> dict:
    """Return the combined dashboard block for an asset/source pair."""
    asset_object_id, source_object_id, asset, source = get_asset_and_source(asset_id, source_id)
    metric_label = get_metric_label(asset)

    summary = build_summary_data(asset_object_id, source_object_id, metric_label)
    if not summary:
        raise ValueError("No series data found for the given assetId and sourceId")

    trend = build_trend_data(asset_object_id, source_object_id, metric_label)
    forecast = build_forecast_data(asset_object_id, source_object_id, metric_label)
    risk = build_risk_data(asset_object_id, source_object_id, metric_label)

    return serialize_value(
        {
            "asset": {
                "id": asset_object_id,
                "symbol": asset["symbol"],
                "name": asset["name"],
                "assetClass": asset.get("assetClass"),
                "region": asset.get("region"),
            },
            "source": {
                "id": source_object_id,
                "name": source["name"],
                "type": source.get("type"),
            },
            "summary": summary,
            "trend": trend,
            "forecast": forecast,
            "risk": risk,
        }
    )


@mcp.tool()
def compare_assets(asset_id_1: str, asset_id_2: str, source_id: str) -> dict:
    """Compare two assets under the same data source."""
    if asset_id_1 == asset_id_2:
        raise ValueError("Please choose two different assets")

    asset_object_id_1 = to_object_id(asset_id_1, "assetId1")
    asset_object_id_2 = to_object_id(asset_id_2, "assetId2")
    source_object_id = to_object_id(source_id, "sourceId")

    asset_1 = get_asset_or_404(asset_object_id_1)
    if not asset_1:
        raise ValueError("Asset 1 not found")

    asset_2 = get_asset_or_404(asset_object_id_2)
    if not asset_2:
        raise ValueError("Asset 2 not found")

    source = get_source_or_404(source_object_id)
    if not source:
        raise ValueError("Source not found")

    asset_map = {
        asset_object_id_1: asset_1,
        asset_object_id_2: asset_2,
    }

    pipeline = [
        {
            "$match": {
                "asset_id": {"$in": [asset_object_id_1, asset_object_id_2]},
                "source_id": source_object_id,
                "is_deleted": False,
            }
        },
        {
            "$addFields": {
                "analytic_value": {
                    "$ifNull": ["$metrics.close", "$metrics.exchange_rate"]
                }
            }
        },
        {
            "$match": {
                "analytic_value": {"$ne": None}
            }
        },
        {"$sort": {"ts": 1}},
        {
            "$group": {
                "_id": "$asset_id",
                "count": {"$sum": 1},
                "min_value": {"$min": "$analytic_value"},
                "max_value": {"$max": "$analytic_value"},
                "avg_value": {"$avg": "$analytic_value"},
                "first_ts": {"$first": "$ts"},
                "last_ts": {"$last": "$ts"},
                "latest_value": {"$last": "$analytic_value"},
            }
        },
    ]

    results = list(db.series_points.aggregate(pipeline))
    if not results:
        raise ValueError("No series data found for the given asset ids and sourceId")

    comparisons = []
    for item in results:
        asset_doc = asset_map.get(item["_id"])
        metric_label = get_metric_label(asset_doc)

        comparisons.append(
            {
                "asset_id": item["_id"],
                "asset_symbol": asset_doc["symbol"] if asset_doc else None,
                "asset_name": asset_doc["name"] if asset_doc else None,
                "source_id": source_object_id,
                "source_name": source["name"],
                "metric_label": metric_label,
                "count": item["count"],
                "min_value": item["min_value"],
                "max_value": item["max_value"],
                "avg_value": round(item["avg_value"], 2) if item["avg_value"] is not None else None,
                "latest_value": item["latest_value"],
                "from": item["first_ts"],
                "to": item["last_ts"],
            }
        )

    return serialize_value(
        {
            "source_id": source_object_id,
            "source_name": source["name"],
            "comparisons": comparisons,
        }
    )


@mcp.tool()
def explain_change(asset_id: str, source_id: str) -> dict:
    """Return a grounded plain-English explanation based only on warehouse analytics."""
    asset_object_id, source_object_id, asset, source = get_asset_and_source(asset_id, source_id)
    metric_label = get_metric_label(asset)

    summary = build_summary_data(asset_object_id, source_object_id, metric_label)
    trend = build_trend_data(asset_object_id, source_object_id, metric_label)
    forecast = build_forecast_data(asset_object_id, source_object_id, metric_label)
    risk = build_risk_data(asset_object_id, source_object_id, metric_label)

    if not summary or not trend or not risk:
        raise ValueError("No series data found for the given assetId and sourceId")

    explanation_parts = [
        f"{asset['symbol']} ({asset['name']}) from {source['name']} has {summary['count']} active time-series points",
        f"between {summary['from'].date()} and {summary['to'].date()}",
        f"with {metric_label} moving from {trend['first_value']} to {trend['latest_value']}",
        f"({trend['direction']}, {trend['percent_change']}% overall).",
        f"The latest {metric_label} is {summary['latest_value']}.",
        f"Risk is classified as {risk['risk_level']} based on volatility_percent={risk['volatility_percent']}.",
    ]

    if "error" not in forecast:
        explanation_parts.append(
            f"The naive next-value forecast is {forecast['predicted_next_value']} "
            f"using method={forecast['method']}."
        )

    return serialize_value(
        {
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_name": source["name"],
            "metric_label": metric_label,
            "grounded_explanation": " ".join(explanation_parts),
            "summary": summary,
            "trend": trend,
            "forecast": forecast,
            "risk": risk,
        }
    )


@mcp.tool()
def get_asset_history(asset_key: str):
    """
    Retrieve full version history of an asset (temporal records).
    """
    try:
        safe_key = quote(asset_key, safe="")

        response = requests.get(
            f"{API_BASE_URL}/assets/history/{safe_key}",
            timeout=30,
        )

        if response.status_code != 200:
            return {
                "error": "Failed to fetch asset history",
                "details": response.json()
            }

        return response.json()

    except Exception as e:
        return {"error": str(e)}
    

@mcp.tool()
def list_sources_for_asset(asset_key: str):
    """
    List available sources that provide data for a given asset.
    """
    try:
        safe_key = quote(asset_key, safe="")

        asset_resp = requests.get(
            f"{API_BASE_URL}/assets/by-key/{safe_key}",
            timeout=30,
        )

        if asset_resp.status_code != 200:
            return {
                "error": "Asset not found",
                "details": asset_resp.json()
            }

        asset = asset_resp.json()
        asset_class = asset.get("assetClass")

        sources_resp = requests.get(
            f"{API_BASE_URL}/sources",
            timeout=30,
        )

        if sources_resp.status_code != 200:
            return {
                "error": "Failed to fetch sources",
                "details": sources_resp.json()
            }

        sources = sources_resp.json()

        filtered = []

        for s in sources:
            name = s.get("name", "").lower()

            if asset_class == "crypto" and "binance" in name:
                filtered.append(s)
            elif asset_class == "fx" and "frankfurter" in name:
                filtered.append(s)

        return filtered

    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")