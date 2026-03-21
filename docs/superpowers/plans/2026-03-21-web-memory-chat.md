# Web Memory Chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack web chat application with all 3 ReMe long-term memory types (Personal, Task, Tool), Brave web search, stored in pgvector, powered by Ark LLM.

**Architecture:** Python FastAPI backend exposes SSE streaming chat + REST memory APIs. React+TypeScript frontend with chat UI, session management sidebar, and memory inspector panel. ReMe memories stored in PostgreSQL via pgvector. Brave Search as a registered tool.

**Tech Stack:** Python (FastAPI, AgentScope, ReMe, asyncpg), TypeScript (React, Vite), PostgreSQL + pgvector, Brave Search API, Ark LLM (OpenAI-compatible)

---

## File Structure

```
examples/web_memory_chat/
├── backend/
│   ├── main.py                  # FastAPI app, routes, CORS, startup/shutdown
│   ├── config.py                # All config (Ark, DB, Brave, etc.)
│   ├── agent_manager.py         # Creates/caches agents per user+session, manages ReMe lifecycle
│   ├── tools.py                 # brave_search tool function
│   ├── requirements.txt         # Python dependencies
│   └── .env.example             # Template env file
├── frontend/
│   ├── src/
│   │   ├── main.tsx             # React entry point
│   │   ├── App.tsx              # Layout: sidebar + chat + memory panel
│   │   ├── components/
│   │   │   ├── ChatView.tsx     # Chat messages + input, handles SSE stream
│   │   │   ├── Sidebar.tsx      # User/session list, new/switch/delete session
│   │   │   └── MemoryPanel.tsx  # Displays stored memories from pgvector
│   │   ├── api.ts               # fetch wrappers for backend endpoints
│   │   └── types.ts             # Shared TS types (Message, Session, Memory)
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
└── README.md
```

---

## Task 1: Backend — Config & Dependencies

**Files:**
- Create: `examples/web_memory_chat/backend/config.py`
- Create: `examples/web_memory_chat/backend/requirements.txt`
- Create: `examples/web_memory_chat/backend/.env.example`

- [ ] **Step 0: Ensure database exists with pgvector extension**

```bash
PGPASSWORD=postgres123 psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE agentscope_poc;" 2>/dev/null || true
PGPASSWORD=postgres123 psql -h localhost -p 5432 -U postgres -d agentscope_poc -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
Expected: `CREATE EXTENSION` (or already exists)

- [ ] **Step 1: Create requirements.txt**

```txt
fastapi>=0.100.0
uvicorn>=0.23.0
python-dotenv>=1.0.0
httpx>=0.24.0
psycopg[binary]>=3.1.0
asyncpg>=0.28.0
agentscope
reme-ai
```

- [ ] **Step 2: Create .env.example**

```env
# Ark LLM
ARK_API_KEY=your-ark-api-key
ARK_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
ARK_CHAT_MODEL=seed-2-0-lite-260228
ARK_EMBEDDING_MODEL=skylark-embedding-vision-250615
ARK_EMBEDDING_DIM=2048

# PostgreSQL + pgvector
DB_CONNECTION_STRING=postgresql://postgres:postgres123@localhost:5432/agentscope_poc

# Brave Search
BRAVE_API_KEY=your-brave-api-key
```

- [ ] **Step 3: Create config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

ARK_API_KEY = os.environ["ARK_API_KEY"]
ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3")
ARK_CHAT_MODEL = os.environ.get("ARK_CHAT_MODEL", "seed-2-0-lite-260228")
ARK_EMBEDDING_MODEL = os.environ.get("ARK_EMBEDDING_MODEL", "skylark-embedding-vision-250615")
ARK_EMBEDDING_DIM = int(os.environ.get("ARK_EMBEDDING_DIM", "2048"))

DB_CONNECTION_STRING = os.environ.get(
    "DB_CONNECTION_STRING",
    "postgresql://postgres:postgres123@localhost:5432/agentscope_poc",
)

BRAVE_API_KEY = os.environ["BRAVE_API_KEY"]
```

