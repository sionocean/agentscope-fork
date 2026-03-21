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

export interface DocumentItem {
  doc_id: string;
  filename: string;
  file_type: string;   // "text" | "pdf" | "image"
  chunks: number;
  uploaded_at: string;
  file_size: number;
}
