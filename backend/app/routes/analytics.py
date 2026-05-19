from flask import Blueprint, jsonify, request
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.db.mongo import db
from app.utils.serializers import serialize_value
from app.routes.series import get_deletion_cutoff

analytics_bp = Blueprint("analytics", __name__)


def get_asset_or_404(asset_object_id):
    return db.assets.find_one({"_id": asset_object_id})


def get_source_or_404(source_object_id):
    return db.data_sources.find_one({"_id": source_object_id})


def get_metric_label(asset_doc):
    if asset_doc and asset_doc.get("assetClass") == "fx":
        return "exchange_rate"
    return "close"


def get_value_expr():
    return {
        "$ifNull": [
            "$metrics.close",
            "$metrics.exchange_rate"
        ]
    }


def parse_as_of(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_series_match(asset_object_id, source_object_id, as_of_dt=None):
    """
    Builds the common temporal match clause for active analytic rows.
    Rules:
    - only active rows (is_deleted=False)
    - only rows for the given asset/source
    - if asOf is provided, rows must have ts <= asOf
    - if deletion marker exists, rows must be strictly before deletion cutoff
    """
    match = {
        "asset_id": asset_object_id,
        "source_id": source_object_id,
        "is_deleted": False,
    }

    ts_conditions = {}

    if as_of_dt:
        ts_conditions["$lte"] = as_of_dt

    deletion_cutoff = get_deletion_cutoff(asset_object_id, source_object_id, as_of_dt)

    if deletion_cutoff:
        existing_upper = ts_conditions.get("$lte")

        if existing_upper is None:
            ts_conditions["$lt"] = deletion_cutoff
        else:
            if deletion_cutoff <= existing_upper:
                ts_conditions.pop("$lte", None)
                ts_conditions["$lt"] = deletion_cutoff

    if ts_conditions:
        match["ts"] = ts_conditions

    return match


def count_active_analytic_points(asset_object_id, source_object_id, as_of_dt=None):
    pipeline = [
        {
            "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
        },
        {
            "$addFields": {
                "analytic_value": get_value_expr()
            }
        },
        {
            "$match": {
                "analytic_value": {"$ne": None}
            }
        },
        {
            "$count": "count"
        }
    ]

    result = list(db.series_points.aggregate(pipeline))
    return result[0]["count"] if result else 0


def build_insufficient_data_message(
    asset_object_id,
    source_object_id,
    as_of_dt=None,
    required_points=1,
    analytic_label="compute this analytic",
):
    count = count_active_analytic_points(asset_object_id, source_object_id, as_of_dt)

    if count == 0:
        deletion_cutoff = get_deletion_cutoff(asset_object_id, source_object_id, as_of_dt)

        if as_of_dt and deletion_cutoff and deletion_cutoff <= as_of_dt:
            return (
                "No active series data found for the selected asset/source and asOf time slice. "
                f"The series is marked unavailable starting {deletion_cutoff.date()}."
            )

        if as_of_dt:
            return "No active series data found for the selected asset/source and asOf time slice."

        return "No active series data found for the selected asset/source."

    if count < required_points:
        return (
            f"At least {required_points} active series points are required to {analytic_label}; "
            f"found {count}."
        )

    return None


def build_summary_data(asset_object_id, source_object_id, metric_label="close", as_of_dt=None):
    pipeline = [
        {
            "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
        },
        {
            "$addFields": {
                "analytic_value": get_value_expr()
            }
        },
        {
            "$match": {
                "analytic_value": {"$ne": None}
            }
        },
        {
            "$sort": {
                "ts": 1
            }
        },
        {
            "$group": {
                "_id": None,
                "count": {"$sum": 1},
                "min_value": {"$min": "$analytic_value"},
                "max_value": {"$max": "$analytic_value"},
                "avg_value": {"$avg": "$analytic_value"},
                "first_ts": {"$first": "$ts"},
                "last_ts": {"$last": "$ts"},
                "latest_value": {"$last": "$analytic_value"}
            }
        }
    ]

    result = list(db.series_points.aggregate(pipeline))
    if not result:
        return None

    summary = result[0]
    return {
        "metric_label": metric_label,
        "count": summary["count"],
        "min_value": summary["min_value"],
        "max_value": summary["max_value"],
        "avg_value": round(summary["avg_value"], 2) if summary["avg_value"] is not None else None,
        "latest_value": summary["latest_value"],
        "from": summary["first_ts"],
        "to": summary["last_ts"],
        "as_of": as_of_dt
    }


def build_trend_data(asset_object_id, source_object_id, metric_label="close", as_of_dt=None):
    pipeline = [
        {
            "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
        },
        {
            "$addFields": {
                "analytic_value": get_value_expr()
            }
        },
        {
            "$match": {
                "analytic_value": {"$ne": None}
            }
        },
        {
            "$sort": {
                "ts": 1
            }
        },
        {
            "$group": {
                "_id": None,
                "first_value": {"$first": "$analytic_value"},
                "latest_value": {"$last": "$analytic_value"},
                "first_ts": {"$first": "$ts"},
                "last_ts": {"$last": "$ts"},
                "count": {"$sum": 1}
            }
        }
    ]

    result = list(db.series_points.aggregate(pipeline))
    if not result:
        return None

    trend = result[0]
    first_value = trend["first_value"]
    latest_value = trend["latest_value"]
    absolute_change = latest_value - first_value

    if first_value == 0:
        percent_change = None
    else:
        percent_change = round((absolute_change / first_value) * 100, 2)

    if absolute_change > 0:
        direction = "up"
    elif absolute_change < 0:
        direction = "down"
    else:
        direction = "flat"

    return {
        "metric_label": metric_label,
        "count": trend["count"],
        "from": trend["first_ts"],
        "to": trend["last_ts"],
        "first_value": first_value,
        "latest_value": latest_value,
        "absolute_change": round(absolute_change, 2),
        "percent_change": percent_change,
        "direction": direction,
        "as_of": as_of_dt
    }


def build_forecast_data(asset_object_id, source_object_id, metric_label="close", as_of_dt=None):
    pipeline = [
        {
            "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
        },
        {
            "$addFields": {
                "analytic_value": get_value_expr()
            }
        },
        {
            "$match": {
                "analytic_value": {"$ne": None}
            }
        },
        {
            "$sort": {
                "ts": -1
            }
        },
        {
            "$project": {
                "analytic_value": 1,
                "ts": 1
            }
        },
        {
            "$limit": 2
        }
    ]

    points = list(db.series_points.aggregate(pipeline))

    if not points:
        return {"error": "No series data found for the given assetId and sourceId"}

    if len(points) < 2:
        return {"error": "At least 2 series points are required to compute forecast"}

    latest_point = points[0]
    previous_point = points[1]

    latest_value = latest_point["analytic_value"]
    previous_value = previous_point["analytic_value"]

    trend_value = latest_value - previous_value
    predicted_next_value = latest_value + trend_value

    return {
        "metric_label": metric_label,
        "previous_ts": previous_point["ts"],
        "latest_ts": latest_point["ts"],
        "previous_value": previous_value,
        "latest_value": latest_value,
        "trend": round(trend_value, 2),
        "predicted_next_value": round(predicted_next_value, 2),
        "method": "naive_linear_projection",
        "as_of": as_of_dt
    }


def build_risk_data(asset_object_id, source_object_id, metric_label="close", as_of_dt=None):
    pipeline = [
        {
            "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
        },
        {
            "$addFields": {
                "analytic_value": get_value_expr()
            }
        },
        {
            "$match": {
                "analytic_value": {"$ne": None}
            }
        },
        {
            "$group": {
                "_id": None,
                "count": {"$sum": 1},
                "min_value": {"$min": "$analytic_value"},
                "max_value": {"$max": "$analytic_value"},
                "avg_value": {"$avg": "$analytic_value"}
            }
        }
    ]

    result = list(db.series_points.aggregate(pipeline))
    if not result:
        return None

    risk_data = result[0]

    avg_value = risk_data["avg_value"]
    min_value = risk_data["min_value"]
    max_value = risk_data["max_value"]
    volatility_range = max_value - min_value

    if avg_value in (None, 0):
        volatility_percent = None
        risk_level = "unknown"
    else:
        volatility_percent = round((volatility_range / avg_value) * 100, 2)

        if volatility_percent < 5:
            risk_level = "low"
        elif volatility_percent < 15:
            risk_level = "medium"
        else:
            risk_level = "high"

    return {
        "metric_label": metric_label,
        "count": risk_data["count"],
        "min_value": min_value,
        "max_value": max_value,
        "avg_value": round(avg_value, 2) if avg_value is not None else None,
        "volatility_range": round(volatility_range, 2),
        "volatility_percent": volatility_percent,
        "risk_level": risk_level,
        "method": "range_over_average",
        "as_of": as_of_dt
    }


def build_moving_average_data(asset_object_id, source_object_id, window=5, metric_label="close", as_of_dt=None):
    if window < 2:
        return {"error": "window must be at least 2"}

    points = list(
        db.series_points.aggregate([
            {
                "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
            },
            {
                "$addFields": {
                    "analytic_value": get_value_expr()
                }
            },
            {
                "$match": {
                    "analytic_value": {"$ne": None}
                }
            },
            {
                "$sort": {
                    "ts": 1
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "ts": 1,
                    "value": "$analytic_value"
                }
            }
        ])
    )

    if not points:
        return {"error": "No series data found for the given assetId and sourceId"}

    results = []
    rolling_values = []

    for point in points:
        rolling_values.append(point["value"])
        if len(rolling_values) > window:
            rolling_values.pop(0)

        moving_average = None
        if len(rolling_values) == window:
            moving_average = round(sum(rolling_values) / window, 2)

        results.append({
            "ts": point["ts"],
            "value": point["value"],
            "moving_average": moving_average
        })

    latest_ma = next(
        (item["moving_average"] for item in reversed(results) if item["moving_average"] is not None),
        None
    )

    return {
        "metric_label": metric_label,
        "window": window,
        "count": len(results),
        "latest_moving_average": latest_ma,
        "series": results,
        "as_of": as_of_dt
    }

def build_compare_data(asset_object_id_1, asset_object_id_2, source_object_id, asset_1, asset_2, source, as_of_dt=None):
    asset_map = {
        asset_object_id_1: asset_1,
        asset_object_id_2: asset_2,
    }

    comparisons = []

    for asset_object_id in [asset_object_id_1, asset_object_id_2]:
        pipeline = [
            {
                "$match": build_series_match(asset_object_id, source_object_id, as_of_dt)
            },
            {
                "$addFields": {
                    "analytic_value": get_value_expr()
                }
            },
            {
                "$match": {
                    "analytic_value": {"$ne": None}
                }
            },
            {
                "$sort": {
                    "ts": 1
                }
            },
            {
                "$group": {
                    "_id": "$asset_id",
                    "count": {"$sum": 1},
                    "min_value": {"$min": "$analytic_value"},
                    "max_value": {"$max": "$analytic_value"},
                    "avg_value": {"$avg": "$analytic_value"},
                    "first_ts": {"$first": "$ts"},
                    "last_ts": {"$last": "$ts"},
                    "latest_value": {"$last": "$analytic_value"}
                }
            }
        ]

        result = list(db.series_points.aggregate(pipeline))

        if not result:
            return {
                "error": f"No valid historical series data found for asset {asset_map[asset_object_id]['symbol']} under the selected source/time slice"
            }

        item = result[0]
        asset_doc = asset_map.get(item["_id"])
        metric_label = get_metric_label(asset_doc)

        comparisons.append({
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
            "as_of": as_of_dt
        })

    return {
        "source_id": source_object_id,
        "source_name": source["name"],
        "as_of": as_of_dt,
        "comparisons": comparisons
    }

@analytics_bp.route("/analytics/summary", methods=["GET"])
def get_analytics_summary():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        insufficient_message = build_insufficient_data_message(
            asset_object_id,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label="compute summary",
        )
        if insufficient_message:
            return jsonify({"error": insufficient_message}), 404

        summary_data = build_summary_data(asset_object_id, source_object_id, metric_label, as_of_dt)

        response = {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **summary_data
        }

        return jsonify(serialize_value(response))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute analytics summary",
            "details": str(e)
        }), 500


