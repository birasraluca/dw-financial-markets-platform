from flask import Blueprint, jsonify
from bson import ObjectId
from bson.errors import InvalidId
from app.db.mongo import db
from app.utils.serializers import serialize_doc, serialize_docs

ingestions_bp = Blueprint("ingestions", __name__)

@ingestions_bp.route("/ingestions", methods=["GET"])
def get_ingestions():
    try:
        ingestions = list(db.ingestions.find().sort("started_at", -1))
        return jsonify(serialize_docs(ingestions))
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch ingestions",
            "details": str(e)
        }), 500


@ingestions_bp.route("/ingestions/<ingestion_id>", methods=["GET"])
def get_ingestion_by_id(ingestion_id):
    try:
        ingestion = db.ingestions.find_one({"_id": ObjectId(ingestion_id)})
    except InvalidId:
        return jsonify({"error": "Invalid ingestion id"}), 400
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch ingestion",
            "details": str(e)
        }), 500

    if not ingestion:
        return jsonify({"error": "Ingestion not found"}), 404

    return jsonify(serialize_doc(ingestion))