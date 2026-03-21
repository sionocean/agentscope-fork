import type { MemoryItem, DocumentItem } from "./types";

const BASE = "/api";

export async function* streamChat(
  userId: string,
  sessionId: string,
  userInput: string,
) {
  const resp = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      session_id: sessionId,
      user_input: userInput,
    }),
  });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (line.startsWith("data: ")) {
        yield JSON.parse(line.slice(6));
      }
    }
  }
}

export async function getSessions(userId: string): Promise<string[]> {
  const r = await fetch(`${BASE}/sessions/${userId}`);
  return (await r.json()).sessions;
}

export async function getHistory(
  userId: string,
  sessionId: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): Promise<any[]> {
  const r = await fetch(`${BASE}/history/${userId}/${sessionId}`);
  return (await r.json()).messages ?? [];
}

export async function deleteSession(userId: string, sessionId: string) {
  await fetch(`${BASE}/sessions/${userId}/${sessionId}`, {
    method: "DELETE",
  });
}

export async function getMemories(userId: string): Promise<MemoryItem[]> {
  const r = await fetch(`${BASE}/memories/${userId}`);
  return (await r.json()).memories;
}

export async function clearMemories(userId: string): Promise<number> {
  const r = await fetch(`${BASE}/memories/${userId}`, { method: "DELETE" });
  return (await r.json()).deleted ?? 0;
}

export async function getDocuments(
  userId: string,
): Promise<DocumentItem[]> {
  const res = await fetch(`${BASE}/documents/${userId}`);
  const data = await res.json();
  return data.documents ?? [];
}

export async function uploadDocument(
  userId: string,
  file: File,
): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/documents/${userId}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.error || "Upload failed");
  }
  const data = await res.json();
  return data.document;
}

export async function deleteDocument(
  userId: string,
  docId: string,
): Promise<void> {
  await fetch(`${BASE}/documents/${userId}/${docId}`, { method: "DELETE" });
}

export async function clearDocuments(userId: string): Promise<void> {
  await fetch(`${BASE}/documents/${userId}`, { method: "DELETE" });
}
