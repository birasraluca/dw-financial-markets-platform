from flask import Blueprint, jsonify, request
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.db.mongo import db
from app.utils.serializers import serialize_docs, serialize_value
from app.ingestion.services.warehouse_loader import insert_series_delete_marker

series_bp = Blueprint("series", __name__)


def parse_datetime(value: str, field_name: str):
    """
    Parse YYYY-MM-DD or ISO datetime string.
    Returns (datetime_obj, None) on success, or (None, (response, status_code)) on failure.
    """
    if not value:
        return None, None

    try:
        return datetime.fromisoformat(value), None
    except ValueError:
        return None, (
            jsonify({"error": f"Invalid '{field_name}' date format. Use YYYY-MM-DD or ISO format."}),
            400,
        )


def get_deletion_cutoff(asset_object_id, source_object_id, as_of_dt=None):
    """
    Returns the earliest deletion marker timestamp for the asset/source pair.
    If as_of_dt is provided, only markers up to that time are considered.
    """
    query = {
        "asset_id": asset_object_id,
        "source_id": source_object_id,
        "is_deleted": True,
        "marker_type": "deletion",
    }

    if as_of_dt:
        query["ts"] = {"$lte": as_of_dt}

    marker = db.series_points.find_one(query, sort=[("ts", 1)])
    return marker["ts"] if marker else None


@series_bp.route("/series", methods=["GET"])
def get_series():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        date_from = request.args.get("from")
        date_to = request.args.get("to")
        as_of = request.args.get("asOf")
        include_deleted = request.args.get("includeDeleted", "false").lower() == "true"
        limit = request.args.get("limit")

        query = {}

        # Default behavior: only active series rows
        if not include_deleted:
            query["is_deleted"] = False

        asset_object_id = None
        source_object_id = None

        if asset_id:
            try:
                asset_object_id = ObjectId(asset_id)
                query["asset_id"] = asset_object_id
            except InvalidId:
                return jsonify({"error": "Invalid assetId"}), 400

        if source_id:
            try:
                source_object_id = ObjectId(source_id)
                query["source_id"] = source_object_id
            except InvalidId:
                return jsonify({"error": "Invalid sourceId"}), 400

        from_dt, from_err = parse_datetime(date_from, "from")
        if from_err:
            return from_err

        to_dt, to_err = parse_datetime(date_to, "to")
        if to_err:
            return to_err

        as_of_dt, as_of_err = parse_datetime(as_of, "asOf")
        if as_of_err:
            return as_of_err

        ts_conditions = {}

        if from_dt:
            ts_conditions["$gte"] = from_dt

        if to_dt:
            ts_conditions["$lte"] = to_dt

        if as_of_dt:
            # asOf means: return state up to this moment
            # If there is already an upper bound, keep the earlier one.
            if "$lte" in ts_conditions:
                ts_conditions["$lte"] = min(ts_conditions["$lte"], as_of_dt)
            else:
                ts_conditions["$lte"] = as_of_dt

        # Apply deletion marker cutoff only for normal active queries
        # and only when asset+source are both known.
        if not include_deleted and asset_object_id and source_object_id:
            deletion_cutoff = get_deletion_cutoff(asset_object_id, source_object_id, as_of_dt)

            if deletion_cutoff:
                # Active rows are valid strictly before the deletion marker timestamp.
                existing_upper = ts_conditions.get("$lte")

                if existing_upper is None:
                    ts_conditions["$lt"] = deletion_cutoff
                else:
                    # Keep the tighter upper bound between existing upper and deletion cutoff.
                    # Since deletion is exclusive, convert to $lt when cutoff is tighter.
                    if deletion_cutoff <= existing_upper:
                        ts_conditions.pop("$lte", None)
                        ts_conditions["$lt"] = deletion_cutoff

        if ts_conditions:
            query["ts"] = ts_conditions

        cursor = db.series_points.find(query).sort("ts", 1)

        if limit:
            try:
                limit_value = int(limit)
                if limit_value <= 0:
                    return jsonify({"error": "limit must be a positive integer"}), 400
                cursor = cursor.limit(limit_value)
            except ValueError:
                return jsonify({"error": "Invalid limit. Use a positive integer."}), 400

        series_points = list(cursor)
        return jsonify(serialize_docs(series_points))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch series data",
            "details": str(e)
        }), 500


@series_bp.route("/series/history", methods=["GET"])
def get_series_history():
    try:
        asset_id = request.args.get("assetId")
        source_id = request.args.get("sourceId")
        limit = request.args.get("limit")

        query = {}

        if asset_id:
            try:
                query["asset_id"] = ObjectId(asset_id)
            except InvalidId:
                return jsonify({"error": "Invalid assetId"}), 400

        if source_id:
            try:
                query["source_id"] = ObjectId(source_id)
            except InvalidId:
                return jsonify({"error": "Invalid sourceId"}), 400

        cursor = db.series_points.find(query).sort("ts", 1)

        if limit:
            try:
                limit_value = int(limit)
                if limit_value <= 0:
                    return jsonify({"error": "limit must be a positive integer"}), 400
                cursor = cursor.limit(limit_value)
            except ValueError:
                return jsonify({"error": "Invalid limit. Use a positive integer."}), 400

        rows = list(cursor)
        return jsonify(serialize_docs(rows))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch series history",
            "details": str(e)
        }), 500


@series_bp.route("/series/delete-marker", methods=["POST"])
def create_series_delete_marker():
    try:
        body = request.get_json(silent=True)
        if body is None:
            return jsonify({"error": "Request body must be valid JSON"}), 400

        asset_id = body.get("assetId")
        source_id = body.get("sourceId")
        valid_from = body.get("validFrom")
        reason = body.get("reason", "manual delete marker")

        if not asset_id:
            return jsonify({"error": "assetId is required"}), 400
        if not source_id:
            return jsonify({"error": "sourceId is required"}), 400
        if not valid_from:
            return jsonify({"error": "validFrom is required"}), 400

        try:
            asset_object_id = ObjectId(asset_id)
        except InvalidId:
            return jsonify({"error": "Invalid assetId"}), 400

        try:
            source_object_id = ObjectId(source_id)
        except InvalidId:
            return jsonify({"error": "Invalid sourceId"}), 400

        asset = db.assets.find_one({"_id": asset_object_id})
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        source = db.data_sources.find_one({"_id": source_object_id})
        if not source:
            return jsonify({"error": "Source not found"}), 404

        try:
            valid_from_dt = datetime.fromisoformat(valid_from)
        except ValueError:
            return jsonify({"error": "Invalid validFrom date format. Use YYYY-MM-DD or ISO format."}), 400

        marker_id, inserted = insert_series_delete_marker(
            asset_id=asset_object_id,
            source_id=source_object_id,
            valid_from=valid_from_dt,
            ingestion_id=None,
            reason=reason,
        )

        return jsonify(serialize_value({
            "message": "Deletion marker processed",
            "marker_id": marker_id,
            "inserted": inserted,
            "asset_id": asset_object_id,
            "source_id": source_object_id,
            "valid_from": valid_from_dt,
            "reason": reason,
        }))

    except Exception as e:
        return jsonify({
            "error": "Failed to create deletion marker",
            "details": str(e)
        }), 500