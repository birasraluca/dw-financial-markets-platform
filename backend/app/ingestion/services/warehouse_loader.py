from datetime import datetime
from app.db.mongo import db


def normalize_asset_payload(asset_doc: dict) -> dict:
    symbol = asset_doc["symbol"].strip().upper()

    return {
        "asset_key": symbol,
        "symbol": symbol,
        "name": asset_doc.get("name"),
        "assetClass": asset_doc.get("assetClass"),
        "region": asset_doc.get("region"),
        "attributes": asset_doc.get("attributes", {}),
        "provider_mappings": asset_doc.get("provider_mappings", {}),
    }


def normalize_source_payload(
    name: str,
    source_type: str,
    base_url: str,
    notes: str,
    refresh_rate: str = None,
) -> dict:
    source_key = name.strip().lower()

    return {
        "source_key": source_key,
        "name": name,
        "type": source_type,
        "baseUrl": base_url,
        "notes": notes,
        "refreshRate": refresh_rate,
    }


def asset_metadata_changed(existing: dict, incoming: dict) -> bool:
    comparable_fields = [
        "symbol",
        "name",
        "assetClass",
        "region",
        "attributes",
        "provider_mappings",
    ]

    for field in comparable_fields:
        if existing.get(field) != incoming.get(field):
            return True

    return False


def source_metadata_changed(existing: dict, incoming: dict) -> bool:
    comparable_fields = [
        "name",
        "type",
        "baseUrl",
        "notes",
        "refreshRate",
    ]

    for field in comparable_fields:
        if existing.get(field) != incoming.get(field):
            return True

    return False


def get_or_create_source(
    name: str,
    source_type: str,
    base_url: str,
    notes: str,
    refresh_rate: str = None,
):
    """
    Temporal versioning behavior:
    - if current active version does not exist -> insert version 1
    - if current active version exists and metadata is unchanged -> return it
    - if metadata changed -> close old version and insert new version
    """
    incoming = normalize_source_payload(
        name=name,
        source_type=source_type,
        base_url=base_url,
        notes=notes,
        refresh_rate=refresh_rate,
    )

    source_key = incoming["source_key"]

    existing = db.data_sources.find_one({
        "source_key": source_key,
        "is_current": True,
        "is_deleted": False,
    })

    now = datetime.utcnow()

    if not existing:
        doc = {
            **incoming,
            "valid_from": now,
            "valid_to": None,
            "is_current": True,
            "is_deleted": False,
            "version": 1,
        }
        result = db.data_sources.insert_one(doc)
        return db.data_sources.find_one({"_id": result.inserted_id})

    if not source_metadata_changed(existing, incoming):
        return existing

    db.data_sources.update_one(
        {"_id": existing["_id"]},
        {
            "$set": {
                "valid_to": now,
                "is_current": False,
            }
        }
    )

    new_doc = {
        **incoming,
        "valid_from": now,
        "valid_to": None,
        "is_current": True,
        "is_deleted": False,
        "version": existing.get("version", 1) + 1,
    }

    result = db.data_sources.insert_one(new_doc)
    return db.data_sources.find_one({"_id": result.inserted_id})


def get_or_create_asset(asset_doc: dict):
    """
    Temporal versioning behavior:
    - if current active version does not exist -> insert version 1
    - if current active version exists and metadata is unchanged -> return it
    - if metadata changed -> close old version and insert new version
    """
    incoming = normalize_asset_payload(asset_doc)
    asset_key = incoming["asset_key"]

    existing = db.assets.find_one({
        "asset_key": asset_key,
        "is_current": True,
        "is_deleted": False,
    })

    now = datetime.utcnow()

    if not existing:
        doc = {
            **incoming,
            "valid_from": now,
            "valid_to": None,
            "is_current": True,
            "is_deleted": False,
            "version": 1,
        }
        result = db.assets.insert_one(doc)
        return db.assets.find_one({"_id": result.inserted_id})

    if not asset_metadata_changed(existing, incoming):
        return existing

    db.assets.update_one(
        {"_id": existing["_id"]},
        {
            "$set": {
                "valid_to": now,
                "is_current": False,
            }
        }
    )

    new_doc = {
        **incoming,
        "valid_from": now,
        "valid_to": None,
        "is_current": True,
        "is_deleted": False,
        "version": existing.get("version", 1) + 1,
    }

    result = db.assets.insert_one(new_doc)
    return db.assets.find_one({"_id": result.inserted_id})


def insert_series_points(rows: list, source_id, ingestion_id):
    inserted = 0
    skipped = 0

    for row in rows:
        asset = get_or_create_asset(row["asset"])

        doc = {
            "asset_id": asset["_id"],
            "source_id": source_id,
            "ts": row["ts"],
            "metrics": row["metrics"],
            "ingestion_id": ingestion_id,
            "is_deleted": False,
            "marker_type": None,
            "reason": None,
        }

        exists = db.series_points.find_one({
            "asset_id": doc["asset_id"],
            "source_id": doc["source_id"],
            "ts": doc["ts"],
            "is_deleted": False,
        })

        if exists:
            skipped += 1
            continue

        db.series_points.insert_one(doc)
        inserted += 1

    return inserted, skipped