- [ ] **Step 4: Create .env with real values and verify imports**

Copy `.env.example` to `.env`, fill in real keys. Run:
```bash
cd examples/web_memory_chat/backend
python -c "from config import *; print('Config OK')"
```
Expected: `Config OK`

- [ ] **Step 5: Commit**

```bash
git add examples/web_memory_chat/backend/{config.py,requirements.txt,.env.example}
git commit -m "feat(web-memory-chat): add backend config and dependencies"
```

---

## Task 2: Backend — Brave Search Tool

**Files:**
- Create: `examples/web_memory_chat/backend/tools.py`

- [ ] **Step 1: Implement brave_search tool function**

The function must return `ToolResponse` (AgentScope's tool interface) so it can be registered in `Toolkit`. Use `httpx` to call the Brave Search REST API.

```python
import httpx
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from config import BRAVE_API_KEY


async def brave_search(query: str, count: int = 5) -> ToolResponse:
    """Search the web using Brave Search API.

    Args:
        query: The search query string.
        count: Number of results to return (max 20, default 5).

    Returns:
        ToolResponse containing search results with titles, URLs and descriptions.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(count, 20)},
            headers={"X-Subscription-Token": BRAVE_API_KEY},
            timeout=15,
        )

    if resp.status_code != 200:
        return ToolResponse(
            content=[TextBlock(type="text", text=f"Search failed: {resp.status_code}")],
        )

    data = resp.json()
    results = data.get("web", {}).get("results", [])

    if not results:
        return ToolResponse(
            content=[TextBlock(type="text", text="No results found.")],
        )

    lines = []
    for r in results:
        lines.append(f"**{r['title']}**")
        lines.append(f"URL: {r['url']}")
        lines.append(f"{r.get('description', '')}")
        lines.append("")

    return ToolResponse(
        content=[TextBlock(type="text", text="\n".join(lines))],
    )
```

- [ ] **Step 2: Verify tool works**

```bash
python -c "
import asyncio
from tools import brave_search
async def test():
    r = await brave_search('python asyncio')
    print([b['text'][:80] for b in r.content])
asyncio.run(test())
"
```
Expected: List with search result text.

- [ ] **Step 3: Commit**

```bash
git add examples/web_memory_chat/backend/tools.py
git commit -m "feat(web-memory-chat): add brave_search tool"
```

---

## Task 3: Backend — Agent Manager (Memory + Agent Lifecycle)

**Files:**
- Create: `examples/web_memory_chat/backend/agent_manager.py`

This is the core module. It manages:
- Per-user ReMe memory instances (Personal, Task, Tool) with pgvector storage
- Per-session ReActAgent instances with all 3 memory types attached
- Async context lifecycle (ReMe requires `async with`)

- [ ] **Step 1: Implement AgentManager class**

Key design decisions:
- **Personal Memory**: one per user (persists across sessions) — attached to agent via `long_term_memory` with mode `"both"`
- **Task Memory**: one per user (learns from all sessions) — record/retrieve called manually around agent invocations
- **Tool Memory**: one per user — retrieve guidelines on agent creation, inject into sys_prompt. Record after each tool call.
- **Session state**: saved/loaded via `JSONSession` keyed by `{user_id}-{session_id}`

The `ReActAgent` only supports one `long_term_memory` parameter, so Personal Memory gets that slot (it benefits most from agent-controlled record/retrieve). Task Memory and Tool Memory are managed programmatically.

```python
import asyncio
import json
from typing import AsyncGenerator

from agentscope.agent import ReActAgent
from agentscope.embedding import ArkEmbedding
from agentscope.embedding._ark_embedding import register_ark_embedding_backend
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory, ReMePersonalLongTermMemory
from agentscope.memory import ReMeTaskLongTermMemory, ReMeToolLongTermMemory
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.pipeline import stream_printing_messages
from agentscope.session import JSONSession
from agentscope.tool import Toolkit

from config import (
    ARK_API_KEY, ARK_BASE_URL, ARK_CHAT_MODEL,
    ARK_EMBEDDING_MODEL, ARK_EMBEDDING_DIM, DB_CONNECTION_STRING,
)
from tools import brave_search

# Register Ark embedding backend for flowllm (ReMe internals)
register_ark_embedding_backend()

# Shared ReMe config args for Ark + pgvector
REME_CONFIG_ARGS = [
    "embedding_model.default.backend=ark_multimodal",
    "vector_store.default.backend=pgvector",
    f"vector_store.default.params={{\"connection_string\": \"{DB_CONNECTION_STRING}\"}}",
]


def _make_model(stream: bool = True) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name=ARK_CHAT_MODEL,
        api_key=ARK_API_KEY,
        stream=stream,
        client_kwargs={"base_url": ARK_BASE_URL},
    )


def _make_embedding() -> ArkEmbedding:
    return ArkEmbedding(
        api_key=ARK_API_KEY,
        model_name=ARK_EMBEDDING_MODEL,
        base_url=ARK_BASE_URL,
        dimensions=ARK_EMBEDDING_DIM,
    )


class AgentManager:
    """Manages per-user memories and per-session agents."""

    def __init__(self) -> None:
        # user_id -> {personal, task, tool} memory instances
        self._memories: dict[str, dict] = {}
        # (user_id, session_id) -> ReActAgent
        self._agents: dict[tuple[str, str], ReActAgent] = {}
        self._session = JSONSession(save_dir="./sessions")
        # Prevent concurrent _ensure_memories for the same user
        self._locks: dict[str, asyncio.Lock] = {}

    def _user_lock(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    async def _ensure_memories(self, user_id: str) -> dict:
        """Create and start ReMe memories for a user if not yet active."""
        async with self._user_lock(user_id):
            if user_id in self._memories:
                return self._memories[user_id]

        personal = ReMePersonalLongTermMemory(
            agent_name="Friday", user_name=user_id,
            model=_make_model(stream=False),
            embedding_model=_make_embedding(),
            reme_config_args=REME_CONFIG_ARGS,
        )
        task = ReMeTaskLongTermMemory(
            agent_name="Friday", user_name=user_id,
            model=_make_model(stream=False),
            embedding_model=_make_embedding(),
            reme_config_args=REME_CONFIG_ARGS,
        )
        tool = ReMeToolLongTermMemory(
            agent_name="Friday", user_name=user_id,
            model=_make_model(stream=False),
            embedding_model=_make_embedding(),
            reme_config_args=REME_CONFIG_ARGS,
        )

        await personal.__aenter__()
        await task.__aenter__()
        await tool.__aenter__()

        mem = {"personal": personal, "task": task, "tool": tool}
        self._memories[user_id] = mem
        return mem

    async def get_agent(self, user_id: str, session_id: str) -> ReActAgent:
        """Get or create an agent for the given user+session."""
        key = (user_id, session_id)
        if key in self._agents:
            return self._agents[key]

        memories = await self._ensure_memories(user_id)

        # Retrieve tool guidelines and inject into sys_prompt
        tool_guidelines = await memories["tool"].retrieve(
            msg=Msg(role="user", content="brave_search", name="user"),
        )
        guidelines_section = ""
        if tool_guidelines:
            guidelines_section = f"\n\n## Tool Guidelines:\n{tool_guidelines}"

        toolkit = Toolkit()
        toolkit.register_tool_function(brave_search)

        agent = ReActAgent(
            name="Friday",
            sys_prompt=(
                "You are Friday, a helpful AI assistant with long-term memory "
                "and web search capabilities.\n\n"
                "## Memory Guidelines:\n"
                "1. When users share personal info, preferences, or facts, "
                "record them with `record_to_memory`.\n"
                "2. Before answering questions about the user, FIRST call "
                "`retrieve_from_memory`.\n"
                "3. Use `brave_search` to find up-to-date information.\n"
                "4. Always respond in the same language as the user."
                + guidelines_section
            ),
            model=_make_model(),
            formatter=OpenAIChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            long_term_memory=memories["personal"],
            long_term_memory_mode="both",
        )

        # Load session state if exists
        await self._session.load_session_state(
            session_id=f"{user_id}-{session_id}",
            agent=agent,
        )

        self._agents[key] = agent
        return agent

    async def chat(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response as SSE data lines."""
        agent = await self.get_agent(user_id, session_id)
        msg = Msg("user", user_input, "user")

        async for msg_out, _ in stream_printing_messages(
            agents=[agent],
            coroutine_task=agent(msg),
        ):
            import json as _json
            data = _json.dumps(msg_out.to_dict(), ensure_ascii=False)
            yield f"data: {data}\n\n"

        # Save session state
        await self._session.save_session_state(
            session_id=f"{user_id}-{session_id}",
            agent=agent,
        )

        # Record to task memory (the conversation trajectory)
        memories = self._memories.get(user_id)
        if memories:
            recent = (await agent.memory.get_memory())[-4:]  # last 2 turns
            if recent:
                await memories["task"].record(msgs=recent, score=0.8)

    async def get_sessions(self, user_id: str) -> list[str]:
        """List session IDs for a user (from saved files)."""
        import os
        sessions = []
        save_dir = "./sessions"
        if os.path.exists(save_dir):
            prefix = f"{user_id}-"
            for f in os.listdir(save_dir):
                if f.startswith(prefix) and f.endswith(".json"):
                    sid = f[len(prefix):-5]  # strip prefix and .json
                    sessions.append(sid)
        return sorted(sessions)

    async def delete_session(self, user_id: str, session_id: str) -> None:
        """Delete a session's state."""
        import os
        key = (user_id, session_id)
        self._agents.pop(key, None)
        path = f"./sessions/{user_id}-{session_id}.json"
        if os.path.exists(path):
            os.remove(path)

    async def shutdown(self) -> None:
        """Clean up all ReMe memory contexts."""
        for mem in self._memories.values():
            for m in mem.values():
                await m.__aexit__()
        self._memories.clear()
        self._agents.clear()
```

- [ ] **Step 2: Verify AgentManager instantiation**

```bash
python -c "
import asyncio
from agent_manager import AgentManager
mgr = AgentManager()
print('AgentManager: OK')
"
```
Expected: `AgentManager: OK` (no errors on import)

- [ ] **Step 3: Commit**

```bash
git add examples/web_memory_chat/backend/agent_manager.py
git commit -m "feat(web-memory-chat): add agent manager with 3 ReMe memory types + pgvector"
```

---

## Task 4: Backend — FastAPI Server

**Files:**
- Create: `examples/web_memory_chat/backend/main.py`

- [ ] **Step 1: Implement FastAPI app with all endpoints**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from agent_manager import AgentManager

manager = AgentManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await manager.shutdown()


app = FastAPI(title="AgentScope Memory Chat", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_id = data.get("user_id", "default")
    session_id = data.get("session_id", "default")
    user_input = data.get("user_input", "")
    return StreamingResponse(
        manager.chat(user_id, session_id, user_input),
        media_type="text/event-stream",
    )


@app.get("/sessions/{user_id}")
async def list_sessions(user_id: str):
    sessions = await manager.get_sessions(user_id)
    return {"sessions": sessions}


@app.delete("/sessions/{user_id}/{session_id}")
async def delete_session(user_id: str, session_id: str):
    await manager.delete_session(user_id, session_id)
    return {"status": "deleted"}


@app.get("/memories/{user_id}")
async def get_memories(user_id: str):
    """Query stored memories for a user from pgvector."""
    import asyncpg
    from config import DB_CONNECTION_STRING
    memories = []
    try:
        conn = await asyncpg.connect(DB_CONNECTION_STRING)
        # List tables matching this user's workspace
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE tablename LIKE $1",
            f"workspace_{user_id}%",
        )
        for row in tables:
            table = row["tablename"]
            rows = await conn.fetch(
                f'SELECT id, content, metadata FROM "{table}" ORDER BY id DESC LIMIT 50',
            )
            for r in rows:
                memories.append({
                    "id": str(r["id"]),
                    "content": r["content"],
                    "metadata": r["metadata"] if r["metadata"] else {},
                    "table": table,
                })
        await conn.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"memories": memories}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 2: Start server and test health endpoint**

