import { useState } from "react";
import { apiGet } from "@/lib/api";

export default function RAGSearchPanel() {
  const [namespace, setNamespace] = useState("company_rubrics");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);


  const handleSearch = async (e) => {
    e.preventDefault();

    if (!query.trim()) {
      setError("Enter a search query.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setResults([]);


      const data = await apiGet(
        `/rag/search?namespace=${namespace}&query=${encodeURIComponent(query)}`
      );

      setResults(data.results || []);

      if (data.results && data.results.length === 0) {
        setError(
          "No results found. Try a different query or check that you've uploaded documents."
        );
      }
    } catch (err) {
      setError(
        err.message ||
        "Search failed. The search endpoint may not be implemented yet."
      );
    } finally {
      setLoading(false);
    }
  };


  return (
    <div className="card">
      {}
      <h3 className="card-title">RAG Knowledge Base Search</h3>
      <p className="text-small text-muted" style={{ marginBottom: "1.5rem" }}>
        Query what the AI agents can see. Useful for debugging and verifying indexed content.
      </p>

      {}
      <form onSubmit={handleSearch} style={{ marginBottom: "1.5rem" }}>
        {}
        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", fontSize: "0.875rem", fontWeight: "500", marginBottom: "0.5rem" }}>
            Knowledge Base
          </label>
          <select
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
            style={{
              width: "100%",
              padding: "0.5rem",
              border: "1px solid #e5e7eb",
              borderRadius: "4px",
              fontSize: "0.875rem",
            }}
          >
            <option value="company_rubrics">Company Rubrics (hiring standards)</option>
            <option value="market_data">Market Data (compensation)</option>
          </select>
          <p className="text-small text-muted" style={{ marginTop: "0.25rem" }}>
            {namespace === "company_rubrics"
              ? "Searches hiring standards, interview processes, seniority definitions."
              : "Searches salary benchmarks, compensation data, market rates."}
          </p>
        </div>

        {}
        <div style={{ marginBottom: "1rem" }}>
          <label style={{ display: "block", fontSize: "0.875rem", fontWeight: "500", marginBottom: "0.5rem" }}>
            Search Query
          </label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              namespace === "company_rubrics"
                ? "e.g., senior engineer responsibilities"
                : "e.g., senior engineer salary san francisco"
            }
            style={{
              width: "100%",
              padding: "0.5rem",
              border: "1px solid #e5e7eb",
              borderRadius: "4px",
              fontSize: "0.875rem",
            }}
          />
        </div>

        {}
        <button
          type="submit"
          className="button button-primary"
          disabled={loading}
          style={{ width: "100%" }}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {}
      {error && (
        <div style={{ padding: "0.75rem", backgroundColor: "#fee2e2", borderRadius: "4px", marginBottom: "1.5rem" }}>
          <p style={{ fontSize: "0.875rem", color: "#991b1b" }}>{error}</p>
        </div>
      )}

      {}
      {results.length > 0 && (
        <div>
          <h4 style={{ fontSize: "0.875rem", fontWeight: "600", marginBottom: "1rem" }}>
            Results ({results.length})
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {results.map((result, idx) => (
              <div
                key={idx}
                style={{
                  padding: "1rem",
                  backgroundColor: "#f9fafb",
                  border: "1px solid #e5e7eb",
                  borderRadius: "4px",
                }}
              >
                {}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: "0.5rem",
                  }}
                >
                  <p style={{ fontSize: "0.875rem", fontWeight: "500" }}>
                    Chunk {result.chunk_index || "?"}
                  </p>
                  {result.score && (
                    <span
                      style={{
                        fontSize: "0.75rem",
                        backgroundColor: "#dbeafe",
                        color: "#1e40af",
                        padding: "0.25rem 0.5rem",
                        borderRadius: "4px",
                      }}
                    >
                      Relevance: {(result.score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>

                {}
                {result.metadata?.source && (
                  <p className="text-small text-muted" style={{ marginBottom: "0.5rem" }}>
                    Source: <code style={{ fontSize: "0.75rem" }}>{result.metadata.source}</code>
                  </p>
                )}

                {}
                <p
                  className="text-small"
                  style={{
                    color: "#374151",
                    lineHeight: "1.5",
                    maxHeight: "150px",
                    overflow: "auto",
                  }}
                >
                  {result.text || result.content || "(No text available)"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {}
      {!loading && results.length === 0 && !error && query && (
        <div style={{ padding: "1rem", backgroundColor: "#f3f4f6", borderRadius: "4px", textAlign: "center" }}>
          <p className="text-small text-muted">No results. Try a different query.</p>
        </div>
      )}

      {}
      {!loading && results.length === 0 && !error && !query && (
        <div style={{ padding: "1rem", backgroundColor: "#f3f4f6", borderRadius: "4px", textAlign: "center" }}>
          <p className="text-small text-muted">Enter a search query to explore the knowledge base.</p>
        </div>
      )}

    </div>
  );
}
