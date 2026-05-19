import { useEffect, useMemo, useState } from "react";
import {
  fetchLookupOptions,
  fetchValidCombinations,
  fetchDashboard,
  fetchSeries,
  fetchCompare,
  runBinanceIngestion,
  runFrankfurterIngestion,
  fetchRecentIngestions,
  fetchAssetHistory,
  fetchSourceHistory,
  fetchIngestionById,
  queryAssistant,
} from "./api";
import "./App.css";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  if (typeof value !== "number") {
    return value;
  }

  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: value % 1 !== 0 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDateLabel(isoString) {
  if (!isoString) return "-";
  return isoString.slice(0, 10);
}

function getTrendBadgeClass(direction) {
  if (direction === "up") return "badge badge-up";
  if (direction === "down") return "badge badge-down";
  return "badge badge-flat";
}

function getRiskBadgeClass(level) {
  if (level === "low") return "badge badge-low";
  if (level === "medium") return "badge badge-medium";
  if (level === "high") return "badge badge-high";
  return "badge";
}

function getStatusBadgeClass(status) {
  if (status === "success") return "badge-success";
  if (status === "failed") return "badge-failed";
  if (status === "running") return "badge-running";
  return "badge-flat";
}

function prettifyMetricLabel(metricLabel) {
  if (metricLabel === "exchange_rate") return "Exchange Rate";
  return "Close";
}

function getSeriesValue(point) {
  return point.metrics?.close ?? point.metrics?.exchange_rate ?? null;
}

function formatDateTimeLabel(isoString) {
  if (!isoString) return "-";
  return isoString.replace("T", " ").slice(0, 19);
}

function getCurrentBadgeClass(isCurrent) {
  return isCurrent ? "badge badge-up" : "badge badge-flat";
}

function getMetadataStatus(row) {
  if (row?.is_current && row?.is_deleted) {
    return {
      label: "current deleted",
      className: "badge badge-deleted",
    };
  }

  if (row?.is_current) {
    return {
      label: "current active",
      className: "badge badge-current",
    };
  }

  return {
    label: "historical",
    className: "badge badge-historical",
  };
}

function CompareCard({ item }) {
  const metricTitle = prettifyMetricLabel(item.metric_label);

  return (
    <div className="card">
      <h3>
        {item.asset_symbol} - {item.asset_name}
      </h3>
      <p><strong>Source:</strong> {item.source_name}</p>
      <p><strong>Count:</strong> {formatNumber(item.count)}</p>
      <p><strong>Min {metricTitle}:</strong> {formatNumber(item.min_value)}</p>
      <p><strong>Max {metricTitle}:</strong> {formatNumber(item.max_value)}</p>
      <p><strong>Avg {metricTitle}:</strong> {formatNumber(item.avg_value)}</p>
      <p><strong>Latest {metricTitle}:</strong> {formatNumber(item.latest_value)}</p>
      <p><strong>From:</strong> {formatDateLabel(item.from)}</p>
      <p><strong>To:</strong> {formatDateLabel(item.to)}</p>
    </div>
  );
}

