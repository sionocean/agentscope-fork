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
            data = json.dumps(msg_out.to_dict(), ensure_ascii=False)
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
                    sid = f[len(prefix):-5]
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
