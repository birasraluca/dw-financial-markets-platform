from app.db.mongo import db

def reset():
    print("Clearing database...")

    db.series_points.delete_many({})
    db.assets.delete_many({})
    db.data_sources.delete_many({})
    db.ingestions.delete_many({})

    print("Database cleared successfully.")

if __name__ == "__main__":
    reset()