```bash
cd examples/web_memory_chat/backend
python main.py &
sleep 2
curl http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 3: Test chat endpoint with curl**

```bash
curl -N http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","session_id":"s1","user_input":"hello"}'
```
Expected: SSE data lines with streaming response.

- [ ] **Step 4: Kill test server, commit**

```bash
pkill -f "main.py" || true
git add examples/web_memory_chat/backend/main.py
git commit -m "feat(web-memory-chat): add FastAPI server with chat, sessions, memories endpoints"
```

---

## Task 5: Frontend — Project Scaffolding

**Files:**
- Create: `examples/web_memory_chat/frontend/package.json`
- Create: `examples/web_memory_chat/frontend/tsconfig.json`
- Create: `examples/web_memory_chat/frontend/vite.config.ts`
- Create: `examples/web_memory_chat/frontend/index.html`
- Create: `examples/web_memory_chat/frontend/src/main.tsx`
- Create: `examples/web_memory_chat/frontend/src/types.ts`
- Create: `examples/web_memory_chat/frontend/src/api.ts`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "web-memory-chat",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

Standard React+Vite tsconfig with `"jsx": "react-jsx"`, `"strict": true`.

- [ ] **Step 3: Create vite.config.ts**

Proxy `/api` to `http://localhost:8000` so the frontend can call the backend without CORS issues in dev.

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
```

- [ ] **Step 4: Create index.html, main.tsx, types.ts, api.ts**

`types.ts` — shared types:
```typescript
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
```

`api.ts` — backend API wrappers:
```typescript
const BASE = "/api";

