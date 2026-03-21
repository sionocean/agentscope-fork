import React, { useState, KeyboardEvent } from "react";

interface SidebarProps {
  userId: string;
  onUserChange: (userId: string) => void;
  sessionId: string;
  onSessionChange: (sessionId: string) => void;
  sessions: string[];
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
}

const sessionItemStyle = (isActive: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "7px 8px",
  borderRadius: "4px",
  cursor: "pointer",
  background: isActive ? "#2563eb" : "transparent",
  color: isActive ? "#fff" : "#e0e0e0",
  marginBottom: "2px",
  transition: "background 0.15s",
  userSelect: "none",
});

const deleteButtonStyle = (isActive: boolean): React.CSSProperties => ({
  background: "none",
  border: "none",
  cursor: "pointer",
  color: isActive ? "rgba(255,255,255,0.7)" : "#888",
  fontSize: "14px",
  lineHeight: 1,
  padding: "0 2px",
  marginLeft: "6px",
  flexShrink: 0,
  borderRadius: "3px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
});

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: "240px",
    minWidth: "240px",
    height: "100vh",
    background: "#111",
    borderRight: "1px solid #1e1e1e",
    display: "flex",
    flexDirection: "column",
    padding: "16px 0",
    boxSizing: "border-box",
    color: "#e0e0e0",
    position: "fixed",
    left: 0,
    top: 0,
    bottom: 0,
    overflowY: "hidden",
  },
  section: {
    padding: "0 12px",
    marginBottom: "16px",
  },
  label: {
    display: "block",
    fontSize: "11px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.08em",
    color: "#888",
    marginBottom: "6px",
  },
  input: {
    width: "100%",
    background: "#1a1a1a",
    border: "1px solid #2a2a2a",
    borderRadius: "4px",
    color: "#e0e0e0",
    fontSize: "13px",
    padding: "6px 8px",
    boxSizing: "border-box" as const,
    outline: "none",
  },
  newSessionButton: {
    width: "100%",
    background: "#2563eb",
    border: "none",
    borderRadius: "4px",
    color: "#fff",
    fontSize: "13px",
    fontWeight: 600,
    padding: "8px 0",
    cursor: "pointer",
    marginBottom: "0",
  },
  sessionsHeader: {
    padding: "0 12px",
    marginBottom: "6px",
  },
  sessionsLabel: {
    display: "block",
    fontSize: "11px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.08em",
    color: "#888",
  },
  sessionList: {
    flex: 1,
    overflowY: "auto" as const,
    padding: "0 8px",
  },
  sessionIdText: {
    fontSize: "13px",
    fontFamily: "monospace",
    flexGrow: 1,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
  },
};

export default function Sidebar({
  userId,
  onUserChange,
  sessionId,
  onSessionChange,
  sessions,
  onNewSession,
  onDeleteSession,
}: SidebarProps) {
  const [localUserId, setLocalUserId] = useState(userId);

  const handleUserIdBlur = () => {
    const trimmed = localUserId.trim();
    if (trimmed && trimmed !== userId) {
      onUserChange(trimmed);
    }
  };

  const handleUserIdKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      const trimmed = localUserId.trim();
      if (trimmed && trimmed !== userId) {
        onUserChange(trimmed);
      }
      (e.target as HTMLInputElement).blur();
    }
  };

  const handleDeleteClick = (
    e: React.MouseEvent,
    sid: string,
  ) => {
    e.stopPropagation();
    const confirmed = window.confirm(
      `Delete session "${sid.slice(0, 8)}"? This cannot be undone.`,
    );
    if (confirmed) {
      onDeleteSession(sid);
    }
  };

  return (
    <aside style={styles.sidebar}>
      <div style={styles.section}>
        <label style={styles.label} htmlFor="user-id-input">
          User ID
        </label>
        <input
          id="user-id-input"
          style={styles.input}
          type="text"
          value={localUserId}
          onChange={(e) => setLocalUserId(e.target.value)}
          onBlur={handleUserIdBlur}
          onKeyDown={handleUserIdKeyDown}
          placeholder="Enter user ID"
          spellCheck={false}
          autoComplete="off"
        />
      </div>

      <div style={styles.section}>
        <button style={styles.newSessionButton} onClick={onNewSession}>
          + New Session
        </button>
      </div>

      <div style={styles.sessionsHeader}>
        <span style={styles.sessionsLabel}>Sessions</span>
      </div>

      <div style={styles.sessionList}>
        {sessions.length === 0 && (
          <div
            style={{
              color: "#888",
              fontSize: "12px",
              padding: "8px 8px",
              textAlign: "center",
            }}
          >
            No sessions yet
          </div>
        )}
        {sessions.map((sid) => {
          const isActive = sid === sessionId;
          return (
            <div
              key={sid}
              style={sessionItemStyle(isActive)}
              onClick={() => onSessionChange(sid)}
              title={sid}
            >
              <span style={styles.sessionIdText}>
                {sid.slice(0, 8)}
              </span>
              <button
                style={deleteButtonStyle(isActive)}
                onClick={(e) => handleDeleteClick(e, sid)}
                title="Delete session"
                aria-label={`Delete session ${sid.slice(0, 8)}`}
              >
                &#x2715;
              </button>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
