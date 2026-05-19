from flask import Blueprint, jsonify, request
from bson import ObjectId
from bson.errors import InvalidId
from app.db.mongo import db
from app.utils.serializers import serialize_value
from app.routes.analytics import (
    get_asset_or_404,
    get_source_or_404,
    get_metric_label,
    build_summary_data,
    build_trend_data,
    build_forecast_data,
    build_risk_data,
    build_moving_average_data,
    build_compare_data,
    parse_as_of,
)
from app.routes.series import get_deletion_cutoff

assistant_bp = Blueprint("assistant", __name__)


def to_object_id(value: str, field_name: str):
    if not value:
        return None
    try:
        return ObjectId(value)
    except InvalidId:
        raise ValueError(f"Invalid {field_name}")


def build_explanation_text(asset, source, summary, trend, forecast, risk, as_of_dt=None):
    metric_label = summary.get("metric_label", get_metric_label(asset))
    as_of_text = f" as of {as_of_dt.date()}" if as_of_dt else ""

    lines = [
        f"{asset['symbol']} ({asset['name']}) from {source['name']}{as_of_text}:",
        f"- {summary['count']} active time-series points from {summary['from'].date()} to {summary['to'].date()}",
        f"- {metric_label} moved from {trend['first_value']} to {trend['latest_value']} ({trend['direction']}, {trend['percent_change']}%)",
        f"- latest {metric_label}: {summary['latest_value']}",
        f"- min/max/avg: {summary['min_value']} / {summary['max_value']} / {summary['avg_value']}",
        f"- risk level: {risk['risk_level']} (volatility {risk['volatility_percent']}%)",
    ]

    if forecast and "error" not in forecast:
        lines.append(
            f"- naive next-value forecast: {forecast['predicted_next_value']} ({forecast['method']})"
        )

    return "\n".join(lines)


def build_asset_history_answer(asset_history):
    if not asset_history:
        return "No asset history found."

    latest = asset_history[-1]
    versions = len(asset_history)

    lines = [
        f"Asset history for {latest.get('symbol')} ({latest.get('name')}):",
        f"- {versions} recorded version(s)",
    ]

    current_version = next((item for item in asset_history if item.get("is_current")), None)
    if current_version:
        lines.append(
            f"- current version: v{current_version.get('version')} "
            f"(deleted={current_version.get('is_deleted')})"
        )

    for item in asset_history:
        lines.append(
            f"- v{item.get('version')}: valid_from={item.get('valid_from')}, "
            f"valid_to={item.get('valid_to')}, is_current={item.get('is_current')}, "
            f"is_deleted={item.get('is_deleted')}"
        )

    return "\n".join(lines)


def list_sources_for_asset_data(asset):
    asset_class = asset.get("assetClass")

    sources = list(
        db.data_sources.find(
            {"is_current": True, "is_deleted": False},
            {"name": 1, "type": 1, "source_key": 1}
        ).sort("name", 1)
    )

    filtered = []

    for source in sources:
        source_name = (source.get("name") or "").lower()

        if asset_class == "crypto" and "binance" in source_name:
            filtered.append(source)
        elif asset_class == "fx" and "frankfurter" in source_name:
            filtered.append(source)

    return filtered


