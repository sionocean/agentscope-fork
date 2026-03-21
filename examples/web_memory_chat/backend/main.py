import sys
import os
import warnings
from datetime import datetime

# Suppress DeprecationWarnings from third-party libs (aiofiles, asyncio, etc.)
# Must be set before any async code runs.
warnings.filterwarnings("ignore", category=DeprecationWarning)
os.environ["PYTHONWARNINGS"] = "ignore::DeprecationWarning"

# Ensure stdout is unbuffered so trace logs appear immediately
if not os.environ.get("PYTHONUNBUFFERED"):
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

# Auto-write logs to logs/ directory (tee: both terminal + file)
_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(
    _log_dir,
    datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log",
)


import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Specific noise patterns from CPython 3.14 internals and third-party libs.
# These are exact substrings that only appear in warning/error output, not
# in user content or API responses.
_SUPPRESS = (
    "DeprecationWarning: 'asyncio.iscoroutinefunction'",
    "DeprecationWarning: websockets.legacy",
    "DeprecationWarning: websockets.server.WebSocketServerProtocol",
    "Unsupported block type thinking in the message, skipped.",
)


class _Tee:
    """Write to both terminal (with colors) and log file (plain text)."""

    def __init__(self, terminal, logfile):  # type: ignore[no-untyped-def]
        self.terminal = terminal
        self.logfile = logfile

    def write(self, data: str) -> int:
        if any(s in data for s in _SUPPRESS):
            return len(data)
        self.terminal.write(data)
        self.terminal.flush()
        self.logfile.write(_ANSI_RE.sub("", data))
        self.logfile.flush()
        return len(data)

    def flush(self) -> None:
        self.terminal.flush()
        self.logfile.flush()

    def fileno(self) -> int:
        return self.terminal.fileno()

    def isatty(self) -> bool:
        return self.terminal.isatty()


_log_fh = open(_log_file, "w", encoding="utf-8")  # noqa: SIM115
sys.stdout = _Tee(sys.__stdout__, _log_fh)  # type: ignore[assignment]
sys.stderr = _Tee(sys.__stderr__, _log_fh)  # type: ignore[assignment]
print(f"Logging to {_log_file}")

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


@app.get("/history/{user_id}/{session_id}")
async def get_history(user_id: str, session_id: str):
    msgs = await manager.get_history(user_id, session_id)
    return {"messages": msgs}


@app.delete("/sessions/{user_id}/{session_id}")
async def delete_session(user_id: str, session_id: str):
    await manager.delete_session(user_id, session_id)
    return {"status": "deleted"}


@app.delete("/memories/{user_id}")
async def clear_memories(user_id: str):
    """Delete all memories for a user from pgvector."""
    deleted = await manager.clear_memories(user_id)
    return {"status": "cleared", "deleted": deleted}


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
                f'SELECT unique_id, content, metadata FROM "{table}" LIMIT 50',
            )
            for r in rows:
                import json as _json
                meta = r["metadata"]
                if isinstance(meta, str):
                    try:
                        meta = _json.loads(meta)
                    except Exception:
                        meta = {}
                memories.append({
                    "id": str(r["unique_id"]),
                    "content": r["content"],
                    "metadata": meta if isinstance(meta, dict) else {},
                    "table": table,
                })
        await conn.close()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"memories": memories}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
