class DatabaseConstants:
    """Constants for database operations"""

    # Default database configuration
    DEFAULT_MONGODB_URL = "mongodb://localhost:27017"
    DEFAULT_DB_NAME = "finance_bot"

    # Collection names
    EMBEDDING_COLLECTION = "embeddings"
    ERROR_COLLECTION = "error_logs"
    LLM_USAGE_COLLECTION = "llm_usage_logs"
    FINANCIAL_DATA_COLLECTION = "financial_data_collection"

    # Database connection settings
    DEFAULT_CONNECTION_TIMEOUT = 30000  # 30 seconds
    DEFAULT_SERVER_SELECTION_TIMEOUT = 5000  # 5 seconds
    DEFAULT_MAX_POOL_SIZE = 100
