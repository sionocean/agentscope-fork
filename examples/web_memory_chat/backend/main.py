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