export async function* streamChat(userId: string, sessionId: string, userInput: string) {
  const resp = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, session_id: sessionId, user_input: userInput }),
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

export async function deleteSession(userId: string, sessionId: string) {
  await fetch(`${BASE}/sessions/${userId}/${sessionId}`, { method: "DELETE" });
}

import type { MemoryItem } from "./types";

export async function getMemories(userId: string): Promise<MemoryItem[]> {
  const r = await fetch(`${BASE}/memories/${userId}`);
  return (await r.json()).memories;
}
```

- [ ] **Step 5: npm install and verify dev server starts**

```bash
cd examples/web_memory_chat/frontend
npm install
npm run dev &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
```
Expected: `200`

- [ ] **Step 6: Commit**

```bash
git add examples/web_memory_chat/frontend/
git commit -m "feat(web-memory-chat): scaffold React+Vite frontend with types and API layer"
```

---

## Task 6: Frontend — Chat View Component

**Files:**
- Create: `examples/web_memory_chat/frontend/src/components/ChatView.tsx`

- [ ] **Step 1: Implement ChatView**

Key behaviors:
- Display messages as a scrollable list (user right-aligned, assistant left-aligned)
- Streaming: use `streamChat()` async generator, update assistant message in-place by `msg.id`
- Show thinking blocks (collapsible, muted style)
- Show tool_use / tool_result blocks (green-tinted, monospace)
- Input textarea with Enter-to-send (Shift+Enter for newline)
- Auto-scroll to bottom on new content

Props: `userId: string`, `sessionId: string`

Parse SSE messages: each has `id`, `content` (array of blocks or string). Group by `id`, update existing message element. Extract `text`, `thinking`, `tool_use`, `tool_result` block types.

- [ ] **Step 2: Verify it renders with mock data**

- [ ] **Step 3: Commit**

```bash
git add examples/web_memory_chat/frontend/src/components/ChatView.tsx
git commit -m "feat(web-memory-chat): add ChatView component with SSE streaming"
```

---

## Task 7: Frontend — Sidebar Component

**Files:**
- Create: `examples/web_memory_chat/frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Implement Sidebar**

