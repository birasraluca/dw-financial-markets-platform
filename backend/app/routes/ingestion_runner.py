from flask import Blueprint, jsonify, request
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.utils.serializers import serialize_docs, serialize_value

from app.ingestion.providers.binance import (
    fetch_klines,
    normalize_klines,
    to_milliseconds,
)
from app.ingestion.providers.frankfurter import (
    fetch_fx_time_series,
    normalize_fx_time_series,
)
from app.ingestion.services.ingestion_logger import (
    create_ingestion_event,
    complete_ingestion_event,
    hash_payload,
)
from app.ingestion.services.warehouse_loader import (
    get_or_create_source,
    insert_series_points,
    mark_asset_as_deleted_version,
)
from app.db.mongo import db


ingestion_runner_bp = Blueprint("ingestion_runner", __name__)

def validate_date_range(date_from: str, date_to: str):
    """
    Validates that:
    - both dates are valid ISO dates (YYYY-MM-DD or ISO datetime)
    - from <= to

    Returns:
        (from_dt, to_dt, None) on success
        (None, None, (json_response, status_code)) on failure
    """
    try:
        from_dt = datetime.fromisoformat(date_from)
    except ValueError:
        return None, None, (jsonify({"error": "Invalid 'from' date format. Use YYYY-MM-DD or ISO format."}), 400)

    try:
        to_dt = datetime.fromisoformat(date_to)
    except ValueError:
        return None, None, (jsonify({"error": "Invalid 'to' date format. Use YYYY-MM-DD or ISO format."}), 400)

    if from_dt > to_dt:
        return None, None, (jsonify({"error": "'from' date must be earlier than or equal to 'to' date"}), 400)

    return from_dt, to_dt, None


def validate_binance_inputs(symbol: str, interval: str):
    """
    Basic Binance-specific validation.
    - symbol required and uppercased
    - interval must be one of allowed values
    """
    if not symbol:
        return None, None, (jsonify({"error": "symbol is required"}), 400)

    normalized_symbol = symbol.strip().upper()

    allowed_intervals = {"1d", "1h", "4h"}
    normalized_interval = (interval or "").strip()

    if normalized_interval not in allowed_intervals:
        return None, None, (
            jsonify({"error": f"Invalid interval. Allowed values: {', '.join(sorted(allowed_intervals))}"}),
            400,
        )

    return normalized_symbol, normalized_interval, None


def validate_frankfurter_inputs(base: str, quote: str):
    """
    Basic Frankfurter-specific validation.
    - base and quote required
    - must be exactly 3 alphabetic letters
    - must not be the same
    """
    if not base:
        return None, None, (jsonify({"error": "base is required"}), 400)

    if not quote:
        return None, None, (jsonify({"error": "quote is required"}), 400)

    normalized_base = base.strip().upper()
    normalized_quote = quote.strip().upper()

    if len(normalized_base) != 3 or not normalized_base.isalpha():
        return None, None, (
            jsonify({"error": "Invalid base currency. Use a 3-letter currency code like EUR or USD"}), 400
        )

    if len(normalized_quote) != 3 or not normalized_quote.isalpha():
        return None, None, (
            jsonify({"error": "Invalid quote currency. Use a 3-letter currency code like EUR or USD"}), 400
        )

    if normalized_base == normalized_quote:
        return None, None, (
            jsonify({"error": "base and quote must be different currency codes"}), 400
        )

    return normalized_base, normalized_quote, None


@ingestion_runner_bp.route("/ingestions/run/binance", methods=["POST"])
def run_binance_ingestion():
    try:
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        symbol = body.get("symbol")
        asset_name = body.get("name")
        interval = body.get("interval", "1d")
        date_from = body.get("from")
        date_to = body.get("to")

        if not asset_name:
            return jsonify({"error": "name is required"}), 400
        if not date_from:
            return jsonify({"error": "from is required"}), 400
        if not date_to:
            return jsonify({"error": "to is required"}), 400

        symbol, interval, binance_error = validate_binance_inputs(symbol, interval)
        if binance_error:
            return binance_error

        _, _, date_error = validate_date_range(date_from, date_to)
        if date_error:
            return date_error

        start_time_ms = to_milliseconds(date_from)
        end_time_ms = to_milliseconds(date_to)

        source = get_or_create_source(
            name="Binance",
            source_type="REST API",
            base_url="https://api.binance.com/api/v3",
            notes="Crypto spot market data with historical OHLCV klines",
            refresh_rate="daily"
        )

        ingestion_id = create_ingestion_event(
            source_id=source["_id"],
            endpoint="/api/v3/klines",
            params={
                "symbol": symbol,
                "name": asset_name,
                "interval": interval,
                "from": date_from,
                "to": date_to,
            }
        )

        try:
            raw_payload, request_url = fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
                limit=1000,
            )

            rows = normalize_klines(
                symbol=symbol,
                asset_name=asset_name,
                raw_payload=raw_payload,
            )

            auto_delete_info = None

            if not rows:
                valid_from_dt = datetime.fromisoformat(date_from)

                auto_delete_info = mark_asset_as_deleted_version(
                    asset_key=symbol,
                    source_id=source["_id"],
                    valid_from=valid_from_dt,
                    reason="Provider returned no rows for requested Binance asset/range",
                    ingestion_id=ingestion_id,
                )

                inserted = 0
                skipped = 0
            else:
                inserted, skipped = insert_series_points(
                    rows=rows,
                    source_id=source["_id"],
                    ingestion_id=ingestion_id,
                )

            complete_ingestion_event(
                ingestion_id=ingestion_id,
                status="success",
                rows_inserted=inserted,
                rows_skipped=skipped,
                response_hash=hash_payload(raw_payload),
                raw_payload_preview=serialize_value({
                    "request_url": request_url,
                    "items": len(raw_payload),
                    "symbol": symbol,
                    "interval": interval,
                    "auto_delete_info": auto_delete_info,
                })
            )

            return jsonify(serialize_value({
                "message": "Binance ingestion completed",
                "rows_inserted": inserted,
                "rows_skipped": skipped,
                "source": source["name"],
                "symbol": symbol,
                "interval": interval,
                "auto_delete_info": auto_delete_info,
            }))

        except Exception as inner_exc:
            complete_ingestion_event(
                ingestion_id=ingestion_id,
                status="failed",
                error_message=str(inner_exc),
            )
            raise

    except Exception as e:
        return jsonify({
            "error": "Binance ingestion failed",
            "details": str(e)
        }), 500


