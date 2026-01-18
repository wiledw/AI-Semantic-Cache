import React, { useState } from "react";

type ApiResponse = {
  response: string;
  metadata: {
    source: string;
    similarity?: number | null;
  };
};

type StatsResponse = {
  requests: number;
  cache_hits: number;
  cache_misses: number;
  llm_calls: number;
  llm_fallbacks: number;
  cache_hit_rate: number;
  estimated_llm_cost: number;
  estimated_cache_savings: number;
};

const DEFAULT_QUERY =
  "What's the weather like in New York today?";

const API_URL =
  (import.meta as ImportMeta & { env: { VITE_API_URL?: string } }).env
    .VITE_API_URL ?? "http://localhost:3000/api/query";
const STATS_URL =
  (import.meta as ImportMeta & { env: { VITE_STATS_URL?: string } }).env
    .VITE_STATS_URL ?? "http://localhost:3000/api/stats";

export default function App() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);

  const fetchStats = async () => {
    try {
      const response = await fetch(STATS_URL);
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as StatsResponse;
      setStats(data);
    } catch {
      // Ignore stats errors to avoid blocking UI.
    }
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, forceRefresh }),
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || "Request failed");
      }

      const data = (await response.json()) as ApiResponse;
      setResult(data);
      fetchStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    fetchStats();
    const interval = window.setInterval(fetchStats, 5000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <div style={styles.page}>
      <main style={styles.card}>
        <header style={styles.header}>
          <h1 style={styles.title}>Boardy Semantic Cache Demo</h1>
          <p style={styles.subtitle}>
            Submit a query and see whether the response came from cache or the LLM.
          </p>
        </header>

        <form onSubmit={onSubmit} style={styles.form}>
          <label style={styles.label}>
            Query
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={4}
              style={styles.textarea}
            />
          </label>

          <label style={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={forceRefresh}
              onChange={(event) => setForceRefresh(event.target.checked)}
            />
            Force refresh (skip cache)
          </label>

          <button type="submit" disabled={loading} style={styles.button}>
            {loading ? "Loading..." : "Send query"}
          </button>
        </form>

        <section style={styles.result}>
          <div style={styles.statsCard}>
            <h2 style={styles.sectionTitle}>Live Stats</h2>
            {stats ? (
              <div style={styles.statsGrid}>
                <div>
                  <div style={styles.statLabel}>Requests</div>
                  <div style={styles.statValue}>{stats.requests}</div>
                </div>
                <div>
                  <div style={styles.statLabel}>Cache hits</div>
                  <div style={styles.statValue}>{stats.cache_hits}</div>
                </div>
                <div>
                  <div style={styles.statLabel}>Cache misses</div>
                  <div style={styles.statValue}>{stats.cache_misses}</div>
                </div>
                <div>
                  <div style={styles.statLabel}>Hit rate</div>
                  <div style={styles.statValue}>
                    {(stats.cache_hit_rate * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div style={styles.statLabel}>LLM calls</div>
                  <div style={styles.statValue}>{stats.llm_calls}</div>
                </div>
                <div>
                  <div style={styles.statLabel}>LLM fallbacks</div>
                  <div style={styles.statValue}>{stats.llm_fallbacks}</div>
                </div>
                <div>
                  <div style={styles.statLabel}>Est. LLM cost</div>
                  <div style={styles.statValue}>
                    ${stats.estimated_llm_cost.toFixed(4)}
                  </div>
                </div>
                <div>
                  <div style={styles.statLabel}>Est. savings</div>
                  <div style={styles.statValue}>
                    ${stats.estimated_cache_savings.toFixed(4)}
                  </div>
                </div>
              </div>
            ) : (
              <p style={styles.placeholder}>Loading stats...</p>
            )}
          </div>
          {error && (
            <div style={styles.error}>
              Error: {error}
            </div>
          )}
          {result && (
            <div>
              <p style={styles.metaLine}>
                Source: <strong>{result.metadata.source}</strong>
              </p>
              {result.metadata.similarity !== undefined && (
                <p style={styles.metaLine}>
                  Similarity:{" "}
                  <strong>{result.metadata.similarity?.toFixed(4)}</strong>
                </p>
              )}
              <div style={styles.responseBox}>
                {result.response}
              </div>
            </div>
          )}
          {!error && !result && (
            <p style={styles.placeholder}>
              Submit a query to see results here.
            </p>
          )}
        </section>
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "#f5f6f8",
    padding: "40px 16px",
    display: "flex",
    justifyContent: "center",
  },
  card: {
    width: "100%",
    maxWidth: 720,
    background: "#fff",
    borderRadius: 12,
    padding: 28,
    boxShadow: "0 10px 30px rgba(0,0,0,0.08)",
  },
  header: {
    marginBottom: 24,
  },
  title: {
    margin: 0,
    fontSize: 28,
  },
  subtitle: {
    margin: "8px 0 0",
    color: "#555",
  },
  form: {
    display: "grid",
    gap: 16,
  },
  label: {
    display: "flex",
    flexDirection: "column",
    fontWeight: 600,
    gap: 8,
  },
  textarea: {
    width: "100%",
    padding: 12,
    fontSize: 14,
    fontFamily: "inherit",
    borderRadius: 8,
    border: "1px solid #ddd",
    resize: "vertical",
  },
  checkboxRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 14,
  },
  button: {
    padding: "12px 16px",
    borderRadius: 8,
    border: "none",
    background: "#111827",
    color: "#fff",
    fontSize: 14,
    cursor: "pointer",
  },
  result: {
    marginTop: 24,
    borderTop: "1px solid #eee",
    paddingTop: 16,
  },
  statsCard: {
    background: "#f9fafb",
    borderRadius: 10,
    padding: 16,
    border: "1px solid #e5e7eb",
    marginBottom: 16,
  },
  sectionTitle: {
    margin: "0 0 12px",
    fontSize: 16,
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    gap: 12,
  },
  statLabel: {
    fontSize: 12,
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  },
  statValue: {
    fontSize: 16,
    fontWeight: 600,
    marginTop: 4,
  },
  metaLine: {
    margin: "4px 0",
    color: "#333",
  },
  responseBox: {
    marginTop: 12,
    padding: 16,
    background: "#f9fafb",
    borderRadius: 8,
    border: "1px solid #eee",
    whiteSpace: "pre-wrap",
  },
  placeholder: {
    color: "#777",
  },
  error: {
    color: "#b91c1c",
    background: "#fee2e2",
    padding: 12,
    borderRadius: 8,
  },
};