@assistant_bp.route("/assistant/query", methods=["POST"])
def assistant_query():
    try:
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        prompt = (body.get("prompt") or "").strip()
        asset_id = body.get("assetId")
        source_id = body.get("sourceId")
        compare_asset_id_1 = body.get("compareAssetId1")
        compare_asset_id_2 = body.get("compareAssetId2")
        compare_source_id = body.get("compareSourceId")
        as_of = body.get("asOf")

        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        as_of_dt = parse_as_of(as_of)
        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        prompt_lower = prompt.lower()

        # 1) list assets
        if "list assets" in prompt_lower or "available assets" in prompt_lower:
            assets = list(
                db.assets.find(
                    {"is_current": True, "is_deleted": False},
                    {"symbol": 1, "name": 1, "assetClass": 1}
                ).sort("symbol", 1)
            )

            answer = "Available assets:\n" + "\n".join(
                f"- {a.get('symbol')} ({a.get('name')}, {a.get('assetClass')})"
                for a in assets
            )

            return jsonify(serialize_value({
                "mode": "list_assets",
                "answer": answer,
                "data": assets,
            }))
        
        # 1b) asset history
        if (
            "asset history" in prompt_lower
            or "history of this asset" in prompt_lower
            or "show asset history" in prompt_lower
        ):
            if not asset_id:
                return jsonify({"error": "assetId is required for asset history prompts"}), 400

            asset_object_id = to_object_id(asset_id, "assetId")
            asset = get_asset_or_404(asset_object_id)
            if not asset:
                return jsonify({"error": "Asset not found"}), 404

            asset_history = list(
                db.assets.find({"asset_key": asset["asset_key"]})
                .sort([("version", 1), ("valid_from", 1)])
            )

            if not asset_history:
                return jsonify({"error": "No asset history found for the selected asset"}), 404

            answer = build_asset_history_answer(asset_history)

            return jsonify(serialize_value({
                "mode": "asset_history",
                "answer": answer,
                "data": asset_history,
            }))
        

        # 1c) list sources for asset
        if (
            "sources for asset" in prompt_lower
            or "list sources for asset" in prompt_lower
            or "what sources" in prompt_lower
            or "which sources" in prompt_lower
        ):
            if not asset_id:
                return jsonify({"error": "assetId is required for source discovery prompts"}), 400

            asset_object_id = to_object_id(asset_id, "assetId")
            asset = get_asset_or_404(asset_object_id)
            if not asset:
                return jsonify({"error": "Asset not found"}), 404

            filtered_sources = list_sources_for_asset_data(asset)

            if not filtered_sources:
                return jsonify({"error": "No matching sources found for the selected asset"}), 404

            answer = (
                f"Available sources for {asset['symbol']} ({asset['name']}):\n"
                + "\n".join(
                    f"- {source.get('name')} ({source.get('type')})"
                    for source in filtered_sources
                )
            )

            return jsonify(serialize_value({
                "mode": "sources_for_asset",
                "answer": answer,
                "data": filtered_sources,
            }))

        # 2) selected asset/source required from here on
        asset_object_id = to_object_id(asset_id, "assetId") if asset_id else None
        source_object_id = to_object_id(source_id, "sourceId") if source_id else None

        # 3) compare
        if "compare" in prompt_lower:
            if not compare_asset_id_1 or not compare_asset_id_2 or not compare_source_id:
                return jsonify({
                    "error": "compareAssetId1, compareAssetId2, and compareSourceId are required for compare prompts"
                }), 400

            asset_object_id_1 = to_object_id(compare_asset_id_1, "compareAssetId1")
            asset_object_id_2 = to_object_id(compare_asset_id_2, "compareAssetId2")
            compare_source_object_id = to_object_id(compare_source_id, "compareSourceId")

            asset_1 = get_asset_or_404(asset_object_id_1)
            if not asset_1:
                return jsonify({"error": "Compare asset 1 not found"}), 404

            asset_2 = get_asset_or_404(asset_object_id_2)
            if not asset_2:
                return jsonify({"error": "Compare asset 2 not found"}), 404

            source = get_source_or_404(compare_source_object_id)
            if not source:
                return jsonify({"error": "Compare source not found"}), 404

            compare_data = build_compare_data(
                asset_object_id_1,
                asset_object_id_2,
                compare_source_object_id,
                asset_1,
                asset_2,
                source,
                as_of_dt,
            )

            if "error" in compare_data:
                return jsonify(compare_data), 404

            answer_lines = [
                f"Comparison under {source['name']}" + (f" as of {as_of_dt.date()}" if as_of_dt else "") + ":"
            ]

            for item in compare_data["comparisons"]:
                answer_lines.append(
                    f"- {item['asset_symbol']}: latest={item['latest_value']}, "
                    f"min={item['min_value']}, max={item['max_value']}, avg={item['avg_value']}, "
                    f"count={item['count']}, range={item['from'].date()} to {item['to'].date()}"
                )

            return jsonify(serialize_value({
                "mode": "compare",
                "answer": "\n".join(answer_lines),
                "data": compare_data,
            }))

        # Remaining modes need selected asset/source
        if not asset_object_id:
            return jsonify({"error": "assetId is required for this prompt"}), 400

        if not source_object_id:
            return jsonify({"error": "sourceId is required for this prompt"}), 400

        asset = get_asset_or_404(asset_object_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = get_source_or_404(source_object_id)
        if not source:
            return jsonify({"error": "Source not found"}), 404

        metric_label = get_metric_label(asset)

        # 4) dashboard
        if "dashboard" in prompt_lower:
            summary = build_summary_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            if not summary:
                return jsonify({"error": "No series data found for the given assetId and sourceId"}), 404

            trend = build_trend_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            forecast = build_forecast_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            risk = build_risk_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            moving_average = build_moving_average_data(asset_object_id, source_object_id, 5, metric_label, as_of_dt)

            answer = build_explanation_text(asset, source, summary, trend, forecast, risk, as_of_dt)

            return jsonify(serialize_value({
                "mode": "dashboard",
                "answer": answer,
                "data": {
                    "asset": {
                        "id": asset_object_id,
                        "symbol": asset["symbol"],
                        "name": asset["name"],
                        "assetClass": asset.get("assetClass"),
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
                    "moving_average": moving_average,
                },
            }))

        # 5) trend
        if "trend" in prompt_lower or "explain" in prompt_lower:
            summary = build_summary_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            trend = build_trend_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            forecast = build_forecast_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            risk = build_risk_data(asset_object_id, source_object_id, metric_label, as_of_dt)

            if not summary or not trend or not risk:
                return jsonify({"error": "No series data found for the given assetId and sourceId"}), 404

            answer = build_explanation_text(asset, source, summary, trend, forecast, risk, as_of_dt)

            return jsonify(serialize_value({
                "mode": "trend_explanation",
                "answer": answer,
                "data": {
                    "summary": summary,
                    "trend": trend,
                    "forecast": forecast,
                    "risk": risk,
                },
            }))

        # 6) risk
        if "risk" in prompt_lower:
            risk = build_risk_data(asset_object_id, source_object_id, metric_label, as_of_dt)
            if not risk:
                return jsonify({"error": "No series data found for the given assetId and sourceId"}), 404

            answer = (
                f"Risk summary for {asset['symbol']} from {source['name']}"
                + (f" as of {as_of_dt.date()}" if as_of_dt else "")
                + f":\n"
                f"- risk level: {risk['risk_level']}\n"
                f"- volatility range: {risk['volatility_range']}\n"
                f"- volatility percent: {risk['volatility_percent']}\n"
                f"- min/max/avg: {risk['min_value']} / {risk['max_value']} / {risk['avg_value']}"
            )

            return jsonify(serialize_value({
                "mode": "risk",
                "answer": answer,
                "data": risk,
            }))

        # 7) time series
        if "time series" in prompt_lower or "fetch time series" in prompt_lower or "series" in prompt_lower:
            query = {
                "asset_id": asset_object_id,
                "source_id": source_object_id,
                "is_deleted": False,
            }

            if as_of_dt:
                query["ts"] = {"$lte": as_of_dt}

            deletion_cutoff = get_deletion_cutoff(asset_object_id, source_object_id, as_of_dt)
            if deletion_cutoff:
                existing_ts = query.get("ts", {})
                if "$lte" in existing_ts:
                    if deletion_cutoff <= existing_ts["$lte"]:
                        query["ts"] = {"$lt": deletion_cutoff}
                else:
                    query["ts"] = {"$lt": deletion_cutoff}

            rows = list(
                db.series_points.find(query, {"ts": 1, "metrics": 1})
                .sort("ts", 1)
                .limit(20)
            )

            if not rows:
                return jsonify({"error": "No time series data found for the selected asset/source"}), 404

            answer = (
                f"Fetched {len(rows)} time-series points for {asset['symbol']} from {source['name']}"
                + (f" as of {as_of_dt.date()}" if as_of_dt else "")
                + "."
            )

            return jsonify(serialize_value({
                "mode": "time_series",
                "answer": answer,
                "data": rows,
            }))

        # default fallback: dashboard-style answer
        summary = build_summary_data(asset_object_id, source_object_id, metric_label, as_of_dt)
        trend = build_trend_data(asset_object_id, source_object_id, metric_label, as_of_dt)
        forecast = build_forecast_data(asset_object_id, source_object_id, metric_label, as_of_dt)
        risk = build_risk_data(asset_object_id, source_object_id, metric_label, as_of_dt)

        if not summary or not trend or not risk:
            return jsonify({"error": "No series data found for the given assetId and sourceId"}), 404

        answer = build_explanation_text(asset, source, summary, trend, forecast, risk, as_of_dt)

        return jsonify(serialize_value({
            "mode": "default",
            "answer": answer,
            "data": {
                "summary": summary,
                "trend": trend,
                "forecast": forecast,
                "risk": risk,
            },
        }))

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({
            "error": "Assistant query failed",
            "details": str(e)
        }), 500