@analytics_bp.route("/analytics/compare", methods=["GET"])
def get_analytics_compare():
    try:
        asset_id_1 = request.args.get("assetId1")
        asset_id_2 = request.args.get("assetId2")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")

        if not asset_id_1:
            return jsonify({"error": "assetId1 is required"}), 400

        if not asset_id_2:
            return jsonify({"error": "assetId2 is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        if asset_id_1 == asset_id_2:
            return jsonify({"error": "Please choose two different assets"}), 400

        try:
            asset_object_id_1 = ObjectId(asset_id_1)
        except InvalidId:
            return jsonify({"error": "Invalid assetId1"}), 400

        try:
            asset_object_id_2 = ObjectId(asset_id_2)
        except InvalidId:
            return jsonify({"error": "Invalid assetId2"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset_1 = get_asset_or_404(asset_object_id_1)
        if not asset_1:
            return jsonify({"error": "Asset 1 not found"}), 404

        asset_2 = get_asset_or_404(asset_object_id_2)
        if not asset_2:
            return jsonify({"error": "Asset 2 not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404
        
        asset_1_message = build_insufficient_data_message(
            asset_object_id_1,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label=f"compare asset {asset_1.get('symbol')}",
        )
        if asset_1_message:
            return jsonify({
                "error": f"{asset_1.get('symbol')}: {asset_1_message}"
            }), 404

        asset_2_message = build_insufficient_data_message(
            asset_object_id_2,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label=f"compare asset {asset_2.get('symbol')}",
        )
        if asset_2_message:
            return jsonify({
                "error": f"{asset_2.get('symbol')}: {asset_2_message}"
            }), 404

        compare_data = build_compare_data(
            asset_object_id_1,
            asset_object_id_2,
            source_object_id,
            asset_1,
            asset_2,
            source,
            as_of_dt
        )

        if "error" in compare_data:
            return jsonify(compare_data), 404

        return jsonify(serialize_value(compare_data))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute analytics comparison",
            "details": str(e)
        }), 500


@analytics_bp.route("/analytics/trend", methods=["GET"])
def get_analytics_trend():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        insufficient_message = build_insufficient_data_message(
            asset_object_id,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label="compute trend",
        )
        if insufficient_message:
            return jsonify({"error": insufficient_message}), 404

        trend_data = build_trend_data(asset_object_id, source_object_id, metric_label, as_of_dt)

        response = {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **trend_data
        }

        return jsonify(serialize_value(response))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute analytics trend",
            "details": str(e)
        }), 500


@analytics_bp.route("/analytics/forecast", methods=["GET"])
def get_analytics_forecast():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        insufficient_message = build_insufficient_data_message(
            asset_object_id,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=2,
            analytic_label="compute forecast",
        )
        if insufficient_message:
            status_code = 404 if insufficient_message.startswith("No active series data found") else 400
            return jsonify({"error": insufficient_message}), status_code

        forecast_data = build_forecast_data(asset_object_id, source_object_id, metric_label, as_of_dt)

        response = {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **forecast_data
        }

        return jsonify(serialize_value(response))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute analytics forecast",
            "details": str(e)
        }), 500


