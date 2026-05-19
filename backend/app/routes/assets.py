from flask import Blueprint, jsonify, request
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.db.mongo import db
from app.utils.serializers import serialize_doc, serialize_docs

assets_bp = Blueprint("assets", __name__)


def parse_as_of(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_as_of_query(entity_key_field: str, entity_key: str, as_of_dt: datetime):
    return {
        entity_key_field: entity_key,
        "valid_from": {"$lte": as_of_dt},
        "$or": [
            {"valid_to": None},
            {"valid_to": {"$gt": as_of_dt}}
        ]
    }


@assets_bp.route("/assets", methods=["GET"])
def get_assets():
    try:
        asset_class = request.args.get("assetClass")
        active_only = request.args.get("activeOnly", "true").lower() == "true"
        include_deleted = request.args.get("includeDeleted", "false").lower() == "true"

        query = {}

        if active_only:
            query["is_current"] = True
            query["is_deleted"] = False
        else:
            if not include_deleted:
                query["is_deleted"] = False

        if asset_class:
            query["assetClass"] = asset_class

        docs = list(db.assets.find(query).sort([("symbol", 1), ("version", -1), ("valid_from", -1)]))

        return jsonify(serialize_docs(docs)), 200

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch assets",
            "details": str(e)
        }), 500


@assets_bp.route("/assets/<asset_id>", methods=["GET"])
def get_asset_by_id(asset_id):
    try:
        asset = db.assets.find_one({"_id": ObjectId(asset_id)})
    except InvalidId:
        return jsonify({"error": "Invalid asset id"}), 400
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch asset",
            "details": str(e)
        }), 500

    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    return jsonify(serialize_doc(asset))


@assets_bp.route("/assets/by-key/<path:asset_key>", methods=["GET"])
def get_asset_by_key(asset_key):
    try:
        as_of = request.args.get("asOf")
        as_of_dt = parse_as_of(as_of)

        normalized_key = asset_key.strip().upper()

        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        if as_of_dt:
            query = build_as_of_query("asset_key", normalized_key, as_of_dt)
        else:
            query = {
                "asset_key": normalized_key,
                "is_current": True
            }

        asset = db.assets.find_one(query)

        if not asset:
            return jsonify({"error": "Asset version not found for the requested key/asOf"}), 404

        return jsonify(serialize_doc(asset))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch asset by key",
            "details": str(e)
        }), 500


@assets_bp.route("/assets/history/<path:asset_key>", methods=["GET"])
def get_asset_history(asset_key):
    try:
        normalized_key = asset_key.strip().upper()

        assets = list(
            db.assets.find(
                {"asset_key": normalized_key}
            ).sort([("version", 1), ("valid_from", 1)])
        )

        if not assets:
            return jsonify({"error": "No asset history found for the given key"}), 404

        return jsonify(serialize_docs(assets))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch asset history",
            "details": str(e)
        }), 500