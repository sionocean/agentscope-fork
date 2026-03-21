# examples/web_memory_chat/backend/knowledge_manager.py
"""Per-user knowledge base management: upload, index, retrieve, delete."""
import asyncio
import base64
import json
import mimetypes
import os
from datetime import datetime
from typing import Any

from agentscope.embedding import ArkEmbedding
from agentscope.message import TextBlock, ImageBlock, URLSource
from agentscope.rag import (
    SimpleKnowledge,
    PgVectorStore,
    TextReader,
    PDFReader,
    ImageReader,
    Document,
    DocMetadata,
)
from agentscope.tool import ToolResponse

from config import (
    ARK_API_KEY,
    ARK_BASE_URL,
    ARK_EMBEDDING_MODEL,
    ARK_EMBEDDING_DIM,
    DB_CONNECTION_STRING,
    KNOWLEDGE_CHUNK_SIZE,
    KNOWLEDGE_SPLIT_BY,
)
from trace_logger import log

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")

# File extension → (reader_factory, category)
_EXT_MAP: dict[str, tuple[Any, str]] = {}


def _init_ext_map():
    global _EXT_MAP
    if _EXT_MAP:
        return
    text_reader = TextReader(
        chunk_size=KNOWLEDGE_CHUNK_SIZE,
        split_by=KNOWLEDGE_SPLIT_BY,
    )
    pdf_reader = PDFReader(
        chunk_size=KNOWLEDGE_CHUNK_SIZE,
        split_by=KNOWLEDGE_SPLIT_BY,
    )
    image_reader = ImageReader()
    _EXT_MAP.update({
        ".txt": (text_reader, "text"),
        ".md": (text_reader, "text"),
        ".pdf": (pdf_reader, "pdf"),
        ".png": (image_reader, "image"),
        ".jpg": (image_reader, "image"),
        ".jpeg": (image_reader, "image"),
        ".gif": (image_reader, "image"),
        ".webp": (image_reader, "image"),
    })


def _make_embedding() -> ArkEmbedding:
    return ArkEmbedding(
        api_key=ARK_API_KEY,
        model_name=ARK_EMBEDDING_MODEL,
        base_url=ARK_BASE_URL,
        dimensions=ARK_EMBEDDING_DIM,
    )


