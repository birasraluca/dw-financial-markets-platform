import hashlib
import json
from datetime import datetime
from app.db.mongo import db


def hash_payload(payload) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_ingestion_event(source_id, endpoint, params, asset_ids=None):
    now = datetime.utcnow()

    doc = {
        "source_id": source_id,
        "started_at": now,
        "finished_at": None,
        "duration_ms": None,
        "status": "running",
        "endpoint": endpoint,
        "params": params,
        "asset_ids": asset_ids or [],
        "rows_inserted": 0,
        "rows_skipped": 0,
        "error_message": None,
        "response_hash": None,
        "raw_payload_preview": None,
    }

    result = db.ingestions.insert_one(doc)
    return result.inserted_id


def complete_ingestion_event(
    ingestion_id,
    status,
    rows_inserted=0,
    rows_skipped=0,
    response_hash=None,
    raw_payload_preview=None,
    error_message=None,
):
    existing = db.ingestions.find_one({"_id": ingestion_id})

    finished_at = datetime.utcnow()
    duration_ms = None

    if existing and existing.get("started_at"):
        delta = finished_at - existing["started_at"]
        duration_ms = int(delta.total_seconds() * 1000)

    db.ingestions.update_one(
        {"_id": ingestion_id},
        {
            "$set": {
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "status": status,
                "rows_inserted": rows_inserted,
                "rows_skipped": rows_skipped,
                "response_hash": response_hash,
                "raw_payload_preview": raw_payload_preview,
                "error_message": error_message,
            }
        }
    )