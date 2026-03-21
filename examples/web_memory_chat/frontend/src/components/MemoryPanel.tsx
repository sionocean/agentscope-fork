import { useState, useEffect } from "react";
import { getMemories, clearMemories } from "../api";
import type { MemoryItem } from "../types";

interface MemoryPanelProps {
  userId: string;
  refreshTrigger: number;
}

function cleanTableName(table: string): string {
  return table.replace(/^workspace_/, "");
}

function MetadataPreview({ metadata }: { metadata: Record<string, unknown> }) {
  if (!metadata || Object.keys(metadata).length === 0) return null;
  const preview = JSON.stringify(metadata, null, 2);
  return (
    <pre
      style={{
        margin: "4px 0 0 0",
        padding: "4px 6px",
        background: "#111",
        borderRadius: 4,
        fontSize: 10,
        color: "#888",
        overflowX: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-all",
        maxHeight: 80,
        overflowY: "auto",
      }}
    >
      {preview}
    </pre>
  );
}

function MemoryItemCard({ item }: { item: MemoryItem }) {
  const [expanded, setExpanded] = useState(false);
  const TRUNCATE_AT = 200;
  const isTruncatable = item.content.length > TRUNCATE_AT;
  const displayContent =
    !expanded && isTruncatable
      ? item.content.slice(0, TRUNCATE_AT) + "…"
      : item.content;

  return (
    <div
      style={{
        background: "#1a1a1a",
        borderRadius: 6,
        padding: "8px 10px",
        marginBottom: 6,
        fontSize: 12,
        color: "#d4d4d4",
      }}
    >
      <p style={{ margin: 0, lineHeight: 1.5, wordBreak: "break-word" }}>
        {displayContent}
      </p>
      {isTruncatable && (
        <button
          onClick={() => setExpanded((e) => !e)}
          style={{
            marginTop: 4,
            background: "none",
            border: "none",
            color: "#888",
            cursor: "pointer",
            fontSize: 11,
            padding: 0,
          }}
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
      <MetadataPreview metadata={item.metadata} />
    </div>
  );
}

function MemoryGroup({
  tableName,
  items,
}: {
  tableName: string;
  items: MemoryItem[];
}) {
  const [open, setOpen] = useState(true);
  const label = cleanTableName(tableName);

  return (
    <div style={{ marginBottom: 12 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          background: "none",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 0",
          color: "#d4d4d4",
          fontWeight: "bold",
          fontSize: 13,
          textAlign: "left",
        }}
      >
        <span style={{ textTransform: "capitalize" }}>
          {label}{" "}
          <span style={{ color: "#888", fontWeight: "normal" }}>
            ({items.length})
          </span>
        </span>
        <span style={{ fontSize: 10, color: "#888", userSelect: "none" }}>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div>
          {items.map((item) => (
            <MemoryItemCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MemoryPanel({ userId, refreshTrigger }: MemoryPanelProps) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMemories = async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getMemories(userId);
      setMemories(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load memories");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMemories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, refreshTrigger]);

  // Group memories by table
  const groups: Record<string, MemoryItem[]> = {};
  for (const item of memories) {
    const key = item.table ?? "default";
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  const tableNames = Object.keys(groups);

  return (
    <aside
      style={{
        width: "100%",
        height: "100%",
        background: "#111",
        borderLeft: "1px solid #1e1e1e",
        display: "flex",
        flexDirection: "column",
        overflowY: "auto",
        boxSizing: "border-box",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "14px 14px 10px",
          borderBottom: "1px solid #1e1e1e",
          position: "sticky",
          top: 0,
          background: "#111",
          zIndex: 1,
        }}
      >
        <span style={{ fontWeight: "bold", fontSize: 13, color: "#d4d4d4" }}>
          Memories
        </span>
        <button
          onClick={fetchMemories}
          disabled={loading}
          title="Refresh memories"
          style={{
            background: "none",
            border: "1px solid #333",
            borderRadius: 4,
            color: "#888",
            cursor: loading ? "default" : "pointer",
            fontSize: 11,
            padding: "3px 8px",
            opacity: loading ? 0.5 : 1,
          }}
        >
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
        <button
          onClick={async () => {
            if (!window.confirm(`Clear all memories for user "${userId}"?`)) return;
            const n = await clearMemories(userId);
            alert(`Cleared ${n} memories.`);
            fetchMemories();
          }}
          disabled={loading || memories.length === 0}
          title="Clear all memories"
          style={{
            background: "none",
            border: "1px solid #553333",
            borderRadius: 4,
            color: "#e57373",
            cursor: memories.length === 0 ? "not-allowed" : "pointer",
            fontSize: 12,
            padding: "3px 8px",
            opacity: memories.length === 0 ? 0.4 : 1,
          }}
        >
          Clear All
        </button>
      </div>

      {/* Body */}
      <div style={{ padding: "12px 14px", flex: 1 }}>
        {loading && memories.length === 0 ? (
          <p style={{ color: "#888", fontSize: 12, margin: 0 }}>
            Loading memories…
          </p>
        ) : error ? (
          <p style={{ color: "#e05c5c", fontSize: 12, margin: 0 }}>
            Error: {error}
          </p>
        ) : tableNames.length === 0 ? (
          <p style={{ color: "#888", fontSize: 12, margin: 0 }}>
            No memories stored yet
          </p>
        ) : (
          tableNames.map((table) => (
            <MemoryGroup key={table} tableName={table} items={groups[table]} />
          ))
        )}
      </div>
    </aside>
  );
}
