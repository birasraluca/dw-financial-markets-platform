# Financial Markets Data Warehouse Platform

A temporal NoSQL data warehouse platform for financial markets data.

The platform supports:
- financial data ingestion from external providers
- temporal/versioned metadata management
- time-series storage and analytics
- provenance tracking
- REST API exploration
- MCP-integrated assistant for natural language interaction

---

# Features

## Financial Data Ingestion
Supports ingestion from external financial data providers:

- Binance (cryptocurrency OHLCV market data)
- Frankfurter (foreign exchange rates)

The platform records:
- ingestion timestamps
- source/provider provenance
- ingestion parameters
- inserted/skipped row counts
- ingestion status/history

---

## Temporal NoSQL Data Warehouse

Implements a temporal data warehouse model using MongoDB.

### Temporal behavior
- records are never updated in place
- changes create new metadata versions
- deletions are represented through delete-marker records
- historical states can be queried using `asOf`

### Supported entities
- financial assets
- data sources/providers
- financial time series
- ingestion/provenance records

---

## REST API

The platform exposes a REST API for:
- asset discovery
- source discovery
- time-series retrieval
- analytics
- temporal history inspection
- provenance exploration

### Example endpoints

## Assets
```http
GET /assets
GET /assets/<id>
GET /assets/by-key/<asset_key>
GET /assets/history/<asset_key>
```

## Sources
```http
GET /sources
GET /sources/<id>
GET /sources/by-key/<source_key>
GET /sources/history/<source_key>
```

## Time Series
```http
GET /series
POST /series/delete-marker
```

## Analytics
```http
GET /analytics/summary
GET /analytics/trend
GET /analytics/forecast
GET /analytics/risk
GET /analytics/moving-average
GET /analytics/compare
GET /analytics/dashboard
```

## Ingestion
```http
POST /ingestions/run/binance
POST /ingestions/run/frankfurter
GET /ingestions/recent
GET /ingestions/<id>
```

## Assistant
```http
POST /assistant/query
```

---

# Analytics Capabilities

The platform supports:
- summaries (count/min/max/average/latest)
- trend analysis
- simple forecasting
- volatility/risk signals
- moving averages
- asset comparisons
- dashboard aggregation

Analytics support:
- temporal filtering using `asOf`
- delete-marker awareness
- provenance-aware exploration

---

# MCP Assistant Integration

The platform includes an MCP-integrated assistant capable of:
- listing assets
- listing data sources
- fetching time series
- summarizing trends
- comparing assets
- explaining changes
- retrieving temporal metadata history

Assistant responses are grounded in the platform’s warehouse data.

---

# Frontend Dashboard

The React frontend provides:
- asset/source selection
- analytics dashboards
- time-series visualizations
- asset comparison charts
- ingestion management
- provenance exploration
- metadata history inspection
- assistant interaction interface

---

# Tech Stack

## Backend
- Python
- Flask
- MongoDB
- MCP (FastMCP)

## Frontend
- React
- Vite
- Recharts

---

# Project Structure

```text
dw-financial-markets-platform/
│
├── backend/
│   ├── app/
│   │   ├── db/
│   │   ├── ingestion/
│   │   ├── routes/
│   │   ├── services/
│   │   └── utils/
│   │
│   ├── mcp_server.py
│   ├── refresh_db.ps1
│   ├── refresh_db.py
│   ├── requirements.txt
│   └── run.py
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
│
├── README.md
└── .gitignore
```

---

# Setup Instructions

# 1. Clone Repository

```bash
git clone https://github.com/birasraluca/dw-financial-markets-platform.git
cd dw-financial-markets-platform
```

---

# 2. Backend Setup

Navigate to backend:

```bash
cd backend
```

Create virtual environment:

```bash
python -m venv venv
```

Activate virtual environment:

## Windows
```bash
venv\Scripts\activate
```

## Linux / macOS
```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env` file:

```env
MONGO_URI=your_mongodb_connection_string
DB_NAME=dw_project

BINANCE_API_BASE_URL=https://api.binance.com/api/v3
FRANKFURTER_API_BASE_URL=https://api.frankfurter.dev/v2
```

Run backend:

```bash
python run.py
```

Backend runs on:

```text
http://localhost:5000
```

---

# 3. Frontend Setup

Navigate to frontend:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Run frontend:

```bash
npm run dev
```

Frontend runs on:

```text
http://localhost:5173
```

---

# Example Ingestion Commands

## Binance

```bash
curl.exe -X POST http://localhost:5000/ingestions/run/binance ^
-H "Content-Type: application/json" ^
-d "{\"symbol\":\"BTCUSDT\",\"name\":\"Bitcoin / Tether\",\"interval\":\"1d\",\"from\":\"2024-01-01\",\"to\":\"2024-12-31\"}"
```

## Frankfurter

```bash
curl.exe -X POST http://localhost:5000/ingestions/run/frankfurter ^
-H "Content-Type: application/json" ^
-d "{\"base\":\"EUR\",\"quote\":\"USD\",\"from\":\"2024-01-01\",\"to\":\"2024-12-31\"}"
```

---

# Temporal Data Model

The platform implements temporal versioning for metadata.

Metadata entities include:
- `asset_key`
- `source_key`
- `valid_from`
- `valid_to`
- `version`
- `is_current`
- `is_deleted`

Delete-marker records are used instead of physical deletions.

---

# Example Use Cases

- explore available financial assets
- retrieve historical FX or crypto data
- compare financial assets
- inspect ingestion provenance
- retrieve historical metadata versions
- analyze trends and volatility
- interact with the warehouse using natural language

---

# Screenshots

## Dashboard
<img width="456" height="638" alt="image" src="https://github.com/user-attachments/assets/6a685d1d-1cbc-4fa7-9f8c-52289dc15ba7" />

<img width="449" height="276" alt="image" src="https://github.com/user-attachments/assets/da288bd7-408e-412f-9a66-69ded7cb311e" />
<img width="449" height="478" alt="image" src="https://github.com/user-attachments/assets/79dc6425-9903-4300-b988-0070d56ede8b" />


## Ingestion
<img width="448" height="614" alt="image" src="https://github.com/user-attachments/assets/b99a9a00-5489-4937-a603-962b5cb1c816" />
<img width="427" height="327" alt="image" src="https://github.com/user-attachments/assets/d407b68f-d025-43a2-8bf4-c3a106c28540" />


## Asset Comparison
<img width="457" height="494" alt="image" src="https://github.com/user-attachments/assets/1d7ae476-d4e3-4d18-85d2-7df8c0c444cf" />


## Metadata History
<img width="450" height="175" alt="image" src="https://github.com/user-attachments/assets/a498b7c5-76ef-4c01-8b82-8ac59ccb47b9" />


## Assistant Interaction
<img width="449" height="501" alt="image" src="https://github.com/user-attachments/assets/613baa8c-6c0f-4a01-aa0f-b2024b6328bc" />