function IngestionHistoryTable({ rows }) {
  if (!rows.length) {
    return <p>No ingestion runs yet.</p>;
  }

  return (
    <div className="table-wrapper">
      <table className="ingestion-table">
        <thead>
          <tr>
            <th>Started</th>
            <th>Finished</th>
            <th>Duration</th>
            <th>Status</th>
            <th>Endpoint</th>
            <th>Rows Inserted</th>
            <th>Rows Skipped</th>
            <th>Params</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row._id}>
              <td>{formatDateLabel(row.started_at)}</td>
              <td>{formatDateLabel(row.finished_at)}</td>
              <td>{row.duration_ms != null ? `${formatNumber(row.duration_ms)} ms` : "-"}</td>
              <td>
                <span className={`badge ${getStatusBadgeClass(row.status)}`}>
                  {row.status || "-"}
                </span>
              </td>
              <td>{row.endpoint || "-"}</td>
              <td>{formatNumber(row.rows_inserted)}</td>
              <td>{formatNumber(row.rows_skipped)}</td>
              <td className="params-cell">
                {row.params ? JSON.stringify(row.params) : "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetadataHistoryTable({ title, rows, type }) {
  if (!rows.length) {
    return (
      <div className="card">
        <h3>{title}</h3>
        <p>No history available.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>{title}</h3>
      <div className="table-wrapper">
        <table className="ingestion-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Current</th>
              <th>Deleted</th>
              <th>Valid From</th>
              <th>Valid To</th>
              <th>{type === "asset" ? "Name" : "Notes"}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row._id}>
                <td>{formatNumber(row.version)}</td>
                <td>
                  <span className={getMetadataStatus(row).className}>
                    {getMetadataStatus(row).label}
                  </span>
                </td>
                <td>
                  <span className={row.is_deleted ? "badge badge-deleted" : "badge badge-current"}>
                    {row.is_deleted ? "yes" : "no"}
                  </span>
                </td>
                <td>{formatDateTimeLabel(row.valid_from)}</td>
                <td>{formatDateTimeLabel(row.valid_to)}</td>
                <td>{type === "asset" ? row.name || "-" : row.notes || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProvenanceTable({ rows, selectedIngestionId, onSelect }) {
  if (!rows.length) {
    return <p>No provenance records available for this source.</p>;
  }

  return (
    <div className="table-wrapper">
      <table className="ingestion-table">
        <thead>
          <tr>
            <th>Started</th>
            <th>Duration</th>
            <th>Status</th>
            <th>Endpoint</th>
            <th>Inserted</th>
            <th>Skipped</th>
            <th>Params</th>
            <th>Response Hash</th>
            <th>Preview</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isSelected = row._id === selectedIngestionId;

            return (
              <tr
                key={row._id}
                onClick={() => onSelect?.(row._id)}
                style={{
                  cursor: "pointer",
                  background: isSelected ? "rgba(127, 179, 255, 0.12)" : "transparent",
                }}
                title="Click to view full ingestion details"
              >
                <td>{formatDateTimeLabel(row.started_at)}</td>
                <td>{row.duration_ms != null ? `${formatNumber(row.duration_ms)} ms` : "-"}</td>
                <td>
                  <span className={`badge ${getStatusBadgeClass(row.status)}`}>
                    {row.status || "-"}
                  </span>
                </td>
                <td>{row.endpoint || "-"}</td>
                <td>{formatNumber(row.rows_inserted)}</td>
                <td>{formatNumber(row.rows_skipped)}</td>
                <td className="params-cell">
                  {row.params ? JSON.stringify(row.params) : "-"}
                </td>
                <td className="params-cell">
                  {row.response_hash ? String(row.response_hash).slice(0, 16) + "..." : "-"}
                </td>
                <td className="params-cell">
                  {row.raw_payload_preview ? JSON.stringify(row.raw_payload_preview) : "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function IngestionDetailsCard({ details }) {
  if (!details) {
    return (
      <div className="card">
        <h3>Ingestion Details</h3>
        <p>Select an ingestion row to inspect full details.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Ingestion Details</h3>
      <p><strong>Started:</strong> {formatDateTimeLabel(details.started_at)}</p>
      <p><strong>Finished:</strong> {formatDateTimeLabel(details.finished_at)}</p>
      <p><strong>Duration:</strong> {details.duration_ms != null ? `${formatNumber(details.duration_ms)} ms` : "-"}</p>
      <p>
        <strong>Status:</strong>{" "}
        <span className={`badge ${getStatusBadgeClass(details.status)}`}>
          {details.status || "-"}
        </span>
      </p>
      <p><strong>Endpoint:</strong> {details.endpoint || "-"}</p>
      <p><strong>Rows Inserted:</strong> {formatNumber(details.rows_inserted)}</p>
      <p><strong>Rows Skipped:</strong> {formatNumber(details.rows_skipped)}</p>
      <p><strong>Response Hash:</strong> {details.response_hash || "-"}</p>

      <p><strong>Params:</strong></p>
      <pre className="json-block">
        {details.params ? JSON.stringify(details.params, null, 2) : "-"}
      </pre>

      <p><strong>Payload Preview:</strong></p>
      <pre className="json-block">
        {details.raw_payload_preview ? JSON.stringify(details.raw_payload_preview, null, 2) : "-"}
      </pre>

      <p><strong>Error Message:</strong></p>
      <pre className="json-block">
        {details.error_message || "-"}
      </pre>
    </div>
  );
}

function normalizeSeriesData(rows, seriesKeys) {
  if (!rows.length) return rows;

  const baselines = {};

  for (const key of seriesKeys) {
    const firstValid = rows.find((row) => row[key] !== null && row[key] !== undefined);
    baselines[key] = firstValid ? firstValid[key] : null;
  }

  return rows.map((row) => {
    const normalizedRow = { date: row.date };

    for (const key of seriesKeys) {
      const value = row[key];
      const baseline = baselines[key];

      if (value === null || value === undefined || baseline === null || baseline === 0) {
        normalizedRow[key] = null;
      } else {
        normalizedRow[key] = Number(((value / baseline) * 100).toFixed(2));
      }
    }

    return normalizedRow;
  });
}


function AssistantChatHistory({ messages }) {
  if (!messages.length) {
    return (
      <div className="card">
        <h3>Conversation</h3>
        <p>No messages yet. Ask something about the selected data.</p>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Conversation</h3>
      <div className="assistant-chat-list">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`assistant-chat-message assistant-chat-${message.role}`}
          >
            <div className="assistant-chat-meta">
              <strong>{message.role === "user" ? "You" : "Assistant"}</strong>
              {message.mode && message.role === "assistant" && (
                <span className="assistant-chat-mode">{message.mode}</span>
              )}
            </div>

            <pre className="assistant-chat-content">{message.content}</pre>

            {message.role === "assistant" && message.data && (
              <details style={{ marginTop: "8px" }}>
                <summary style={{ cursor: "pointer" }}>Structured data</summary>
                <pre className="json-block" style={{ marginTop: "8px" }}>
                  {JSON.stringify(message.data, null, 2)}
                </pre>
              </details>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function App() {
  const [assets, setAssets] = useState([]);
  const [sources, setSources] = useState([]);
  const [validCombinations, setValidCombinations] = useState([]);

  const [selectedAssetId, setSelectedAssetId] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState("");

  const [compareAssetId1, setCompareAssetId1] = useState("");
  const [compareAssetId2, setCompareAssetId2] = useState("");
  const [compareSourceId, setCompareSourceId] = useState("");

  const [dashboard, setDashboard] = useState(null);
  const [seriesData, setSeriesData] = useState([]);
  const [compareData, setCompareData] = useState(null);
  const [compareSeriesData, setCompareSeriesData] = useState([]);
  const [recentIngestions, setRecentIngestions] = useState([]);

  const [movingAverageWindow, setMovingAverageWindow] = useState(5);

  const [loadingOptions, setLoadingOptions] = useState(true);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [loadingCompare, setLoadingCompare] = useState(false);
  const [loadingIngestionHistory, setLoadingIngestionHistory] = useState(false);
  const [runningIngestion, setRunningIngestion] = useState(false);

  const [error, setError] = useState("");
  const [compareError, setCompareError] = useState("");
  const [ingestionError, setIngestionError] = useState("");
  const [ingestionSuccess, setIngestionSuccess] = useState("");

  const [ingestionProvider, setIngestionProvider] = useState("binance");
  const [ingestionFrom, setIngestionFrom] = useState("2024-01-01");
  const [ingestionTo, setIngestionTo] = useState("2024-12-31");

  const [binanceSymbol, setBinanceSymbol] = useState("BTCUSDT");
  const [binanceName, setBinanceName] = useState("Bitcoin / Tether");
  const [binanceInterval, setBinanceInterval] = useState("1d");

  const [fxBase, setFxBase] = useState("EUR");
  const [fxQuote, setFxQuote] = useState("USD");

  const [dashboardAsOf, setDashboardAsOf] = useState("");
  const [compareAsOf, setCompareAsOf] = useState("");

  const [assetHistory, setAssetHistory] = useState([]);
  const [sourceHistory, setSourceHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState("");

  const [selectionIngestions, setSelectionIngestions] = useState([]);
  const [loadingSelectionIngestions, setLoadingSelectionIngestions] = useState(false);
  const [selectionIngestionsError, setSelectionIngestionsError] = useState("");

  const [normalizeCompare, setNormalizeCompare] = useState(false);

  const [selectedIngestionId, setSelectedIngestionId] = useState("");
  const [selectedIngestionDetails, setSelectedIngestionDetails] = useState(null);
  const [loadingIngestionDetails, setLoadingIngestionDetails] = useState(false);
  const [ingestionDetailsError, setIngestionDetailsError] = useState("");

  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [assistantError, setAssistantError] = useState("");

  const [assistantMessages, setAssistantMessages] = useState([]);

  const cryptoAssets = useMemo(
    () => assets.filter((asset) => asset.assetClass === "crypto"),
    [assets]
  );

  const fxAssets = useMemo(
    () => assets.filter((asset) => asset.assetClass === "fx"),
    [assets]
  );

  const assetsWithAnyData = useMemo(() => {
    const validAssetIds = new Set(validCombinations.map((row) => row.asset_id));
    return assets.filter((asset) => validAssetIds.has(asset._id));
  }, [assets, validCombinations]);

  const compareAsset1Doc = useMemo(
    () => assets.find((asset) => asset._id === compareAssetId1),
    [assets, compareAssetId1]
  );

  const compareAsset2Doc = useMemo(
    () => assets.find((asset) => asset._id === compareAssetId2),
    [assets, compareAssetId2]
  );

  const validSourceIdsForSelectedAsset = useMemo(() => {
    if (!selectedAssetId) return [];
    return [
      ...new Set(
        validCombinations
          .filter((row) => row.asset_id === selectedAssetId)
          .map((row) => row.source_id)
      ),
    ];
  }, [validCombinations, selectedAssetId]);

  const filteredDashboardSources = useMemo(() => {
    if (!selectedAssetId) return sources;
    return sources.filter((source) => validSourceIdsForSelectedAsset.includes(source._id));
  }, [sources, selectedAssetId, validSourceIdsForSelectedAsset]);

  const validAsset2IdsForAsset1 = useMemo(() => {
    if (!compareAssetId1) return [];

    const sourceIdsForAsset1 = new Set(
      validCombinations
        .filter((row) => row.asset_id === compareAssetId1)
        .map((row) => row.source_id)
    );

    return [
      ...new Set(
        validCombinations
          .filter(
            (row) =>
              row.asset_id !== compareAssetId1 &&
              sourceIdsForAsset1.has(row.source_id)
          )
          .map((row) => row.asset_id)
      ),
    ];
  }, [validCombinations, compareAssetId1]);

  const filteredCompareAsset2Options = useMemo(() => {
    if (!compareAssetId1) return assetsWithAnyData;
    return assetsWithAnyData.filter((asset) => validAsset2IdsForAsset1.includes(asset._id));
  }, [assetsWithAnyData, compareAssetId1, validAsset2IdsForAsset1]);

  const validCompareSourceIds = useMemo(() => {
    if (!compareAssetId1 || !compareAssetId2) return [];

    const asset1SourceIds = new Set(
      validCombinations
        .filter((row) => row.asset_id === compareAssetId1)
        .map((row) => row.source_id)
    );

    const asset2SourceIds = new Set(
      validCombinations
        .filter((row) => row.asset_id === compareAssetId2)
        .map((row) => row.source_id)
    );

    return [...asset1SourceIds].filter((id) => asset2SourceIds.has(id));
  }, [validCombinations, compareAssetId1, compareAssetId2]);

  const filteredCompareSources = useMemo(() => {
    return sources.filter((source) => validCompareSourceIds.includes(source._id));
  }, [sources, validCompareSourceIds]);

  async function loadHistoryData(assetId, sourceId) {
    if (!assetId || !sourceId) {
      setAssetHistory([]);
      setSourceHistory([]);
      setHistoryError("");
      return;
    }

    try {
      setLoadingHistory(true);
      setHistoryError("");

      const assetDoc = assets.find((asset) => asset._id === assetId);
      const sourceDoc = sources.find((source) => source._id === sourceId);

      if (!assetDoc?.asset_key || !sourceDoc?.source_key) {
        setAssetHistory([]);
        setSourceHistory([]);
        return;
      }

      const [assetHistoryRows, sourceHistoryRows] = await Promise.all([
        fetchAssetHistory(assetDoc.asset_key),
        fetchSourceHistory(sourceDoc.source_key),
      ]);

      setAssetHistory(assetHistoryRows || []);
      setSourceHistory(sourceHistoryRows || []);
      setHistoryError("");
    } catch (err) {
      setAssetHistory([]);
      setSourceHistory([]);
      setHistoryError(err.message || "Failed to load metadata history.");
    } finally {
      setLoadingHistory(false);
    }
  }

  async function loadDashboardData(assetId, sourceId, window, asOf = "") {
    if (!assetId || !sourceId) {
      return;
    }

    try {
      setLoadingDashboard(true);
      setError("");

      const dashboardData = await fetchDashboard(assetId, sourceId, window, asOf);

      const chartSeries = (dashboardData.moving_average?.series || []).map((point) => ({
        date: formatDateLabel(point.ts),
        value: point.value,
        movingAverage: point.moving_average,
      }));

      setDashboard(dashboardData);
      setSeriesData(chartSeries);
      setError("");
    } catch (err) {
      setDashboard(null);
      setSeriesData([]);
      setError(err.message || "No data available for this asset/source combination.");
    } finally {
      setLoadingDashboard(false);
    }
  }

  async function loadCompareData(assetId1, assetId2, sourceId, asOf = "") {
    if (!assetId1 || !assetId2 || !sourceId) {
      setCompareData(null);
      setCompareSeriesData([]);
      setCompareError("");
      return;
    }

    if (assetId1 === assetId2) {
      setCompareData(null);
      setCompareSeriesData([]);
      setCompareError("Please choose two different assets for comparison.");
      return;
    }

    try {
      setLoadingCompare(true);
      setCompareError("");

      const [data, series1, series2] = await Promise.all([
        fetchCompare(assetId1, assetId2, sourceId, asOf),
        fetchSeries(assetId1, sourceId, asOf),
        fetchSeries(assetId2, sourceId, asOf),
      ]);

      const asset1Symbol = assets.find((asset) => asset._id === assetId1)?.symbol || "Asset 1";
      const asset2Symbol = assets.find((asset) => asset._id === assetId2)?.symbol || "Asset 2";

      const map1 = new Map(
        series1
          .filter((point) => !point.is_deleted)
          .map((point) => [formatDateLabel(point.ts), getSeriesValue(point)])
      );

      const map2 = new Map(
        series2
          .filter((point) => !point.is_deleted)
          .map((point) => [formatDateLabel(point.ts), getSeriesValue(point)])
      );

      const allDates = [...new Set([...map1.keys(), ...map2.keys()])].sort();

      const mergedSeries = allDates.map((date) => ({
        date,
        [asset1Symbol]: map1.get(date) ?? null,
        [asset2Symbol]: map2.get(date) ?? null,
      }));

      setCompareData(data);
      setCompareSeriesData(mergedSeries);
      setCompareError("");
    } catch (err) {
      setCompareData(null);
      setCompareSeriesData([]);
      setCompareError(
        err.message || "No comparison data available for the selected assets/source."
      );
    } finally {
      setLoadingCompare(false);
    }
  }

  async function handleAssistantQuery(promptOverride = "") {
    const finalPrompt = (promptOverride || assistantPrompt).trim();

    if (!finalPrompt) return;

    try {
      setAssistantLoading(true);
      setAssistantError("");

      const payload = {
        prompt: finalPrompt,
        assetId: selectedAssetId || "",
        sourceId: selectedSourceId || "",
        compareAssetId1: compareAssetId1 || "",
        compareAssetId2: compareAssetId2 || "",
        compareSourceId: compareSourceId || "",
        asOf: dashboardAsOf || compareAsOf || "",
      };

      const result = await queryAssistant(payload);

      setAssistantError("");

      setAssistantMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-user`,
          role: "user",
          content: finalPrompt,
        },
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: result.answer || "-",
          mode: result.mode || "",
          data: result.data || null,
        },
      ]);

      setAssistantPrompt("");
    } catch (err) {
      setAssistantError(err.message || "Assistant query failed.");

      setAssistantMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-user`,
          role: "user",
          content: finalPrompt,
        },
        {
          id: `${Date.now()}-error`,
          role: "assistant",
          content: err.message || "Assistant query failed.",
          mode: "error",
          data: null,
        },
      ]);
    } finally {
      setAssistantLoading(false);
    }
  }

  async function loadSelectionIngestions(sourceId) {
    if (!sourceId) {
      setSelectionIngestions([]);
      setSelectionIngestionsError("");
      return;
    }

    try {
      setSelectedIngestionId("");
      setSelectedIngestionDetails(null);
      setLoadingSelectionIngestions(true);
      setSelectionIngestionsError("");

      const rows = await fetchRecentIngestions({
        sourceId,
        limit: 10,
      });

      setSelectionIngestions(rows || []);
      setSelectionIngestionsError("");
    } catch (err) {
      setSelectionIngestions([]);
      setSelectionIngestionsError(err.message || "Failed to load provenance details.");
    } finally {
      setLoadingSelectionIngestions(false);
    }
  }

  async function loadRecentIngestions() {
    try {
      setLoadingIngestionHistory(true);
      const rows = await fetchRecentIngestions();
      setRecentIngestions(rows || []);
    } catch (err) {
      setIngestionError(err.message || "Failed to load recent ingestions.");
    } finally {
      setLoadingIngestionHistory(false);
    }
  }

  async function loadIngestionDetails(ingestionId) {
    if (!ingestionId) {
      setSelectedIngestionDetails(null);
      setIngestionDetailsError("");
      return;
    }

    try {
      setLoadingIngestionDetails(true);
      setIngestionDetailsError("");

      const details = await fetchIngestionById(ingestionId);
      setSelectedIngestionDetails(details || null);
      setIngestionDetailsError("");
    } catch (err) {
      setSelectedIngestionDetails(null);
      setIngestionDetailsError(err.message || "Failed to load ingestion details.");
    } finally {
      setLoadingIngestionDetails(false);
    }
  }

  async function refreshLookupData() {
    const [lookupData, combinationsData] = await Promise.all([
      fetchLookupOptions(),
      fetchValidCombinations(),
    ]);

    const loadedAssets = lookupData.assets || [];
    const loadedSources = lookupData.sources || [];
    const loadedCombinations = combinationsData || [];

    setAssets(loadedAssets);
    setSources(loadedSources);
    setValidCombinations(loadedCombinations);

    return {
      loadedAssets,
      loadedSources,
      loadedCombinations,
    };
  }

  async function handleRunIngestion() {
    try {
      setRunningIngestion(true);
      setIngestionError("");
      setIngestionSuccess("");

      let result;

      if (ingestionProvider === "binance") {
        result = await runBinanceIngestion({
          symbol: binanceSymbol,
          name: binanceName,
          interval: binanceInterval,
          from: ingestionFrom,
          to: ingestionTo,
        });
      } else {
        result = await runFrankfurterIngestion({
          base: fxBase,
          quote: fxQuote,
          from: ingestionFrom,
          to: ingestionTo,
        });
      }

      setIngestionSuccess(result.message || "Ingestion completed successfully.");

      await refreshLookupData();
      await loadRecentIngestions();

      if (selectedSourceId) {
        await loadSelectionIngestions(selectedSourceId);
      }

      if (selectedAssetId && selectedSourceId) {
        await loadDashboardData(selectedAssetId, selectedSourceId, movingAverageWindow, dashboardAsOf);
      }

      if (compareAssetId1 && compareAssetId2 && compareSourceId) {
        await loadCompareData(compareAssetId1, compareAssetId2, compareSourceId, compareAsOf);
      }
    } catch (err) {
      setIngestionError(err.message || "Failed to run ingestion.");
    } finally {
      setRunningIngestion(false);
    }
  }

  function buildMcpPrompts({
    dashboard,
    compareAsset1Doc,
    compareAsset2Doc,
    selectedSourceName,
    dashboardAsOf,
    compareAsOf,
  }) {
    const assetSymbol = dashboard?.asset?.symbol || "BTCUSDT";
    const sourceName = selectedSourceName || dashboard?.source?.name || "Binance";
    const compare1 = compareAsset1Doc?.symbol || "BTCUSDT";
    const compare2 = compareAsset2Doc?.symbol || "ETHUSDT";

    const dashboardAsOfText = dashboardAsOf ? ` as of ${dashboardAsOf}` : "";
    const compareAsOfText = compareAsOf ? ` as of ${compareAsOf}` : "";

    return [
      `List all available assets.`,
      `Show the dashboard for ${assetSymbol} from ${sourceName}${dashboardAsOfText}.`,
      `Explain the trend for ${assetSymbol} from ${sourceName}${dashboardAsOfText}.`,
      `Summarize the risk for ${assetSymbol} from ${sourceName}${dashboardAsOfText}.`,
      `Compare ${compare1} and ${compare2} under ${sourceName}${compareAsOfText}.`,
      `Fetch the time series for ${assetSymbol} from ${sourceName}${dashboardAsOfText}.`,
    ];
  }

  useEffect(() => {
    async function loadInitialData() {
      try {
        setLoadingOptions(true);
        setError("");
        setCompareError("");
        setIngestionError("");

        const [lookupData, combinationsData, ingestionsData] = await Promise.all([
          fetchLookupOptions(),
          fetchValidCombinations(),
          fetchRecentIngestions(),
        ]);

        const loadedAssets = lookupData.assets || [];
        const loadedSources = lookupData.sources || [];
        const loadedCombinations = combinationsData || [];

        setAssets(loadedAssets);
        setSources(loadedSources);
        setValidCombinations(loadedCombinations);
        setRecentIngestions(ingestionsData || []);

        const firstCombination = loadedCombinations[0];

        const firstAssetId = firstCombination ? firstCombination.asset_id : "";
        const firstSourceId = firstCombination ? firstCombination.source_id : "";

        const secondAssetId =
          loadedCombinations.find(
            (row) =>
              row.source_id === firstSourceId &&
              row.asset_id !== firstAssetId
          )?.asset_id || "";

        setSelectedAssetId(firstAssetId);
        setSelectedSourceId(firstSourceId);

        setCompareAssetId1(firstAssetId);
        setCompareAssetId2(secondAssetId);
        setCompareSourceId(firstSourceId);

        if (firstAssetId && firstSourceId) {
          await loadDashboardData(firstAssetId, firstSourceId, movingAverageWindow, dashboardAsOf);
        }

        if (firstAssetId && secondAssetId && firstSourceId) {
          await loadCompareData(firstAssetId, secondAssetId, firstSourceId, compareAsOf);
        }
      } catch (err) {
        setError(err.message || "Failed to load initial data");
      } finally {
        setLoadingOptions(false);
      }
    }

    loadInitialData();
  }, []);

  useEffect(() => {
    if (!selectedAssetId || !filteredDashboardSources.length) return;

    const isCurrentSourceStillValid = filteredDashboardSources.some(
      (source) => source._id === selectedSourceId
    );

    if (!isCurrentSourceStillValid) {
      setSelectedSourceId(filteredDashboardSources[0]._id);
    }
  }, [selectedAssetId, filteredDashboardSources, selectedSourceId]);

  useEffect(() => {
    if (!compareAssetId1) return;

    const isCurrentAsset2Valid = filteredCompareAsset2Options.some(
      (asset) => asset._id === compareAssetId2
    );

    if (!isCurrentAsset2Valid) {
      setCompareAssetId2(filteredCompareAsset2Options[0]?._id || "");
      setCompareSourceId("");
      setCompareData(null);
      setCompareSeriesData([]);
      setCompareError("");
    }
  }, [compareAssetId1, compareAssetId2, filteredCompareAsset2Options]);

  useEffect(() => {
    if (!compareAssetId1 || !compareAssetId2) return;

    const isCurrentCompareSourceValid = filteredCompareSources.some(
      (source) => source._id === compareSourceId
    );

    if (!isCurrentCompareSourceValid) {
      setCompareSourceId(filteredCompareSources[0]?._id || "");
    }
  }, [compareAssetId1, compareAssetId2, filteredCompareSources, compareSourceId]);

  useEffect(() => {
    if (!loadingOptions && selectedAssetId && selectedSourceId) {
      loadDashboardData(selectedAssetId, selectedSourceId, movingAverageWindow, dashboardAsOf);
    }
  }, [selectedAssetId, selectedSourceId, movingAverageWindow, dashboardAsOf]);

  useEffect(() => {
    if (!loadingOptions && selectedAssetId && selectedSourceId) {
      loadHistoryData(selectedAssetId, selectedSourceId);
    }
  }, [selectedAssetId, selectedSourceId, loadingOptions, assets, sources]);

  useEffect(() => {
    if (!loadingOptions && compareAssetId1 && compareAssetId2 && compareSourceId) {
      loadCompareData(compareAssetId1, compareAssetId2, compareSourceId, compareAsOf);
    }
  }, [compareAssetId1, compareAssetId2, compareSourceId, compareAsOf]);

  useEffect(() => {
    if (!loadingOptions && selectedSourceId) {
      loadSelectionIngestions(selectedSourceId);
    }
  }, [selectedSourceId, loadingOptions]);

  const metricTitle = dashboard ? prettifyMetricLabel(dashboard.summary.metric_label) : "Close";
  const compareMetricTitle = compareData?.comparisons?.[0]
    ? prettifyMetricLabel(compareData.comparisons[0].metric_label)
    : "Value";

    const compareSeriesKeys = [
    compareAsset1Doc?.symbol || "Asset 1",
    compareAsset2Doc?.symbol || "Asset 2",
  ];

  const displayedCompareSeriesData = normalizeCompare
    ? normalizeSeriesData(compareSeriesData, compareSeriesKeys)
    : compareSeriesData;

  const selectedSourceDoc = sources.find((source) => source._id === selectedSourceId);

  const latestAssetHistoryRow = assetHistory.length ? assetHistory[assetHistory.length - 1] : null;
  const latestSourceHistoryRow = sourceHistory.length ? sourceHistory[sourceHistory.length - 1] : null;

  const selectedAssetStatus = latestAssetHistoryRow ? getMetadataStatus(latestAssetHistoryRow) : null;
  const selectedSourceStatus = latestSourceHistoryRow ? getMetadataStatus(latestSourceHistoryRow) : null;

  const mcpPrompts = buildMcpPrompts({
    dashboard,
    compareAsset1Doc,
    compareAsset2Doc,
    selectedSourceName: selectedSourceDoc?.name,
    dashboardAsOf,
    compareAsOf,
  });

  return (
    <div className="app">
      <div className="container">
        <h1>DW Financial Data Demo</h1>
        <p className="subtitle">
          Ingestion, warehouse analytics, temporal history, and comparison dashboard
        </p>

        <div className="panel">
          <h2>Run ingestion</h2>

          <div className="filters">
            <div className="field">
              <label htmlFor="provider">Provider</label>
              <select
                id="provider"
                value={ingestionProvider}
                onChange={(e) => setIngestionProvider(e.target.value)}
              >
                <option value="binance">Binance</option>
                <option value="frankfurter">Frankfurter</option>
              </select>
            </div>

            <div className="field">
              <label htmlFor="ingestionFrom">From</label>
              <input
                id="ingestionFrom"
                type="date"
                value={ingestionFrom}
                onChange={(e) => setIngestionFrom(e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="ingestionTo">To</label>
              <input
                id="ingestionTo"
                type="date"
                value={ingestionTo}
                onChange={(e) => setIngestionTo(e.target.value)}
              />
            </div>
          </div>

          {ingestionProvider === "binance" ? (
            <div className="filters filters-three">
              <div className="field">
                <label htmlFor="binanceSymbol">Symbol</label>
                <input
                  id="binanceSymbol"
                  type="text"
                  value={binanceSymbol}
                  onChange={(e) => setBinanceSymbol(e.target.value.toUpperCase())}
                  placeholder="BTCUSDT"
                />
              </div>

              <div className="field">
                <label htmlFor="binanceName">Name</label>
                <input
                  id="binanceName"
                  type="text"
                  value={binanceName}
                  onChange={(e) => setBinanceName(e.target.value)}
                  placeholder="Bitcoin / Tether"
                />
              </div>

              <div className="field">
                <label htmlFor="binanceInterval">Interval</label>
                <select
                  id="binanceInterval"
                  value={binanceInterval}
                  onChange={(e) => setBinanceInterval(e.target.value)}
                >
                  <option value="1d">1d</option>
                  <option value="1h">1h</option>
                  <option value="4h">4h</option>
                </select>
              </div>
            </div>
          ) : (
            <div className="filters">
              <div className="field">
                <label htmlFor="fxBase">Base Currency</label>
                <input
                  id="fxBase"
                  type="text"
                  value={fxBase}
                  onChange={(e) => setFxBase(e.target.value.toUpperCase())}
                  placeholder="EUR"
                />
              </div>

              <div className="field">
                <label htmlFor="fxQuote">Quote Currency</label>
                <input
                  id="fxQuote"
                  type="text"
                  value={fxQuote}
                  onChange={(e) => setFxQuote(e.target.value.toUpperCase())}
                  placeholder="USD"
                />
              </div>
            </div>
          )}

          <div className="actions-row">
            <button onClick={handleRunIngestion} disabled={runningIngestion}>
              {runningIngestion ? "Running ingestion..." : "Run ingestion"}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={loadRecentIngestions}
              disabled={loadingIngestionHistory}
            >
              {loadingIngestionHistory ? "Refreshing..." : "Refresh history"}
            </button>
          </div>

          {ingestionSuccess && <div className="success">{ingestionSuccess}</div>}
          {ingestionError && <div className="error">{ingestionError}</div>}
        </div>

        <div className="panel">
          <h2>Recent ingestion runs</h2>
          {loadingIngestionHistory ? (
            <p>Loading recent ingestions...</p>
          ) : (
            <IngestionHistoryTable rows={recentIngestions} />
          )}
        </div>

        <div className="panel">
          <h2>Select data</h2>
          {dashboardAsOf && (
            <p className="hint">Showing dashboard as of {dashboardAsOf}</p>
          )}

          {loadingOptions ? (
            <p>Loading assets and sources...</p>
          ) : (
            <>
              <div className="filters" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
                <div className="field">
                  <label htmlFor="asset">Asset</label>
                  <select
                    id="asset"
                    value={selectedAssetId}
                    onChange={(e) => setSelectedAssetId(e.target.value)}
                  >
                    {assetsWithAnyData.map((asset) => (
                      <option key={asset._id} value={asset._id}>
                        {asset.symbol} - {asset.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="source">Source</label>
                  <select
                    id="source"
                    value={selectedSourceId}
                    onChange={(e) => setSelectedSourceId(e.target.value)}
                  >
                    {filteredDashboardSources.map((source) => (
                      <option key={source._id} value={source._id}>
                        {source.name} - {source.type}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="maWindow">Moving Avg Window</label>
                  <select
                    id="maWindow"
                    value={movingAverageWindow}
                    onChange={(e) => setMovingAverageWindow(Number(e.target.value))}
                  >
                    <option value={3}>3</option>
                    <option value={5}>5</option>
                    <option value={10}>10</option>
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="dashboardAsOf">As Of</label>
                  <input
                    id="dashboardAsOf"
                    type="date"
                    value={dashboardAsOf}
                    onChange={(e) => setDashboardAsOf(e.target.value)}
                  />
                </div>
              </div>

              {loadingDashboard && <p>Updating dashboard...</p>}
            </>
          )}
        </div>

        {error && !dashboard && (
          <div className="panel">
            <div className="error">{error}</div>
          </div>
        )}

        {loadingDashboard && !dashboard && (
          <div className="panel">
            <p>Loading dashboard...</p>
          </div>
        )}

        {dashboard && (
          <>
            <div className="panel">
              <h2>Selection</h2>
              <div className="grid two-cols">
              <div className="card">
                <h3>Asset</h3>
                <p><strong>Symbol:</strong> {dashboard.asset.symbol}</p>
                <p><strong>Name:</strong> {dashboard.asset.name}</p>
                <p><strong>Class:</strong> {dashboard.asset.assetClass}</p>
                {selectedAssetStatus && (
                  <p>
                    <strong>Metadata Status:</strong>{" "}
                    <span className={selectedAssetStatus.className}>
                      {selectedAssetStatus.label}
                    </span>
                  </p>
                )}
                {latestAssetHistoryRow && (
                  <>
                    <p><strong>Version:</strong> {formatNumber(latestAssetHistoryRow.version)}</p>
                    <p><strong>Valid From:</strong> {formatDateTimeLabel(latestAssetHistoryRow.valid_from)}</p>
                    <p><strong>Valid To:</strong> {formatDateTimeLabel(latestAssetHistoryRow.valid_to)}</p>
                  </>
                )}
              </div>

              <div className="card">
                <h3>Source</h3>
                <p><strong>Name:</strong> {dashboard.source.name}</p>
                <p><strong>Type:</strong> {dashboard.source.type}</p>
                {selectedSourceStatus && (
                  <p>
                    <strong>Metadata Status:</strong>{" "}
                    <span className={selectedSourceStatus.className}>
                      {selectedSourceStatus.label}
                    </span>
                  </p>
                )}
                {latestSourceHistoryRow && (
                  <div className="selection-meta-block">
                    <p><strong>Version:</strong> {formatNumber(latestSourceHistoryRow.version)}</p>
                    <p><strong>Valid From:</strong> {formatDateTimeLabel(latestSourceHistoryRow.valid_from)}</p>
                    <p><strong>Valid To:</strong> {formatDateTimeLabel(latestSourceHistoryRow.valid_to)}</p>
                    <p><strong>Base URL:</strong> {latestSourceHistoryRow.baseUrl || "-"}</p>
                    <p><strong>Notes:</strong> {latestSourceHistoryRow.notes || "-"}</p>
                  </div>
                )}
              </div>
            </div>
            </div>

            <div className="panel">
              <h2>Metadata History</h2>
              <p className="hint">
                Temporal version history for the selected asset and source.
              </p>

              {loadingHistory && <p>Loading history...</p>}
              {historyError && <div className="error">{historyError}</div>}

              {!loadingHistory && !historyError && (
                <div className="grid two-cols">
                  <MetadataHistoryTable
                    title="Asset History"
                    rows={assetHistory}
                    type="asset"
                  />
                  <MetadataHistoryTable
                    title="Source History"
                    rows={sourceHistory}
                    type="source"
                  />
                </div>
              )}
            </div>

            <div className="panel">
              <h2>Provenance / Ingestion Trace</h2>
              <p className="hint">
                Recent ingestion events for the selected source, including parameters, payload preview, and response hash.
              </p>

              {loadingSelectionIngestions && <p>Loading provenance details...</p>}
              {selectionIngestionsError && <div className="error">{selectionIngestionsError}</div>}

              {!loadingSelectionIngestions && !selectionIngestionsError && (
                <>
                  <ProvenanceTable
                    rows={selectionIngestions}
                    selectedIngestionId={selectedIngestionId}
                    onSelect={(ingestionId) => {
                      setSelectedIngestionId(ingestionId);
                      loadIngestionDetails(ingestionId);
                    }}
                  />

                  <div style={{ marginTop: "18px" }}>
                    {loadingIngestionDetails && <p>Loading ingestion details...</p>}
                    {ingestionDetailsError && <div className="error">{ingestionDetailsError}</div>}
                    {!loadingIngestionDetails && !ingestionDetailsError && (
                      <IngestionDetailsCard details={selectedIngestionDetails} />
                    )}
                  </div>
                </>
              )}
            </div>

            <div className="panel">
              <h2>{metricTitle} Trend + Moving Average</h2>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={seriesData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip formatter={(value) => formatNumber(value)} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="value"
                      name={metricTitle}
                      stroke="#5c8fd6"
                      strokeWidth={3}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="movingAverage"
                      name={`MA(${movingAverageWindow})`}
                      stroke="#d16ba5"
                      strokeWidth={2}
                      dot={false}
                      strokeDasharray="6 4"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="grid">
              <div className="card">
                <h3>Summary</h3>
                <p><strong>Count:</strong> {formatNumber(dashboard.summary.count)}</p>
                <p><strong>Min {metricTitle}:</strong> {formatNumber(dashboard.summary.min_value)}</p>
                <p><strong>Max {metricTitle}:</strong> {formatNumber(dashboard.summary.max_value)}</p>
                <p><strong>Avg {metricTitle}:</strong> {formatNumber(dashboard.summary.avg_value)}</p>
                <p><strong>Latest {metricTitle}:</strong> {formatNumber(dashboard.summary.latest_value)}</p>
                <p><strong>From:</strong> {formatDateLabel(dashboard.summary.from)}</p>
                <p><strong>To:</strong> {formatDateLabel(dashboard.summary.to)}</p>
              </div>

              <div className="card">
                <h3>Trend</h3>
                <p>
                  <strong>Direction:</strong>{" "}
                  <span className={getTrendBadgeClass(dashboard.trend.direction)}>
                    {dashboard.trend.direction}
                  </span>
                </p>
                <p><strong>First {metricTitle}:</strong> {formatNumber(dashboard.trend.first_value)}</p>
                <p><strong>Latest {metricTitle}:</strong> {formatNumber(dashboard.trend.latest_value)}</p>
                <p><strong>Absolute Change:</strong> {formatNumber(dashboard.trend.absolute_change)}</p>
                <p><strong>Percent Change:</strong> {formatNumber(dashboard.trend.percent_change)}%</p>
              </div>

              <div className="card">
                <h3>Moving Average</h3>
                <p><strong>Window:</strong> {formatNumber(dashboard.moving_average.window)}</p>
                <p><strong>Latest MA:</strong> {formatNumber(dashboard.moving_average.latest_moving_average)}</p>
                <p><strong>Series Points:</strong> {formatNumber(dashboard.moving_average.count)}</p>
                <p><strong>Metric:</strong> {metricTitle}</p>
              </div>

              <div className="card">
                <h3>Forecast</h3>
                <p><strong>Previous {metricTitle}:</strong> {formatNumber(dashboard.forecast.previous_value)}</p>
                <p><strong>Latest {metricTitle}:</strong> {formatNumber(dashboard.forecast.latest_value)}</p>
                <p><strong>Trend:</strong> {formatNumber(dashboard.forecast.trend)}</p>
                <p><strong>Predicted Next {metricTitle}:</strong> {formatNumber(dashboard.forecast.predicted_next_value)}</p>
                <p><strong>Method:</strong> {dashboard.forecast.method}</p>
              </div>

              <div className="card">
                <h3>Risk</h3>
                <p>
                  <strong>Risk Level:</strong>{" "}
                  <span className={getRiskBadgeClass(dashboard.risk.risk_level)}>
                    {dashboard.risk.risk_level}
                  </span>
                </p>
                <p><strong>Volatility Range:</strong> {formatNumber(dashboard.risk.volatility_range)}</p>
                <p><strong>Volatility %:</strong> {formatNumber(dashboard.risk.volatility_percent)}%</p>
                <p><strong>Min {metricTitle}:</strong> {formatNumber(dashboard.risk.min_value)}</p>
                <p><strong>Max {metricTitle}:</strong> {formatNumber(dashboard.risk.max_value)}</p>
                <p><strong>Method:</strong> {dashboard.risk.method}</p>
              </div>
            </div>
          </>
        )}

        <div className="panel">
          <h2>Compare assets</h2>
          {compareAsOf && (
            <p className="hint">Showing comparison as of {compareAsOf}</p>
          )}

          {loadingOptions ? (
            <p>Loading compare options...</p>
          ) : (
            <>
              <div className="filters" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
                <div className="field">
                  <label htmlFor="compareAsset1">Asset 1</label>
                  <select
                    id="compareAsset1"
                    value={compareAssetId1}
                    onChange={(e) => setCompareAssetId1(e.target.value)}
                  >
                    {assetsWithAnyData.map((asset) => (
                      <option key={asset._id} value={asset._id}>
                        {asset.symbol} - {asset.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="compareAsset2">Asset 2</label>
                  <select
                    id="compareAsset2"
                    value={compareAssetId2}
                    onChange={(e) => setCompareAssetId2(e.target.value)}
                  >
                    {filteredCompareAsset2Options.map((asset) => (
                      <option key={asset._id} value={asset._id}>
                        {asset.symbol} - {asset.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label htmlFor="compareSource">Source</label>
                  <select
                    id="compareSource"
                    value={compareSourceId}
                    onChange={(e) => setCompareSourceId(e.target.value)}
                  >
                    {filteredCompareSources.map((source) => (
                      <option key={source._id} value={source._id}>
                        {source.name} - {source.type}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="compareAsOf">As Of</label>
                  <input
                    id="compareAsOf"
                    type="date"
                    value={compareAsOf}
                    onChange={(e) => setCompareAsOf(e.target.value)}
                  />
                </div>
              </div>

              <div className="actions-row">
                <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <input
                    type="checkbox"
                    checked={normalizeCompare}
                    onChange={(e) => setNormalizeCompare(e.target.checked)}
                  />
                  Normalize compare chart (base = 100)
                </label>
              </div>

              {loadingCompare && <p>Updating comparison...</p>}
            </>
          )}
        </div>

        {compareError && (
          <div className="panel">
            <div className="error">{compareError}</div>
          </div>
        )}

        {compareData && (
          <>
            <div className="panel">
              <h2>
                {normalizeCompare
                  ? `${compareMetricTitle} Normalized Comparison Chart`
                  : `${compareMetricTitle} Comparison Chart`}
              </h2>
              <p className="hint">
                {normalizeCompare
                  ? "Each series is rebased to 100 at its first visible point so you can compare relative movement."
                  : "Showing raw values for each selected asset under the shared source."}
              </p>
              <div className="chart-wrapper">
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={displayedCompareSeriesData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip
                      formatter={(value) =>
                        normalizeCompare ? `${formatNumber(value)} (base 100)` : formatNumber(value)
                      }
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey={compareAsset1Doc?.symbol || "Asset 1"}
                      stroke="#5c8fd6"
                      strokeWidth={3}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey={compareAsset2Doc?.symbol || "Asset 2"}
                      stroke="#d16ba5"
                      strokeWidth={3}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="panel">
              <h2>Comparison Results</h2>
              <div className="grid two-cols">
                {compareData.comparisons.map((item) => (
                  <CompareCard key={item.asset_id} item={item} />
                ))}
              </div>
            </div>
          </>
        )}

        <div className="panel">
          <h2>LLM / MCP Assistant</h2>
          <p className="hint">
            Ask grounded questions about the selected data. The assistant uses warehouse-backed platform functions.
          </p>

          <div className="field" style={{ marginTop: "16px" }}>
            <label htmlFor="assistantPrompt">Ask the assistant</label>
            <input
              id="assistantPrompt"
              type="text"
              value={assistantPrompt}
              onChange={(e) => setAssistantPrompt(e.target.value)}
              placeholder="Example: Explain the trend for the selected asset"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !assistantLoading && assistantPrompt.trim()) {
                  handleAssistantQuery();
                }
              }}
            />
          </div>

          <div className="actions-row">
            <button
              type="button"
              onClick={() => handleAssistantQuery()}
              disabled={assistantLoading || !assistantPrompt.trim()}
            >
              {assistantLoading ? "Thinking..." : "Ask Assistant"}
            </button>

            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                setAssistantPrompt("");
                setAssistantError("");
                setAssistantMessages([]);
              }}
            >
              Clear Conversation
            </button>
          </div>

          {assistantError && <div className="error">{assistantError}</div>}

          <div className="prompt-list" style={{ marginTop: "18px" }}>
            {mcpPrompts.map((prompt, index) => (
              <button
                key={index}
                type="button"
                className="prompt-card"
                onClick={() => {
                  setAssistantPrompt(prompt);
                  handleAssistantQuery(prompt);
                }}
              >
                <p>{prompt}</p>
              </button>
            ))}
          </div>

          <div style={{ marginTop: "18px" }}>
            {assistantLoading && <p>Generating grounded response...</p>}
            <AssistantChatHistory messages={assistantMessages} />
          </div>
        </div>

        {!!cryptoAssets.length && (
          <div className="panel">
            <h2>Available crypto assets</h2>
            <p className="hint">
              {cryptoAssets.map((asset) => asset.symbol).join(", ")}
            </p>
          </div>
        )}

        {!!fxAssets.length && (
          <div className="panel">
            <h2>Available FX pairs</h2>
            <p className="hint">
              {fxAssets.map((asset) => asset.symbol).join(", ")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;