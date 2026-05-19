from flask import Flask
from app.routes.assets import assets_bp
from app.routes.sources import sources_bp
from app.routes.series import series_bp
from app.routes.ingestions import ingestions_bp
from app.routes.analytics import analytics_bp
from app.db.mongo import db, client, ensure_indexes
from app.routes.lookup import lookup_bp
from app.routes.ingestion_runner import ingestion_runner_bp
from app.routes.assistant import assistant_bp
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:5173"}})
ensure_indexes()

app.register_blueprint(assets_bp)
app.register_blueprint(sources_bp)
app.register_blueprint(series_bp)
app.register_blueprint(ingestions_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(lookup_bp)
app.register_blueprint(ingestion_runner_bp)
app.register_blueprint(assistant_bp)

@app.route("/")
def home():
    return {"message": "DW project backend is running"}

@app.route("/test-db")
def test_db():
    try:
        client.admin.command("ping")
        collections = db.list_collection_names()
        return {
            "message": "MongoDB connection works",
            "collections": collections
        }
    except Exception as e:
        return {
            "message": "MongoDB connection failed",
            "error": str(e)
        }, 500

if __name__ == "__main__":
    app.run(debug=False)