import asyncio
import json
import time
from datetime import datetime
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
from agentscope.tool import Toolkit, ToolResponse

from config import (
    ARK_API_KEY, ARK_BASE_URL, ARK_CHAT_MODEL,
    ARK_EMBEDDING_MODEL, ARK_EMBEDDING_DIM, DB_CONNECTION_STRING,
    REME_LANGUAGE,
)
from tools import brave_search
from trace_logger import (
    install_http_tracing,
    install_loguru_tracing,
    install_uvicorn_filter,
    install_agentscope_filter,
    log,
    TRACE_CONFIG,
)

# Install all tracing/filtering
install_http_tracing()
install_loguru_tracing()
install_uvicorn_filter()
install_agentscope_filter()

# Register Ark embedding backend for flowllm (ReMe internals)
register_ark_embedding_backend()

# Suppress the "Unsupported block type thinking" warning from OpenAIChatFormatter.
# Ark models return thinking blocks which are valid but not recognized by the
# formatter when re-sending history. They are safely skipped.
import logging as _logging
_logging.getLogger("agentscope").addFilter(
    type("_ThinkingFilter", (_logging.Filter,), {
        "filter": staticmethod(
            lambda r: "Unsupported block type thinking" not in r.getMessage()
        ),
    })(),
)


def _log_streamed_response(blocks: list) -> None:
    """Log the final accumulated content of a completed streamed response."""
    if not TRACE_CONFIG.get("LLM_API_BODY"):
        return
    from trace_logger import _COLORS
    color = _COLORS.get("LLM_API", "")
    reset = _COLORS["RESET"]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "thinking":
            text = block.get("thinking", "")
            if text:
                print(f"{color}    [thinking] {text}{reset}")
        elif btype == "text":
            text = block.get("text", "")
            if text:
                print(f"{color}    [assistant] {text}{reset}")
        elif btype == "tool_use":
            name = block.get("name", "?")
            inp = block.get("input", {})
            print(f"{color}    [tool_call] {name}({json.dumps(inp, ensure_ascii=False)}){reset}")
        elif btype == "tool_result":
            name = block.get("name", "?")
            output = block.get("output", block.get("content", ""))
            print(f"{color}    [tool_result:{name}] {output}{reset}")

# Shared ReMe config args for Ark + pgvector
REME_CONFIG_ARGS = [
    "embedding_model.default.backend=ark_multimodal",
    "vector_store.default.backend=pgvector",
    f"vector_store.default.params={{\"connection_string\": \"{DB_CONNECTION_STRING}\"}}",
    f"language={REME_LANGUAGE}",
]

