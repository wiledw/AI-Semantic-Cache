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
  "How to update my password?";

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
  const [textareaFocused, setTextareaFocused] = useState(false);
  const [buttonHovered, setButtonHovered] = useState(false);

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
          <h1 style={styles.title}>Semantic Cache Demo</h1>
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
              onFocus={() => setTextareaFocused(true)}
              onBlur={() => setTextareaFocused(false)}
              rows={4}
              style={{
                ...styles.textarea,
                ...(textareaFocused ? styles.textareaFocus : {}),
              }}
            />
          </label>

          <label style={styles.checkboxRow}>
            <input
              type="checkbox"
              checked={forceRefresh}
              onChange={(event) => setForceRefresh(event.target.checked)}
              style={{ cursor: "pointer" }}
            />
            Force refresh (skip cache)
          </label>

          <button
            type="submit"
            disabled={loading}
            onMouseEnter={() => setButtonHovered(true)}
            onMouseLeave={() => setButtonHovered(false)}
            style={{
              ...styles.button,
              ...(buttonHovered && !loading ? styles.buttonHover : {}),
              ...(loading ? styles.buttonDisabled : {}),
            }}
          >
            {loading ? "⏳ Loading..." : "🚀 Send Query"}
          </button>
        </form>

        <section style={styles.result}>
          <div style={styles.statsCard}>
            <h2 style={styles.sectionTitle}>
              📊 Live Stats
            </h2>
            {stats ? (
              <div style={styles.statsGrid}>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>Requests</div>
                  <div style={styles.statValue}>{stats.requests}</div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>Cache Hits</div>
                  <div style={{ ...styles.statValue, color: "#10b981" }}>
                    {stats.cache_hits}
                  </div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>Cache Misses</div>
                  <div style={{ ...styles.statValue, color: "#f59e0b" }}>
                    {stats.cache_misses}
                  </div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>Hit Rate</div>
                  <div
                    style={{
                      ...styles.statValue,
                      color:
                        stats.cache_hit_rate > 0.7
                          ? "#10b981"
                          : stats.cache_hit_rate > 0.4
                          ? "#f59e0b"
                          : "#ef4444",
                    }}
                  >
                    {(stats.cache_hit_rate * 100).toFixed(1)}%
                  </div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>LLM Calls</div>
                  <div style={{ ...styles.statValue, color: "#3b82f6" }}>
                    {stats.llm_calls}
                  </div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>LLM Fallbacks</div>
                  <div style={{ ...styles.statValue, color: "#8b5cf6" }}>
                    {stats.llm_fallbacks}
                  </div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>Est. LLM Cost</div>
                  <div style={{ ...styles.statValue, color: "#ef4444" }}>
                    ${stats.estimated_llm_cost.toFixed(4)}
                  </div>
                </div>
                <div style={styles.statItem}>
                  <div style={styles.statLabel}>Est. Savings</div>
                  <div style={{ ...styles.statValue, color: "#10b981" }}>
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
              <span>⚠️</span>
              <span>Error: {error}</span>
            </div>
          )}
          {result && (
            <div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
                <p style={styles.metaLine}>
                  <span>Source:</span>
                  <span
                    style={{
                      ...styles.metaBadge,
                      ...(result.metadata.source === "cache"
                        ? styles.sourceCache
                        : styles.sourceLLM),
                    }}
                  >
                    {result.metadata.source === "cache" ? "💾 Cache" : "🤖 LLM"}
                  </span>
                </p>
                {result.metadata.similarity !== undefined &&
                  result.metadata.similarity !== null && (
                    <p style={styles.metaLine}>
                      <span>Similarity:</span>
                      <strong style={{ color: "#667eea" }}>
                        {(result.metadata.similarity * 100).toFixed(2)}%
                      </strong>
                    </p>
                  )}
              </div>
              <div style={styles.responseBox}>{result.response}</div>
            </div>
          )}
          {!error && !result && (
            <p style={styles.placeholder}>
              💡 Submit a query to see results here.
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
    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    padding: "40px 16px",
    display: "flex",
    justifyContent: "center",
    alignItems: "flex-start",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif",
  },
  card: {
    width: "100%",
    maxWidth: 900,
    background: "#ffffff",
    borderRadius: 20,
    padding: "40px",
    boxShadow: "0 20px 60px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.1)",
    backdropFilter: "blur(10px)",
    transition: "transform 0.3s ease, box-shadow 0.3s ease",
  },
  header: {
    marginBottom: 32,
    textAlign: "center" as const,
  },
  title: {
    margin: 0,
    fontSize: "clamp(28px, 5vw, 36px)",
    fontWeight: 700,
    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
    backgroundClip: "text",
    letterSpacing: "-0.02em",
  },
  subtitle: {
    margin: "12px 0 0",
    color: "#64748b",
    fontSize: 16,
    lineHeight: 1.6,
  },
  form: {
    display: "grid",
    gap: 20,
  },
  label: {
    display: "flex",
    flexDirection: "column",
    fontWeight: 600,
    gap: 10,
    color: "#1e293b",
    fontSize: 14,
  },
  textarea: {
    width: "100%",
    padding: "16px",
    fontSize: 15,
    fontFamily: "inherit",
    borderRadius: 12,
    border: "2px solid #e2e8f0",
    resize: "vertical",
    transition: "all 0.2s ease",
    backgroundColor: "#f8fafc",
    color: "#1e293b",
    lineHeight: 1.5,
  },
  textareaFocus: {
    outline: "none",
    borderColor: "#667eea",
    backgroundColor: "#ffffff",
    boxShadow: "0 0 0 3px rgba(102, 126, 234, 0.1)",
  },
  checkboxRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    fontSize: 14,
    color: "#475569",
    cursor: "pointer",
    padding: "8px 0",
  },
  button: {
    padding: "16px 24px",
    borderRadius: 12,
    border: "none",
    background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
    color: "#ffffff",
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
    transition: "all 0.3s ease",
    boxShadow: "0 4px 15px rgba(102, 126, 234, 0.4)",
    textTransform: "none",
    letterSpacing: "0.01em",
  },
  buttonHover: {
    transform: "translateY(-2px)",
    boxShadow: "0 6px 20px rgba(102, 126, 234, 0.5)",
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: "not-allowed",
    transform: "none",
  },
  result: {
    marginTop: 32,
    borderTop: "2px solid #f1f5f9",
    paddingTop: 24,
  },
  statsCard: {
    background: "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)",
    borderRadius: 16,
    padding: "24px",
    border: "1px solid #e2e8f0",
    marginBottom: 24,
    boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
  },
  sectionTitle: {
    margin: "0 0 20px",
    fontSize: 20,
    fontWeight: 700,
    color: "#1e293b",
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    gap: 16,
  },
  statItem: {
    background: "#ffffff",
    borderRadius: 12,
    padding: "16px",
    border: "1px solid #e2e8f0",
    transition: "all 0.2s ease",
    boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
  },
  statItemHover: {
    transform: "translateY(-2px)",
    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    borderColor: "#cbd5e1",
  },
  statLabel: {
    fontSize: 11,
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    fontWeight: 600,
    marginBottom: 8,
  },
  statValue: {
    fontSize: 24,
    fontWeight: 700,
    color: "#1e293b",
    lineHeight: 1.2,
  },
  metaLine: {
    margin: "8px 0",
    color: "#475569",
    fontSize: 14,
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  metaBadge: {
    display: "inline-block",
    padding: "4px 12px",
    borderRadius: 20,
    fontSize: 12,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  sourceCache: {
    background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
    color: "#ffffff",
  },
  sourceLLM: {
    background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "#ffffff",
  },
  responseBox: {
    marginTop: 16,
    padding: "24px",
    background: "linear-gradient(135deg, #f8fafc 0%, #ffffff 100%)",
    borderRadius: 12,
    border: "2px solid #e2e8f0",
    whiteSpace: "pre-wrap",
    color: "#1e293b",
    lineHeight: 1.7,
    fontSize: 15,
    boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
  },
  placeholder: {
    color: "#94a3b8",
    fontStyle: "italic",
    textAlign: "center" as const,
    padding: "40px 20px",
  },
  error: {
    color: "#dc2626",
    background: "linear-gradient(135deg, #fee2e2 0%, #fecaca 100%)",
    padding: "16px 20px",
    borderRadius: 12,
    border: "2px solid #fca5a5",
    fontWeight: 500,
    display: "flex",
    alignItems: "center",
    gap: 8,
    boxShadow: "0 2px 8px rgba(220, 38, 38, 0.15)",
  },
};
