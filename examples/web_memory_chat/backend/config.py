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