Features:
- Text input for user ID (defaults to "default")
- List of sessions for the current user (fetched from `/sessions/{userId}`)
- "New Session" button (generates UUID)
- Click session to switch
- Delete session button (with confirmation)
- Active session highlighted

Props: `userId`, `onUserChange`, `sessionId`, `onSessionChange`, `sessions`, `onNewSession`, `onDeleteSession`

- [ ] **Step 2: Commit**

```bash
git add examples/web_memory_chat/frontend/src/components/Sidebar.tsx
git commit -m "feat(web-memory-chat): add Sidebar with session management"
```

---

## Task 8: Frontend — Memory Panel Component

**Files:**
- Create: `examples/web_memory_chat/frontend/src/components/MemoryPanel.tsx`

- [ ] **Step 1: Implement MemoryPanel**

Features:
- Fetches memories from `/memories/{userId}` on load and after each chat
- Groups by table name (workspace_xxx maps to memory type)
- Displays each memory's content and metadata
- Refresh button
- Collapsible sections per memory type

Props: `userId`, `refreshTrigger` (incremented after each chat to auto-refresh)

- [ ] **Step 2: Commit**

```bash
git add examples/web_memory_chat/frontend/src/components/MemoryPanel.tsx
git commit -m "feat(web-memory-chat): add MemoryPanel component"
```

