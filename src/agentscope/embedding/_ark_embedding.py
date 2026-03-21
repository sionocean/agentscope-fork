# -*- coding: utf-8 -*-
"""Ark multimodal embedding model for AgentScope and flowllm (ReMe).

ByteDance Volcengine Ark provides embedding via a ``/embeddings/multimodal``
endpoint whose request/response format differs from the standard OpenAI
``/embeddings`` endpoint:

* **Request** – ``input`` is a list of typed objects
  ``[{"type": "text", "text": "..."}]`` instead of plain strings.
* **Response** – ``data`` is a single object ``{"embedding": [...]}``
  (one embedding per call, regardless of how many input items).

This module provides:

1. ``ArkEmbedding`` – an ``EmbeddingModelBase`` subclass for direct use in
   AgentScope (RAG, vector stores, etc.).
2. ``register_ark_embedding_backend()`` – registers an ``ark_multimodal``
   backend in *flowllm*'s registry so that *ReMeApp* can call the Ark
   embedding API internally.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any, List

from ._cache_base import EmbeddingCacheBase
from ._embedding_base import EmbeddingModelBase
from ._embedding_response import EmbeddingResponse
from ._embedding_usage import EmbeddingUsage
from ..message import TextBlock


def _ark_post_sync(
    base_url: str,
    api_key: str,
    model_name: str,
    text: str,
) -> tuple[list[float], int]:
    """Synchronous single-text embedding call."""
    import httpx

    resp = httpx.post(
        f"{base_url}/embeddings/multimodal",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": model_name,
            "input": [{"type": "text", "text": text}],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Ark embedding error ({resp.status_code}): {resp.text}",
        )
    data = resp.json()
    raw = data["data"]
    emb = raw["embedding"] if isinstance(raw, dict) else raw[0]["embedding"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return emb, tokens


async def _ark_post_async(
    client: Any,
    base_url: str,
    api_key: str,
    model_name: str,
    text: str,
) -> tuple[list[float], int]:
    """Asynchronous single-text embedding call (reuses client)."""
    resp = await client.post(
        f"{base_url}/embeddings/multimodal",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": model_name,
            "input": [{"type": "text", "text": text}],
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Ark embedding error ({resp.status_code}): {resp.text}",
        )
    data = resp.json()
    raw = data["data"]
    emb = raw["embedding"] if isinstance(raw, dict) else raw[0]["embedding"]
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return emb, tokens


class ArkEmbedding(EmbeddingModelBase):
    """AgentScope embedding model that calls Ark /embeddings/multimodal.

    The Ark multimodal endpoint returns **one** embedding per API call, so
    each text in the input list is embedded with a separate request (run
    concurrently via ``asyncio.gather``).
    """

    supported_modalities: list[str] = ["text"]

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str = "https://ark.ap-southeast.bytepluses.com/api/v3",
        dimensions: int = 2048,
        embedding_cache: EmbeddingCacheBase | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name, dimensions)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.embedding_cache = embedding_cache

    async def __call__(
        self,
        text: List[str | TextBlock],
        **kwargs: Any,
    ) -> EmbeddingResponse:
        import httpx

        # Normalise to plain strings
        texts: list[str] = []
        for item in text:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
            else:
                raise ValueError(f"Unsupported input type: {type(item)}.")

        if self.embedding_cache:
            cache_key = {
                "model": self.model_name,
                "texts": texts,
                "dimensions": self.dimensions,
            }
            cached = await self.embedding_cache.retrieve(
                identifier=cache_key,
            )
            if cached:
                return EmbeddingResponse(
                    embeddings=cached,
                    usage=EmbeddingUsage(tokens=0, time=0),
                    source="cache",
                )

        start = datetime.now()
        async with httpx.AsyncClient() as client:
            tasks = [
                _ark_post_async(
                    client, self.base_url, self.api_key,
                    self.model_name, t,
                )
                for t in texts
            ]
            results = await asyncio.gather(*tasks)

        elapsed = (datetime.now() - start).total_seconds()
        embeddings = [r[0] for r in results]
        total_tokens = sum(r[1] for r in results)

        if self.embedding_cache:
            await self.embedding_cache.store(
                identifier=cache_key,
                embeddings=embeddings,
            )

        return EmbeddingResponse(
            embeddings=embeddings,
            usage=EmbeddingUsage(tokens=total_tokens, time=elapsed),
        )


def register_ark_embedding_backend() -> None:
    """Register ``ark_multimodal`` as a flowllm embedding backend.

    Must be called **before** any ``ReMeApp`` is constructed.

    Example::

        from agentscope.embedding._ark_embedding import (
            register_ark_embedding_backend,
        )
        register_ark_embedding_backend()

        memory = ReMePersonalLongTermMemory(
            ...,
            reme_config_args=[
                "embedding_model.default.backend=ark_multimodal",
            ],
        )
    """
    try:
        from flowllm.core.context import C
        from flowllm.core.embedding_model import BaseEmbeddingModel
        from flowllm.core.enumeration import RegistryEnum
    except ImportError:
        return

    registry = C.registry_dict.get(RegistryEnum.EMBEDDING_MODEL)
    if registry and "ark_multimodal" in registry:
        return

    @C.register_embedding_model("ark_multimodal")
    class ArkMultiModalEmbeddingModel(BaseEmbeddingModel):
        """flowllm embedding backend for Ark /embeddings/multimodal.

        Each text is embedded in a separate API call because the Ark
        multimodal endpoint returns one embedding per request.
        """

        def __init__(
            self,
            model_name: str = "",
            dimensions: int = 2048,
            max_batch_size: int = 10,
            max_retries: int = 3,
            raise_exception: bool = True,
            api_key: str | None = None,
            base_url: str | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(
                model_name=model_name,
                dimensions=dimensions,
                max_retries=max_retries,
                raise_exception=raise_exception,
                max_batch_size=max_batch_size,
                **kwargs,
            )
            self.api_key = api_key or os.getenv(
                "FLOW_EMBEDDING_API_KEY", "",
            )
            self.base_url = (
                base_url
                or os.getenv("FLOW_EMBEDDING_BASE_URL", "")
            ).rstrip("/")

        def _get_embeddings(
            self, input_text: str | List[str],
        ) -> list[float] | list[list[float]]:
            if isinstance(input_text, str):
                emb, _ = _ark_post_sync(
                    self.base_url, self.api_key,
                    self.model_name, input_text,
                )
                return emb

            results = [
                _ark_post_sync(
                    self.base_url, self.api_key,
                    self.model_name, t,
                )
                for t in input_text
            ]
            return [r[0] for r in results]

        async def _async_get_embeddings(
            self, input_text: str | List[str],
        ) -> list[float] | list[list[float]]:
            import httpx

            if isinstance(input_text, str):
                texts = [input_text]
            else:
                texts = list(input_text)

            async with httpx.AsyncClient() as client:
                tasks = [
                    _ark_post_async(
                        client, self.base_url, self.api_key,
                        self.model_name, t,
                    )
                    for t in texts
                ]
                results = await asyncio.gather(*tasks)

            embs = [r[0] for r in results]
            if isinstance(input_text, str):
                return embs[0]
            return embs