# ── System prompt ──────────────────────────────────────────────────
SYS_PROMPT = """\
You are Friday, a helpful AI assistant with long-term memory \
and web search capabilities.

## Personal Memory (record_to_memory / retrieve_from_memory)
These tools manage personal facts about the user.
- **Record**: When users share personal info (name, preferences, \
habits, facts about themselves), call `record_to_memory`.
- **Retrieve**: Before answering questions about the user, FIRST \
call `retrieve_from_memory` to check stored information.

## Task Experience Memory (record_task_experience / retrieve_task_experience)
These tools manage reusable task execution experiences.
- **Record**: After you successfully complete a concrete task \
(debugging, writing code, research, planning), call \
`record_task_experience` to save the approach and lessons learned. \
Do NOT record routine conversations — only actionable experiences.
- **Retrieve**: When facing a task similar to one you may have \
solved before, call `retrieve_task_experience` to check past \
approaches.

## Web Search (brave_search)
Use `brave_search` to find up-to-date information from the web.

## General Rules
- Always respond in the same language as the user.
- Always check memory before saying you don't know something \
about the user.\
"""


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
        self._memories: dict[str, dict] = {}
        self._agents: dict[tuple[str, str], ReActAgent] = {}
        self._session = JSONSession(save_dir="./sessions")
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

            log.reme("init_memories", user=user_id,
                     types="personal,task,tool", storage="pgvector")
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
            log.reme("memories_ready", user=user_id)
            return mem

    async def get_agent(self, user_id: str, session_id: str) -> ReActAgent:
        """Get or create an agent for the given user+session."""
        key = (user_id, session_id)
        if key in self._agents:
            log.framework("agent_cache_hit", user=user_id,
                          session=session_id[:8])
            return self._agents[key]

        log.framework("agent_create", user=user_id, session=session_id[:8])
        memories = await self._ensure_memories(user_id)

        # ── Tool Memory: retrieve guidelines, inject into sys_prompt ──
        log.reme("retrieve_tool_guidelines", tool="brave_search")
        tool_guidelines = await memories["tool"].retrieve(
            msg=Msg(role="user", content="brave_search", name="user"),
        )
        guidelines_section = ""
        if tool_guidelines:
            guidelines_section = (
                f"\n\n## Tool Guidelines (from past experience):\n"
                f"{tool_guidelines}"
            )

        # ── Build toolkit ──
        toolkit = Toolkit()
        toolkit.register_tool_function(brave_search)

        # Task Memory: register as agent-callable tools with distinct names
        # We wrap the task memory methods so they appear as separate tools
        # from personal memory's record_to_memory / retrieve_from_memory.
        task_mem = memories["task"]

        async def record_task_experience(
            thinking: str,
            content: list[str],
            score: float = 1.0,
        ) -> ToolResponse:
            """Record a task execution experience for future reference.

            Call this after completing a concrete task (debugging, coding,
            research, planning) to save the approach and lessons learned.

            Args:
                thinking: Why this experience is valuable.
                content: List of actionable insights and steps.
                score: Success quality 0.0-1.0 (1.0=fully successful).

            Returns:
                Confirmation message.
            """
            log.reme("record_task_experience",
                     thinking=thinking, items=len(content),
                     score=score)
            return await task_mem.record_to_memory(
                thinking=thinking, content=content, score=score,
            )

        async def retrieve_task_experience(
            keywords: list[str],
        ) -> ToolResponse:
            """Retrieve past task experiences relevant to the current task.

            Call this when facing a task similar to one solved before.

            Args:
                keywords: Search terms describing the task.

            Returns:
                Relevant past experiences, or empty if none found.
            """
            log.reme("retrieve_task_experience", keywords=keywords)
            return await task_mem.retrieve_from_memory(keywords=keywords)

        toolkit.register_tool_function(record_task_experience)
        toolkit.register_tool_function(retrieve_task_experience)

        # ── Create agent ──
        agent = ReActAgent(
            name="Friday",
            sys_prompt=SYS_PROMPT + guidelines_section,
            model=_make_model(),
            formatter=OpenAIChatFormatter(),
            toolkit=toolkit,
            memory=InMemoryMemory(),
            # Personal Memory gets the long_term_memory slot
            long_term_memory=memories["personal"],
            long_term_memory_mode="agent_control",
        )

        # Load session state if exists
        await self._session.load_session_state(
            session_id=f"{user_id}-{session_id}",
            agent=agent,
        )

        self._agents[key] = agent
        log.framework(
            "agent_ready", user=user_id, session=session_id[:8],
            tools="brave_search,record_to_memory,retrieve_from_memory,"
                  "record_task_experience,retrieve_task_experience",
        )
        return agent

    async def chat(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response as SSE data lines."""
        log.framework("chat_start", user=user_id, session=session_id[:8],
                       input=user_input)
        t0 = time.monotonic()
        agent = await self.get_agent(user_id, session_id)
        # Disable built-in console printing — we log ourselves after completion
        agent.set_console_output_enabled(False)
        msg = Msg("user", user_input, "user")

        chunk_count = 0
        logged_tool_use_ids: set[str] = set()   # for dedup tool_use logs
        logged_tool_result_ids: set[str] = set()  # for dedup tool_result logs
        tool_executions: list[dict] = []
        # Track last content per msg id for logging after stream ends
        last_content: dict[str, list] = {}

        async for msg_out, _ in stream_printing_messages(
            agents=[agent],
            coroutine_task=agent(msg),
        ):
            chunk_count += 1
            msg_id = msg_out.id if hasattr(msg_out, 'id') else ""
            content = msg_out.content if hasattr(msg_out, 'content') else None

            # Track accumulated content per message (overwritten each chunk)
            if isinstance(content, list) and msg_id:
                last_content[msg_id] = content

            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    bid = block.get("id", "")
                    btype = block.get("type", "")

                    if btype == "tool_use" and bid and bid not in logged_tool_use_ids:
                        logged_tool_use_ids.add(bid)
                        tool_name = block.get("name", "?")
                        log.tool(f"call:{tool_name}")
                        tool_executions.append({
                            "id": bid,
                            "tool_name": tool_name,
                            "input": block.get("input", {}),
                            "t0": time.monotonic(),
                        })

                    elif btype == "tool_result" and bid not in logged_tool_result_ids:
                        logged_tool_result_ids.add(bid)
                        name = block.get("name", "?")
                        output = block.get("output",
                                           block.get("content", ""))
                        log.tool(f"result:{name}",
                                 output=str(output))
                        # Match back to tool_use by tool_use_id
                        tool_use_id = block.get("tool_use_id", "")
                        for te in tool_executions:
                            if te["id"] == tool_use_id:
                                te["output"] = str(output)
                                te["success"] = True
                                te["time_cost"] = (
                                    time.monotonic() - te["t0"]
                                )
                                break

            data = json.dumps(msg_out.to_dict(), ensure_ascii=False)
            yield f"data: {data}\n\n"

        # Log all completed streamed responses
        for blocks in last_content.values():
            _log_streamed_response(blocks)

        elapsed = (time.monotonic() - t0) * 1000
        log.framework("chat_done", user=user_id, session=session_id[:8],
                       chunks=chunk_count, time=f"{elapsed:.0f}ms")

        # Fire-and-forget background work
        asyncio.create_task(
            self._post_chat(user_id, session_id, agent, tool_executions),
        )

    async def _post_chat(
        self,
        user_id: str,
        session_id: str,
        agent: ReActAgent,
        tool_executions: list[dict],
    ) -> None:
        """Background: save session + record tool executions to Tool Memory."""
        try:
            # 1. Save session state
            log.framework("session_save",
                          session=f"{user_id}-{session_id[:8]}")
            await self._session.save_session_state(
                session_id=f"{user_id}-{session_id}",
                agent=agent,
            )

            # 2. Record tool executions to Tool Memory (if any)
            memories = self._memories.get(user_id)
            if not memories:
                return

            # Filter to only external tools (not memory tools)
            external_tools = [
                te for te in tool_executions
                if te["tool_name"] in ("brave_search",)
                and "output" in te
            ]
            if external_tools:
                tool_msgs = []
                for te in external_tools:
                    tool_record = {
                        "create_time": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S",
                        ),
                        "tool_name": te["tool_name"],
                        "input": te["input"],
                        "output": te["output"],
                        "token_cost": 0,
                        "success": te.get("success", True),
                        "time_cost": round(te.get("time_cost", 0), 2),
                    }
                    tool_msgs.append(
                        Msg(
                            role="assistant",
                            content=json.dumps(tool_record,
                                               ensure_ascii=False),
                            name="assistant",
                        ),
                    )
                log.reme("tool_memory_record",
                         user=user_id, tools=len(tool_msgs))
                await memories["tool"].record(msgs=tool_msgs)
                log.reme("tool_memory_done", user=user_id)

        except Exception:
            import traceback
            traceback.print_exc()

    async def get_sessions(self, user_id: str) -> list[str]:
        """List session IDs for a user (from saved files)."""
        import os
        sessions = []
        save_dir = "./sessions"
        if os.path.exists(save_dir):
            prefix = f"{user_id}-"
            for f in os.listdir(save_dir):
                if f.startswith(prefix) and f.endswith(".json"):
                    sid = f[len(prefix):-5]
                    sessions.append(sid)
        return sorted(sessions)

    async def get_history(self, user_id: str, session_id: str) -> list[dict]:
        """Get chat history for a session."""
        agent = await self.get_agent(user_id, session_id)
        msgs = await agent.memory.get_memory()
        return [m.to_dict() for m in msgs]

    async def delete_session(self, user_id: str, session_id: str) -> None:
        """Delete a session's state."""
        import os
        key = (user_id, session_id)
        self._agents.pop(key, None)
        path = f"./sessions/{user_id}-{session_id}.json"
        if os.path.exists(path):
            os.remove(path)

    async def clear_memories(self, user_id: str) -> int:
        """Delete all memories for a user from pgvector."""
        import asyncpg
        from config import DB_CONNECTION_STRING
        deleted = 0
        conn = await asyncpg.connect(DB_CONNECTION_STRING)
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE tablename LIKE $1",
            f"workspace_{user_id}%",
        )
        for row in tables:
            table = row["tablename"]
            result = await conn.execute(f'DELETE FROM "{table}"')
            count = int(result.split(" ")[-1]) if result else 0
            deleted += count
            log.pgvector(f"cleared:{table}", deleted=count)
        await conn.close()
        keys_to_remove = [k for k in self._agents if k[0] == user_id]
        for k in keys_to_remove:
            self._agents.pop(k, None)
        log.reme("memories_cleared", user=user_id, total=deleted)
        return deleted

    async def shutdown(self) -> None:
        """Clean up all ReMe memory contexts."""
        for mem in self._memories.values():
            for m in mem.values():
                await m.__aexit__()
        self._memories.clear()
        self._agents.clear()
