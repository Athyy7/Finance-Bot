from pydantic_settings import BaseSettings

from backend.app.constants.database_constants import DatabaseConstants
from backend.app.constants.pinecone_constants import PineconeConstants
from backend.app.constants.relace_constants import RelaceConstants
from backend.app.constants.supabase_constants import SupabaseConstants


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"

    # OpenAI API settings (optional, for fallback)
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-5-mini-2025-08-07"  #"gpt-5-2025-08-07"   #"gpt-4.1-mini-2025-04-14"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    # API Service timeout settings
    API_SERVICE_CONNECT_TIMEOUT: float = 60.0
    API_SERVICE_READ_TIMEOUT: float = 1000.0
    API_SERVICE_WRITE_TIMEOUT: float = 120.0
    API_SERVICE_POOL_TIMEOUT: float = 60.0

    # MongoDB settings
    MONGODB_URL: str = DatabaseConstants.DEFAULT_MONGODB_URL
    MONGODB_DB_NAME: str = DatabaseConstants.DEFAULT_DB_NAME
    ERROR_COLLECTION_NAME: str = DatabaseConstants.ERROR_COLLECTION
    LLM_USAGE_COLLECTION_NAME: str = DatabaseConstants.LLM_USAGE_COLLECTION
    FINANCIAL_DATA_COLLECTION_NAME: str = DatabaseConstants.FINANCIAL_DATA_COLLECTION

    # Supabase settings
    SUPABASE_API_URL: str = SupabaseConstants.SUPABASE_API_URL
    SUPABASE_TIMEOUT: int = SupabaseConstants.TIMEOUT

    # Relace settings
    RELACE_API_URL: str = RelaceConstants.RELACE_API_URL
   

    # Pinecone settings
    PINECONE_API_KEY: str
    PINECONE_API_VERSION: str = PineconeConstants.PINECONE_API_VERSION
    PINECONE_CREATE_INDEX_URL: str = PineconeConstants.PINECONE_CREATE_INDEX_URL
    PINECONE_EMBED_URL: str = PineconeConstants.PINECONE_EMBED_URL
    PINECONE_UPSERT_URL: str = PineconeConstants.PINECONE_UPSERT_URL
    PINECONE_RERANK_URL: str = PineconeConstants.PINECONE_RERANK_URL
    PINECONE_QUERY_URL: str = PineconeConstants.PINECONE_QUERY_URL
    PINECONE_LIST_INDEXES_URL: str = PineconeConstants.PINECONE_LIST_INDEXES_URL
    INDEXING_SIMILARITY_METRIC: str = (
        PineconeConstants.INDEXING_SIMILARITY_METRIC
    )
    INDEXING_EMBEDDING_MODEL: str = PineconeConstants.INDEXING_EMBEDDING_MODEL
    INDEXING_SEMAPHORE_VALUE: int = PineconeConstants.INDEXING_SEMAPHORE_VALUE


    class Config:
        env_file = ".env"


settings = Settings()