@analytics_bp.route("/analytics/risk", methods=["GET"])
def get_analytics_risk():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        insufficient_message = build_insufficient_data_message(
            asset_object_id,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label="compute risk",
        )
        if insufficient_message:
            return jsonify({"error": insufficient_message}), 404

        risk_data = build_risk_data(asset_object_id, source_object_id, metric_label, as_of_dt)

        response = {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **risk_data
        }

        return jsonify(serialize_value(response))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute analytics risk signal",
            "details": str(e)
        }), 500


@analytics_bp.route("/analytics/moving-average", methods=["GET"])
def get_analytics_moving_average():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")
        window = request.args.get("window", default=5, type=int)

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        if window < 2:
            return jsonify({"error": "window must be at least 2"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        insufficient_message = build_insufficient_data_message(
            asset_object_id,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label="compute moving average",
        )
        if insufficient_message:
            return jsonify({"error": insufficient_message}), 404

        moving_average_data = build_moving_average_data(
            asset_object_id,
            source_object_id,
            window,
            metric_label,
            as_of_dt
        )

        if moving_average_data.get("count", 0) < window:
            moving_average_data["warning"] = (
                f"Only {moving_average_data.get('count', 0)} active series points are available; "
                f"at least {window} are needed before a moving average can be produced."
            )

        response = {
            "asset_id": asset_object_id,
            "asset_symbol": asset["symbol"],
            "asset_name": asset["name"],
            "source_id": source_object_id,
            "source_name": source["name"],
            **moving_average_data
        }

        return jsonify(serialize_value(response))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute moving average",
            "details": str(e)
        }), 500