def insert_series_delete_marker(
    asset_id,
    source_id,
    valid_from,
    ingestion_id=None,
    reason="manual delete marker",
):
    existing_marker = db.series_points.find_one({
        "asset_id": asset_id,
        "source_id": source_id,
        "ts": valid_from,
        "is_deleted": True,
        "marker_type": "deletion",
    })

    if existing_marker:
        return existing_marker["_id"], False

    doc = {
        "asset_id": asset_id,
        "source_id": source_id,
        "ts": valid_from,
        "metrics": {},
        "ingestion_id": ingestion_id,
        "is_deleted": True,
        "marker_type": "deletion",
        "reason": reason,
    }

    result = db.series_points.insert_one(doc)
    return result.inserted_id, True

def mark_asset_as_deleted_version(asset_key: str, source_id, valid_from, reason="auto-marked unavailable", ingestion_id=None):
    """
    Closes the current active asset version and inserts a new current deleted version.
    Also inserts a delete marker into series_points for the previously active asset version id.
    """
    normalized_asset_key = asset_key.strip().upper()

    existing = db.assets.find_one({
        "asset_key": normalized_asset_key,
        "is_current": True,
    })

    if not existing:
        return {
            "asset_found": False,
            "asset_deleted_version_created": False,
            "series_delete_marker_inserted": False,
            "deleted_asset_id": None,
            "series_marker_id": None,
        }

    if existing.get("is_deleted") is True:
        return {
            "asset_found": True,
            "asset_deleted_version_created": False,
            "series_delete_marker_inserted": False,
            "deleted_asset_id": existing["_id"],
            "series_marker_id": None,
        }

    # Close previous active version
    db.assets.update_one(
        {"_id": existing["_id"]},
        {
            "$set": {
                "valid_to": valid_from,
                "is_current": False,
            }
        }
    )

    # Insert new deleted version
    deleted_doc = {
        "asset_key": existing["asset_key"],
        "symbol": existing.get("symbol"),
        "name": existing.get("name"),
        "assetClass": existing.get("assetClass"),
        "region": existing.get("region"),
        "attributes": existing.get("attributes", {}),
        "provider_mappings": existing.get("provider_mappings", {}),
        "valid_from": valid_from,
        "valid_to": None,
        "is_current": True,
        "is_deleted": True,
        "version": existing.get("version", 1) + 1,
        "deletion_reason": reason,
    }

    deleted_result = db.assets.insert_one(deleted_doc)

    # IMPORTANT:
    # Insert the series delete marker for the PREVIOUS active asset version id,
    # because historical series rows already point to that asset_id.
    marker_id, marker_inserted = insert_series_delete_marker(
        asset_id=existing["_id"],
        source_id=source_id,
        valid_from=valid_from,
        ingestion_id=ingestion_id,
        reason=reason,
    )

    return {
        "asset_found": True,
        "asset_deleted_version_created": True,
        "series_delete_marker_inserted": marker_inserted,
        "deleted_asset_id": deleted_result.inserted_id,
        "series_marker_id": marker_id,
    }


def mark_source_as_deleted_version(source_key: str, valid_from, reason="source marked unavailable"):
    """
    Closes the current active source version and inserts a new current deleted version.
    This is NOT automatically used in normal asset/pair ingestions, but supports
    metadata-level source deletion versioning if you ever need it.
    """
    normalized_source_key = source_key.strip().lower()

    existing = db.data_sources.find_one({
        "source_key": normalized_source_key,
        "is_current": True,
    })

    if not existing:
        return {
            "source_found": False,
            "source_deleted_version_created": False,
            "deleted_source_id": None,
        }

    if existing.get("is_deleted") is True:
        return {
            "source_found": True,
            "source_deleted_version_created": False,
            "deleted_source_id": existing["_id"],
        }

    db.data_sources.update_one(
        {"_id": existing["_id"]},
        {
            "$set": {
                "valid_to": valid_from,
                "is_current": False,
            }
        }
    )

    deleted_doc = {
        "source_key": existing["source_key"],
        "name": existing.get("name"),
        "type": existing.get("type"),
        "baseUrl": existing.get("baseUrl"),
        "notes": existing.get("notes"),
        "refreshRate": existing.get("refreshRate"),
        "valid_from": valid_from,
        "valid_to": None,
        "is_current": True,
        "is_deleted": True,
        "version": existing.get("version", 1) + 1,
        "deletion_reason": reason,
    }

    result = db.data_sources.insert_one(deleted_doc)

    return {
        "source_found": True,
        "source_deleted_version_created": True,
        "deleted_source_id": result.inserted_id,
    }