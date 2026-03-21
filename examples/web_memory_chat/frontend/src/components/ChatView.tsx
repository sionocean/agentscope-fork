import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  KeyboardEvent,
} from "react";
import { streamChat } from "../api";

// ---------------------------------------------------------------------------
// Local types for SSE content blocks
// ---------------------------------------------------------------------------

interface TextBlock {
  type: "text";
  text: string;
}

interface ThinkingBlock {
  type: "thinking";
  thinking: string;
}

interface ToolUseBlock {
  type: "tool_use";
  name: string;
  input: Record<string, unknown>;
}

interface ToolResultBlock {
  type: "tool_result";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  content: any;
}

type ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock;

interface SseMessage {
  id: string;
  name?: string;
  role: "user" | "assistant";
  content: string | ContentBlock[];
  timestamp?: string;
}

// Internal display message — content is always normalised to blocks.
interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  blocks: ContentBlock[];
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normaliseContent(content: unknown): ContentBlock[] {
  if (typeof content === "string") {
    return content ? [{ type: "text", text: content }] : [];
  }
  if (Array.isArray(content)) {
    return content as ContentBlock[];
  }
  if (content && typeof content === "object") {
    return [{ type: "text", text: JSON.stringify(content) }];
  }
  return [];
}

function extractText(blocks: ContentBlock[]): string {
  return blocks
    .filter((b): b is TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("");
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const ThinkingBlockView: React.FC<{ text: string }> = ({ text }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{
        marginTop: 4,
        borderLeft: "2px solid #7c3aed",
        paddingLeft: 8,
      }}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "#a78bfa",
          fontSize: 12,
          padding: "2px 0",
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <span style={{ fontSize: 10 }}>{expanded ? "▼" : "▶"}</span>
        <em>Thinking…</em>
      </button>
      {expanded && (
        <pre
          style={{
            margin: "4px 0 0 0",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 12,
            color: "#c4b5fd",
            fontStyle: "italic",
            background: "#1e1330",
            borderRadius: 4,
            padding: 8,
          }}
        >
          {text}
        </pre>
      )}
    </div>
  );
};

const ToolUseView: React.FC<{ block: ToolUseBlock }> = ({ block }) => (
  <div
    style={{
      marginTop: 4,
      background: "#0d2112",
      border: "1px solid #22c55e44",
      borderRadius: 4,
      padding: 8,
      fontSize: 12,
      fontFamily: "monospace",
      color: "#86efac",
    }}
  >
    <div style={{ fontWeight: 700, marginBottom: 4 }}>
      Tool: <span style={{ color: "#4ade80" }}>{block.name}</span>
    </div>
    <pre
      style={{
        margin: 0,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        color: "#6ee7b7",
      }}
    >
      {JSON.stringify(block.input, null, 2)}
    </pre>
  </div>
);

const ToolResultView: React.FC<{ block: ToolResultBlock }> = ({ block }) => {
  const raw = block.content;
  let text: string;
  if (Array.isArray(raw)) {
    text = raw
      .map((c) => (c.type === "text" ? (c as TextBlock).text : JSON.stringify(c)))
      .join("\n");
  } else if (typeof raw === "string") {
    text = raw;
  } else {
    text = raw ? JSON.stringify(raw) : "(empty result)";
  }

  return (
    <div
      style={{
        marginTop: 4,
        background: "#0d2112",
        border: "1px solid #22c55e44",
        borderRadius: 4,
        padding: 8,
        fontSize: 12,
        fontFamily: "monospace",
        color: "#6ee7b7",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 4, color: "#86efac" }}>
        Tool result
      </div>
      <pre
        style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {text}
      </pre>
    </div>
  );
};

