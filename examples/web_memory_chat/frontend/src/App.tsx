import { useState, useEffect, useCallback } from "react";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";
import MemoryPanel from "./components/MemoryPanel";
import KnowledgePanel from "./components/KnowledgePanel";
import { getSessions, deleteSession } from "./api";

export default function App() {
  const [userId, setUserId] = useState("default");
  const [sessionId, setSessionId] = useState<string>(() =>
    crypto.randomUUID(),
  );
  const [sessions, setSessions] = useState<string[]>([]);
  const [memoryRefresh, setMemoryRefresh] = useState(0);
  const [showMemory, setShowMemory] = useState(true);
  const [rightTab, setRightTab] = useState<"memory" | "knowledge">("memory");

  // Apply global body styles
  useEffect(() => {
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.background = "#0a0a0a";
    document.body.style.overflow = "hidden";
    document.body.style.height = "100vh";
    document.body.style.boxSizing = "border-box";
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const data = await getSessions(userId);
      setSessions(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Failed to fetch sessions:", e);
    }
  }, [userId]);

  // Fetch sessions on mount and when userId changes
  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  const handleUserChange = (newUserId: string) => {
    setUserId(newUserId);
    // Generate a new session for the new user
    setSessionId(crypto.randomUUID());
  };

  const handleNewSession = () => {
    const newId = crypto.randomUUID();
    setSessions((prev) => (prev.includes(newId) ? prev : [newId, ...prev]));
    setSessionId(newId);
  };

  const handleDeleteSession = async (sid: string) => {
    try {
      await deleteSession(userId, sid);
    } catch (e) {
      console.error("Failed to delete session:", e);
    }
    setSessions((prev) => prev.filter((s) => s !== sid));
    // If deleted session was active, generate a new one
    if (sid === sessionId) {
      setSessionId(crypto.randomUUID());
    }
  };

  const handleChatComplete = useCallback(() => {
    setMemoryRefresh((n) => n + 1);
    fetchSessions();
  }, [fetchSessions]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row",
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
        background: "#0a0a0a",
        fontFamily: "system-ui, sans-serif",
        color: "#e0e0e0",
        boxSizing: "border-box",
      }}
    >
      {/* Left: Sidebar (fixed 240px) */}
      <Sidebar
        userId={userId}
        onUserChange={handleUserChange}
        sessionId={sessionId}
        onSessionChange={setSessionId}
        sessions={sessions}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* Center: ChatView (flex: 1, offset left sidebar) */}
      <div
        style={{
          flex: 1,
          marginLeft: 240,
          display: "flex",
          flexDirection: "column",
          height: "100vh",
          overflow: "hidden",
          minWidth: 0,
        }}
      >
        <ChatView
          userId={userId}
          sessionId={sessionId}
          onChatComplete={handleChatComplete}
        />
      </div>

      {/* Right: MemoryPanel (fixed 300px) with toggle button */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          alignItems: "stretch",
          position: "relative",
          flexShrink: 0,
        }}
      >
        {/* Toggle button */}
        <button
          onClick={() => setShowMemory((v) => !v)}
          title={showMemory ? "Hide memory panel" : "Show memory panel"}
          style={{
            position: "absolute",
            top: "50%",
            left: showMemory ? -16 : -20,
            transform: "translateY(-50%)",
            zIndex: 10,
            background: "#1a1a1a",
            border: "1px solid #333",
            borderRadius: "4px 0 0 4px",
            color: "#888",
            cursor: "pointer",
            fontSize: 12,
            padding: "6px 4px",
            lineHeight: 1,
            writingMode: "vertical-rl",
          }}
        >
          {showMemory ? "▶" : "◀"}
        </button>

        {/* Right tab panel */}
        {showMemory && (
          <div style={{
            width: 380, borderLeft: "1px solid #333", display: "flex",
            flexDirection: "column", background: "#1a1a1a",
          }}>
            {/* Tab bar */}
            <div style={{
              display: "flex", borderBottom: "1px solid #333",
            }}>
              {(["memory", "knowledge"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setRightTab(tab)}
                  style={{
                    flex: 1, padding: "8px 0", border: "none",
                    background: rightTab === tab ? "#2a2a2a" : "transparent",
                    color: rightTab === tab ? "#fff" : "#888",
                    cursor: "pointer", fontSize: 12, fontWeight: 600,
                    borderBottom: rightTab === tab
                      ? "2px solid #60a5fa" : "2px solid transparent",
                  }}
                >
                  {tab === "memory" ? "Memory" : "Knowledge"}
                </button>
              ))}
            </div>
            {/* Panel content */}
            <div style={{ flex: 1, overflow: "hidden", padding: 8 }}>
              {rightTab === "memory" ? (
                <MemoryPanel
                  userId={userId}
                  refreshTrigger={memoryRefresh}
                />
              ) : (
                <KnowledgePanel
                  userId={userId}
                  refreshKey={memoryRefresh}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
