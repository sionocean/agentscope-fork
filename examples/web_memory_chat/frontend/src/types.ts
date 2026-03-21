export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  toolCalls?: string[];
}

export interface MemoryItem {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  table: string;
}