const MessageBubble: React.FC<{ msg: DisplayMessage }> = ({ msg }) => {
  const isUser = msg.role === "user";
  const textContent = extractText(msg.blocks);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 12,
      }}
    >
      <div
        style={{
          maxWidth: "72%",
          borderRadius: 12,
          padding: "10px 14px",
          background: isUser ? "#1d4ed8" : "#1a1a1a",
          color: "#e0e0e0",
          wordBreak: "break-word",
        }}
      >
        {isUser ? (
          <span style={{ whiteSpace: "pre-wrap" }}>{textContent}</span>
        ) : (
          msg.blocks.map((block, i) => {
            if (block.type === "text") {
              return (
                <span
                  key={i}
                  style={{ whiteSpace: "pre-wrap", display: "block" }}
                >
                  {block.text}
                </span>
              );
            }
            if (block.type === "thinking") {
              return <ThinkingBlockView key={i} text={block.thinking} />;
            }
            if (block.type === "tool_use") {
              return <ToolUseView key={i} block={block} />;
            }
            if (block.type === "tool_result") {
              return <ToolResultView key={i} block={block as ToolResultBlock} />;
            }
            return null;
          })
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface ChatViewProps {
  userId: string;
  sessionId: string;
  onChatComplete?: () => void;
}

const ChatView: React.FC<ChatViewProps> = ({
  userId,
  sessionId,
  onChatComplete,
}) => {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Clear messages when session changes.
  useEffect(() => {
    setMessages([]);
    setInput("");
  }, [sessionId]);

  // Auto-scroll to bottom whenever messages update.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput("");
    setIsStreaming(true);

    // Append user message immediately.
    const userMsg: DisplayMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      blocks: [{ type: "text", text }],
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      for await (const raw of streamChat(userId, sessionId, text)) {
        const sseMsg = raw as SseMessage;
        const incomingBlocks = normaliseContent(sseMsg.content);

        setMessages((prev) => {
          const existingIdx = prev.findIndex((m) => m.id === sseMsg.id);
          if (existingIdx !== -1) {
            // Update in-place — content accumulates.
            const updated = [...prev];
            updated[existingIdx] = {
              ...updated[existingIdx],
              blocks: incomingBlocks,
            };
            return updated;
          }
          // New message from the assistant.
          const newMsg: DisplayMessage = {
            id: sseMsg.id,
            role: sseMsg.role,
            blocks: incomingBlocks,
            timestamp: sseMsg.timestamp ?? new Date().toISOString(),
          };
          return [...prev, newMsg];
        });
      }
    } catch (err) {
      console.error("streamChat error:", err);
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          blocks: [
            {
              type: "text",
              text: "An error occurred while streaming the response.",
            },
          ],
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsStreaming(false);
      onChatComplete?.();
    }
  }, [input, isStreaming, userId, sessionId, onChatComplete]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#0a0a0a",
        color: "#e0e0e0",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {/* Message list */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              margin: "auto",
              color: "#555",
              textAlign: "center",
              fontSize: 14,
            }}
          >
            Start the conversation by typing a message below.
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {isStreaming && (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-start",
              marginBottom: 12,
            }}
          >
            <div
              style={{
                background: "#1a1a1a",
                borderRadius: 12,
                padding: "10px 14px",
                color: "#888",
                fontSize: 14,
                fontStyle: "italic",
              }}
            >
              thinking…
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div
        style={{
          borderTop: "1px solid #2a2a2a",
          padding: "12px 16px",
          background: "#111",
          display: "flex",
          gap: 10,
          alignItems: "flex-end",
        }}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isStreaming}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={1}
          style={{
            flex: 1,
            background: "#1a1a1a",
            color: "#e0e0e0",
            border: "1px solid #333",
            borderRadius: 8,
            padding: "10px 12px",
            fontSize: 14,
            resize: "none",
            outline: "none",
            fontFamily: "inherit",
            lineHeight: 1.5,
            maxHeight: 160,
            overflowY: "auto",
          }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
          }}
        />
        <button
          onClick={sendMessage}
          disabled={isStreaming || !input.trim()}
          style={{
            background: isStreaming || !input.trim() ? "#1d3a6e" : "#1d4ed8",
            color: isStreaming || !input.trim() ? "#4a6096" : "#fff",
            border: "none",
            borderRadius: 8,
            padding: "10px 18px",
            fontSize: 14,
            cursor: isStreaming || !input.trim() ? "not-allowed" : "pointer",
            transition: "background 0.15s",
            whiteSpace: "nowrap",
          }}
        >
          {isStreaming ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
};

export default ChatView;
