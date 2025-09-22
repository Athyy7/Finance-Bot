class PineconeConstants:
    """Constants for Pinecone operations"""

    # Pinecone API endpoints
    PINECONE_CREATE_INDEX_URL: str = "https://api.pinecone.io/indexes"
    PINECONE_API_VERSION: str = "2025-01"
    PINECONE_EMBED_URL: str = "https://api.pinecone.io/embed"
    PINECONE_UPSERT_URL: str = "https://{}/vectors/upsert"
    PINECONE_RERANK_URL: str = "https://api.pinecone.io/rerank"
    PINECONE_QUERY_URL: str = "https://{}/query"
    PINECONE_LIST_INDEXES_URL: str = "https://api.pinecone.io/indexes"
    
    # Indexing configuration
    INDEXING_SIMILARITY_METRIC: str = "cosine"
    INDEXING_EMBEDDING_MODEL: str = "llama-text-embed-v2"
    INDEXING_SEMAPHORE_VALUE: int = 5