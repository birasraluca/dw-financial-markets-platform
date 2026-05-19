const API_BASE_URL = "http://localhost:5000";

async function handleJsonResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.error || data?.details || fallbackMessage);
  }

  return data;
}

export async function fetchLookupOptions() {
  const response = await fetch(`${API_BASE_URL}/lookup/options`);
  return handleJsonResponse(response, "Failed to load lookup options");
}

export async function fetchValidCombinations() {
  const response = await fetch(`${API_BASE_URL}/lookup/valid-combinations`);
  return handleJsonResponse(response, "Failed to load valid combinations");
}

export async function fetchDashboard(assetId, sourceId, window = 5, asOf = "") {
  const params = new URLSearchParams({
    assetId,
    sourceId,
    window: String(window),
  });

  if (asOf) {
    params.append("asOf", asOf);
  }

  const response = await fetch(`${API_BASE_URL}/analytics/dashboard?${params.toString()}`);
  return handleJsonResponse(response, "Failed to load dashboard data");
}

export async function fetchSeries(assetId, sourceId, asOf = "") {
  const params = new URLSearchParams({
    assetId,
    sourceId,
  });

  if (asOf) {
    params.append("asOf", asOf);
  }

  const response = await fetch(`${API_BASE_URL}/series?${params.toString()}`);
  return handleJsonResponse(response, "Failed to load series data");
}

export async function fetchCompare(assetId1, assetId2, sourceId, asOf = "") {
  const params = new URLSearchParams({
    assetId1,
    assetId2,
    sourceId,
  });

  if (asOf) {
    params.append("asOf", asOf);
  }

  const response = await fetch(`${API_BASE_URL}/analytics/compare?${params.toString()}`);
  return handleJsonResponse(response, "Failed to load comparison data");
}

export async function runBinanceIngestion(payload) {
  const response = await fetch(`${API_BASE_URL}/ingestions/run/binance`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response, "Failed to run Binance ingestion");
}

export async function runFrankfurterIngestion(payload) {
  const response = await fetch(`${API_BASE_URL}/ingestions/run/frankfurter`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response, "Failed to run Frankfurter ingestion");
}

export async function fetchRecentIngestions({ sourceId = "", status = "", limit = 20 } = {}) {
  const params = new URLSearchParams();

  if (sourceId) {
    params.append("sourceId", sourceId);
  }

  if (status) {
    params.append("status", status);
  }

  if (limit) {
    params.append("limit", String(limit));
  }

  const queryString = params.toString();
  const url = queryString
    ? `${API_BASE_URL}/ingestions/recent?${queryString}`
    : `${API_BASE_URL}/ingestions/recent`;

  const response = await fetch(url);
  return handleJsonResponse(response, "Failed to load recent ingestions");
}

export async function fetchAssetHistory(assetKey) {
  const response = await fetch(`${API_BASE_URL}/assets/history/${encodeURIComponent(assetKey)}`);
  return handleJsonResponse(response, "Failed to load asset history");
}

export async function fetchSourceHistory(sourceKey) {
  const response = await fetch(`${API_BASE_URL}/sources/history/${encodeURIComponent(sourceKey)}`);
  return handleJsonResponse(response, "Failed to load source history");
}

export async function fetchIngestionById(ingestionId) {
  const response = await fetch(`${API_BASE_URL}/ingestions/${encodeURIComponent(ingestionId)}`);
  return handleJsonResponse(response, "Failed to load ingestion details");
}

export async function queryAssistant(payload) {
  const response = await fetch(`${API_BASE_URL}/assistant/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse(response, "Assistant query failed");
}