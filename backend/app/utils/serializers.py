from bson import ObjectId
from datetime import datetime

def serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    return value

def serialize_doc(doc):
    if not doc:
        return None
    return {k: serialize_value(v) for k, v in doc.items()}

def serialize_docs(docs):
    return [serialize_doc(doc) for doc in docs]