---

## Task 9: Frontend — App Layout & Integration

**Files:**
- Create: `examples/web_memory_chat/frontend/src/App.tsx`
- Modify: `examples/web_memory_chat/frontend/src/main.tsx`

- [ ] **Step 1: Implement App.tsx**

Layout: 3-column flex layout
- Left: Sidebar (240px)
- Center: ChatView (flex-1)
- Right: MemoryPanel (300px, collapsible)

State management (useState):
- `userId`, `sessionId`, `sessions`, `memoryRefreshCounter`

On mount: fetch sessions for default user. On session change: reset chat.

- [ ] **Step 2: Wire up main.tsx**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
```

- [ ] **Step 3: End-to-end test**

Start backend (`python main.py`) and frontend (`npm run dev`). Open `http://localhost:5173`. Send a message. Verify:
1. Streaming response appears
2. Session appears in sidebar
3. After recording memory, it shows in Memory Panel

- [ ] **Step 4: Commit**

```bash
git add examples/web_memory_chat/frontend/src/{App.tsx,main.tsx}
git commit -m "feat(web-memory-chat): integrate App layout with all components"
```

---

## Task 10: README & Final Polish

**Files:**
- Create: `examples/web_memory_chat/README.md`

- [ ] **Step 1: Write README**

Include:
- What the demo does (chat + 3 types of long-term memory + web search + pgvector)
- Prerequisites (Python 3.12+, Node 18+, PostgreSQL with pgvector)
- Quick start steps (create DB, install deps, configure .env, start backend, start frontend)
- Architecture diagram (text)
- Screenshots placeholder
- API reference table

- [ ] **Step 2: Full end-to-end test flow**

1. Start fresh: drop and recreate `agentscope_poc` DB
2. Start backend, start frontend
3. As "alice": tell agent personal info, verify memory panel shows it
4. Search something with brave_search, verify tool call renders
5. Switch to new session, ask "what do you know about me?" — verify cross-session memory retrieval
6. Switch to user "bob", verify isolated memories
7. Refresh page, verify session list persists

- [ ] **Step 3: Commit**

```bash
git add examples/web_memory_chat/README.md
git commit -m "docs(web-memory-chat): add README with setup instructions"
```
