from flask import Blueprint, jsonify
from app.db.mongo import db
from app.utils.serializers import serialize_docs, serialize_value

lookup_bp = Blueprint("lookup", __name__)


@lookup_bp.route("/lookup/options", methods=["GET"])
def get_lookup_options():
    try:
        assets = list(
            db.assets.find(
                {
                    "is_current": True,
                    "is_deleted": False
                },
                {
                    "asset_key": 1,
                    "symbol": 1,
                    "name": 1,
                    "assetClass": 1
                }
            ).sort("symbol", 1)
        )

        sources = list(
            db.data_sources.find(
                {
                    "is_current": True,
                    "is_deleted": False
                },
                {
                    "source_key": 1,
                    "name": 1,
                    "type": 1
                }
            ).sort("name", 1)
        )

        response = {
            "assets": serialize_docs(assets),
            "sources": serialize_docs(sources)
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch lookup options",
            "details": str(e)
        }), 500


@lookup_bp.route("/lookup/valid-combinations", methods=["GET"])
def get_valid_combinations():
    try:
        pipeline = [
            {
                "$match": {
                    "is_deleted": False
                }
            },
            {
                "$group": {
                    "_id": {
                        "asset_id": "$asset_id",
                        "source_id": "$source_id"
                    }
                }
            },
            {
                "$lookup": {
                    "from": "assets",
                    "localField": "_id.asset_id",
                    "foreignField": "_id",
                    "as": "asset"
                }
            },
            {
                "$lookup": {
                    "from": "data_sources",
                    "localField": "_id.source_id",
                    "foreignField": "_id",
                    "as": "source"
                }
            }
        ]

        results = list(db.series_points.aggregate(pipeline))

        combinations = []
        for row in results:
            asset = row["asset"][0] if row["asset"] else None
            source = row["source"][0] if row["source"] else None

            combinations.append({
                "asset_id": row["_id"]["asset_id"],
                "source_id": row["_id"]["source_id"],
                "asset_symbol": asset.get("symbol") if asset else None,
                "asset_name": asset.get("name") if asset else None,
                "source_name": source.get("name") if source else None,
            })

        return jsonify(serialize_value(combinations))

    except Exception as e:
        return jsonify({
            "error": "Failed to fetch valid combinations",
            "details": str(e)
        }), 500