@ingestion_runner_bp.route("/ingestions/run/frankfurter", methods=["POST"])
def run_frankfurter_ingestion():
    try:
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        base = body.get("base")
        quote = body.get("quote")
        date_from = body.get("from")
        date_to = body.get("to")

        if not date_from:
            return jsonify({"error": "from is required"}), 400
        if not date_to:
            return jsonify({"error": "to is required"}), 400

        base, quote, fx_error = validate_frankfurter_inputs(base, quote)
        if fx_error:
            return fx_error

        _, _, date_error = validate_date_range(date_from, date_to)
        if date_error:
            return date_error

        source = get_or_create_source(
            name="Frankfurter",
            source_type="REST API",
            base_url="https://api.frankfurter.dev/v2",
            notes="FX market data with historical exchange rates",
            refresh_rate="daily"
        )

        ingestion_id = create_ingestion_event(
            source_id=source["_id"],
            endpoint="/rates",
            params={
                "base": base,
                "quote": quote,
                "from": date_from,
                "to": date_to,
            }
        )

        try:
            raw_payload, request_url = fetch_fx_time_series(
                base=base,
                quote=quote,
                date_from=date_from,
                date_to=date_to,
            )

            rows = normalize_fx_time_series(
                base=base,
                quote=quote,
                raw_payload=raw_payload,
            )

            auto_delete_info = None
            asset_key = f"{base.upper()}/{quote.upper()}"

            if not rows:
                valid_from_dt = datetime.fromisoformat(date_from)

                auto_delete_info = mark_asset_as_deleted_version(
                    asset_key=asset_key,
                    source_id=source["_id"],
                    valid_from=valid_from_dt,
                    reason="Provider returned no rows for requested FX pair/range",
                    ingestion_id=ingestion_id,
                )

                inserted = 0
                skipped = 0
            else:
                inserted, skipped = insert_series_points(
                    rows=rows,
                    source_id=source["_id"],
                    ingestion_id=ingestion_id,
                )

            complete_ingestion_event(
                ingestion_id=ingestion_id,
                status="success",
                rows_inserted=inserted,
                rows_skipped=skipped,
                response_hash=hash_payload(raw_payload),
                raw_payload_preview=serialize_value({
                    "request_url": request_url,
                    "items": len(raw_payload),
                    "pair": f"{base}/{quote}",
                    "auto_delete_info": auto_delete_info,
                })
            )

            return jsonify(serialize_value({
                "message": "Frankfurter ingestion completed",
                "rows_inserted": inserted,
                "rows_skipped": skipped,
                "source": source["name"],
                "pair": f"{base}/{quote}",
                "auto_delete_info": auto_delete_info,
            }))

        except Exception as inner_exc:
            complete_ingestion_event(
                ingestion_id=ingestion_id,
                status="failed",
                error_message=str(inner_exc),
            )
            raise

    except Exception as e:
        return jsonify({
            "error": "Frankfurter ingestion failed",
            "details": str(e)
        }), 500


@ingestion_runner_bp.route("/ingestions/recent", methods=["GET"])
def get_recent_ingestions():
    try:
        source_id = request.args.get("sourceId")
        status = request.args.get("status")
        limit = request.args.get("limit", default=20, type=int)

        query = {}

        if source_id:
            try:
                query["source_id"] = ObjectId(source_id)
            except InvalidId:
                return jsonify({"error": "Invalid sourceId"}), 400

        if status:
            query["status"] = status

        if limit is None or limit <= 0:
            limit = 20

        rows = list(
            db.ingestions.find(query)
            .sort("started_at", -1)
            .limit(limit)
        )

        return jsonify(serialize_docs(rows))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch recent ingestions",
            "details": str(e)
        }), 500