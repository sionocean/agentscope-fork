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

# ReMe language: "cn" for Chinese, "en" for English (affects time parsing,
# deduplication keywords, internal prompts)
# ReMe language: "zh" for Chinese, "en" for English
# NOTE: use "zh" not "cn" — prompt templates use _zh suffix
REME_LANGUAGE = os.environ.get("REME_LANGUAGE", "zh")

# Knowledge / RAG settings
KNOWLEDGE_CHUNK_SIZE = int(os.environ.get("KNOWLEDGE_CHUNK_SIZE", "512"))
KNOWLEDGE_SPLIT_BY = os.environ.get("KNOWLEDGE_SPLIT_BY", "paragraph")