@analytics_bp.route("/analytics/dashboard", methods=["GET"])
def get_analytics_dashboard():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        as_of = request.args.get("asOf")
        window = request.args.get("window", default=5, type=int)

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400

        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        insufficient_message = build_insufficient_data_message(
            asset_object_id,
            source_object_id,
            as_of_dt=as_of_dt,
            required_points=1,
            analytic_label="build dashboard",
        )
        if insufficient_message:
            return jsonify({"error": insufficient_message}), 404

        summary_data = build_summary_data(asset_object_id, source_object_id, metric_label, as_of_dt)

        trend_data = build_trend_data(asset_object_id, source_object_id, metric_label, as_of_dt)
        forecast_data = build_forecast_data(asset_object_id, source_object_id, metric_label, as_of_dt)
        risk_data = build_risk_data(asset_object_id, source_object_id, metric_label, as_of_dt)
        moving_average_data = build_moving_average_data(
            asset_object_id,
            source_object_id,
            window,
            metric_label,
            as_of_dt
        )

        if moving_average_data.get("count", 0) < window:
            moving_average_data["warning"] = (
                f"Only {moving_average_data.get('count', 0)} active series points are available; "
                f"at least {window} are needed before a moving average can be produced."
            )

        response = {
            "asset": {
                "id": asset_object_id,
                "symbol": asset["symbol"],
                "name": asset["name"],
                "assetClass": asset.get("assetClass")
            },
            "source": {
                "id": source_object_id,
                "name": source["name"],
                "type": source.get("type")
            },
            "summary": summary_data,
            "trend": trend_data,
            "forecast": forecast_data,
            "risk": risk_data,
            "moving_average": moving_average_data
        }

        return jsonify(serialize_value(response))

    except Exception as e:
        return jsonify({
            "error": "Failed to compute analytics dashboard",
            "details": str(e)
        }), 500