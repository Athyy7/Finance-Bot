from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.config.settings import settings


class MongoDB:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.mongodb_client = None

    def connect(self):
        try:
            self.mongodb_client = AsyncIOMotorClient(
                self.database_url, maxpoolsize=30, minpoolsize=5
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to connect to MongoDB: {str(e)} "
                       f"\nError while connecting to MongoDB (from database.py in connect())",
            )

    def get_mongo_client(self):
        if not self.mongodb_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MongoDB client is not connected. "
                       "\nError while connecting to MongoDB client (from database.py in get_mongo_client())",
            )
        return self.mongodb_client

    def get_collection(self, collection_name: str, method_name: str = None):
        """
        Get any collection from the MongoDB client.

        Args:
            collection_name (str): The name of the collection to get
            method_name (str): Optional, used for error messages
        """
        try:
            if not self.mongodb_client:
                raise HTTPException(
                    status_code=503,
                    detail=f"MongoDB client is not connected. Error in {method_name}()",
                )
            return self.mongodb_client[settings.MONGODB_DB_NAME][collection_name]
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unable to access {collection_name} collection: {str(e)} "
                       f"(from database.py in {method_name}())",
            )

    def get_error_collection(self):
        return self.get_collection(settings.ERROR_COLLECTION_NAME, "get_error_collection")

    def get_llm_usage_collection(self):
        return self.get_collection(settings.LLM_USAGE_COLLECTION_NAME, "get_llm_usage_collection")

    def get_financial_data_collection(self):
        return self.get_collection(settings.FINANCIAL_DATA_COLLECTION_NAME, "get_financial_data_collection")

    def disconnect(self):
        try:
            if self.mongodb_client:
                self.mongodb_client.close()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unable to close MongoDB connection: {str(e)} "
                       f"\nError while disconnecting (from database.py in disconnect())",
            )


# Instantiate the MongoDB class
mongodb_database = MongoDB(settings.MONGODB_URL)


# Standalone function for compatibility with SQL-style projects
def create_db_and_tables():
    """
    Placeholder for compatibility.
    MongoDB does not require table creation like SQL databases.
    """
    pass


