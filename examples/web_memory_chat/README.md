# Web Memory Chat — AgentScope Demo

A full-stack web chat application demonstrating AgentScope's ReMe long-term memory system with real-time streaming, multi-user support, and persistent vector storage.

## What This Demo Does

This demo showcases a production-style chat application built on AgentScope with:

- **3 types of ReMe long-term memory**: Personal (user facts), Task (goals/todos), and Tool (search results/references)
- **Brave web search** integration via AgentScope's tool system
- **pgvector storage** in PostgreSQL for semantic memory retrieval
- **Ark LLM** (ByteDance Volcengine, OpenAI-compatible API)
- **Multi-user, multi-session** support with isolated memory per user
- **Memory Inspector Panel** to visualize what's stored in the vector database

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────┐     ┌──────────────┐
│   React UI  │────▶│  FastAPI Backend                     │────▶│  PostgreSQL   │
│  (Vite dev) │ SSE │  ├── ReActAgent + OpenAIChatFormatter│     │  + pgvector   │
│             │◀────│  ├── ReMe Personal Memory            │     │              │
│  - ChatView │     │  ├── ReMe Task Memory                │     └──────────────┘
│  - Sidebar  │     │  ├── ReMe Tool Memory                │
│  - Memory   │     │  └── Brave Search Tool               │     ┌──────────────┐
│    Panel    │     │                                      │────▶│  Ark LLM API │
└─────────────┘     └──────────────────────────────────────┘     └──────────────┘
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

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /chat | SSE streaming chat |
| GET | /sessions/{user_id} | List sessions |
| DELETE | /sessions/{user_id}/{session_id} | Delete session |
| GET | /memories/{user_id} | Query stored memories |
| GET | /health | Health check |

## Usage Tips

- **Personal memory**: Tell the agent personal info ("My name is Alice, I love hiking") then ask "What do you know about me?"
- **Web search**: Ask it to search something ("Search for the latest Python news")
- **Session persistence**: Switch sessions — memory persists across sessions for the same user
- **User isolation**: Switch users — memories are isolated per user
- **Memory Panel**: Check the Memory Panel on the right to see what's stored in pgvector