class KnowledgeManager:
    """Manages per-user SimpleKnowledge instances and document lifecycle."""

    def __init__(self) -> None:
        self._knowledge: dict[str, SimpleKnowledge] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        _init_ext_map()

    def _user_lock(self, user_id: str) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    async def _get_knowledge(self, user_id: str) -> SimpleKnowledge:
        """Get or create a SimpleKnowledge for the user."""
        async with self._user_lock(user_id):
            if user_id in self._knowledge:
                return self._knowledge[user_id]
            store = PgVectorStore(
                connection_string=DB_CONNECTION_STRING,
                collection_name=f"knowledge_{user_id}",
                dimensions=ARK_EMBEDDING_DIM,
            )
            kb = SimpleKnowledge(
                embedding_store=store,
                embedding_model=_make_embedding(),
            )
            self._knowledge[user_id] = kb
            log.framework("knowledge_init", user=user_id)
            return kb

    # ── Metadata helpers ───────────────────────────────────────────

    def _meta_path(self, user_id: str) -> str:
        return os.path.join(UPLOAD_DIR, user_id, "metadata.json")

    def _load_meta(self, user_id: str) -> list[dict]:
        path = self._meta_path(user_id)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_meta(self, user_id: str, meta: list[dict]) -> None:
        path = self._meta_path(user_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # ── Upload & Index ─────────────────────────────────────────────

    async def upload_document(
        self,
        user_id: str,
        filename: str,
        file_bytes: bytes,
    ) -> dict:
        """Process and index an uploaded file.

        Returns metadata dict for the indexed document.
        """
        if not file_bytes:
            raise ValueError("Empty file")

        ext = os.path.splitext(filename)[1].lower()
        if ext not in _EXT_MAP:
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported: {', '.join(_EXT_MAP.keys())}"
            )

        reader, category = _EXT_MAP[ext]
        kb = await self._get_knowledge(user_id)

        # Save file to disk
        user_dir = os.path.join(UPLOAD_DIR, user_id)
        os.makedirs(user_dir, exist_ok=True)
        file_path = os.path.join(user_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        log.tool(f"upload:{category}", user=user_id, file=filename,
                 size=len(file_bytes))

        if category == "image":
            docs = await self._index_image(
                kb, user_id, filename, file_bytes, file_path,
            )
        elif category == "pdf":
            docs = await reader(file_path)
            # Override doc_id to be filename-based (consistent with text/image)
            import hashlib
            doc_id = hashlib.sha256(
                f"{user_id}/{filename}".encode()
            ).hexdigest()
            for doc in docs:
                doc.metadata.doc_id = doc_id
            await kb.add_documents(docs)
        else:
            # text / md — read file content as string
            text_content = file_bytes.decode("utf-8", errors="replace")
            docs = await reader(text_content)
            # Override doc_id to be based on filename (not content hash)
            # so we can track and delete by filename
            import hashlib
            doc_id = hashlib.sha256(
                f"{user_id}/{filename}".encode()
            ).hexdigest()
            for doc in docs:
                doc.metadata.doc_id = doc_id
                doc.id = doc_id
            await kb.add_documents(docs)

        doc_id = docs[0].metadata.doc_id if docs else "unknown"
        meta_entry = {
            "doc_id": doc_id,
            "filename": filename,
            "file_type": category,
            "chunks": len(docs),
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "file_size": len(file_bytes),
        }

        # Update metadata file
        meta_list = self._load_meta(user_id)
        # Remove existing entry with same doc_id (re-upload)
        meta_list = [m for m in meta_list if m["doc_id"] != doc_id]
        meta_list.append(meta_entry)
        self._save_meta(user_id, meta_list)

        log.tool(f"indexed:{category}", user=user_id, file=filename,
                 chunks=len(docs), doc_id=doc_id[:12])
        return meta_entry

    async def _index_image(
        self,
        kb: SimpleKnowledge,
        user_id: str,
        filename: str,
        file_bytes: bytes,
        file_path: str,
    ) -> list[Document]:
        """Index an image: embed with base64 data URL, store with served URL."""
        import hashlib

        # 1. Create base64 data URL for embedding (Ark can't access localhost)
        media_type = mimetypes.guess_type(filename)[0] or "image/png"
        b64 = base64.b64encode(file_bytes).decode("ascii")
        data_url = f"data:{media_type};base64,{b64}"

        # 2. Embed using data URL
        embed_block = ImageBlock(
            type="image",
            source=URLSource(type="url", url=data_url),
        )
        resp = await kb.embedding_model([embed_block])

        # 3. Create document with served URL for storage & display
        served_url = f"/uploads/{user_id}/{filename}"
        store_block = ImageBlock(
            type="image",
            source=URLSource(type="url", url=served_url),
        )
        doc_id = hashlib.sha256(
            f"{user_id}/{filename}".encode()
        ).hexdigest()
        doc = Document(
            metadata=DocMetadata(
                content=store_block,
                doc_id=doc_id,
                chunk_id=0,
                total_chunks=1,
            ),
            embedding=resp.embeddings[0],
        )

        # 4. Store directly (bypass add_documents to avoid re-embedding)
        await kb.embedding_store.add([doc])
        return [doc]

    # ── List & Delete ──────────────────────────────────────────────

    def list_documents(self, user_id: str) -> list[dict]:
        """List indexed documents for a user."""
        return self._load_meta(user_id)

    async def delete_document(self, user_id: str, doc_id: str) -> bool:
        """Delete a document by doc_id: remove from pgvector + metadata."""
        kb = await self._get_knowledge(user_id)
        await kb.embedding_store.delete(doc_id=doc_id)

        meta_list = self._load_meta(user_id)
        # Find and remove the file
        removed = None
        new_meta = []
        for m in meta_list:
            if m["doc_id"] == doc_id:
                removed = m
            else:
                new_meta.append(m)
        self._save_meta(user_id, new_meta)

        # Remove uploaded file
        if removed:
            file_path = os.path.join(
                UPLOAD_DIR, user_id, removed["filename"],
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            log.tool("doc_deleted", user=user_id,
                     file=removed["filename"])

        return removed is not None

    async def clear_documents(self, user_id: str) -> int:
        """Delete all documents for a user."""
        meta_list = self._load_meta(user_id)
        count = len(meta_list)
        kb = await self._get_knowledge(user_id)
        for m in meta_list:
            await kb.embedding_store.delete(doc_id=m["doc_id"])
        self._save_meta(user_id, [])
        # Remove uploaded files
        user_dir = os.path.join(UPLOAD_DIR, user_id)
        if os.path.isdir(user_dir):
            for f in os.listdir(user_dir):
                if f != "metadata.json":
                    os.remove(os.path.join(user_dir, f))
        log.tool("docs_cleared", user=user_id, count=count)
        return count

    # ── Retrieval tool for agent ───────────────────────────────────

    def make_search_tool(self, user_id: str):
        """Create a search_knowledge tool function bound to this user."""
        manager = self

        async def search_knowledge(
            query: str,
            limit: int = 5,
        ) -> ToolResponse:
            """Search the user's uploaded knowledge base for relevant
            information.

            Use this tool when the user asks about content from documents
            they have uploaded (PDF, text files, images). For general web
            information, use brave_search instead.

            Args:
                query: Specific search query. Use concrete terms, not
                    pronouns like "it" or "that".
                limit: Max number of results to return (default 5).

            Returns:
                Relevant document chunks with similarity scores.
            """
            kb = await manager._get_knowledge(user_id)
            docs = await kb.retrieve(
                query=query,
                limit=limit,
                score_threshold=0.3,
            )
            log.tool(
                "search_knowledge", user=user_id,
                query=query, results=len(docs),
            )
            if not docs:
                return ToolResponse(
                    content=[TextBlock(
                        type="text",
                        text="No relevant documents found in the knowledge "
                             "base. The user may not have uploaded relevant "
                             "documents, or try rephrasing your query.",
                    )],
                )
            blocks = []
            for doc in docs:
                content = doc.metadata.content
                if content.get("type") == "text":
                    desc = content["text"]
                elif content.get("type") == "image":
                    url = content.get("source", {}).get("url", "")
                    desc = f"[Image: {url}]"
                else:
                    desc = str(content)
                blocks.append(TextBlock(
                    type="text",
                    text=f"[Score: {doc.score:.2f}] {desc}",
                ))
            return ToolResponse(content=blocks)

        return search_knowledge
