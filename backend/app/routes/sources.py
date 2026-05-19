from flask import Blueprint, jsonify, request
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.db.mongo import db
from app.utils.serializers import serialize_doc, serialize_docs

sources_bp = Blueprint("sources", __name__)


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


@sources_bp.route("/sources", methods=["GET"])
def get_sources():
    try:
        source_type = request.args.get("type")
        active_only = request.args.get("activeOnly", "true").lower() == "true"
        include_deleted = request.args.get("includeDeleted", "false").lower() == "true"

        query = {}

        if active_only:
            query["is_current"] = True
            query["is_deleted"] = False
        else:
            if not include_deleted:
                query["is_deleted"] = False

        if source_type:
            query["type"] = source_type

        docs = list(
            db.data_sources.find(query).sort([("name", 1), ("version", -1), ("valid_from", -1)])
        )

        return jsonify(serialize_docs(docs)), 200

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch sources",
            "details": str(e)
        }), 500


@sources_bp.route("/sources/<source_id>", methods=["GET"])
def get_source_by_id(source_id):
    try:
        source = db.data_sources.find_one({"_id": ObjectId(source_id)})
    except InvalidId:
        return jsonify({"error": "Invalid source id"}), 400
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch source",
            "details": str(e)
        }), 500

    if not source:
        return jsonify({"error": "Source not found"}), 404

    return jsonify(serialize_doc(source))


@sources_bp.route("/sources/by-key/<source_key>", methods=["GET"])
def get_source_by_key(source_key):
    try:
        as_of = request.args.get("asOf")
        as_of_dt = parse_as_of(as_of)

        normalized_key = source_key.strip().lower()

        if as_of and not as_of_dt:
            return jsonify({"error": "Invalid asOf date format. Use YYYY-MM-DD or ISO format."}), 400

        if as_of_dt:
            query = build_as_of_query("source_key", normalized_key, as_of_dt)
        else:
            query = {
                "source_key": normalized_key,
                "is_current": True
            }

        source = db.data_sources.find_one(query)

        if not source:
            return jsonify({"error": "Source version not found for the requested key/asOf"}), 404

        return jsonify(serialize_doc(source))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch source by key",
            "details": str(e)
        }), 500


@sources_bp.route("/sources/history/<source_key>", methods=["GET"])
def get_source_history(source_key):
    try:
        normalized_key = source_key.strip().lower()

        sources = list(
            db.data_sources.find(
                {"source_key": normalized_key}
            ).sort([("version", 1), ("valid_from", 1)])
        )

        if not sources:
            return jsonify({"error": "No source history found for the given key"}), 404

        return jsonify(serialize_docs(sources))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch source history",
            "details": str(e)
        }), 500