# Web Memory Chat — AgentScope Demo

A full-stack web chat application demonstrating AgentScope's ReMe long-term memory system with real-time streaming, multi-user support, and persistent vector storage.

## Features

- **3 types of ReMe long-term memory**:
  - **Personal Memory** — records user facts, preferences, habits (agent-controlled via `record_to_memory` / `retrieve_from_memory`)
  - **Task Memory** — records reusable task execution experiences (agent-controlled via `record_task_experience` / `retrieve_task_experience`)
  - **Tool Memory** — automatically records tool execution results, retrieves guidelines into system prompt
- **Brave Web Search** integration via AgentScope's tool system
- **pgvector storage** in PostgreSQL for semantic memory retrieval
- **Ark LLM** (ByteDance Volcengine, OpenAI-compatible API) with custom `ArkEmbedding` adapter
- **Multi-user, multi-session** support with isolated memory per user
- **Memory Inspector Panel** to visualize what's stored in the vector database
- **Observability logging** — structured trace logs with layer tags (`FRAMEWORK`, `LLM_API`, `TOOL`, `REME`, `EMBEDDING`, `PGVECTOR`), configurable per source

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐     ┌──────────────┐
│   React UI  │────>│  FastAPI Backend (port 8010)          │────>│  PostgreSQL  │
│  (Vite dev) │ SSE │  ├── ReActAgent + OpenAIChatFormatter │     │  + pgvector  │
│             │<────│  ├── ReMe Personal Memory             │     │              │
│  - ChatView │     │  ├── ReMe Task Memory                 │     └──────────────┘
│  - Sidebar  │     │  ├── ReMe Tool Memory                 │
│  - Memory   │     │  └── Brave Search Tool                │     ┌──────────────┐
│    Panel    │     │                                       │────>│  Ark LLM API │
└─────────────┘     └──────────────────────────────────────┘     │  + Embedding │
                                                                  └──────────────┘
```

## Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL with pgvector extension
- Ark API key (ByteDance Volcengine)
- Brave Search API key

## Quick Start

### 1. Database Setup

```bash
PGPASSWORD=postgres123 psql -h localhost -p 5432 -U postgres \
  -c "CREATE DATABASE agentscope_poc;"
PGPASSWORD=postgres123 psql -h localhost -p 5432 -U postgres \
  -d agentscope_poc -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 2. Backend

```bash
cd examples/web_memory_chat/backend
cp .env.example .env
# Edit .env with your API keys
pip install -r requirements.txt
python main.py
```

### 3. Frontend (new terminal)

```bash
cd examples/web_memory_chat/frontend
npm install
npm run dev
```

### 4. Open http://localhost:5173

## Configuration

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `ARK_API_KEY` | (required) | Ark LLM API key |
| `ARK_BASE_URL` | `https://ark.ap-southeast.bytepluses.com/api/v3` | Ark API base URL |
| `ARK_CHAT_MODEL` | `seed-2-0-lite-260228` | Chat model name |
| `ARK_EMBEDDING_MODEL` | `skylark-embedding-vision-250615` | Embedding model name |
| `ARK_EMBEDDING_DIM` | `2048` | Embedding dimensions |
| `DB_CONNECTION_STRING` | `postgresql://postgres:postgres123@localhost:5432/agentscope_poc` | PostgreSQL connection |
| `BRAVE_API_KEY` | (required) | Brave Search API key |
| `REME_LANGUAGE` | `zh` | ReMe prompt language (`zh` or `en`) |

### Observability (trace_logger.py)

Edit `TRACE_CONFIG` at the top of `trace_logger.py` to toggle log sources:

```python
TRACE_CONFIG = {
    "FRAMEWORK": True,    # agent lifecycle, chat start/done
    "LLM_API":   True,    # outgoing LLM chat/completions calls
    "TOOL":      True,    # tool calls (brave_search, memory tools)
    "REME":      True,    # ReMe memory operations
    "EMBEDDING": True,    # embedding API calls
    "PGVECTOR":  True,    # pgvector operations
    "FLOWLLM":   False,   # flowllm internal logs (verbose)
    "LLM_API_BODY": True, # full request/response body for LLM calls
    ...
}
```

Logs are written to both terminal and `backend/logs/` directory.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /chat | SSE streaming chat |
| GET | /sessions/{user_id} | List sessions |
| GET | /history/{user_id}/{session_id} | Get chat history |
| DELETE | /sessions/{user_id}/{session_id} | Delete session |
| GET | /memories/{user_id} | Query stored memories |
| DELETE | /memories/{user_id} | Clear all memories |
| GET | /health | Health check |

## Usage Tips

- **Personal memory**: Tell the agent personal info ("My name is Alice, I love hiking") then ask "What do you know about me?"
- **Task memory**: After completing a concrete task, the agent will record the experience. Ask similar questions later and it will retrieve past approaches.
- **Web search**: Ask it to search something ("Search for the latest Python news")
- **Session persistence**: Switch sessions — memory persists across sessions for the same user
- **User isolation**: Switch users — memories are isolated per user
- **Memory Panel**: Check the Memory Panel on the right to see stored memories, with "Clear All" button to reset
