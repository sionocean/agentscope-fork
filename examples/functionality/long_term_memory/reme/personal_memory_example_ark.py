# -*- coding: utf-8 -*-
"""Personal memory example using ByteDance Ark as LLM/Embedding provider.

This example shows how to run ReMe long-term memory with a non-standard
OpenAI-compatible provider (Volcengine Ark) whose embedding endpoint uses
the ``/embeddings/multimodal`` format.

Two things make this work:
1. ``ArkEmbedding`` – an AgentScope embedding model that calls the Ark
   multimodal endpoint and exposes ``api_key`` / ``base_url`` so the
   ReMe base class can extract credentials.
2. ``register_ark_embedding_backend()`` – registers an ``ark_multimodal``
   backend in flowllm's model registry so that ReMeApp's **internal**
   embedding calls also go through the correct endpoint.

Usage:
    export ARK_API_KEY='your-api-key'
    python personal_memory_example_ark.py
"""
import asyncio
import os

from dotenv import load_dotenv

from agentscope.agent import ReActAgent
from agentscope.embedding import ArkEmbedding
from agentscope.embedding._ark_embedding import register_ark_embedding_backend
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory, ReMePersonalLongTermMemory
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit

load_dotenv()

# ── Ark configuration ───────────────────────────────────────────────
ARK_API_KEY = os.environ.get(
    "ARK_API_KEY",
    "fafe646a-a9e9-4add-bf98-21265842e47a",
)
ARK_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
ARK_CHAT_MODEL = "seed-2-0-lite-260228"
ARK_EMBEDDING_MODEL = "skylark-embedding-vision-250615"
ARK_EMBEDDING_DIM = 2048


# ── Register the custom flowllm embedding backend BEFORE any ReMeApp ──
register_ark_embedding_backend()


async def test_react_agent_with_memory(
    memory: ReMePersonalLongTermMemory,
) -> None:
    """Test ReActAgent integration with personal memory."""
    toolkit = Toolkit()
    agent = ReActAgent(
        name="Friday",
        sys_prompt=(
            "You are a helpful assistant named Friday with long-term "
            "memory capabilities.\n\n"
            "## Memory Management Guidelines:\n"
            "1. When users share personal information or preferences, "
            "record them using `record_to_memory`.\n"
            "2. Before answering questions about the user, FIRST call "
            "`retrieve_from_memory` to check stored information.\n"
            "Always check your memory first."
        ),
        model=OpenAIChatModel(
            model_name=ARK_CHAT_MODEL,
            api_key=ARK_API_KEY,
            stream=False,
            client_kwargs={"base_url": ARK_BASE_URL},
        ),
        formatter=OpenAIChatFormatter(),
        toolkit=toolkit,
        memory=InMemoryMemory(),
        long_term_memory=memory,
        long_term_memory_mode="both",
    )

    await agent.memory.clear()

    print("User: I prefer to stay in homestays when traveling to Hangzhou")
    msg = Msg(
        role="user",
        content="I prefer to stay in homestays when traveling to Hangzhou",
        name="user",
    )
    msg = await agent(msg)
    print(f"Agent: {msg.get_text_content()}\n")

    print("User: What preferences do I have?")
    msg = Msg(
        role="user",
        content="What preferences do I have?",
        name="user",
    )
    msg = await agent(msg)
    print(f"Agent: {msg.get_text_content()}\n")


async def main() -> None:
    """Run the personal memory example with Ark provider."""
    embedding_model = ArkEmbedding(
        api_key=ARK_API_KEY,
        model_name=ARK_EMBEDDING_MODEL,
        base_url=ARK_BASE_URL,
        dimensions=ARK_EMBEDDING_DIM,
    )

    long_term_memory = ReMePersonalLongTermMemory(
        agent_name="Friday",
        user_name="user_123",
        model=OpenAIChatModel(
            model_name=ARK_CHAT_MODEL,
            api_key=ARK_API_KEY,
            stream=False,
            client_kwargs={"base_url": ARK_BASE_URL},
        ),
        embedding_model=embedding_model,
        # Tell ReMeApp to use the ark_multimodal backend internally
        reme_config_args=[
            "embedding_model.default.backend=ark_multimodal",
        ],
    )

    print("=" * 60)
    print("ReMe Personal Memory – Ark Provider")
    print(f"  Chat:      {ARK_CHAT_MODEL}")
    print(f"  Embedding: {ARK_EMBEDDING_MODEL} (dim={ARK_EMBEDDING_DIM})")
    print("=" * 60)
    print()

    async with long_term_memory:
        await test_react_agent_with_memory(long_term_memory)

    print("=" * 60)
    print("Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
